/**
 * The signed-out path after the server rejects a session.
 *
 * Firebase can authenticate a user the backend then refuses (a token the
 * verifier cannot validate returns 401). Discarding that silently left the
 * demo in a loop: sign in, bounce straight back to the sign-in screen, with
 * nothing on screen saying why.
 */

import { jest } from '@jest/globals';
import { render, screen, waitFor } from '@testing-library/react-native';

import { ApiClient } from '../src/api/client';
import { ApiError } from '../src/api/errors';
import type { AuthAdapter, AuthUser } from '../src/auth/firebase';
import { DemoApp } from '../src/app/DemoApp';
import { SessionProvider } from '../src/app/SessionProvider';
import { resolveEnvConfig } from '../src/config/env';

const env = resolveEnvConfig({
  EXPO_PUBLIC_API_BASE_URL: 'http://localhost:8000',
  EXPO_PUBLIC_FIREBASE_API_KEY: 'key',
  EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN: 'demo.firebaseapp.com',
  EXPO_PUBLIC_FIREBASE_PROJECT_ID: 'demo',
  EXPO_PUBLIC_FIREBASE_APP_ID: 'app',
});

function signedInAuth(signOutUser: () => Promise<void>): AuthAdapter {
  let listener: ((user: AuthUser | null) => void) | null = null;
  return {
    observe: (next) => {
      listener = next;
      // Firebase reports the restored session on the next tick.
      setTimeout(() => listener?.({ uid: 'uid-1' }), 0);
      return () => {
        listener = null;
      };
    },
    signIn: jest.fn(async () => undefined),
    signUp: jest.fn(async () => undefined),
    signOutUser: jest.fn(signOutUser),
    getIdToken: jest.fn(async () => 'token'),
    describePasswordPolicy: jest.fn(async () => null),
    checkPassword: jest.fn(async () => ({ ok: true }) as const),
  };
}

function stubMe(error: ApiError) {
  jest.spyOn(ApiClient.prototype, 'request').mockRejectedValue(error);
}

describe('a session the server rejects', () => {
  it('signs Firebase out and says why, instead of bouncing silently', async () => {
    const signOutUser = jest.fn(async () => undefined);
    const auth = signedInAuth(signOutUser);
    // The provider builds its own client, so the transport is stubbed instead.
    // The provider builds its own client, so the transport is stubbed instead.
    stubMe(
      new ApiError({
        kind: 'auth',
        code: 'INVALID_TOKEN',
        status: 401,
        message: '유효하지 않은 인증 토큰입니다.',
      }),
    );

    await render(
      <SessionProvider envOverride={env} authOverride={auth}>
        <DemoApp />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(
        screen.getByText('유효하지 않은 인증 토큰입니다.'),
      ).toBeOnTheScreen(),
    );
    // Firebase must not stay authenticated while the app reports signed out.
    expect(signOutUser).toHaveBeenCalled();
    expect(
      screen.getByRole('header', {
        name: '오늘도 자신과의 싸움에서\n승리하러 왔군요',
      }),
    ).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: '로그인' })).toBeOnTheScreen();
  });

  it('keeps the session when no token reached the server, and offers a retry', async () => {
    const signOutUser = jest.fn(async () => undefined);
    const auth = signedInAuth(signOutUser);
    stubMe(
      new ApiError({
        kind: 'auth',
        code: 'AUTHENTICATION_REQUIRED',
        status: 401,
        message: '인증이 필요합니다.',
      }),
    );

    await render(
      <SessionProvider envOverride={env} authOverride={auth}>
        <DemoApp />
      </SessionProvider>,
    );

    // A refresh blip is retryable, not a verdict: the user stays signed in.
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: '다시 시도' }),
      ).toBeOnTheScreen(),
    );
    expect(signOutUser).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '로그인' })).toBeNull();
  });
});
