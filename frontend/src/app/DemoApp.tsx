/**
 * Root of the real user flow: splash, configuration check, auth, onboarding,
 * then the signed-in journey.
 *
 * The routing here is driven only by the session state, so there is no path
 * into the app that skips Firebase authentication or the server's view of the
 * user.
 */

import { useEffect, useState } from 'react';

import { useSession } from './SessionProvider';
import { MainFlow } from './MainFlow';
import { Button } from '../components/primitives';
import {
  ErrorState,
  LoadingState,
  ScreenHeading,
  ScreenShell,
} from '../components/states/ScreenState';
import { SignInScreen } from '../features/auth/SignInScreen';
import { ConfigurationRequiredScreen } from '../features/config/ConfigurationRequiredScreen';
import { OnboardingScreen } from '../features/onboarding/OnboardingScreen';
import { SplashScreen } from '../features/splash/SplashScreen';

/** Minimum time the splash stays up so the boot does not flash past. */
const SPLASH_MINIMUM_MS = 900;

export function DemoApp() {
  const session = useSession();
  const [splashDone, setSplashDone] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setSplashDone(true), SPLASH_MINIMUM_MS);
    return () => clearTimeout(timer);
  }, []);

  const booting = !splashDone || session.status.kind === 'configuring';
  if (booting) {
    return <SplashScreen bootStatus="pending" />;
  }

  switch (session.status.kind) {
    case 'misconfigured':
      return <ConfigurationRequiredScreen issues={session.status.issues} />;

    case 'signedOut':
      return session.auth ? (
        <SignInScreen auth={session.auth} />
      ) : (
        <ConfigurationRequiredScreen
          issues={[
            {
              key: 'EXPO_PUBLIC_FIREBASE_API_KEY',
              message: 'Firebase 인증을 초기화하지 못했습니다.',
            },
          ]}
        />
      );

    case 'loadingProfile':
      return (
        <ScreenShell>
          <ScreenHeading title="불러오는 중" />
          <LoadingState label="계정 정보를 확인하고 있어요" />
        </ScreenShell>
      );

    case 'profileError':
      return (
        <ScreenShell>
          <ScreenHeading title="연결하지 못했어요" />
          <ErrorState
            message={session.status.message}
            onRetry={() => void session.refreshMe()}
          />
          <Button
            label="로그아웃"
            tone="secondary"
            onPress={() => void session.signOut()}
          />
        </ScreenShell>
      );

    case 'signedIn': {
      const me = session.status.me;
      if (session.api === null) {
        return (
          <ConfigurationRequiredScreen
            issues={[
              {
                key: 'EXPO_PUBLIC_API_BASE_URL',
                message: 'API 클라이언트를 만들지 못했습니다.',
              },
            ]}
          />
        );
      }
      if (!me.onboarding_completed) {
        return (
          <OnboardingScreen
            api={session.api}
            onCompleted={() => void session.refreshMe()}
            onSignOut={() => void session.signOut()}
          />
        );
      }
      return (
        <MainFlow
          api={session.api}
          me={me}
          onRefreshMe={session.refreshMe}
          onSignOut={() => void session.signOut()}
        />
      );
    }

    default:
      return <SplashScreen bootStatus="pending" />;
  }
}
