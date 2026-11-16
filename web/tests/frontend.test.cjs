const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const ts = require('typescript');

// Exercise the actual TypeScript sources without another test runner dependency.
for (const extension of ['.ts', '.tsx']) {
  require.extensions[extension] = (module, filename) => {
    const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: {
        target: ts.ScriptTarget.ES2020,
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
        esModuleInterop: true
      },
      fileName: filename
    });
    module._compile(outputText, filename);
  };
}

const previousApiBase = process.env.NEXT_PUBLIC_API_BASE;
process.env.NEXT_PUBLIC_API_BASE = 'https://portal.invalid/base/';
const { request, getRequestErrorCode, getRequestErrorMessage } = require('../app/_lib/api.ts');
if (previousApiBase === undefined) delete process.env.NEXT_PUBLIC_API_BASE;
else process.env.NEXT_PUBLIC_API_BASE = previousApiBase;

const { mapConcurrent, startPolling } = require('../app/_lib/async.ts');
const { readPreference, writePreference } = require('../app/_lib/storage.ts');
const { shouldApplyBootJobUpdate } = require('../app/(management)/wol/_lib/bootJobs.ts');
const React = require('react');
const { renderToString, renderToStaticMarkup } = require('react-dom/server');
const { LanguageProvider, useLanguage } = require('../app/_i18n/LanguageProvider.tsx');

test('status workers cap concurrency while retaining the order of all results', async () => {
  let active = 0;
  let peak = 0;
  const inputs = Array.from({ length: 11 }, (_, index) => index);
  const results = await mapConcurrent(inputs, 4, async (value) => {
    active++;
    peak = Math.max(peak, active);
    await new Promise((resolve) => setImmediate(resolve));
    active--;
    return value * 2;
  });
  assert.equal(peak, 4);
  assert.equal(active, 0);
  assert.deepEqual(results, inputs.map((value) => value * 2));
  assert.deepEqual(await mapConcurrent([], 4, async () => assert.fail('unexpected task')), []);
});

test('slow polls never overlap and stopping aborts the active request', async (context) => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  const signals = [];
  const resolvers = [];
  const stop = startPolling(async (signal) => {
    signals.push(signal);
    await new Promise((resolve) => resolvers.push(resolve));
  }, 2000);
  context.after(stop);

  context.mock.timers.tick(2000);
  assert.equal(signals.length, 1);
  context.mock.timers.tick(10_000);
  assert.equal(signals.length, 1);
  resolvers.shift()();
  await Promise.resolve();
  await Promise.resolve();
  context.mock.timers.tick(1999);
  assert.equal(signals.length, 1);
  context.mock.timers.tick(1);
  assert.equal(signals.length, 2);

  stop();
  assert.equal(signals[1].aborted, true);
  resolvers.shift()();
  await Promise.resolve();
  await Promise.resolve();
  context.mock.timers.tick(20_000);
  assert.equal(signals.length, 2);
});

test('stopping before the first poll prevents the request', (context) => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  const stop = startPolling(async () => assert.fail('unexpected poll'), 2000);
  stop();
  context.mock.timers.tick(20_000);
});

test('a failed poll settles before the next scheduled retry', async (context) => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  const warning = context.mock.method(console, 'warn', () => {});
  let calls = 0;
  const stop = startPolling(async () => {
    calls++;
    throw new Error('network unavailable');
  }, 2000);
  context.after(stop);
  context.mock.timers.tick(2000);
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(calls, 1);
  assert.equal(warning.mock.callCount(), 1);
  context.mock.timers.tick(2000);
  await Promise.resolve();
  assert.equal(calls, 2);
});

test('old snapshots cannot undo cancellation, reopen dismissed jobs, or replace another job', () => {
  const running = { id: 'job-1', terminal: false, updated_at: '2026-01-01T01:00:05Z' };
  const older = { ...running, updated_at: '2026-01-01T01:00:04Z' };
  const cancelled = { ...running, terminal: true, state: 'cancelled', updated_at: '2026-01-01T01:00:06Z' };
  assert.equal(shouldApplyBootJobUpdate(running, older), false);
  assert.equal(shouldApplyBootJobUpdate(running, cancelled), true);
  assert.equal(shouldApplyBootJobUpdate(cancelled, running), false);
  assert.equal(shouldApplyBootJobUpdate(null, running), false);
  assert.equal(shouldApplyBootJobUpdate({ ...running, id: 'job-2' }, running), false);
});

