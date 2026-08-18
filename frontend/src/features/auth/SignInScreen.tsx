/**
 * Real Firebase email/password sign-in and sign-up.
 *
 * The backend accepts only a verified Firebase ID token, and Kakao/Naver are
 * reserved-but-unimplemented contracts, so this screen offers exactly the one
 * provider the demo can actually authenticate with. No provider is shown that
 * would not work if tapped.
 */

import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useAsyncAction } from '../../api/useAsync';
import { Button, InlineFeedback, TextField } from '../../components/primitives';
import {
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';
import type { AuthAdapter } from '../../auth/firebase';

type Mode = 'signIn' | 'signUp';

export function SignInScreen({ auth }: { auth: AuthAdapter }) {
  const [mode, setMode] = useState<Mode>('signIn');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [validation, setValidation] = useState<string | null>(null);

  const submit = useAsyncAction(async (nextMode: Mode) => {
    if (nextMode === 'signUp') {
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
    if (password.length < 6) {
      setValidation('비밀번호는 6자 이상이어야 합니다.');
      return;
    }
    void submit.run(mode);
  }, [email, mode, password, submit]);

  const toggleMode = useCallback(() => {
    setValidation(null);
    submit.clearError();
    setMode((current) => (current === 'signIn' ? 'signUp' : 'signIn'));
  }, [submit]);

  const isSignUp = mode === 'signUp';

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
          onChangeText={setPassword}
          placeholder="6자 이상"
          secureTextEntry={!showPassword}
          textContentType="password"
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
      </View>

      {validation ? <InlineFeedback tone="error" message={validation} /> : null}
      {submit.error ? (
        <InlineFeedback tone="error" message={submit.error} />
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
