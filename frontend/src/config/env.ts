/**
 * Runtime configuration, read only from `EXPO_PUBLIC_*` environment variables.
 *
 * Nothing here is a secret store: Expo inlines `EXPO_PUBLIC_*` into the client
 * bundle, so only values that are safe in a shipped app belong here. Firebase
 * Web config is public by design; the account's real protection is the Firebase
 * security rules and the backend's ID-token verification.
 *
 * Missing configuration fails closed. The app reports why instead of falling
 * back to a bypass, because a demo that silently skips auth would not be
 * exercising the real contract.
 */

export type FirebaseWebConfig = {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
};

export type EnvIssue = {
  key: string;
  message: string;
};

export type EnvConfig =
  | { status: 'ready'; apiBaseUrl: string; firebase: FirebaseWebConfig }
  | { status: 'incomplete'; issues: EnvIssue[] };

const FIREBASE_KEYS = {
  apiKey: 'EXPO_PUBLIC_FIREBASE_API_KEY',
  authDomain: 'EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN',
  projectId: 'EXPO_PUBLIC_FIREBASE_PROJECT_ID',
  appId: 'EXPO_PUBLIC_FIREBASE_APP_ID',
} as const;

function read(value: string | undefined): string {
  return typeof value === 'string' ? value.trim() : '';
}

/**
 * Expo replaces `process.env.EXPO_PUBLIC_X` at build time only for statically
 * written property accesses, so each key is spelled out rather than looked up.
 */
function rawEnv(): Record<string, string> {
  return {
    EXPO_PUBLIC_API_BASE_URL: read(process.env.EXPO_PUBLIC_API_BASE_URL),
    EXPO_PUBLIC_FIREBASE_API_KEY: read(
      process.env.EXPO_PUBLIC_FIREBASE_API_KEY,
    ),
    EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN: read(
      process.env.EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN,
    ),
    EXPO_PUBLIC_FIREBASE_PROJECT_ID: read(
      process.env.EXPO_PUBLIC_FIREBASE_PROJECT_ID,
    ),
    EXPO_PUBLIC_FIREBASE_APP_ID: read(process.env.EXPO_PUBLIC_FIREBASE_APP_ID),
  };
}

export function resolveEnvConfig(
  source: Record<string, string> = rawEnv(),
): EnvConfig {
  const issues: EnvIssue[] = [];

  const apiBaseUrl = source.EXPO_PUBLIC_API_BASE_URL ?? '';
  if (!apiBaseUrl) {
    issues.push({
      key: 'EXPO_PUBLIC_API_BASE_URL',
      message: 'API 서버 주소가 설정되지 않았습니다.',
    });
  } else if (!/^https?:\/\//.test(apiBaseUrl)) {
    issues.push({
      key: 'EXPO_PUBLIC_API_BASE_URL',
      message: 'API 서버 주소는 http:// 또는 https:// 로 시작해야 합니다.',
    });
  }

  const firebase: Record<string, string> = {};
  for (const [field, key] of Object.entries(FIREBASE_KEYS)) {
    const value = source[key] ?? '';
    if (!value) {
      issues.push({
        key,
        message: 'Firebase 설정값이 없습니다.',
      });
      continue;
    }
    firebase[field] = value;
  }

  if (issues.length > 0) {
    return { status: 'incomplete', issues };
  }

  return {
    status: 'ready',
    apiBaseUrl: apiBaseUrl.replace(/\/+$/, ''),
    firebase: firebase as unknown as FirebaseWebConfig,
  };
}