test('requests normalize the API base, preserve JSON bodies, and do not forward timeout options', async (context) => {
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'https://portal.invalid/base/api/targets');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers.get('Content-Type'), 'application/json');
    assert.equal(options.body, '{"target":"testpc"}');
    assert.equal('timeoutMs' in options, false);
    return new Response('{"ok":true}', { status: 200 });
  });
  assert.deepEqual(await request('api/targets', { method: 'POST', body: { target: 'testpc' }, timeoutMs: 5000 }), { ok: true });
});

test('HTTP failures retain structured error messages, codes, and status', async (context) => {
  context.mock.method(globalThis, 'fetch', async () => new Response(
    JSON.stringify({ detail: { error: 'active_boot_job', message: 'A boot job is already running.' } }),
    { status: 409 }
  ));
  await assert.rejects(request('/api/boot/ubuntu', { method: 'POST' }), (error) => {
    assert.equal(error.status, 409);
    assert.equal(getRequestErrorCode(error), 'active_boot_job');
    assert.equal(getRequestErrorMessage(error, 'fallback'), 'A boot job is already running.');
    return true;
  });
});

test('a stalled read times out without retrying or leaving its caller blocked', async (context) => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  let calls = 0;
  context.mock.method(globalThis, 'fetch', async (_url, options) => {
    calls++;
    return new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
    });
  });
  const pending = assert.rejects(request('/api/jobs/job-1', { timeoutMs: 15_000 }), { name: 'TimeoutError' });
  context.mock.timers.tick(15_000);
  await pending;
  assert.equal(calls, 1);
});

test('poll cancellation propagates to fetch immediately', async (context) => {
  const controller = new AbortController();
  context.mock.method(globalThis, 'fetch', async (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
  }));
  const pending = assert.rejects(request('/api/jobs/job-1', { signal: controller.signal }), { name: 'AbortError' });
  controller.abort();
  await pending;
});

test('successful reads and empty responses clear their timeout', async (context) => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  let requestSignal;
  context.mock.method(globalThis, 'fetch', async (_url, options) => {
    requestSignal = options.signal;
    return new Response(null, { status: 204 });
  });
  assert.equal(await request('/api/targets/testpc', { timeoutMs: 100 }), undefined);
  context.mock.timers.tick(1000);
  assert.equal(requestSignal.aborted, false);
});

test('blocked preference storage does not break loading or changing preferences', () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {};
    Object.defineProperty(globalThis.window, 'localStorage', {
      get() { throw new DOMException('Storage blocked', 'SecurityError'); }
    });
    assert.equal(readPreference('theme'), null);
    assert.doesNotThrow(() => writePreference('theme', 'light'));
    globalThis.window = { localStorage: { getItem: () => 'light', setItem: () => { throw new Error('quota'); } } };
    assert.equal(readPreference('theme'), 'light');
    assert.doesNotThrow(() => writePreference('theme', 'dark'));
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});

test('server HTML matches the initial browser render with an English preference', () => {
  function Greeting() {
    const { language, t } = useLanguage();
    return React.createElement('span', { lang: language }, t('settings.title'));
  }
  const content = React.createElement(LanguageProvider, null, React.createElement(Greeting));
  const previousWindow = globalThis.window;
  try {
    delete globalThis.window;
    const serverHtml = renderToString(content);
    globalThis.window = { localStorage: { getItem: () => 'en' }, navigator: { language: 'en-US' } };
    assert.equal(renderToString(content), serverHtml);
    assert.match(serverHtml, /lang="ko"/);
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});

test('pending power commands disable every power button', () => {
  const { TargetsCard } = require('../app/(management)/wol/_components/TargetsCard.tsx');
  const target = { name: 'testpc', ip: '192.0.2.10', has_mac: true, can_boot_ubuntu: true };
  const html = renderToStaticMarkup(React.createElement(LanguageProvider, null,
    React.createElement(TargetsCard, {
      targets: [target], filteredTargets: [target], actionLoadingKey: 'wake:testpc',
      onAction() {}, onBootUbuntu() {}, onEdit() {}, onDelete() {}
    })
  ));
  const actionButtons = html.match(/<button[^>]*data-action="[^"]+"[^>]*>/g);
  assert.equal(actionButtons.length, 4);
  for (const button of actionButtons) assert.match(button, /disabled=""/);
});
