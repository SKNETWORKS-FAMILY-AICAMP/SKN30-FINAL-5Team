import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';

import { fontFamilies, useAuthFonts } from '../../app/fonts';
import { useAsyncAction } from '../../api/useAsync';
import type { AuthAdapter } from '../../auth/firebase';
import {
  Button,
  Card,
  InlineFeedback,
  TextField,
} from '../../components/primitives';
import { colors, radii, spacing } from '../../components/theme';
import { SPLASH_ASSETS } from '../splash/SplashScreen';
import type { LoginPreviewState } from './previewStates';

export const LOGIN_LAYOUT = {
  sheetMaxHeight: '92%' as const,
  sheetTopRadius: 28,
  sheetHorizontalPadding: 22,
  sheetBottomPadding: 30,
  islandWidth: '118%' as const,
  islandLeft: '-9%' as const,
  islandTop: 64,
  questionLeft: '33%' as const,
  questionTop: 146,
} as const;

type LoginFixture = {
  email: string;
  password: string;
  emailError?: string;
  passwordError?: string;
  feedback?: {
    message: string;
    tone: 'success' | 'warning' | 'error';
  };
  linkedProvider?: string;
};

const LOGIN_FIXTURES: Record<LoginPreviewState, LoginFixture> = {
  idle: { email: '', password: '' },
  validation: {
    email: '',
    password: 'short',
    emailError: '이메일을 입력해주세요.',
    passwordError: '비밀번호는 8자 이상이에요.',
  },
  loading: { email: 'prototype@example.com', password: 'password1' },
  'credentials-error': {
    email: 'prototype@example.com',
    password: 'password1',
    feedback: {
      message: '이메일 또는 비밀번호가 올바르지 않아요.',
      tone: 'error',
    },
  },
  'network-error': {
    email: 'prototype@example.com',
    password: 'password1',
    feedback: {
      message:
        '네트워크에 연결할 수 없어요. 연결 상태를 확인한 뒤 다시 시도해주세요.',
      tone: 'error',
    },
  },
  notice: {
    email: 'prototype@example.com',
    password: '',
    feedback: {
      message: '프로필 등록이 완료되었습니다. 로그인해 주세요.',
      tone: 'success',
    },
  },
  blocked: {
    email: '',
    password: '',
    feedback: {
      message: '현재 계정으로는 로그인을 계속할 수 없어요.',
      tone: 'warning',
    },
  },
  linked: {
    email: '',
    password: '',
    linkedProvider: 'Google',
    feedback: {
      message: '연결한 계정: Google. 아래 Google 버튼으로 로그인해주세요.',
      tone: 'success',
    },
  },
  'social-loading': { email: '', password: '' },
};

type LoginScreenProps = {
  auth?: AuthAdapter;
  notice?: string | null;
  onRetry?: () => void;
  onSignUp?: () => void;
  onSocialPress?: (provider: string) => void;
  onSubmit?: (email: string, password: string) => unknown;
  previewState?: LoginPreviewState;
};

export function LoginScreen({ ...props }: LoginScreenProps) {
  return <LoginScreenContent key={props.previewState ?? 'idle'} {...props} />;
}

