import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { signInWithCustomToken } from 'firebase/auth';

import {
  createFirebaseAuthAdapter,
  type AuthAdapter,
} from '../src/auth/firebase';
import {
  requestSocialFirebaseCustomToken,
  type SocialOAuthProvider,
} from '../src/auth/socialOAuth';

jest.mock('../src/auth/socialOAuth', () => ({
  requestSocialFirebaseCustomToken: jest.fn(),
}));

const requestToken = requestSocialFirebaseCustomToken as jest.MockedFunction<
  typeof requestSocialFirebaseCustomToken
>;
const consumeToken = signInWithCustomToken as jest.MockedFunction<
  typeof signInWithCustomToken
>;

function adapter(): AuthAdapter {
  return createFirebaseAuthAdapter(
    {
      apiKey: 'public-api-key',
      authDomain: 'demo.firebaseapp.com',
      projectId: 'demo',
      appId: 'public-app-id',
    },
    {
      apiBaseUrl: 'https://api.example.test',
      socialOAuthRedirectUris: {
        GOOGLE: 'https://app.example.test/oauth/google/callback',
        KAKAO: 'https://app.example.test/oauth/kakao/callback',
      },
    },
  );
}

type ProviderCase = [
  string,
  SocialOAuthProvider,
  string,
  (auth: AuthAdapter) => Promise<void>,
];

describe('Firebase social auth adapter', () => {
  beforeEach(() => {
    requestToken.mockReset();
    consumeToken.mockReset();
    requestToken.mockResolvedValue('one-time-custom-token');
    consumeToken.mockResolvedValue({} as never);
  });

  const providerCases: ProviderCase[] = [
    [
      'Google',
      'GOOGLE',
      'https://app.example.test/oauth/google/callback',
      (auth: AuthAdapter) => auth.signInWithGoogle(),
    ],
    [
      'Kakao',
      'KAKAO',
      'https://app.example.test/oauth/kakao/callback',
      (auth: AuthAdapter) => auth.signInWithKakao(),
    ],
  ];

  it.each(providerCases)(
    'passes the %s HTTPS redirect and immediately consumes the custom token',
    async (_label, provider, redirectUri, signIn) => {
      await signIn(adapter());

      expect(requestToken).toHaveBeenCalledWith(
        provider,
        'https://api.example.test',
        redirectUri,
      );
      expect(consumeToken).toHaveBeenCalledWith(
        expect.any(Object),
        'one-time-custom-token',
      );
    },
  );

  it('fails clearly before OAuth when a provider redirect is missing', async () => {
    const auth = createFirebaseAuthAdapter(
      {
        apiKey: 'public-api-key',
        authDomain: 'demo.firebaseapp.com',
        projectId: 'demo',
        appId: 'public-app-id',
      },
      {
        apiBaseUrl: 'https://api.example.test',
        socialOAuthRedirectUris: { GOOGLE: null, KAKAO: null },
      },
    );

    await expect(auth.signInWithGoogle()).rejects.toMatchObject({
      code: 'auth/social-config-missing',
      userMessage: 'Google 로그인 callback 주소가 설정되지 않았습니다.',
    });
    expect(requestToken).not.toHaveBeenCalled();
    expect(consumeToken).not.toHaveBeenCalled();
  });
});
