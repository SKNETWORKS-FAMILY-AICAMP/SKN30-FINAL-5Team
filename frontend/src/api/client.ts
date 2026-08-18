/**
 * Typed `/api/v1` client.
 *
 * Rules this file enforces so callers cannot get them wrong:
 *
 * - every mutation carries a UUID `Idempotency-Key`
 * - the bearer token is fetched per request and never stored or logged here
 * - non-2xx responses become `ApiError` with the server's machine code intact
 *
 * It deliberately contains no product rules. Safety, duration and completion
 * decisions belong to the server.
 */

import { ApiError, apiErrorFromResponse, networkError } from './errors';

export type TokenProvider = () => Promise<string | null>;

export type ClientOptions = {
  baseUrl: string;
  getToken: TokenProvider;
  fetchImpl?: typeof fetch;
};

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  path: string;
  query?: Record<string, string | undefined>;
  body?: unknown;
  /** Mutations must set this; the server rejects them without a UUID key. */
  idempotent?: boolean;
  ifMatch?: string | number;
  signal?: AbortSignal;
};

/**
 * RFC 4122 v4 identifier. `crypto.randomUUID` is not available on every React
 * Native engine, so fall back to `getRandomValues`, then to `Math.random`.
 * These keys only need to be unique per client request, not unguessable.
 */
export function createIdempotencyKey(): string {
  const globalCrypto = (
    globalThis as { crypto?: { randomUUID?: () => string } }
  ).crypto;
  if (typeof globalCrypto?.randomUUID === 'function') {
    return globalCrypto.randomUUID();
  }

  const bytes = new Uint8Array(16);
  const withValues = (
    globalThis as {
      crypto?: { getRandomValues?: (array: Uint8Array) => Uint8Array };
    }
  ).crypto;
  if (typeof withValues?.getRandomValues === 'function') {
    withValues.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;

  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join('-');
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly getToken: TokenProvider;
  private readonly fetchImpl: typeof fetch;

  constructor({ baseUrl, getToken, fetchImpl }: ClientOptions) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.getToken = getToken;
    // Bound to the global object on purpose. Storing bare `fetch` on the
    // instance makes `this.fetchImpl(...)` call it with the client as receiver,
    // which browsers reject with "Illegal invocation". React Native's fetch
    // does not care, so an unbound reference fails only on web.
    this.fetchImpl = fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  async request<T>({
    method = 'GET',
    path,
    query,
    body,
    idempotent = false,
    ifMatch,
    signal,
  }: RequestOptions): Promise<T> {
    const url = new URL(`${this.baseUrl}/api/v1${path}`);
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value !== undefined) {
        url.searchParams.set(key, value);
      }
    }

    const headers: Record<string, string> = { Accept: 'application/json' };
    const token = await this.getToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }
    if (idempotent) {
      headers['Idempotency-Key'] = createIdempotencyKey();
    }
    if (ifMatch !== undefined) {
      headers['If-Match'] = `"${ifMatch}"`;
    }

    let response: Response;
    try {
      response = await this.fetchImpl(url.toString(), {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal,
      });
    } catch (caught) {
      // A cancelled request is not a connection failure. Screens abort in
      // flight on unmount, and reporting that as "cannot reach the server"
      // would be wrong and would mask the real state.
      if (caught instanceof Error && caught.name === 'AbortError') {
        throw caught;
      }
      // Only the configured base URL and the transport's own reason are
      // surfaced. The full request URL and the headers stay out, because they
      // can carry identifiers and the bearer token.
      throw networkError(this.baseUrl, caught);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    let payload: unknown = null;
    const text = await response.text();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = null;
      }
    }

    if (!response.ok) {
      throw apiErrorFromResponse(response.status, payload);
    }
    return payload as T;
  }
}

export { ApiError };
