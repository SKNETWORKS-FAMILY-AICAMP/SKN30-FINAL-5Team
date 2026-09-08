import { describe, expect, it, jest } from '@jest/globals';

import {
  requestSocialFirebaseCustomToken,
  SocialOAuthFailure,
} from '../src/auth/socialOAuth';

function jsonResponse(body: unknown, ok = true): Response {
  return {
    ok,
    json: async () => body,
  } as Response;
}

describe('social OAuth client', () => {
  it('keeps PKCE material in memory and exchanges only the callback code', async () => {
    const fetchImpl = jest
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({
          provider_code: 'KAKAO',
          authorization_url: 'https://kauth.kakao.com/oauth/authorize',
          state: 'server-state',
          nonce: 'server-nonce',
          expires_at: '2030-01-01T00:00:00+00:00',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          token_type: 'FIREBASE_CUSTOM_TOKEN',
          firebase_custom_token: 'one-time-custom-token',
        }),
      );

    const token = await requestSocialFirebaseCustomToken(
      'KAKAO',
      'https://api.example.com/',
      'https://app.example.test/oauth/kakao/callback',
      {
        fetchImpl,
        randomBytes: async () => new Uint8Array(32),
        sha256Base64: async () => 'challenge/value==',
        openAuthSession: async () => ({
          type: 'success',
          url: 'https://app.example.test/oauth/kakao/callback?code=callback-code&state=server-state',
        }),
        now: () => Date.parse('2029-01-01T00:00:00+00:00'),
      },
    );

    expect(token).toBe('one-time-custom-token');
    expect(fetchImpl).toHaveBeenNthCalledWith(
      1,
      'https://api.example.com/api/v1/auth/social/KAKAO/authorize-init',
      expect.objectContaining({
        body: JSON.stringify({
          redirect_uri: 'https://app.example.test/oauth/kakao/callback',
          code_challenge: 'challenge_value',
          code_challenge_method: 'S256',
        }),
      }),
    );
    expect(fetchImpl).toHaveBeenNthCalledWith(
      2,
      'https://api.example.com/api/v1/auth/social/KAKAO/exchange',
      expect.objectContaining({
        body: JSON.stringify({
          authorization_code: 'callback-code',
          redirect_uri: 'https://app.example.test/oauth/kakao/callback',
          state: 'server-state',
          nonce: 'server-nonce',
          code_verifier: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
        }),
      }),
    );
  });

  it('uses the same strict contract with a provider-specific Google callback', async () => {
    const fetchImpl = jest
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({
          provider_code: 'GOOGLE',
          authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth',
          state: 'google-state',
          nonce: 'google-nonce',
          expires_at: '2030-01-01T00:00:00+00:00',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          token_type: 'FIREBASE_CUSTOM_TOKEN',
          firebase_custom_token: 'google-custom-token',
        }),
      );

    await expect(
      requestSocialFirebaseCustomToken(
        'GOOGLE',
        'https://api.example.com',
        'https://app.example.test/oauth/google/callback',
        {
          fetchImpl,
          randomBytes: async () => new Uint8Array(32),
          sha256Base64: async () => 'challenge',
          openAuthSession: async () => ({
            type: 'success',
            url: 'https://app.example.test/oauth/google/callback?code=google-code&state=google-state',
          }),
          now: () => Date.parse('2029-01-01T00:00:00+00:00'),
        },
      ),
    ).resolves.toBe('google-custom-token');
    expect(fetchImpl).toHaveBeenNthCalledWith(
      1,
      'https://api.example.com/api/v1/auth/social/GOOGLE/authorize-init',
      expect.any(Object),
    );
    expect(fetchImpl).toHaveBeenNthCalledWith(
      2,
      'https://api.example.com/api/v1/auth/social/GOOGLE/exchange',
      expect.any(Object),
    );
  });

  it('reports browser dismissal as an explicit cancellation', async () => {
    await expect(
      requestSocialFirebaseCustomToken(
        'KAKAO',
        'https://api.example.com',
        'https://app.example.test/oauth/kakao/callback',
        {
          fetchImpl: jest.fn<typeof fetch>().mockResolvedValue(
            jsonResponse({
              provider_code: 'KAKAO',
              authorization_url: 'https://kauth.kakao.com/oauth/authorize',
              state: 'state',
              nonce: 'nonce',
              expires_at: '2030-01-01T00:00:00+00:00',
            }),
          ),
          randomBytes: async () => new Uint8Array(32),
          sha256Base64: async () => 'challenge',
          openAuthSession: async () => ({ type: 'cancel' }),
          now: () => Date.parse('2029-01-01T00:00:00+00:00'),
        },
      ),
    ).rejects.toMatchObject({
      code: 'SOCIAL_LOGIN_CANCELLED',
      userMessage: '카카오 로그인이 취소되었습니다.',
    } satisfies Partial<SocialOAuthFailure>);
  });

  it('maps transport and server codes without surfacing provider details', async () => {
    await expect(
      requestSocialFirebaseCustomToken(
        'KAKAO',
        'https://api.example.com',
        'https://app.example.test/oauth/kakao/callback',
        {
          fetchImpl: jest
            .fn<typeof fetch>()
            .mockRejectedValue(new Error('raw')),
          randomBytes: async () => new Uint8Array(32),
          sha256Base64: async () => 'challenge',
        },
      ),
    ).rejects.toMatchObject({
      code: 'NETWORK_UNAVAILABLE',
      userMessage:
        '네트워크에 연결하지 못했습니다. 연결을 확인하고 다시 시도해주세요.',
    });
  });

  it('rejects custom-scheme callbacks before any network request', async () => {
    const fetchImpl = jest.fn<typeof fetch>();

    await expect(
      requestSocialFirebaseCustomToken(
        'KAKAO',
        'https://api.example.com',
        'helkki://auth/kakao',
        { fetchImpl },
      ),
    ).rejects.toMatchObject({
      code: 'SOCIAL_LOGIN_CONFIGURATION_INVALID',
      userMessage: '소셜 로그인 callback 주소는 등록된 HTTPS 주소여야 합니다.',
    });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