function LoginScreenContent({
  auth,
  notice = null,
  onRetry,
  onSignUp,
  onSocialPress,
  onSubmit,
  previewState = 'idle',
}: LoginScreenProps) {
  const fixture = LOGIN_FIXTURES[previewState];
  const [email, setEmail] = useState(fixture.email);
  const [password, setPassword] = useState(fixture.password);
  const [showPassword, setShowPassword] = useState(false);
  const [saveId, setSaveId] = useState(false);
  const [autoLogin, setAutoLogin] = useState(false);
  const [validation, setValidation] = useState<string | null>(null);
  const submit = useAsyncAction(async () => {
    if (!auth) {
      return;
    }
    await auth.signIn(email, password);
  });
  const handleSubmit = useCallback(() => {
    if (!auth) {
      onSubmit?.(email, password);
      return;
    }
    setValidation(null);
    submit.clearError();
    if (!email.trim()) {
      setValidation('이메일을 입력해주세요.');
      return;
    }
    if (!password) {
      setValidation('비밀번호를 입력해주세요.');
      return;
    }
    void submit.run();
  }, [auth, email, onSubmit, password, submit]);
  const isApiFlow = auth !== undefined;
  const isLoading = previewState === 'loading' || submit.pending;
  const isSocialLoading = previewState === 'social-loading';
  const authFonts = useAuthFonts();
  const useLocalHeadingFont = authFonts.loaded && !authFonts.failed;

  return (
    <SafeAreaView
      edges={['top', 'right', 'bottom', 'left']}
      style={styles.screen}
    >
      <StatusBar style="light" />
      <View
        accessible={false}
        importantForAccessibility="no"
        style={styles.artwork}
      >
        <Image
          resizeMode="contain"
          source={SPLASH_ASSETS.splashIsland}
          style={styles.island}
        />
        <Image
          resizeMode="contain"
          source={SPLASH_ASSETS.questionMark}
          style={styles.question}
        />
      </View>
      <View style={styles.scrim} />

      <ScrollView
        keyboardShouldPersistTaps="handled"
        style={styles.sheet}
        contentContainerStyle={styles.sheetContent}
      >
        <View style={styles.handle} />
        <View style={styles.heading}>
          <Text
            accessibilityRole="header"
            style={[styles.title, useLocalHeadingFont && styles.titleFont]}
          >
            오늘도 자신과의 싸움에서{`\n`}승리하러 왔군요
          </Text>
          <Text style={styles.subtitle}>
            좋습니다. 헬끼가 도와드릴게요. 우끽끽~
          </Text>
        </View>

        {fixture.feedback ? (
          <InlineFeedback
            action={
              previewState === 'network-error' ? (
                <Button
                  label="다시 시도"
                  labelStyle={styles.feedbackActionLabel}
                  onPress={onRetry}
                  style={styles.feedbackAction}
                  tone="secondary"
                />
              ) : undefined
            }
            message={fixture.feedback.message}
            tone={fixture.feedback.tone}
          />
        ) : null}
        {notice ? <InlineFeedback message={notice} tone="warning" /> : null}
        {validation ? (
          <InlineFeedback message={validation} tone="error" />
        ) : null}
        {submit.error ? (
          <InlineFeedback message={submit.error} tone="error" />
        ) : null}

        <View style={styles.form}>
          <TextField
            accessibilityLabel="이메일"
            autoCapitalize="none"
            autoComplete="email"
            error={fixture.emailError}
            keyboardType="email-address"
            onChangeText={setEmail}
            placeholder="이메일"
            style={styles.loginField}
            textContentType="emailAddress"
            value={email}
          />
          <TextField
            accessibilityLabel="비밀번호"
            error={fixture.passwordError}
            onChangeText={setPassword}
            placeholder="비밀번호"
            secureTextEntry={!showPassword}
            style={styles.loginField}
            trailing={
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="비밀번호 표시 전환"
                onPress={() => setShowPassword((current) => !current)}
                style={styles.passwordToggle}
              >
                <Text style={styles.passwordToggleLabel}>
                  {showPassword ? '숨기기' : '표시'}
                </Text>
              </Pressable>
            }
            value={password}
          />

          {!isApiFlow ? (
            <View style={styles.preferenceGroup}>
              <CheckRow
                checked={saveId}
                label="이메일 저장"
                onPress={() => setSaveId((current) => !current)}
              />
              <CheckRow
                checked={autoLogin}
                label="자동 로그인"
                onPress={() => setAutoLogin((current) => !current)}
              />
            </View>
          ) : null}

          <Button
            disabled={isLoading}
            label={isLoading ? '로그인 중...' : '로그인'}
            labelStyle={isLoading ? styles.loadingButtonLabel : undefined}
            leading={
              isLoading ? (
                <ActivityIndicator color={colors.surface} size="small" />
              ) : undefined
            }
            onPress={handleSubmit}
            style={isLoading ? styles.loadingButton : undefined}
          />

          <View style={styles.accountLinks}>
            <Pressable
              accessibilityRole="button"
              onPress={onSignUp}
              style={styles.textAction}
            >
              <Text style={styles.primaryLink}>회원가입</Text>
            </Pressable>
            {!isApiFlow ? (
              <>
                <View style={styles.linkDivider} />
                <Text style={styles.secondaryLink}>이메일 · 비밀번호 찾기</Text>
              </>
            ) : null}
          </View>
        </View>

        {!isApiFlow ? (
          <>
            <View style={styles.dividerRow}>
              <View style={styles.divider} />
              <Text style={styles.dividerLabel}>
                {fixture.linkedProvider ? '연결한 계정으로 로그인' : '또는'}
              </Text>
              <View style={styles.divider} />
            </View>

            <View style={styles.socialGroup}>
              <SocialButton
                label={
                  fixture.linkedProvider === 'Google'
                    ? 'Google로 로그인'
                    : 'Google로 계속하기'
                }
                mark="G"
                onPress={() => onSocialPress?.('Google')}
                selected={fixture.linkedProvider === 'Google'}
                tone="google"
              />
              <SocialButton
                label="카카오로 계속하기"
                mark="K"
                onPress={() => onSocialPress?.('카카오')}
                tone="kakao"
              />
              <SocialButton
                label="네이버로 계속하기"
                mark="N"
                onPress={() => onSocialPress?.('네이버')}
                tone="naver"
              />
            </View>
          </>
        ) : null}

        <Text style={styles.terms}>
          계속하면 서비스 이용약관과 개인정보 처리방침에 동의하게 됩니다.
        </Text>
      </ScrollView>

      {isSocialLoading ? (
        <View accessible accessibilityRole="alert" style={styles.busyOverlay}>
          <Card style={styles.busyCard}>
            <ActivityIndicator color={colors.primary} />
            <Text style={styles.busyTitle}>Google 인증 중...</Text>
            <Text style={styles.busyMessage}>
              인증 후 프로필 등록 여부를 확인해요
            </Text>
          </Card>
        </View>
      ) : null}
    </SafeAreaView>
  );
}

