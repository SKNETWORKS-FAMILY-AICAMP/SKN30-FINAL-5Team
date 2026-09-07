/**
 * Ephemeral Google/Kakao authorization-code flow.
 *
 * The verifier, state, nonce, authorization code, and returned custom token
 * live only in this call stack. They are never logged or persisted. Provider
 * credentials stay on the backend; the client ships only its public callback
 * URI and a PKCE challenge.
 */

import * as Crypto from 'expo-crypto';
import * as WebBrowser from 'expo-web-browser';

import type { UserFacingError } from '../api/errors';

WebBrowser.maybeCompleteAuthSession();

export type SocialOAuthProvider = 'GOOGLE' | 'KAKAO';

type AuthorizationInitResponse = {
  provider_code: SocialOAuthProvider;
  authorization_url: string;
  state: string;
  nonce: string;
  expires_at: string;
};

type TokenExchangeResponse = {
  token_type: 'FIREBASE_CUSTOM_TOKEN';
  firebase_custom_token: string;
};

type BrowserResult =
  { type: 'success'; url: string } | { type: 'cancel' | 'dismiss' | 'locked' };

type SocialOAuthDependencies = {
  fetchImpl: typeof fetch;
  openAuthSession: (
    authorizationUrl: string,
    redirectUri: string,
  ) => Promise<BrowserResult>;
  randomBytes: (length: number) => Promise<Uint8Array>;
  sha256Base64: (value: string) => Promise<string>;
  now: () => number;
};

const ERROR_MESSAGES: Record<string, string> = {
  INVALID_OAUTH_STATE:
    '로그인 요청이 만료되었거나 올바르지 않습니다. 다시 시도해주세요.',
  OAUTH_STATE_EXPIRED: '로그인 시간이 만료되었습니다. 다시 시도해주세요.',
  INVALID_OAUTH_NONCE:
    '로그인 요청을 확인하지 못했습니다. 처음부터 다시 시도해주세요.',
  INVALID_PKCE_VERIFIER:
    '로그인 요청을 확인하지 못했습니다. 처음부터 다시 시도해주세요.',
  AUTHORIZATION_CODE_REUSED:
    '이미 사용되었거나 만료된 로그인입니다. 다시 시도해주세요.',
  IDENTITY_ALREADY_LINKED: '이미 다른 계정에 연결된 소셜 계정입니다.',
  RATE_LIMITED: '로그인 시도가 많습니다. 잠시 후 다시 시도해주세요.',
  PROVIDER_UNAVAILABLE:
    '소셜 로그인을 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해주세요.',
  DATABASE_UNAVAILABLE:
    '로그인을 완료하지 못했습니다. 잠시 후 다시 시도해주세요.',
};

export class SocialOAuthFailure extends Error implements UserFacingError {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'SocialOAuthFailure';
    this.code = code;
  }

  get userMessage(): string {
    return this.message;
  }
}

function encodeBase64Url(bytes: Uint8Array): string {
  const alphabet =
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  let output = '';
  for (let index = 0; index < bytes.length; index += 3) {
    const first = bytes[index] ?? 0;
    const second = bytes[index + 1];
    const third = bytes[index + 2];
    output += alphabet[first >> 2];
    output += alphabet[((first & 3) << 4) | ((second ?? 0) >> 4)];
    if (second !== undefined) {
      output += alphabet[((second & 15) << 2) | ((third ?? 0) >> 6)];
    }
    if (third !== undefined) {
      output += alphabet[third & 63];
    }
  }
  return output;
}

function base64ToUrl(value: string): string {
  return value.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function readServerErrorCode(payload: unknown): string {
  if (!isRecord(payload) || !isRecord(payload.error)) {
    return 'SOCIAL_LOGIN_FAILED';
  }
  return typeof payload.error.code === 'string'
    ? payload.error.code
    : 'SOCIAL_LOGIN_FAILED';
}

function failureForServerCode(code: string): SocialOAuthFailure {
  return new SocialOAuthFailure(
    code,
    ERROR_MESSAGES[code] ??
      '소셜 로그인을 완료하지 못했습니다. 다시 시도해주세요.',
  );
}

async function postJson<T>(
  fetchImpl: typeof fetch,
  url: string,
  body: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new SocialOAuthFailure(
      'NETWORK_UNAVAILABLE',
      '네트워크에 연결하지 못했습니다. 연결을 확인하고 다시 시도해주세요.',
    );
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // A malformed response is handled as a generic, user-safe auth failure.
  }
  if (!response.ok) {
    throw failureForServerCode(readServerErrorCode(payload));
  }
  return payload as T;
}

function sameValue(left: string, right: string): boolean {
  if (left.length !== right.length) {
    return false;
  }
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return difference === 0;
}

