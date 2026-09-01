/**
 * Wires environment config, the Firebase adapter and the typed API client into
 * one context the screens consume.
 *
 * The provider owns exactly three things: whether configuration is usable,
 * whether someone is signed in, and the server's view of that user (`GET /me`).
 * Everything else is fetched by the screen that needs it.
 *
 * `status` is derived during render from config + auth + profile state, so the
 * only writes are from genuinely external events: the Firebase auth observer
 * and the resolution of the `/me` request.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { ApiClient } from '../api/client';
import { createApi, type Api } from '../api/endpoints';
import { isApiError } from '../api/errors';
import type { MeResponse } from '../api/types';
import {
  createFirebaseAuthAdapter,
  type AuthAdapter,
  type AuthUser,
} from '../auth/firebase';
import { resolveEnvConfig, type EnvConfig, type EnvIssue } from '../config/env';

export type SessionStatus =
  | { kind: 'configuring' }
  | { kind: 'misconfigured'; issues: EnvIssue[] }
  /** `notice` explains why a previous session ended, when it did not end by choice. */
  | { kind: 'signedOut'; notice: string | null }
  | { kind: 'loadingProfile' }
  | { kind: 'profileError'; message: string }
  | { kind: 'signedIn'; me: MeResponse };

export type SessionValue = {
  status: SessionStatus;
  api: Api | null;
  auth: AuthAdapter | null;
  refreshMe: () => Promise<void>;
  signOut: () => Promise<void>;
};

/** `undefined` means Firebase has not reported yet. */
type KnownUser = AuthUser | null | undefined;

type ProfileState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; me: MeResponse };

const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (value === null) {
    throw new Error('useSession must be used inside SessionProvider');
  }
  return value;
}

const FIREBASE_INIT_ISSUE: EnvIssue = {
  key: 'EXPO_PUBLIC_FIREBASE_API_KEY',
  message: 'Firebase 초기화에 실패했습니다. 설정값을 확인해주세요.',
};

type SessionProviderProps = {
  children: ReactNode;
  /** Test seams; production resolves both from the environment. */
  envOverride?: EnvConfig;
  authOverride?: AuthAdapter;
};

export function SessionProvider({
  children,
  envOverride,
  authOverride,
}: SessionProviderProps) {
  const env = useMemo(() => envOverride ?? resolveEnvConfig(), [envOverride]);

  const [user, setUser] = useState<KnownUser>(undefined);
  const [profile, setProfile] = useState<ProfileState>({ kind: 'loading' });
  const [notice, setNotice] = useState<string | null>(null);
  const requestId = useRef(0);

  const auth = useMemo<AuthAdapter | null>(() => {
    if (authOverride) {
      return authOverride;
    }
    if (env.status !== 'ready') {
      return null;
    }
    try {
      return createFirebaseAuthAdapter(env.firebase);
    } catch {
      return null;
    }
  }, [authOverride, env]);

  const api = useMemo<Api | null>(() => {
    if (env.status !== 'ready' || auth === null) {
      return null;
    }
    return createApi(
      new ApiClient({
        baseUrl: env.apiBaseUrl,
        getToken: () => auth.getIdToken(),
      }),
    );
  }, [auth, env]);

  useEffect(() => {
    if (auth === null) {
      return;
    }
    return auth.observe((next) => {
      requestId.current += 1;
      setUser(next);
      setProfile({ kind: 'loading' });
      // A fresh sign-in supersedes whatever ended the previous session.
      if (next) {
        setNotice(null);
      }
    });
  }, [auth]);

  const applyMeResult = useCallback(
    (generation: number, result: MeResponse | unknown, ok: boolean) => {
      if (requestId.current !== generation) {
        return;
      }
      if (ok) {
        setProfile({ kind: 'ready', me: result as MeResponse });
        return;
      }
      // Only a verdict ends the session. `INVALID_TOKEN` means the server
      // checked this token and rejected it; Firebase is signed out too, because
      // leaving it authenticated while this provider reports `signedOut` sends
      // the user back to the sign-in screen on every attempt with nothing
      // explaining the bounce.
      //
      // `AUTHENTICATION_REQUIRED` only means no usable token reached the
      // server. That is a refresh or transport blip, and tearing the session
      // down for it is what makes a login succeed on one try and fail on the
      // next. It falls through to the retryable error state instead.
      if (
        isApiError(result) &&
        result.kind === 'auth' &&
        result.code === 'INVALID_TOKEN'
      ) {
        setNotice(result.message);
        setUser(null);
        void auth?.signOutUser().catch(() => undefined);
        return;
      }
      setProfile({
        kind: 'error',
        message: isApiError(result)
          ? result.message
          : '프로필을 불러오지 못했습니다.',
      });
    },
    [auth],
  );

  const loadMe = useCallback(async () => {
    if (api === null) {
      return;
    }
    const generation = ++requestId.current;
    await api.getMe().then(
      (me) => applyMeResult(generation, me, true),
      (error: unknown) => applyMeResult(generation, error, false),
    );
  }, [api, applyMeResult]);

  useEffect(() => {
    if (api === null || !user) {
      return;
    }
    const generation = ++requestId.current;
    // Settled in the promise callbacks, so the effect body itself never writes
    // state synchronously.
    api.getMe().then(
      (me) => applyMeResult(generation, me, true),
      (error: unknown) => applyMeResult(generation, error, false),
    );
  }, [api, applyMeResult, user]);

  const signOut = useCallback(async () => {
    if (auth === null) {
      return;
    }
    requestId.current += 1;
    await auth.signOutUser();
  }, [auth]);

  const status = useMemo<SessionStatus>(() => {
    if (env.status === 'incomplete') {
      return { kind: 'misconfigured', issues: env.issues };
    }
    if (auth === null) {
      return { kind: 'misconfigured', issues: [FIREBASE_INIT_ISSUE] };
    }
    if (user === undefined) {
      return { kind: 'configuring' };
    }
    if (user === null) {
      return { kind: 'signedOut', notice };
    }
    if (profile.kind === 'loading') {
      return { kind: 'loadingProfile' };
    }
    if (profile.kind === 'error') {
      return { kind: 'profileError', message: profile.message };
    }
    return { kind: 'signedIn', me: profile.me };
  }, [auth, env, notice, profile, user]);

  const value = useMemo<SessionValue>(
    () => ({ status, api, auth, refreshMe: loadMe, signOut }),
    [api, auth, loadMe, signOut, status],
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}
