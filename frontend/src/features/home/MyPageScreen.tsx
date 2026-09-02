import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { experienceLevelLabel, primaryGoalLabel } from '../../api/labels';
import type {
  ConsentValues,
  MeResponse,
  ProfileSettingsUpdateRequest,
} from '../../api/types';
import { Button, Card, InlineFeedback } from '../../components/primitives';
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from '../../components/states/ScreenState';
import { colors } from '../../components/theme';
import type { TabId } from '../../components/brand/BrandChrome';
import { ProfileAvatar } from '../../components/profile/ProfileAvatar';
import { HomeBottomNavigation } from './HomeScreen';
import {
  MY_PAGE_ACCOUNT_ROWS,
  MY_PAGE_PROFILE_ROWS,
  type MyPagePreviewState,
} from './homeSecondaryModel';
import { ONBOARDING_COACHING_STYLE_OPTIONS } from '../onboarding/onboardingOptions';
import { buildMyPageProfileRows } from './myPageModel';
import {
  MyPageProfileEditor,
  type MyPageEditableField,
  type ProfileImageChange,
} from './MyPageProfileEditor';

export const MY_PAGE_LAYOUT = {
  contentTopPadding: 58,
  contentHorizontalPadding: 16,
  contentBottomPadding: 18,
  sectionGap: 14,
} as const;

type MyPageScreenProps = {
  coachingStyleError?: string | null;
  coachingStylePending?: boolean;
  consentError?: string | null;
  consentPending?: boolean;
  consentValues?: ConsentValues | null;
  deletionDeadline?: string | null;
  joinedDays?: number | null;
  me?: MeResponse;
  onAccountAction?: (label: string) => void;
  onCoachingStyleChange?: (code: string) => void;
  onConfirmLogout?: () => void;
  onConfirmWithdraw?: () => void;
  onConsentChange?: (key: keyof ConsentValues, enabled: boolean) => void;
  onNavigateTab?: (tab: TabId) => void;
  onNotificationChange?: (key: string, enabled: boolean) => void;
  onOpenExerciseCatalog?: () => void;
  onBasicProfileChange?: (
    body: ProfileSettingsUpdateRequest,
    imageChange: ProfileImageChange | undefined,
  ) => void;
  onProfileFieldChange?: (body: ProfileSettingsUpdateRequest) => void;
  onRetryProfile?: () => void;
  onRetryConsents?: () => void;
  persistedSettingsAvailable?: boolean;
  previewState?: MyPagePreviewState;
  profileUpdateError?: string | null;
  profileUpdatePending?: boolean;
  withdrawalError?: string | null;
  withdrawalPending?: boolean;
};

export function MyPageScreen({
  previewState = 'profile',
  ...props
}: MyPageScreenProps) {
  return (
    <MyPageContent key={previewState} {...props} previewState={previewState} />
  );
}

