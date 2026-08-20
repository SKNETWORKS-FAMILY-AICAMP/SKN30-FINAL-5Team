/**
 * Real Firebase email/password sign-in and sign-up.
 *
 * The backend accepts only a verified Firebase ID token, and Kakao/Naver are
 * reserved-but-unimplemented contracts, so this screen offers exactly the one
 * provider the demo can actually authenticate with. No provider is shown that
 * would not work if tapped.
 */

import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useAsyncAction } from '../../api/useAsync';
import { Button, InlineFeedback, TextField } from '../../components/primitives';
import {
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';
import { AuthFailure, type AuthAdapter } from '../../auth/firebase';

type Mode = 'signIn' | 'signUp';

type SignInScreenProps = {
  auth: AuthAdapter;
  /** Why the previous session ended, when it did not end by choice. */
  notice?: string | null;
};

export function SignInScreen({ auth, notice = null }: SignInScreenProps) {
  const [mode, setMode] = useState<Mode>('signIn');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [validation, setValidation] = useState<string | null>(null);
  const [policyHint, setPolicyHint] = useState<string | null>(null);

  const isSignUp = mode === 'signUp';

  // The project's password policy is configured in the Firebase console, so the
  // rule is fetched rather than hardcoded. Stating it up front is what stops a
  // sign-up from being rejected only after the user submits.
  useEffect(() => {
    if (!isSignUp) {
      return;
    }
    let active = true;
    void auth.describePasswordPolicy().then((hint) => {
      if (active) {
        setPolicyHint(hint);
      }
    });
    return () => {
      active = false;
    };
  }, [auth, isSignUp]);

  const submit = useAsyncAction(async (nextMode: Mode) => {
    if (nextMode === 'signUp') {
      // Only sign-up is gated on the policy. An existing account may hold a
      // password that predates a stricter rule, and Firebase still accepts it,
      // so checking here would lock the user out of their own account — and
      // would put a network round trip in front of every login.
      const check = await auth.checkPassword(password);
      if (!check.ok) {
        throw new AuthFailure(check.code, check.message);
      }
      await auth.signUp(email, password);
      return;
    }
    await auth.signIn(email, password);
  });

  const onSubmit = useCallback(() => {
    setValidation(null);
    if (!email.trim()) {
      setValidation('이메일을 입력해주세요.');
      return;
    }
    void submit.run(mode);
  }, [email, mode, submit]);

  const toggleMode = useCallback(() => {
    setValidation(null);
    submit.clearError();
    setMode((current) => (current === 'signIn' ? 'signUp' : 'signIn'));
  }, [submit]);

  return (
    <ScreenShell contentStyle={styles.content}>
      <ScreenHeading
        title={isSignUp ? '헬끼 시작하기' : '헬끼에 로그인'}
        subtitle={
          isSignUp
            ? '테스트 계정을 만들어 데모를 진행해요.'
            : 'Firebase 테스트 계정으로 로그인해요.'
        }
      />

      <View style={styles.form}>
        <TextField
          label="이메일"
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          onChangeText={setEmail}
          placeholder="demo@example.com"
          textContentType="emailAddress"
          value={email}
        />
        <TextField
          label="비밀번호"
          autoCapitalize="none"
          // Sign-up must advertise a *new* password: browsers and keychains
          // then offer to generate a strong one instead of reusing a saved
          // credential, which is what triggers the "this password was found in
          // a breach" prompt during a demo sign-up.
          autoComplete={isSignUp ? 'new-password' : 'current-password'}
          onChangeText={setPassword}
          placeholder="비밀번호"
          secureTextEntry={!showPassword}
          textContentType={isSignUp ? 'newPassword' : 'password'}
          value={password}
          trailing={
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={
                showPassword ? '비밀번호 숨기기' : '비밀번호 보기'
              }
              onPress={() => setShowPassword((current) => !current)}
            >
              <Text style={styles.reveal}>
                {showPassword ? '숨기기' : '보기'}
              </Text>
            </Pressable>
          }
        />
        {isSignUp && policyHint ? (
          <Text style={styles.hint}>{`비밀번호 조건: ${policyHint}`}</Text>
        ) : null}
      </View>

      {notice ? <InlineFeedback tone="warning" message={notice} /> : null}
      {validation ? <InlineFeedback tone="error" message={validation} /> : null}
      {submit.error ? (
        <InlineFeedback tone="error" message={submit.error} />
      ) : null}

      {isSignUp ? (
        <Text style={styles.hint}>
          가입 후 온보딩에서 개인정보 동의와 프로필을 안내해요.
        </Text>
      ) : null}
      <Button
        label={
          submit.pending
            ? '처리 중…'
            : isSignUp
              ? '회원가입하고 시작'
              : '로그인'
        }
        disabled={submit.pending}
        onPress={onSubmit}
      />

      <Pressable
        accessibilityRole="button"
        onPress={toggleMode}
        style={styles.switch}
      >
        <Text style={styles.switchText}>
          {isSignUp
            ? '이미 계정이 있어요. 로그인하기'
            : '계정이 없어요. 회원가입하기'}
        </Text>
      </Pressable>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: spacing.lg,
    paddingTop: 64,
  },
  form: {
    gap: spacing.md,
  },
  hint: {
    color: colors.textMuted,
    fontSize: 12,
  },
  reveal: {
    color: colors.textMuted,
    fontSize: 13,
    fontWeight: '600',
  },
  switch: {
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  switchText: {
    color: colors.greenText,
    fontSize: 13,
    fontWeight: '600',
  },
});
