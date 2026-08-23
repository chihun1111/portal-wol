export type RequestError = Error & {
  status?: number;
  payload?: unknown;
};

export type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

function resolveMessage(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (!value || typeof value !== 'object') {
    return undefined;
  }
  const record = value as Record<string, unknown>;
  return resolveMessage(record.detail) ?? resolveMessage(record.message) ?? resolveMessage(record.error);
}

export function getRequestErrorMessage(error: unknown, fallback: string): string {
  if (!error || typeof error !== 'object') {
    return fallback;
  }
  const message = resolveMessage((error as RequestError).payload);
  return message ?? fallback;
}

export function getRequestErrorCode(error: unknown): string | undefined {
  if (!error || typeof error !== 'object') {
    return undefined;
  }
  const payload = (error as RequestError).payload;
  if (!payload || typeof payload !== 'object') {
    return undefined;
  }
  const detail = (payload as Record<string, unknown>).detail;
  if (!detail || typeof detail !== 'object') {
    return undefined;
  }
  const code = (detail as Record<string, unknown>).error;
  return typeof code === 'string' && code.trim() ? code.trim() : undefined;
}

export async function request<T = unknown>(path: string, init: RequestOptions = {}): Promise<T> {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const url = `${API_BASE}${normalizedPath}`;
  const headers = new Headers(init.headers);
  const rawBody = init.body;
  let body: BodyInit | undefined;

  if (rawBody === undefined || rawBody === null) {
    body = undefined;
  } else if (
    rawBody instanceof FormData ||
    typeof rawBody === 'string' ||
    rawBody instanceof URLSearchParams ||
    rawBody instanceof Blob ||
    rawBody instanceof ArrayBuffer ||
    ArrayBuffer.isView(rawBody)
  ) {
    body = rawBody;
  } else {
    body = JSON.stringify(rawBody);
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url, { ...init, headers, body });
  const text = await response.text();
  let payload: unknown;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const error = new Error('Request failed') as RequestError;
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload as T;
}
