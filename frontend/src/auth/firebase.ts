/**
 * Firebase Authentication adapter (email/password).
 *
 * The backend only accepts a verified Firebase ID token, so this is the single
 * place the app obtains one. There is no local bypass: when configuration is
 * missing the adapter reports it and the app stays signed out.
 *
 * Tokens, emails and passwords never leave this module in logs or storage. The
 * rest of the app sees only `AuthUser` (an opaque uid) and a token getter.
 */

import { initializeApp, type FirebaseApp } from 'firebase/app';
import {
  createUserWithEmailAndPassword,
  getAuth,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut,
  type Auth,
  type User,
} from 'firebase/auth';

import type { FirebaseWebConfig } from '../config/env';

export type AuthUser = {
  uid: string;
};

export type AuthAdapter = {
  observe(listener: (user: AuthUser | null) => void): () => void;
  signIn(email: string, password: string): Promise<void>;
  signUp(email: string, password: string): Promise<void>;
  signOutUser(): Promise<void>;
  getIdToken(): Promise<string | null>;
};

export class AuthFailure extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'AuthFailure';
    this.code = code;
  }
}

/**
 * Firebase surfaces precise reasons (wrong password vs unknown account) that
 * would let a caller probe which emails exist. Collapse credential failures
 * into one message and keep the rest actionable.
 */
const AUTH_MESSAGES: Record<string, string> = {
  'auth/invalid-email': '이메일 형식이 올바르지 않습니다.',
  'auth/invalid-credential': '이메일 또는 비밀번호를 확인해주세요.',
  'auth/wrong-password': '이메일 또는 비밀번호를 확인해주세요.',
  'auth/user-not-found': '이메일 또는 비밀번호를 확인해주세요.',
  'auth/email-already-in-use': '이미 가입된 이메일입니다.',
  'auth/weak-password': '비밀번호는 6자 이상이어야 합니다.',
  'auth/too-many-requests':
    '시도가 많아 잠시 제한되었습니다. 잠시 후 다시 시도해주세요.',
  'auth/network-request-failed':
    '네트워크에 연결하지 못했습니다. 연결을 확인해주세요.',
  'auth/operation-not-allowed':
    'Firebase 테스트 프로젝트에서 이메일/비밀번호 로그인이 켜져 있지 않습니다.',
};

function toAuthFailure(error: unknown): AuthFailure {
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? String((error as { code: unknown }).code)
      : 'auth/unknown';
  return new AuthFailure(
    code,
    AUTH_MESSAGES[code] ?? '로그인을 처리하지 못했습니다. 다시 시도해주세요.',
  );
}

export function createFirebaseAuthAdapter(
  config: FirebaseWebConfig,
): AuthAdapter {
  let app: FirebaseApp;
  let auth: Auth;
  try {
    app = initializeApp(config);
    auth = getAuth(app);
  } catch (error) {
    throw toAuthFailure(error);
  }

  const currentUser = (): User | null => auth.currentUser;

  return {
    observe(listener) {
      return onAuthStateChanged(auth, (user) => {
        listener(user ? { uid: user.uid } : null);
      });
    },

    async signIn(email, password) {
      try {
        await signInWithEmailAndPassword(auth, email.trim(), password);
      } catch (error) {
        throw toAuthFailure(error);
      }
    },

    async signUp(email, password) {
      try {
        await createUserWithEmailAndPassword(auth, email.trim(), password);
      } catch (error) {
        throw toAuthFailure(error);
      }
    },

    async signOutUser() {
      try {
        await signOut(auth);
      } catch (error) {
        throw toAuthFailure(error);
      }
    },

    async getIdToken() {
      const user = currentUser();
      if (!user) {
        return null;
      }
      try {
        // Firebase refreshes the token when it is close to expiry, so the app
        // never caches one itself.
        return await user.getIdToken();
      } catch {
        return null;
      }
    },
  };
}
