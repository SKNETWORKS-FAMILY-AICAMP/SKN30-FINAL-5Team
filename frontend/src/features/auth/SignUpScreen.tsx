import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';

import {
  Button,
  Card,
  InlineFeedback,
  TextField,
} from '../../components/primitives';
import { colors, radii, spacing } from '../../components/theme';
import type { SignUpPreviewState } from './previewStates';

export const SIGN_UP_LAYOUT = {
  headerHorizontalPadding: 20,
  contentHorizontalPadding: 20,
  footerHorizontalPadding: 20,
  footerBottomPadding: 44,
  contentGap: 14,
} as const;

type SignUpFixture = {
  userId: string;
  password: string;
  passwordConfirmation: string;
  idMessage?: string;
  idMessageTone?: 'success' | 'error';
  passwordMessage: string;
  passwordMessageTone: 'muted' | 'success' | 'error';
  confirmationMessage?: string;
  confirmationMessageTone?: 'success' | 'error';
  ready: boolean;
};

const EMPTY_PASSWORD_MESSAGE = '8자 이상, 숫자를 1개 이상 포함해주세요.';

const SIGN_UP_FIXTURES: Record<SignUpPreviewState, SignUpFixture> = {
  idle: {
    userId: '',
    password: '',
    passwordConfirmation: '',
    passwordMessage: EMPTY_PASSWORD_MESSAGE,
    passwordMessageTone: 'muted',
    ready: false,
  },
  'id-invalid': {
    userId: 'abc',
    password: '',
    passwordConfirmation: '',
    idMessage: '영문·숫자 4자 이상으로 입력해주세요.',
    idMessageTone: 'error',
    passwordMessage: EMPTY_PASSWORD_MESSAGE,
    passwordMessageTone: 'muted',
    ready: false,
  },
  'id-taken': {
    userId: 'test1234',
    password: '',
    passwordConfirmation: '',
    idMessage: '이미 사용 중인 아이디예요.',
    idMessageTone: 'error',
    passwordMessage: EMPTY_PASSWORD_MESSAGE,
    passwordMessageTone: 'muted',
    ready: false,
  },
  'id-available': {
    userId: 'prototype-user',
    password: '',
    passwordConfirmation: '',
    idMessage: '사용할 수 있는 아이디예요.',
    idMessageTone: 'success',
    passwordMessage: EMPTY_PASSWORD_MESSAGE,
    passwordMessageTone: 'muted',
    ready: false,
  },
  'password-invalid': {
    userId: 'prototype-user',
    password: 'short',
    passwordConfirmation: '',
    idMessage: '사용할 수 있는 아이디예요.',
    idMessageTone: 'success',
    passwordMessage: '8자 이상, 숫자 포함 조건을 아직 만족하지 않아요.',
    passwordMessageTone: 'error',
    ready: false,
  },
  'password-mismatch': {
    userId: 'prototype-user',
    password: 'password1',
    passwordConfirmation: 'password2',
    idMessage: '사용할 수 있는 아이디예요.',
    idMessageTone: 'success',
    passwordMessage: '사용할 수 있는 비밀번호예요.',
    passwordMessageTone: 'success',
    confirmationMessage: '비밀번호가 서로 달라요.',
    confirmationMessageTone: 'error',
    ready: false,
  },
  ready: {
    userId: 'prototype-user',
    password: 'password1',
    passwordConfirmation: 'password1',
    idMessage: '사용할 수 있는 아이디예요.',
    idMessageTone: 'success',
    passwordMessage: '사용할 수 있는 비밀번호예요.',
    passwordMessageTone: 'success',
    confirmationMessage: '비밀번호가 일치해요.',
    confirmationMessageTone: 'success',
    ready: true,
  },
  loading: {
    userId: 'prototype-user',
    password: 'password1',
    passwordConfirmation: 'password1',
    idMessage: '사용할 수 있는 아이디예요.',
    idMessageTone: 'success',
    passwordMessage: '사용할 수 있는 비밀번호예요.',
    passwordMessageTone: 'success',
    confirmationMessage: '비밀번호가 일치해요.',
    confirmationMessageTone: 'success',
    ready: true,
  },
  failed: {
    userId: 'prototype-user',
    password: 'password1',
    passwordConfirmation: 'password1',
    idMessage: '사용할 수 있는 아이디예요.',
    idMessageTone: 'success',
    passwordMessage: '사용할 수 있는 비밀번호예요.',
    passwordMessageTone: 'success',
    confirmationMessage: '비밀번호가 일치해요.',
    confirmationMessageTone: 'success',
    ready: true,
  },
};

