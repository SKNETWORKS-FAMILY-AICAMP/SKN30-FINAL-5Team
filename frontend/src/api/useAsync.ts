/**
 * Small async-state helpers shared by the API-backed screens.
 *
 * `useAsyncData` loads on mount and exposes retry; `useAsyncAction` runs a
 * mutation once at a time and surfaces its error. Neither retries by itself:
 * mutations carry idempotency keys generated per call, so a silent retry could
 * create a second key for the same intent.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { messageForError } from './errors';

export type AsyncData<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string; error: unknown }
  | { status: 'ready'; data: T };

function sameDeps(a: readonly unknown[], b: readonly unknown[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

export function useAsyncData<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
): { state: AsyncData<T>; reload: () => void; setData: (data: T) => void } {
  const [state, setState] = useState<AsyncData<T>>({ status: 'loading' });
  const [nonce, setNonce] = useState(0);
  const [tracked, setTracked] = useState<{
    deps: readonly unknown[];
    nonce: number;
  }>({ deps, nonce });

  // React's "adjust state when inputs change" pattern. Resetting during render
  // rather than in the effect keeps the previous request's data from being
  // shown for one frame under the new inputs.
  if (nonce !== tracked.nonce || !sameDeps(tracked.deps, deps)) {
    setTracked({ deps, nonce });
    setState({ status: 'loading' });
  }

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    // `load` is re-read whenever `deps` change, which is exactly when the
    // request should be reissued.
    load(controller.signal).then(
      (data) => {
        if (active) {
          setState({ status: 'ready', data });
        }
      },
      (error: unknown) => {
        if (active) {
          setState({ status: 'error', message: messageForError(error), error });
        }
      },
    );

    return () => {
      active = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  const setData = useCallback(
    (data: T) => setState({ status: 'ready', data }),
    [],
  );

  return { state, reload, setData };
}

export function useAsyncAction<Args extends unknown[], T>(
  action: (...args: Args) => Promise<T>,
): {
  run: (...args: Args) => Promise<T | undefined>;
  pending: boolean;
  error: string | null;
  lastError: unknown;
  clearError: () => void;
} {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastError, setLastError] = useState<unknown>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(
    async (...args: Args) => {
      if (inFlight.current) {
        return undefined;
      }
      inFlight.current = true;
      setPending(true);
      setError(null);
      setLastError(null);
      try {
        return await action(...args);
      } catch (caught) {
        if (mounted.current) {
          setError(messageForError(caught));
          setLastError(caught);
        }
        return undefined;
      } finally {
        inFlight.current = false;
        if (mounted.current) {
          setPending(false);
        }
      }
    },
    [action],
  );

  const clearError = useCallback(() => {
    setError(null);
    setLastError(null);
  }, []);

  return { run, pending, error, lastError, clearError };
}

/** The user's local `YYYY-MM-DD`, which the daily resources are keyed by. */
export function localDateString(date: Date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** Monday of the week containing `date`, as `YYYY-MM-DD`. */
export function weekStartString(date: Date = new Date()): string {
  const copy = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const weekday = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - weekday);
  return localDateString(copy);
}