function CheckRow({
  checked,
  label,
  onPress,
}: {
  checked: boolean;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      onPress={onPress}
      style={styles.checkRow}
    >
      <View style={[styles.checkBox, checked && styles.checkBoxChecked]}>
        <Text style={[styles.checkMark, !checked && styles.checkMarkHidden]}>
          ✓
        </Text>
      </View>
      <Text style={styles.checkLabel}>{label}</Text>
    </Pressable>
  );
}

function SocialButton({
  label,
  mark,
  onPress,
  selected = false,
  tone,
}: {
  label: string;
  mark: string;
  onPress: () => void;
  selected?: boolean;
  tone: 'google' | 'kakao' | 'naver';
}) {
  const isGoogle = tone === 'google';

  return (
    <Button
      label={label}
      labelStyle={
        tone === 'naver' ? styles.socialLightLabel : styles.socialDarkLabel
      }
      leading={
        <View style={[styles.socialMark, toneStyles[tone].mark]}>
          <Text style={[styles.socialMarkText, toneStyles[tone].markText]}>
            {mark}
          </Text>
        </View>
      }
      onPress={onPress}
      style={[
        styles.socialButton,
        toneStyles[tone].button,
        selected && styles.socialButtonSelected,
      ]}
      tone={isGoogle ? 'secondary' : 'primary'}
    />
  );
}