type SignUpScreenProps = {
  onBack?: () => void;
  onCheckId?: () => void;
  onSubmit?: () => void;
  previewState?: SignUpPreviewState;
};

export function SignUpScreen({ ...props }: SignUpScreenProps) {
  return <SignUpScreenContent key={props.previewState ?? 'idle'} {...props} />;
}

function SignUpScreenContent({
  onBack,
  onCheckId,
  onSubmit,
  previewState = 'idle',
}: SignUpScreenProps) {
  const fixture = SIGN_UP_FIXTURES[previewState];
  const [userId, setUserId] = useState(fixture.userId);
  const [password, setPassword] = useState(fixture.password);
  const [passwordConfirmation, setPasswordConfirmation] = useState(
    fixture.passwordConfirmation,
  );
  const [showPassword, setShowPassword] = useState(false);
  const isLoading = previewState === 'loading';

  return (
    <SafeAreaView
      edges={['top', 'right', 'bottom', 'left']}
      style={styles.screen}
    >
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="로그인으로 돌아가기"
          onPress={onBack}
          style={styles.backButton}
        >
          <Text style={styles.backIcon}>‹</Text>
        </Pressable>
        <Text accessibilityRole="header" style={styles.headerTitle}>
          회원가입
        </Text>
        <Text style={styles.stepLabel}>1 / 2 · 계정</Text>
      </View>

      <ScrollView
        keyboardShouldPersistTaps="handled"
        style={styles.content}
        contentContainerStyle={styles.contentContainer}
      >
        <Text style={styles.intro}>
          로그인에 사용할 계정 정보만 입력해요.{`\n`}다음 단계에서 프로필을
          등록하면 가입이 마무리돼요.
        </Text>

        <Card style={styles.accountCard}>
          <Text style={styles.cardTitle}>계정 정보</Text>

          <View style={styles.fieldGroup}>
            <RequiredLabel label="아이디" />
            <View style={styles.idRow}>
              <TextField
                accessibilityLabel="회원가입 아이디"
                autoCapitalize="none"
                containerStyle={styles.idField}
                onChangeText={setUserId}
                placeholder="영문·숫자 4자 이상"
                style={[
                  styles.signupField,
                  fixture.idMessageTone === 'error' && styles.fieldError,
                ]}
                value={userId}
              />
              <Button
                label="중복확인"
                labelStyle={styles.compactButtonLabel}
                onPress={onCheckId}
                style={styles.checkButton}
                tone="secondary"
              />
            </View>
            {fixture.idMessage ? (
              <FieldMessage
                message={fixture.idMessage}
                tone={fixture.idMessageTone ?? 'error'}
              />
            ) : null}
          </View>

          <View style={styles.fieldGroup}>
            <RequiredLabel label="비밀번호" />
            <TextField
              accessibilityLabel="회원가입 비밀번호"
              onChangeText={setPassword}
              placeholder="8자 이상, 숫자 포함"
              secureTextEntry={!showPassword}
              style={[
                styles.signupField,
                fixture.passwordMessageTone === 'error' && styles.fieldError,
              ]}
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
            <FieldMessage
              message={fixture.passwordMessage}
              tone={fixture.passwordMessageTone}
            />
          </View>

          <View style={styles.fieldGroup}>
            <RequiredLabel label="비밀번호 확인" />
            <TextField
              accessibilityLabel="회원가입 비밀번호 확인"
              onChangeText={setPasswordConfirmation}
              placeholder="한 번 더 입력해주세요"
              secureTextEntry={!showPassword}
              style={[
                styles.signupField,
                fixture.confirmationMessageTone === 'error' &&
                  styles.fieldError,
              ]}
              value={passwordConfirmation}
            />
            {fixture.confirmationMessage ? (
              <FieldMessage
                message={fixture.confirmationMessage}
                tone={fixture.confirmationMessageTone ?? 'error'}
              />
            ) : null}
          </View>

          <Text style={styles.requiredHint}>
            <Text style={styles.requiredMark}>*</Text> 표시는 필수 입력
            항목이에요.
          </Text>
        </Card>

        {previewState === 'failed' ? (
          <InlineFeedback
            action={
              <Button
                label="다시 시도"
                labelStyle={styles.feedbackActionLabel}
                onPress={onSubmit}
                style={styles.feedbackAction}
                tone="secondary"
              />
            }
            message="회원가입에 실패했어요. 잠시 후 다시 시도해주세요."
            tone="error"
          />
        ) : null}

        <Text style={styles.profileNotice}>
          가입 후 키·체중 등 필수 프로필을 등록해야 홈을 이용할 수 있어요.
        </Text>
      </ScrollView>

      <View style={styles.footer}>
        <Button
          disabled={!fixture.ready || isLoading}
          label={
            isLoading
              ? '가입 처리 중...'
              : fixture.ready
                ? '가입하고 프로필 등록하기'
                : '필수 항목을 채워주세요'
          }
          labelStyle={isLoading ? styles.loadingButtonLabel : undefined}
          leading={
            isLoading ? (
              <ActivityIndicator color={colors.surface} size="small" />
            ) : undefined
          }
          onPress={onSubmit}
          style={[styles.submitButton, isLoading && styles.loadingButton]}
        />
        <Pressable
          accessibilityRole="button"
          onPress={onBack}
          style={styles.loginLink}
        >
          <Text style={styles.loginLinkLabel}>
            이미 계정이 있어요 · 로그인으로
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

function RequiredLabel({ label }: { label: string }) {
  return (
    <View style={styles.requiredLabelRow}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <Text style={styles.requiredMark}>*</Text>
    </View>
  );
}

function FieldMessage({
  message,
  tone,
}: {
  message: string;
  tone: 'muted' | 'success' | 'error';
}) {
  return (
    <Text
      accessibilityRole={tone === 'error' ? 'alert' : undefined}
      style={[styles.fieldMessage, fieldMessageStyles[tone]]}
    >
      {message}
    </Text>
  );
}

const fieldMessageStyles = StyleSheet.create({
  muted: { color: '#A8A49C' },
  success: { color: colors.primary },
  error: { color: colors.fieldError },
});

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: colors.canvas,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingTop: spacing.xl,
    paddingHorizontal: SIGN_UP_LAYOUT.headerHorizontalPadding,
    paddingBottom: spacing.md,
  },
  backButton: {
    width: 34,
    height: 34,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 17,
    backgroundColor: colors.surface,
  },
  backIcon: {
    color: colors.text,
    fontSize: 30,
    lineHeight: 32,
  },
  headerTitle: {
    flex: 1,
    color: colors.text,
    fontSize: 17,
    fontWeight: '700',
  },
  stepLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  content: {
    flex: 1,
  },
  contentContainer: {
    gap: SIGN_UP_LAYOUT.contentGap,
    paddingTop: spacing.xs,
    paddingHorizontal: SIGN_UP_LAYOUT.contentHorizontalPadding,
    paddingBottom: 20,
  },
  intro: {
    color: colors.textMuted,
    fontSize: 14,
    lineHeight: 22,
  },
  accountCard: {
    gap: spacing.lg,
  },
  cardTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
  },
  fieldGroup: {
    gap: 6,
  },
  requiredLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  fieldLabel: {
    color: colors.textMuted,
    fontSize: 13,
    fontWeight: '600',
  },
  requiredMark: {
    color: colors.fieldError,
    fontSize: 13,
    fontWeight: '700',
  },
  idRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  idField: {
    flex: 1,
  },
  signupField: {
    backgroundColor: colors.canvas,
    paddingHorizontal: 14,
  },
  fieldError: {
    borderColor: colors.fieldError,
  },
  checkButton: {
    minHeight: 48,
    borderColor: colors.primary,
    borderRadius: radii.control,
    paddingHorizontal: 14,
  },
  compactButtonLabel: {
    color: colors.primary,
    fontSize: 13,
  },
  passwordToggle: {
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: 2,
  },
  passwordToggleLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  fieldMessage: {
    fontSize: 12,
    lineHeight: 18,
  },
  requiredHint: {
    color: '#A8A49C',
    fontSize: 12,
    lineHeight: 18,
  },
  profileNotice: {
    color: colors.textMuted,
    fontSize: 12.5,
    lineHeight: 19,
  },
  footer: {
    gap: 10,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.canvas,
    paddingTop: 14,
    paddingHorizontal: SIGN_UP_LAYOUT.footerHorizontalPadding,
    paddingBottom: SIGN_UP_LAYOUT.footerBottomPadding,
  },
  submitButton: {
    minHeight: 52,
    borderRadius: radii.card,
  },
  loadingButton: {
    backgroundColor: colors.primaryBusy,
  },
  loadingButtonLabel: {
    color: colors.surface,
  },
  loginLink: {
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loginLinkLabel: {
    color: colors.textMuted,
    fontSize: 13,
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
});
