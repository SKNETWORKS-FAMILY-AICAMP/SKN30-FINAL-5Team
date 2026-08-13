import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button, Card } from '../../components/primitives';
import { colors } from '../../components/theme';
import { fontFamilies, useBrandFonts } from '../../app/fonts';
import { HomeBottomNavigation } from './HomeScreen';
import {
  MY_PAGE_ACCOUNT_ROWS,
  MY_PAGE_PROFILE_ROWS,
  type MyPagePreviewState,
} from './homeSecondaryModel';

export const MY_PAGE_LAYOUT = {
  contentTopPadding: 58,
  contentHorizontalPadding: 16,
  contentBottomPadding: 18,
  sectionGap: 14,
} as const;

type MyPageScreenProps = {
  onAccountAction?: (label: string) => void;
  onConfirmLogout?: () => void;
  onConfirmWithdraw?: () => void;
  onEditProfile?: (row?: string) => void;
  onNavigateTab?: (tab: 'home' | 'log' | 'report' | 'my') => void;
  onNotificationChange?: (key: string, enabled: boolean) => void;
  onOpenSettings?: () => void;
  previewState?: MyPagePreviewState;
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
  onAccountAction,
  onConfirmLogout,
  onConfirmWithdraw,
  onEditProfile,
  onNavigateTab,
  onNotificationChange,
  onOpenSettings,
  previewState = 'profile',
}: MyPageScreenProps) {
  const fonts = useBrandFonts();
  const [coachStyle, setCoachStyle] = useState('든든하게');
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
  const useJua = fonts.loaded && !fonts.failed;

  const toggleNotification = (key: keyof typeof notifications) => {
    const enabled = !notifications[key];
    setNotifications((current) => ({ ...current, [key]: enabled }));
    onNotificationChange?.(key, enabled);
  };

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
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="설정 열기"
            onPress={onOpenSettings}
            style={styles.settingsButton}
          >
            <Text style={styles.settingsIcon}>⚙</Text>
          </Pressable>
        </View>

        <Card style={styles.profileCard}>
          <View style={styles.profileRow}>
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>헬</Text>
            </View>
            <View style={styles.profileCopy}>
              <Text style={styles.nickname}>헬끼님</Text>
              <Text style={styles.joinLine}>함께한 지 7일째</Text>
            </View>
            <Pressable
              accessibilityRole="button"
              onPress={() => onEditProfile?.()}
              style={styles.editProfileButton}
            >
              <Text style={styles.editProfileLabel}>프로필 수정</Text>
            </Pressable>
          </View>
          <View style={styles.tags}>
            {['체력 향상', '초보', '주 4회'].map((tag) => (
              <View key={tag} style={styles.tag}>
                <Text style={styles.tagText}>{tag}</Text>
              </View>
            ))}
          </View>
        </Card>

        <View style={styles.statsRow}>
          <Stat label="완료 운동" value="6" useJua={useJua} />
          <Stat label="연속 기록" value="3일" useJua={useJua} />
          <Stat label="이번 주" value="2/4" useJua={useJua} />
        </View>

        <View style={styles.coachCard}>
          <View style={styles.coachHeader}>
            <Text style={styles.coachTitle}>헬끼 코칭 스타일</Text>
            <View style={styles.coachBadge}>
              <Text style={styles.coachBadgeText}>{coachStyle}</Text>
            </View>
          </View>
          <Text style={styles.coachNote}>{getCoachNote(coachStyle)}</Text>
          <View style={styles.coachOptions}>
            {['차분하게', '든든하게', '강하게'].map((option) => {
              const selected = option === coachStyle;
              return (
                <Pressable
                  key={option}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  onPress={() => setCoachStyle(option)}
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
                    {option}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <SectionTitle label="내 운동 정보" />
        <View style={styles.rowsCard}>
          {MY_PAGE_PROFILE_ROWS.map(([label, value]) => (
            <Pressable
              key={label}
              accessibilityRole="button"
              accessibilityLabel={`${label} 수정`}
              onPress={() => onEditProfile?.(label)}
              style={styles.infoRow}
            >
              <Text style={styles.infoLabel}>{label}</Text>
              <Text style={styles.infoValue}>{value}</Text>
              <Text style={styles.rowArrow}>›</Text>
            </Pressable>
          ))}
        </View>

        <SectionTitle label="알림" />
        <View style={styles.rowsCard}>
          <NotificationRow
            description="예정한 운동 시간을 알려드려요."
            enabled={notifications.routine}
            label="루틴 알림"
            onToggle={() => toggleNotification('routine')}
          />
          <NotificationRow
            description="닫힌 주 리포트가 준비되면 알려드려요."
            enabled={notifications.report}
            label="주간 리포트"
            onToggle={() => toggleNotification('report')}
          />
          <NotificationRow
            description="휴식을 선택한 날에는 압박 알림을 보내지 않아요."
            enabled={notifications.encouragement}
            label="응원 알림"
            onToggle={() => toggleNotification('encouragement')}
          />
        </View>

        <SectionTitle label="계정 · 앱" />
        <View style={styles.rowsCard}>
          {MY_PAGE_ACCOUNT_ROWS.map(([label, value]) => (
            <Pressable
              key={label}
              accessibilityRole="button"
              onPress={() => onAccountAction?.(label)}
              style={styles.accountRow}
            >
              <Text style={styles.accountLabel}>{label}</Text>
              <Text style={styles.accountValue}>{value}</Text>
              <Text style={styles.rowArrow}>›</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.accountActions}>
          <Pressable
            accessibilityRole="button"
            onPress={() => setDialog('logout')}
            style={styles.textAction}
          >
            <Text style={styles.logoutText}>로그아웃</Text>
          </Pressable>
          <View style={styles.divider} />
          <Pressable
            accessibilityRole="button"
            onPress={() => setDialog('withdraw')}
            style={styles.textAction}
          >
            <Text style={styles.withdrawText}>회원 탈퇴</Text>
          </Pressable>
        </View>
      </ScrollView>

      <HomeBottomNavigation activeTab="my" onNavigate={onNavigateTab} />

      {dialog ? (
        <ConfirmationDialog
          kind={dialog}
          onCancel={() => setDialog(null)}
          onConfirm={() => {
            if (dialog === 'logout') onConfirmLogout?.();
            else onConfirmWithdraw?.();
          }}
        />
      ) : null}
    </SafeAreaView>
  );
}

function Stat({
  label,
  useJua,
  value,
}: {
  label: string;
  useJua: boolean;
  value: string;
}) {
  return (
    <View style={styles.statCard}>
      <Text style={[styles.statValue, useJua && styles.jua]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function SectionTitle({ label }: { label: string }) {
  return <Text style={styles.sectionTitle}>{label}</Text>;
}

function NotificationRow({
  description,
  enabled,
  label,
  onToggle,
}: {
  description: string;
  enabled: boolean;
  label: string;
  onToggle: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityState={{ checked: enabled }}
      onPress={onToggle}
      style={styles.notificationRow}
    >
      <View style={styles.notificationCopy}>
        <Text style={styles.notificationLabel}>{label}</Text>
        <Text style={styles.notificationDescription}>{description}</Text>
      </View>
      <View style={[styles.switchTrack, enabled && styles.switchTrackOn]}>
        <View style={[styles.switchKnob, enabled && styles.switchKnobOn]} />
      </View>
    </Pressable>
  );
}

function ConfirmationDialog({
  kind,
  onCancel,
  onConfirm,
}: {
  kind: 'logout' | 'withdraw';
  onCancel: () => void;
  onConfirm: () => void;
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
        <View style={styles.dialogActions}>
          <Button
            label={withdrawing ? '탈퇴하기' : '로그아웃'}
            labelStyle={withdrawing ? styles.dangerLabel : undefined}
            onPress={onConfirm}
            style={withdrawing ? styles.dangerButton : undefined}
            tone={withdrawing ? 'secondary' : 'primary'}
          />
          <Button label="취소" onPress={onCancel} tone="secondary" />
        </View>
      </Card>
    </View>
  );
}

function getCoachNote(style: string) {
  return {
    차분하게: '짧고 차분한 문장으로 오늘 할 일을 안내해요.',
    든든하게: '부담을 주지 않으면서 꾸준히 이어갈 수 있도록 응원해요.',
    강하게: '에너지 있는 표현으로 운동 시작을 북돋아요.',
  }[style];
}

const shadow = {
  shadowColor: '#2F5233',
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
  settingsButton: {
    ...shadow,
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 14,
    backgroundColor: '#FBF6DF',
  },
  settingsIcon: {
    color: colors.text,
    fontSize: 20,
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
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 32,
    backgroundColor: '#F1F6E7',
  },
  avatarText: {
    color: '#3E7A32',
    fontSize: 22,
    fontWeight: '900',
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
    color: '#3E7A32',
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
    borderColor: '#CBDDB4',
    borderRadius: 999,
    backgroundColor: '#F1F6E7',
    paddingHorizontal: 11,
    paddingVertical: 6,
  },
  tagText: {
    color: '#3E7A32',
    fontSize: 11.5,
    fontWeight: '800',
  },
  statsRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: MY_PAGE_LAYOUT.sectionGap,
  },
  statCard: {
    ...shadow,
    minWidth: 0,
    flex: 1,
    alignItems: 'center',
    borderRadius: 18,
    backgroundColor: colors.surface,
    paddingHorizontal: 6,
    paddingVertical: 14,
  },
  statValue: {
    color: '#3E7A32',
    fontSize: 22,
    fontWeight: '800',
    lineHeight: 24,
  },
  jua: {
    fontFamily: fontFamilies.slogan,
    fontWeight: '400',
  },
  statLabel: {
    marginTop: 4,
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: '700',
  },
  coachCard: {
    marginTop: MY_PAGE_LAYOUT.sectionGap,
    borderRadius: 20,
    backgroundColor: '#DCEBC4',
    paddingHorizontal: 14,
    paddingTop: 14,
    paddingBottom: 16,
  },
  coachHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  coachTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
  },
  coachBadge: {
    borderWidth: 1.5,
    borderColor: '#CBDDB4',
    borderRadius: 999,
    backgroundColor: colors.surface,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  coachBadgeText: {
    color: '#3E7A32',
    fontSize: 11,
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
    borderColor: '#CBDDB4',
    borderRadius: 12,
    backgroundColor: colors.surface,
    paddingHorizontal: 4,
  },
  coachOptionSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.primary,
  },
  coachOptionText: {
    color: '#3E7A32',
    fontSize: 12,
    fontWeight: '700',
  },
  coachOptionTextSelected: {
    color: colors.surface,
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
  notificationLabel: {
    color: colors.text,
    fontSize: 14,
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
    backgroundColor: '#4E8B3A',
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
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 18,
    paddingTop: 4,
    paddingBottom: 8,
  },
  textAction: {
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  logoutText: {
    color: colors.textMuted,
    fontSize: 12.5,
    fontWeight: '700',
  },
  withdrawText: {
    color: '#C0BBB1',
    fontSize: 12.5,
    fontWeight: '700',
  },
  divider: {
    width: 1,
    height: 12,
    backgroundColor: '#DFDBD2',
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