function requireInitResponse(
  value: unknown,
  provider: SocialOAuthProvider,
): AuthorizationInitResponse {
  if (
    !isRecord(value) ||
    value.provider_code !== provider ||
    typeof value.authorization_url !== 'string' ||
    typeof value.state !== 'string' ||
    typeof value.nonce !== 'string' ||
    typeof value.expires_at !== 'string'
  ) {
    throw failureForServerCode('SOCIAL_LOGIN_FAILED');
  }
  const authorizationUrl = new URL(value.authorization_url);
  if (
    authorizationUrl.protocol !== 'https:' ||
    !Number.isFinite(Date.parse(value.expires_at))
  ) {
    throw failureForServerCode('SOCIAL_LOGIN_FAILED');
  }
  return value as AuthorizationInitResponse;
}

function requireTokenResponse(value: unknown): TokenExchangeResponse {
  if (
    !isRecord(value) ||
    value.token_type !== 'FIREBASE_CUSTOM_TOKEN' ||
    typeof value.firebase_custom_token !== 'string' ||
    !value.firebase_custom_token
  ) {
    throw failureForServerCode('SOCIAL_LOGIN_FAILED');
  }
  return value as TokenExchangeResponse;
}

function isExpectedCallback(value: string, redirectUri: string): boolean {
  try {
    const callback = new URL(value);
    const expected = new URL(redirectUri);
    return (
      callback.protocol === expected.protocol &&
      callback.host === expected.host &&
      callback.pathname === expected.pathname
    );
  } catch {
    return false;
  }
}

const defaultDependencies: SocialOAuthDependencies = {
  fetchImpl: globalThis.fetch.bind(globalThis),
  openAuthSession: (authorizationUrl, redirectUri) =>
    WebBrowser.openAuthSessionAsync(
      authorizationUrl,
      redirectUri,
    ) as Promise<BrowserResult>,
  randomBytes: Crypto.getRandomBytesAsync,
  sha256Base64: (value) =>
    Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, value, {
      encoding: Crypto.CryptoEncoding.BASE64,
    }),
  now: Date.now,
};

/** Returns a Firebase custom token for immediate SDK consumption only. */
export async function requestSocialFirebaseCustomToken(
  provider: SocialOAuthProvider,
  apiBaseUrl: string,
  redirectUri: string,
  dependencies: Partial<SocialOAuthDependencies> = {},
): Promise<string> {
  const deps = { ...defaultDependencies, ...dependencies };
  const baseUrl = apiBaseUrl.replace(/\/+$/, '');
  let parsedRedirect: URL;
  try {
    parsedRedirect = new URL(redirectUri);
  } catch {
    throw new SocialOAuthFailure(
      'SOCIAL_LOGIN_CONFIGURATION_INVALID',
      '소셜 로그인 callback 주소 설정을 확인해주세요.',
    );
  }
  if (parsedRedirect.protocol !== 'https:' || parsedRedirect.hash) {
    throw new SocialOAuthFailure(
      'SOCIAL_LOGIN_CONFIGURATION_INVALID',
      '소셜 로그인 callback 주소는 등록된 HTTPS 주소여야 합니다.',
    );
  }
  const verifier = encodeBase64Url(await deps.randomBytes(32));
  const challenge = base64ToUrl(await deps.sha256Base64(verifier));

  const init = requireInitResponse(
    await postJson<unknown>(
      deps.fetchImpl,
      `${baseUrl}/api/v1/auth/social/${provider}/authorize-init`,
      {
        redirect_uri: redirectUri,
        code_challenge: challenge,
        code_challenge_method: 'S256',
      },
    ),
    provider,
  );

  const browserResult = await deps.openAuthSession(
    init.authorization_url,
    redirectUri,
  );
  if (browserResult.type !== 'success') {
    throw new SocialOAuthFailure(
      'SOCIAL_LOGIN_CANCELLED',
      `${provider === 'GOOGLE' ? 'Google' : '카카오'} 로그인이 취소되었습니다.`,
    );
  }

  if (!isExpectedCallback(browserResult.url, redirectUri)) {
    throw failureForServerCode('INVALID_OAUTH_STATE');
  }
  const callback = new URL(browserResult.url);
  const providerError = callback.searchParams.get('error');
  if (providerError === 'access_denied') {
    throw new SocialOAuthFailure(
      'SOCIAL_LOGIN_CANCELLED',
      `${provider === 'GOOGLE' ? 'Google' : '카카오'} 로그인이 취소되었습니다.`,
    );
  }
  if (providerError) {
    throw failureForServerCode('SOCIAL_LOGIN_FAILED');
  }

  const state = callback.searchParams.get('state') ?? '';
  const authorizationCode = callback.searchParams.get('code') ?? '';
  if (!state || !authorizationCode || !sameValue(state, init.state)) {
    throw failureForServerCode('INVALID_OAUTH_STATE');
  }
  if (deps.now() >= Date.parse(init.expires_at)) {
    throw failureForServerCode('OAUTH_STATE_EXPIRED');
  }

  const exchanged = requireTokenResponse(
    await postJson<unknown>(
      deps.fetchImpl,
      `${baseUrl}/api/v1/auth/social/${provider}/exchange`,
      {
        authorization_code: authorizationCode,
        redirect_uri: redirectUri,
        state: init.state,
        nonce: init.nonce,
        code_verifier: verifier,
      },
    ),
  );
  return exchanged.firebase_custom_token;
}