const toneStyles = {
  google: StyleSheet.create({
    button: { backgroundColor: colors.surface },
    mark: { backgroundColor: '#FFFFFF' },
    markText: { color: '#4285F4' },
  }),
  kakao: StyleSheet.create({
    button: { backgroundColor: '#FEE500' },
    mark: { backgroundColor: '#FEE500' },
    markText: { color: '#191600' },
  }),
  naver: StyleSheet.create({
    button: { backgroundColor: '#03C75A' },
    mark: { backgroundColor: '#03C75A' },
    markText: { color: colors.surface },
  }),
} as const;

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: colors.splashBackground,
  },
  artwork: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  island: {
    position: 'absolute',
    top: LOGIN_LAYOUT.islandTop,
    left: LOGIN_LAYOUT.islandLeft,
    width: LOGIN_LAYOUT.islandWidth,
    aspectRatio: 1.5,
  },
  question: {
    position: 'absolute',
    top: LOGIN_LAYOUT.questionTop,
    left: LOGIN_LAYOUT.questionLeft,
    width: 56,
    height: 56,
  },
  scrim: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: 'rgba(20, 28, 16, 0.55)',
  },
  sheet: {
    maxHeight: LOGIN_LAYOUT.sheetMaxHeight,
    marginTop: 'auto',
    borderTopLeftRadius: LOGIN_LAYOUT.sheetTopRadius,
    borderTopRightRadius: LOGIN_LAYOUT.sheetTopRadius,
    backgroundColor: colors.canvas,
  },
  sheetContent: {
    gap: spacing.md,
    paddingTop: spacing.lg,
    paddingHorizontal: LOGIN_LAYOUT.sheetHorizontalPadding,
    paddingBottom: LOGIN_LAYOUT.sheetBottomPadding,
  },
  handle: {
    width: 40,
    height: 4,
    alignSelf: 'center',
    borderRadius: 2,
    backgroundColor: '#DCD8CF',
  },
  heading: {
    alignItems: 'center',
    gap: 6,
  },
  title: {
    color: colors.primary,
    fontSize: 22,
    fontWeight: '700',
    letterSpacing: -0.5,
    lineHeight: 30,
    textAlign: 'center',
  },
  titleFont: {
    fontFamily: fontFamilies.loginHeading,
    fontWeight: '400',
  },
  subtitle: {
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 20,
    textAlign: 'center',
  },
  form: {
    gap: 9,
  },
  loginField: {
    borderRadius: radii.button,
    paddingHorizontal: spacing.lg,
  },
  passwordToggle: {
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: spacing.xs,
  },
  passwordToggleLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  preferenceGroup: {
    gap: spacing.sm,
    paddingTop: 2,
    paddingHorizontal: 2,
  },
  checkRow: {
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    paddingVertical: spacing.xs,
  },
  checkBox: {
    width: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: '#D5D0C6',
    borderRadius: 6,
    backgroundColor: colors.surface,
  },
  checkBoxChecked: {
    borderColor: colors.primary,
    backgroundColor: colors.primary,
  },
  checkMark: {
    color: colors.surface,
    fontSize: 12,
    fontWeight: '700',
  },
  checkMarkHidden: {
    color: 'transparent',
  },
  checkLabel: {
    color: colors.text,
    fontSize: 13.5,
    fontWeight: '600',
  },
  accountLinks: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 14,
    paddingTop: 2,
  },
  loadingButton: {
    backgroundColor: colors.primaryBusy,
  },
  loadingButtonLabel: {
    color: colors.surface,
  },
  textAction: {
    minHeight: 36,
    justifyContent: 'center',
  },
  primaryLink: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: '700',
  },
  secondaryLink: {
    color: colors.textMuted,
    fontSize: 13,
  },
  linkDivider: {
    width: 1,
    height: 11,
    backgroundColor: '#DCD8CF',
  },
  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  divider: {
    height: 1,
    flex: 1,
    backgroundColor: colors.border,
  },
  dividerLabel: {
    color: '#A8A49C',
    fontSize: 12,
  },
  socialGroup: {
    gap: 10,
  },
  socialButton: {
    minHeight: 52,
    justifyContent: 'flex-start',
    borderRadius: radii.card,
    paddingHorizontal: spacing.xl,
  },
  socialButtonSelected: {
    borderWidth: 1.5,
    borderColor: colors.primary,
  },
  socialDarkLabel: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '600',
  },
  socialLightLabel: {
    color: colors.surface,
    fontSize: 15,
    fontWeight: '600',
  },
  socialMark: {
    width: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 10,
  },
  socialMarkText: {
    fontSize: 12,
    fontWeight: '900',
  },
  terms: {
    color: '#A8A49C',
    fontSize: 11,
    lineHeight: 18,
    textAlign: 'center',
  },
  feedbackAction: {
    minHeight: 36,
    alignSelf: 'flex-start',
    borderColor: colors.dangerText,
    borderRadius: 10,
    paddingHorizontal: 13,
  },
  feedbackActionLabel: {
    color: colors.dangerText,
    fontSize: 12.5,
  },
  busyOverlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 30,
    backgroundColor: 'rgba(20, 28, 16, 0.6)',
  },
  busyCard: {
    minWidth: 210,
    alignItems: 'center',
    gap: spacing.md,
    borderRadius: 18,
    backgroundColor: colors.canvas,
    paddingHorizontal: 26,
    paddingVertical: 22,
  },
  busyTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  busyMessage: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
    textAlign: 'center',
  },
});
