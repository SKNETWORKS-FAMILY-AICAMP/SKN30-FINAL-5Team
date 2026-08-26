import { useState } from 'react';

import type { AuthAdapter } from '../../auth/firebase';
import { LoginScreen } from './LoginScreen';
import { SignUpScreen } from './SignUpScreen';

type AuthScreen = 'login' | 'signup';

type AuthFlowProps = {
  auth: AuthAdapter;
  notice?: string | null;
};

/** Signed-out flow for the production app. Firebase owns the signed-in exit. */
export function AuthFlow({ auth, notice = null }: AuthFlowProps) {
  const [screen, setScreen] = useState<AuthScreen>('login');

  if (screen === 'signup') {
    return <SignUpScreen auth={auth} onBack={() => setScreen('login')} />;
  }

  return (
    <LoginScreen
      auth={auth}
      notice={notice}
      onSignUp={() => setScreen('signup')}
    />
  );
}