function MyPageContent({
  coachingStyleError = null,
  coachingStylePending = false,
  consentError = null,
  consentPending = false,
  consentValues = null,
  deletionDeadline = null,
  joinedDays = null,
  me,
  onAccountAction,
  onCoachingStyleChange,
  onConfirmLogout,
  onConfirmWithdraw,
  onConsentChange,
  onNavigateTab,
  onNotificationChange,
  onOpenExerciseCatalog,
  onBasicProfileChange,
  onProfileFieldChange,
  onRetryProfile,
  onRetryConsents,
  persistedSettingsAvailable = true,
  previewState = 'profile',
  profileUpdateError = null,
  profileUpdatePending = false,
  withdrawalError = null,
  withdrawalPending = false,
}: MyPageScreenProps) {
  const [previewCoachStyleCode, setPreviewCoachStyleCode] =
    useState('SUPPORTIVE');
  const [editingField, setEditingField] = useState<MyPageEditableField | null>(
    null,
  );
  const [dialog, setDialog] = useState<'logout' | 'withdraw' | null>(
    previewState === 'logout'
      ? 'logout'
      : previewState === 'withdraw'
        ? 'withdraw'
        : null,
  );
  const [notifications, setNotifications] = useState({
    routine: true,
    report: true,
    encouragement: false,
  });
  const profile = me?.profile ?? null;
  const apiBacked = me !== undefined;
  const coachStyleCode = profile?.coaching_style_code ?? previewCoachStyleCode;
  const profileRows = profile
    ? buildMyPageProfileRows(profile)
    : MY_PAGE_PROFILE_ROWS;
  const nickname = profile?.nickname ?? '헬끼';
  const profileTags = profile
    ? [
        primaryGoalLabel(profile.primary_goal_code),
        experienceLevelLabel(profile.experience_level_code),
        `주 ${profile.desired_weekly_workout_count}회`,
      ]
    : ['체력 증진', '초급', '주 4회'];
  const visibleDialog =
    dialog === 'withdraw' && deletionDeadline !== null ? null : dialog;
  const pageState =
    previewState === 'loading' ||
    previewState === 'empty' ||
    previewState === 'error' ||
    previewState === 'permission'
      ? previewState
      : profile === null && apiBacked
        ? 'empty'
        : 'profile';

  const toggleNotification = (key: keyof typeof notifications) => {
    const enabled = !notifications[key];
    setNotifications((current) => ({ ...current, [key]: enabled }));
    onNotificationChange?.(key, enabled);
  };

  if (pageState !== 'profile') {
    return (
      <SafeAreaView edges={['left', 'right']} style={styles.screen}>
        <StatusBar style="dark" />
        <View style={[styles.content, styles.stateContent]}>
          <Text accessibilityRole="header" style={styles.title}>
            마이페이지
          </Text>
          {pageState === 'loading' ? (
            <LoadingState label="프로필 정보를 불러오고 있어요" />
          ) : pageState === 'empty' ? (
            <EmptyState
              actionLabel={onRetryProfile ? '다시 불러오기' : undefined}
              message="아직 등록된 프로필 정보가 없어요."
              onAction={onRetryProfile}
            />
          ) : pageState === 'permission' ? (
            <ErrorState message="이 계정으로는 프로필 정보에 접근할 수 없어요." />
          ) : (
            <ErrorState
              message="프로필 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요."
              onRetry={onRetryProfile}
            />
          )}
        </View>
        <HomeBottomNavigation activeTab="my" onNavigate={onNavigateTab} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={['left', 'right']} style={styles.screen}>
      <StatusBar style="dark" />
      <ScrollView
        showsVerticalScrollIndicator={false}
        style={styles.scroll}
        contentContainerStyle={styles.content}
      >
        <View style={styles.header}>
          <Text accessibilityRole="header" style={styles.title}>
            마이페이지
          </Text>
        </View>

        <Card style={styles.profileCard}>
          <View style={styles.profileRow}>
            <ProfileAvatar
              accessibilityLabel={`${nickname}님의 프로필 이미지`}
              profileImageUrl={profile?.profile_image_url}
              size={64}
              style={styles.avatar}
              testID="my-page-profile-avatar"
            />
            <View style={styles.profileCopy}>
              <Text style={styles.nickname}>{nickname}님</Text>
              <Text style={styles.joinLine}>
                {joinedDays === null
                  ? apiBacked
                    ? '가입 정보를 확인하고 있어요'
                    : '함께한 지 7일째'
                  : `함께한 지 ${joinedDays}일째`}
              </Text>
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{
                disabled:
                  onProfileFieldChange === undefined &&
                  onBasicProfileChange === undefined,
              }}
              disabled={
                onProfileFieldChange === undefined &&
                onBasicProfileChange === undefined
              }
              onPress={() => setEditingField('basic_profile')}
              style={styles.editProfileButton}
            >
              <Text style={styles.editProfileLabel}>프로필 수정</Text>
            </Pressable>
          </View>
          <View style={styles.tags}>
            {profileTags.map((tag) => (
              <View key={tag} style={styles.tag}>
                <Text style={styles.tagText}>{tag}</Text>
              </View>
            ))}
          </View>
        </Card>

        <View style={styles.coachCard}>
          <Text style={styles.coachTitle}>헬끼 코칭 스타일</Text>
          <Text style={styles.coachNote}>
            원하는 방식으로 운동을 안내해드려요.
          </Text>
          <View style={styles.coachOptions}>
            {ONBOARDING_COACHING_STYLE_OPTIONS.map((option) => {
              const selected = option.code === coachStyleCode;
              return (
                <Pressable
                  key={option.code}
                  accessibilityRole="button"
                  accessibilityState={{
                    selected,
                    disabled: coachingStylePending,
                  }}
                  disabled={coachingStylePending}
                  onPress={() => {
                    if (onCoachingStyleChange) {
                      onCoachingStyleChange(option.code);
                    } else {
                      setPreviewCoachStyleCode(option.code);
                    }
                  }}
                  style={[
                    styles.coachOption,
                    selected && styles.coachOptionSelected,
                  ]}
                >
                  <Text
                    style={[
                      styles.coachOptionText,
                      selected && styles.coachOptionTextSelected,
                    ]}
                  >
                    {option.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        {coachingStyleError ? (
          <InlineFeedback
            message={coachingStyleError}
            style={styles.feedback}
            tone="error"
          />
        ) : null}

        <SectionTitle label="내 운동 정보" />
        <View style={styles.rowsCard}>
          {profileRows.map(([field, label, value]) => (
            <Pressable
              key={field}
              accessibilityRole="button"
              accessibilityLabel={`${label} 수정`}
              accessibilityState={{
                disabled: onProfileFieldChange === undefined,
              }}
              disabled={onProfileFieldChange === undefined}
              onPress={() => setEditingField(field)}
              style={styles.infoRow}
            >
              <Text style={styles.infoLabel}>{label}</Text>
              <Text style={styles.infoValue}>{value}</Text>
              <Text style={styles.rowArrow}>›</Text>
            </Pressable>
          ))}
        </View>

        {onOpenExerciseCatalog ? (
          <>
            <SectionTitle label="운동 도구" />
            <View style={styles.rowsCard}>
              <Pressable
                accessibilityRole="button"
                onPress={onOpenExerciseCatalog}
                style={styles.infoRow}
              >
                <Text style={styles.infoLabel}>운동 카탈로그</Text>
                <Text style={styles.infoValue}>둘러보기</Text>
                <Text style={styles.rowArrow}>›</Text>
              </Pressable>
            </View>
          </>
        ) : null}

        <SectionTitle label="알림" />
        <View style={styles.rowsCard}>
          <NotificationRow
            comingSoon={!persistedSettingsAvailable}
            description="예정된 운동 시간을 알려드려요."
            enabled={notifications.routine}
            label="루틴 알림"
            disabled={!persistedSettingsAvailable}
            onToggle={() => toggleNotification('routine')}
          />
          <NotificationRow
            comingSoon={!persistedSettingsAvailable}
            description="이번 주 운동 리포트가 준비되면 알려드려요."
            enabled={notifications.report}
            label="주간 리포트"
            disabled={!persistedSettingsAvailable}
            onToggle={() => toggleNotification('report')}
          />
          <NotificationRow
            comingSoon={!persistedSettingsAvailable}
            description="휴식일에는 알림을 보내지 않아요."
            enabled={notifications.encouragement}
            label="응원 알림"
            disabled={!persistedSettingsAvailable}
            onToggle={() => toggleNotification('encouragement')}
          />
        </View>

        {!persistedSettingsAvailable ? (
          <InlineFeedback
            message="알림과 기기 연동 기능은 준비 중이에요."
            style={styles.feedback}
            tone="warning"
          />
        ) : null}

        <SectionTitle label="선택 동의 관리" />
        <View style={styles.rowsCard}>
          <Text style={styles.consentNote}>
            필수 동의 항목은 여기에서 변경할 수 없어요.
          </Text>
          {consentValues ? (
            OPTIONAL_CONSENTS.map(({ key, label }) => (
              <NotificationRow
                key={key}
                description=""
                disabled={consentPending}
                enabled={consentValues[key]}
                label={label}
                onToggle={() => onConsentChange?.(key, !consentValues[key])}
              />
            ))
          ) : consentError ? (
            <InlineFeedback
              action={
                onRetryConsents ? (
                  <Button
                    label="다시 시도"
                    onPress={onRetryConsents}
                    tone="secondary"
                  />
                ) : undefined
              }
              message={consentError}
              tone="error"
            />
          ) : (
            <Text style={styles.consentNote}>동의 정보를 불러오고 있어요…</Text>
          )}
          {consentValues && consentError ? (
            <InlineFeedback message={consentError} tone="error" />
          ) : null}
          {consentPending && consentValues ? (
            <Text style={styles.consentNote}>저장 중…</Text>
          ) : null}
        </View>

        <SectionTitle label="계정 · 앱" />
        <View style={styles.rowsCard}>
          {MY_PAGE_ACCOUNT_ROWS.map(([label, value]) => (
            <Pressable
              key={label}
              accessibilityRole="button"
              accessibilityState={{ disabled: onAccountAction === undefined }}
              disabled={onAccountAction === undefined}
              onPress={() => onAccountAction?.(label)}
              style={styles.accountRow}
            >
              <Text style={styles.accountLabel}>{label}</Text>
              <Text style={styles.accountValue}>
                {!persistedSettingsAvailable && label === '연동 기기'
                  ? '준비 중'
                  : value}
              </Text>
              <Text style={styles.rowArrow}>›</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.accountActions}>
          <Pressable
            accessibilityRole="button"
            onPress={() => setDialog('logout')}
            style={styles.logoutAction}
          >
            <Text style={styles.logoutText}>로그아웃</Text>
          </Pressable>
          {/* Withdrawal is irreversible, so it never sits beside logout. */}
          {deletionDeadline === null ? (
            <Pressable
              accessibilityRole="button"
              onPress={() => setDialog('withdraw')}
              style={styles.withdrawAction}
            >
              <Text style={styles.withdrawText}>회원 탈퇴</Text>
              <Text style={styles.withdrawHint}>
                운동 기록이 모두 삭제되고 되돌릴 수 없어요.
              </Text>
            </Pressable>
          ) : null}
        </View>

        {deletionDeadline ? (
          <InlineFeedback
            message={`계정 삭제를 접수했어요. 운영 데이터는 ${deletionDeadline.slice(0, 10)}까지 삭제돼요.`}
            style={styles.deletionFeedback}
            tone="warning"
          />
        ) : null}
      </ScrollView>

      <HomeBottomNavigation activeTab="my" onNavigate={onNavigateTab} />

      {visibleDialog ? (
        <ConfirmationDialog
          kind={visibleDialog}
          onCancel={() => setDialog(null)}
          error={visibleDialog === 'withdraw' ? withdrawalError : null}
          pending={visibleDialog === 'withdraw' && withdrawalPending}
          onConfirm={() => {
            if (visibleDialog === 'logout') onConfirmLogout?.();
            else onConfirmWithdraw?.();
          }}
        />
      ) : null}

      {editingField &&
      profile &&
      (onProfileFieldChange ||
        (editingField === 'basic_profile' && onBasicProfileChange)) ? (
        <MyPageProfileEditor
          error={profileUpdateError}
          field={editingField}
          onBasicProfileChange={onBasicProfileChange}
          onChange={onProfileFieldChange ?? (() => undefined)}
          onClose={() => setEditingField(null)}
          pending={profileUpdatePending}
          profile={profile}
        />
      ) : null}
    </SafeAreaView>
  );
}

function SectionTitle({ label }: { label: string }) {
  return <Text style={styles.sectionTitle}>{label}</Text>;
}

function NotificationRow({
  comingSoon = false,
  description,
  disabled = false,
  enabled,
  label,
  onToggle,
}: {
  comingSoon?: boolean;
  description: string;
  disabled?: boolean;
  enabled: boolean;
  label: string;
  onToggle: () => void;
}) {
  // A switch that cannot be saved yet must not look switched on.
  const checked = comingSoon ? false : enabled;

  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityState={{ checked, disabled }}
      disabled={disabled}
      onPress={onToggle}
      style={styles.notificationRow}
    >
      <View style={styles.notificationCopy}>
        <View style={styles.notificationLabelRow}>
          <Text style={styles.notificationLabel}>{label}</Text>
          {comingSoon ? (
            <View style={styles.comingSoonBadge}>
              <Text style={styles.comingSoonBadgeText}>준비 중</Text>
            </View>
          ) : null}
        </View>
        {description ? (
          <Text style={styles.notificationDescription}>{description}</Text>
        ) : null}
      </View>
      <View
        style={[
          styles.switchTrack,
          checked && styles.switchTrackOn,
          disabled && styles.switchTrackDisabled,
        ]}
      >
        <View style={[styles.switchKnob, checked && styles.switchKnobOn]} />
      </View>
    </Pressable>
  );
}

function ConfirmationDialog({
  error,
  kind,
  onCancel,
  onConfirm,
  pending,
}: {
  error?: string | null;
  kind: 'logout' | 'withdraw';
  onCancel: () => void;
  onConfirm: () => void;
  pending?: boolean;
}) {
  const withdrawing = kind === 'withdraw';

  return (
    <View accessibilityViewIsModal style={styles.dialogOverlay}>
      <Card style={styles.dialogCard}>
        <Text accessibilityRole="header" style={styles.dialogTitle}>
          {withdrawing ? '회원 탈퇴할까요?' : '로그아웃할까요?'}
        </Text>
        <Text style={styles.dialogMessage}>
          {withdrawing
            ? '탈퇴하면 운동 기록과 헬끼와의 대화가 모두 삭제되고 되돌릴 수 없어요.'
            : '이 기기에서 계정 연결을 종료하고 로그인 화면으로 이동해요.'}
        </Text>
        {error ? <InlineFeedback message={error} tone="error" /> : null}
        <View style={styles.dialogActions}>
          <Button
            disabled={pending}
            label={pending ? '요청 중…' : withdrawing ? '탈퇴하기' : '로그아웃'}
            labelStyle={withdrawing ? styles.dangerLabel : undefined}
            onPress={onConfirm}
            style={withdrawing ? styles.dangerButton : undefined}
            tone={withdrawing ? 'secondary' : 'primary'}
          />
          <Button
            disabled={pending}
            label="취소"
            onPress={onCancel}
            tone="secondary"
          />
        </View>
      </Card>
    </View>
  );
}

const OPTIONAL_CONSENTS = [
  { key: 'wearable_integration', label: '웨어러블 연동' },
  { key: 'marketing', label: '마케팅 정보 수신' },
] as const satisfies readonly {
  key: keyof ConsentValues;
  label: string;
}[];

const shadow = {
  shadowColor: '#5A4636',
  shadowOffset: { width: 0, height: 4 },
  shadowOpacity: 0.08,
  shadowRadius: 6,
  elevation: 2,
} as const;

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: colors.canvas,
  },
  scroll: {
    flex: 1,
  },
  content: {
    paddingTop: MY_PAGE_LAYOUT.contentTopPadding,
    paddingHorizontal: MY_PAGE_LAYOUT.contentHorizontalPadding,
    paddingBottom: MY_PAGE_LAYOUT.contentBottomPadding,
  },
  stateContent: {
    flex: 1,
    gap: 18,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
    paddingBottom: 14,
  },
  title: {
    color: colors.text,
    fontSize: 22,
    fontWeight: '800',
  },
  profileCard: {
    ...shadow,
    borderRadius: 22,
    paddingHorizontal: 16,
    paddingTop: 18,
    paddingBottom: 16,
  },
  profileRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#FFF8E5',
  },
  profileCopy: {
    minWidth: 0,
    flex: 1,
  },
  nickname: {
    color: colors.text,
    fontSize: 19,
    fontWeight: '800',
  },
  joinLine: {
    marginTop: 3,
    color: colors.textMuted,
    fontSize: 12.5,
    fontWeight: '600',
  },
  editProfileButton: {
    minHeight: 44,
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: '#E2DED4',
    borderRadius: 12,
    backgroundColor: colors.surface,
    paddingHorizontal: 12,
  },
  editProfileLabel: {
    color: '#A45F00',
    fontSize: 12.5,
    fontWeight: '800',
  },
  tags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 14,
  },
  tag: {
    borderWidth: 1.5,
    borderColor: '#F1D39A',
    borderRadius: 999,
    backgroundColor: '#FFF8E5',
    paddingHorizontal: 11,
    paddingVertical: 6,
  },
  tagText: {
    color: '#A45F00',
    fontSize: 11.5,
    fontWeight: '800',
  },
  feedback: {
    marginTop: 10,
  },
  consentNote: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  coachCard: {
    marginTop: MY_PAGE_LAYOUT.sectionGap,
    borderRadius: 20,
    backgroundColor: '#FFEBC2',
    paddingHorizontal: 14,
    paddingTop: 14,
    paddingBottom: 16,
  },
  coachTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
  },
  coachNote: {
    marginTop: 8,
    color: '#4A5B44',
    fontSize: 12.5,
    lineHeight: 19,
  },
  coachOptions: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 12,
  },
  coachOption: {
    minHeight: 38,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: '#F1D39A',
    borderRadius: 12,
    backgroundColor: colors.surface,
    paddingHorizontal: 4,
  },
  coachOptionSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.primary,
  },
  coachOptionText: {
    color: '#A45F00',
    fontSize: 12,
    fontWeight: '700',
  },
  coachOptionTextSelected: {
    color: colors.text,
  },
  sectionTitle: {
    marginTop: 16,
    paddingHorizontal: 6,
    paddingBottom: 8,
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.2,
  },
  rowsCard: {
    ...shadow,
    borderRadius: 20,
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
  },
  infoRow: {
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#F0EDE5',
    paddingVertical: 12,
  },
  infoLabel: {
    color: colors.textMuted,
    fontSize: 13,
    fontWeight: '600',
  },
  infoValue: {
    flex: 1,
    color: colors.text,
    fontSize: 13.5,
    fontWeight: '700',
    textAlign: 'right',
  },
  rowArrow: {
    color: '#C0BBB1',
    fontSize: 22,
  },
  notificationRow: {
    minHeight: 64,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#F0EDE5',
    paddingVertical: 12,
  },
  notificationCopy: {
    minWidth: 0,
    flex: 1,
  },
  notificationLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  notificationLabel: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  comingSoonBadge: {
    borderRadius: 999,
    backgroundColor: '#EDEAE2',
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  comingSoonBadgeText: {
    color: colors.textMuted,
    fontSize: 10.5,
    fontWeight: '700',
  },
  notificationDescription: {
    marginTop: 2,
    color: colors.textMuted,
    fontSize: 11.5,
    lineHeight: 17,
  },
  switchTrack: {
    width: 46,
    height: 26,
    justifyContent: 'center',
    borderRadius: 13,
    backgroundColor: '#D8D4CC',
    paddingHorizontal: 3,
  },
  switchTrackOn: {
    backgroundColor: '#F6BA50',
  },
  switchTrackDisabled: {
    opacity: 0.45,
  },
  switchKnob: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.surface,
  },
  switchKnobOn: {
    alignSelf: 'flex-end',
  },
  accountRow: {
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#F0EDE5',
    paddingVertical: 12,
  },
  accountLabel: {
    flex: 1,
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  accountValue: {
    color: '#A8A49C',
    fontSize: 12.5,
    fontWeight: '600',
  },
  accountActions: {
    alignItems: 'center',
    gap: 14,
    paddingTop: 14,
    paddingBottom: 8,
  },
  deletionFeedback: {
    marginBottom: 12,
  },
  logoutAction: {
    minHeight: 44,
    alignSelf: 'stretch',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: '#E2DED4',
    borderRadius: 14,
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
  },
  logoutText: {
    color: colors.textSub,
    fontSize: 13.5,
    fontWeight: '700',
  },
  withdrawAction: {
    minHeight: 44,
    alignSelf: 'stretch',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
    borderTopWidth: 1,
    borderTopColor: '#E2DED4',
    paddingTop: 14,
    paddingHorizontal: 16,
  },
  withdrawText: {
    color: colors.dangerText,
    fontSize: 12.5,
    fontWeight: '800',
    textDecorationLine: 'underline',
  },
  withdrawHint: {
    color: colors.textMuted,
    fontSize: 11,
    lineHeight: 16,
    textAlign: 'center',
  },
  dialogOverlay: {
    position: 'absolute',
    zIndex: 30,
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(20,28,16,0.5)',
    padding: 26,
  },
  dialogCard: {
    width: '100%',
    gap: 10,
    borderRadius: 20,
    backgroundColor: colors.canvas,
    padding: 22,
  },
  dialogTitle: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '800',
  },
  dialogMessage: {
    color: colors.textMuted,
    fontSize: 13.5,
    lineHeight: 21,
  },
  dialogActions: {
    gap: 8,
    marginTop: 6,
  },
  dangerButton: {
    borderColor: colors.dangerText,
  },
  dangerLabel: {
    color: colors.dangerText,
  },
});
