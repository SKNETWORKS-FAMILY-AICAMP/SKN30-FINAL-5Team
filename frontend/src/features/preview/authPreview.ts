import type { AuthAdapter } from '../../auth/firebase';

/**
 * Network-free adapter for rendering the real signed-out app screen in the
 * preview gallery. The gallery exercises the production UI without creating
 * Firebase users, requesting tokens, or persisting credentials.
 */
export const authPreviewAdapter: AuthAdapter = {
  observe(listener) {
    listener(null);
    return () => undefined;
  },
  async signIn() {},
  async signUp() {},
  async signOutUser() {},
  async getIdToken() {
    return null;
  },
  async describePasswordPolicy() {
    return '6자 이상';
  },
  async checkPassword(password) {
    return password.length >= 6
      ? { ok: true }
      : {
          ok: false,
          code: 'auth/weak-password',
          message: '비밀번호는 6자 이상이어야 합니다.',
        };
  },
};
