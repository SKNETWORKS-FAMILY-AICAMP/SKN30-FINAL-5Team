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
  validatePassword,
  type Auth,
  type PasswordValidationStatus,
  type User,
} from 'firebase/auth';

import type { UserFacingError } from '../api/errors';
import type { FirebaseWebConfig } from '../config/env';

export type AuthUser = {
  uid: string;
};

/**
 * The outcome of checking a password against the project's own policy, before
 * anything is sent to Firebase.
 */
export type PasswordCheck =
  { ok: true } | { ok: false; code: string; message: string };

export type AuthAdapter = {
  observe(listener: (user: AuthUser | null) => void): () => void;
  signIn(email: string, password: string): Promise<void>;
  signUp(email: string, password: string): Promise<void>;
  signOutUser(): Promise<void>;
  getIdToken(): Promise<string | null>;
  /**
   * The project's password requirements as a Korean hint, or `null` when the
   * policy cannot be read. Lets a screen state the rule before the user types
   * instead of after the server rejects them.
   */
  describePasswordPolicy(): Promise<string | null>;
  /** Checks a password against that same policy. */
  checkPassword(password: string): Promise<PasswordCheck>;
};

export class AuthFailure extends Error implements UserFacingError {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'AuthFailure';
    this.code = code;
  }

  /**
   * `message` is already the mapped Korean copy, never the provider's raw text,
   * so it is safe for `messageForError` to render directly.
   */
  get userMessage(): string {
    return this.message;
  }
}

/**
 * Firebase's own minimum when a project defines no custom password policy.
 * Used only as a fallback: the real rule is read from the project.
 */
const BASELINE_MIN_LENGTH = 6;

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
  'auth/missing-password': '비밀번호를 입력해주세요.',
  'auth/weak-password': `비밀번호는 ${BASELINE_MIN_LENGTH}자 이상이어야 합니다.`,
  'auth/password-does-not-meet-requirements':
    '비밀번호가 이 프로젝트의 보안 요건을 충족하지 않습니다. 아래 비밀번호 조건을 확인해주세요.',
  'auth/unsupported-password-policy-schema-version':
    '이 앱이 지원하지 않는 비밀번호 정책 버전입니다. Firebase 콘솔의 비밀번호 정책 설정을 확인해주세요.',
  'auth/user-disabled': '사용할 수 없는 계정입니다.',
  'auth/admin-restricted-operation':
    'Firebase 테스트 프로젝트에서 이메일/비밀번호 가입이 허용되어 있지 않습니다.',
  'auth/invalid-api-key': 'Firebase 설정값(API 키)이 올바르지 않습니다.',
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

/**
 * The policy lookup is a network round trip. It is bounded so a slow or blocked
 * request falls back to the baseline check instead of leaving the caller's
 * submit button spinning with no way forward.
 */
const POLICY_TIMEOUT_MS = 4000;

function withTimeout<T>(work: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([
    work,
    new Promise<never>((_, reject) => {
      timer = setTimeout(
        () => reject(new Error('password policy timed out')),
        ms,
      );
    }),
  ]).finally(() => clearTimeout(timer));
}

/**
 * Renders a policy as a Korean requirement list. Firebase reports each rule
 * independently, and a project may enable any combination of them, so the hint
 * is built from whatever the project actually configured rather than assumed.
 */
function policyRequirements(
  policy: PasswordValidationStatus['passwordPolicy'],
): string[] {
  const options = policy.customStrengthOptions;
  const labels: string[] = [];
  if (options.minPasswordLength !== undefined) {
    labels.push(`${options.minPasswordLength}자 이상`);
  }
  // Firebase's default 4096-character ceiling is an implementation limit,
  // not useful sign-up guidance. Keep enforcing it through validatePassword,
  // but do not show it below the input before a user reaches that limit.
  if (options.containsLowercaseLetter) {
    labels.push('영문 소문자 포함');
  }
  if (options.containsUppercaseLetter) {
    labels.push('영문 대문자 포함');
  }
  if (options.containsNumericCharacter) {
    labels.push('숫자 포함');
  }
  if (options.containsNonAlphanumericCharacter) {
    labels.push('특수문자 포함');
  }
  return labels;
}

/** The subset of `policyRequirements` this password fails. */
function unmetRequirements(status: PasswordValidationStatus): string[] {
  const options = status.passwordPolicy.customStrengthOptions;
  const labels: string[] = [];
  if (status.meetsMinPasswordLength === false) {
    labels.push(`${options.minPasswordLength ?? BASELINE_MIN_LENGTH}자 이상`);
  }
  if (status.meetsMaxPasswordLength === false && options.maxPasswordLength) {
    labels.push(`${options.maxPasswordLength}자 이하`);
  }
  if (status.containsLowercaseLetter === false) {
    labels.push('영문 소문자 포함');
  }
  if (status.containsUppercaseLetter === false) {
    labels.push('영문 대문자 포함');
  }
  if (status.containsNumericCharacter === false) {
    labels.push('숫자 포함');
  }
  if (status.containsNonAlphanumericCharacter === false) {
    labels.push('특수문자 포함');
  }
  return labels;
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

    async describePasswordPolicy() {
      try {
        // `validatePassword` downloads the project's policy and evaluates it
        // locally; the password argument never leaves the device. An empty
        // string is passed because only the policy is wanted here.
        const status = await withTimeout(
          validatePassword(auth, ''),
          POLICY_TIMEOUT_MS,
        );
        const labels = policyRequirements(status.passwordPolicy);
        return labels.length > 0 ? labels.join(' · ') : null;
      } catch {
        return null;
      }
    },

    async checkPassword(password) {
      if (!password) {
        return {
          ok: false,
          code: 'auth/missing-password',
          message: '비밀번호를 입력해주세요.',
        };
      }
      try {
        const status = await withTimeout(
          validatePassword(auth, password),
          POLICY_TIMEOUT_MS,
        );
        if (status.isValid) {
          return { ok: true };
        }
        const labels = unmetRequirements(status);
        return {
          ok: false,
          code: 'auth/password-does-not-meet-requirements',
          message:
            labels.length > 0
              ? `비밀번호가 조건을 충족하지 않습니다: ${labels.join(', ')}`
              : '비밀번호가 이 프로젝트의 보안 요건을 충족하지 않습니다.',
        };
      } catch {
        // The policy could not be read (offline, or an older project). Fall
        // back to Firebase's baseline so this check never rejects a password
        // the server would have accepted.
        return password.length < BASELINE_MIN_LENGTH
          ? {
              ok: false,
              code: 'auth/weak-password',
              message: `비밀번호는 ${BASELINE_MIN_LENGTH}자 이상이어야 합니다.`,
            }
          : { ok: true };
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
        // A refresh can fail on a transient network blip. Returning null here
        // sends the request with no bearer token, which the server reads as
        // "not authenticated" — indistinguishable from a real rejection. Force
        // one more refresh before giving up.
        try {
          return await user.getIdToken(true);
        } catch {
          return null;
        }
      }
    },
  };
}
