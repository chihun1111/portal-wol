/** Run a fixed number of workers so a large target list cannot flood the API. */
export async function mapConcurrent<T, R>(
  items: readonly T[],
  concurrency: number,
  task: (item: T) => Promise<R>
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let nextIndex = 0;
  const worker = async () => {
    while (nextIndex < items.length) {
      const index = nextIndex++;
      results[index] = await task(items[index]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(Math.max(1, concurrency), items.length) }, worker));
  return results;
}

/** Schedule the next poll only after the current request has settled. */
export function startPolling(task: (signal: AbortSignal) => Promise<void>, delayMs: number): () => void {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout>;
  const poll = async () => {
    try {
      await task(controller.signal);
    } catch (error) {
      if (!controller.signal.aborted) console.warn('polling error', error);
    } finally {
      if (!controller.signal.aborted) {
        timer = setTimeout(poll, delayMs);
      }
    }
  };
  timer = setTimeout(poll, delayMs);
  return () => {
    controller.abort();
    clearTimeout(timer);
  };
}
