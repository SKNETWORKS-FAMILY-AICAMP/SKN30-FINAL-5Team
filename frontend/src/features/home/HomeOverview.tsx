import { ActivityIndicator, Image, Pressable, Text, View } from 'react-native';

import { sessionStatusLabel } from '../../api/labels';
import { imageAssets } from '../../assets';
import { ProfileAvatar } from '../../components/profile/ProfileAvatar';
import { GradientActionButton } from '../../components/primitives';
import { useScale } from '../../components/scale';
import { colors } from '../../components/theme';
import { formatRoutineItem, type HomeRoutineItem } from './homeModel';
import type { WeekDay } from './HomeScreen';
import { useHomeStyles } from './homeStyles';
import {
  CalendarIcon,
  CheckinChevronIcon,
  InfoIcon,
  NotificationIcon,
} from './HomeSupport';
import {
  RoutineGenerationLoading,
  type RoutineGenerationPhaseCode,
} from './RoutineGenerationLoading';

export function HomeHeader({
  currentDate,
  disabled,
  hasUnreadNotification,
  notificationPanel,
  onNotifications,
  onProfile,
  profileImageUrl,
  useJua,
  userName,
}: {
  currentDate: string;
  disabled: boolean;
  hasUnreadNotification: boolean;
  notificationPanel?: React.ReactNode;
  onNotifications?: () => void;
  onProfile?: () => void;
  profileImageUrl?: string | null;
  useJua: boolean;
  userName: string;
}) {
  const styles = useHomeStyles();
  const { s } = useScale();
  return (
    <View style={styles.header}>
      <View style={styles.headerCopy}>
        <Text
          accessibilityRole="header"
          style={[styles.greeting, useJua && styles.greetingJua]}
        >
          <Text style={styles.greetingName}>{userName}님</Text>, 오늘도
          반가워요!
        </Text>
        <Text style={styles.date}>{currentDate}</Text>
      </View>
      <View style={styles.headerActions}>
        <Pressable
          accessibilityLabel="알림 보기"
          accessibilityRole="button"
          accessibilityState={{
            disabled: disabled || onNotifications === undefined,
          }}
          disabled={disabled || onNotifications === undefined}
          onPointerDown={(event) => event.stopPropagation()}
          onPress={onNotifications}
          style={[
            styles.notificationButton,
            disabled && styles.disabledControl,
          ]}
        >
          <NotificationIcon />
          <View
            accessibilityLabel="읽지 않은 알림 있음"
            style={[
              styles.notificationDot,
              !hasUnreadNotification && styles.hidden,
            ]}
          />
        </Pressable>
        <Pressable
          accessibilityLabel="프로필 열기"
          accessibilityRole="button"
          accessibilityState={{ disabled }}
          disabled={disabled}
          onPress={onProfile}
          style={[styles.profileButton, disabled && styles.disabledControl]}
        >
          <ProfileAvatar
            accessibilityLabel={`${userName}님의 프로필 이미지`}
            profileImageUrl={profileImageUrl}
            size={s(48)}
            style={styles.profileAvatar}
            testID="home-profile-avatar"
          />
        </Pressable>
        {notificationPanel}
      </View>
    </View>
  );
}

function weekdayAccessibilityLabel(day: WeekDay): string {
  const statuses = day.statusCodes ?? (day.completed ? ['COMPLETED'] : []);
  if (statuses.length === 0) {
    return `${day.label}요일 기록 없음`;
  }
  return `${day.label}요일 ${statuses.map(sessionStatusLabel).join(', ')}`;
}

/**
 * One card carries the weekly goal progress and the weekday completion row.
 * The weekday circles are the only completion visual, so a completed day shows
 * the workout mascot instead of a separate goal-sized cell strip.
 */
export function WeeklyOverviewCard({
  completed,
  disabled,
  goal,
  onOpenCalendar,
  onToggleTip,
  progressPercent,
  showTip,
  weekDays,
  weekLabel,
}: {
  completed: number;
  disabled: boolean;
  goal: number;
  onOpenCalendar?: () => void;
  onToggleTip: () => void;
  progressPercent: number;
  showTip: boolean;
  weekDays: readonly WeekDay[];
  weekLabel: string;
}) {
  const styles = useHomeStyles();
  return (
    <View style={styles.progressCard}>
      <View style={styles.progressHeader}>
        <View style={styles.progressTitleRow}>
          <Text numberOfLines={1} style={styles.cardTitle}>
            이번 주 운동 현황
          </Text>
          <Pressable
            accessibilityLabel="이번 주 운동 현황 설명 보기"
            accessibilityRole="button"
            accessibilityState={{ disabled }}
            disabled={disabled}
            hitSlop={14}
            onPress={onToggleTip}
            style={[styles.iconButton, disabled && styles.disabledControl]}
          >
            <InfoIcon />
          </Pressable>
        </View>
        <View style={styles.progressTitleRow}>
          <Text numberOfLines={1} style={styles.weekRange}>
            {weekLabel}
          </Text>
          <Pressable
            accessibilityLabel="월별·연별 기록 달력 보기"
            accessibilityRole="button"
            accessibilityState={{
              disabled: disabled || onOpenCalendar === undefined,
            }}
            disabled={disabled || onOpenCalendar === undefined}
            hitSlop={13}
            onPress={onOpenCalendar}
            style={[styles.iconButton, disabled && styles.disabledControl]}
          >
            <CalendarIcon />
          </Pressable>
        </View>
      </View>

      {showTip ? (
        <View accessibilityLiveRegion="polite" style={styles.tip}>
          <Text style={styles.tipText}>
            이번 주 목표까지 얼마나 왔는지 확인해보세요.
          </Text>
        </View>
      ) : null}

      <View
        accessibilityLabel={`목표 ${goal}회 중 ${completed}회 완료, 진행률 ${progressPercent}%`}
        accessibilityRole="progressbar"
        accessibilityValue={{ min: 0, max: 100, now: progressPercent }}
        style={styles.countRow}
        testID="weekly-progress-summary"
      >
        <Text style={styles.countLabel}>
          목표 <Text style={styles.countValue}>{goal}회</Text> 중{' '}
          <Text
            style={styles.completedCountValue}
            testID="weekly-completed-count"
          >
            {completed}회
          </Text>{' '}
          완료
        </Text>
        <Text style={styles.progressPercent} testID="weekly-progress-percent">
          {progressPercent}%
        </Text>
      </View>
      <View style={styles.weekRow} testID="weekly-day-row">
        {weekDays.map((day) => (
          <View
            accessible
            accessibilityLabel={weekdayAccessibilityLabel(day)}
            key={day.label}
            style={styles.weekDay}
          >
            <View
              testID={`week-day-${day.label}`}
              style={[
                styles.weekCircle,
                day.completed
                  ? styles.weekCircleCompleted
                  : styles.weekCircleIncomplete,
              ]}
            >
              {day.completed ? (
                <Image
                  resizeMode="contain"
                  source={imageAssets.weeklyProgressCompletedWorkout}
                  style={styles.weekMascot}
                  testID="day-done-image"
                />
              ) : null}
            </View>
            <Text
              style={[
                styles.weekLabel,
                day.completed
                  ? styles.weekLabelCompleted
                  : styles.weekLabelIncomplete,
              ]}
            >
              {day.label}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

export function CheckinButton({
  label = '운동 체크인',
  onPress,
}: {
  label?: string;
  onPress: () => void;
}) {
  const styles = useHomeStyles();
  return (
    <View style={styles.checkinWrapper}>
      <GradientActionButton
        label={label}
        labelStyle={styles.sheetSaveLabel}
        onPress={onPress}
        style={styles.checkinButton}
        testID="home-checkin"
        trailing={<CheckinChevronIcon />}
      />
    </View>
  );
}

export function ExerciseCatalogShortcut({
  disabled,
  onPress,
}: {
  disabled: boolean;
  onPress?: () => void;
}) {
  const styles = useHomeStyles();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || onPress === undefined }}
      disabled={disabled || onPress === undefined}
      onPress={onPress}
      style={({ pressed }) => [
        styles.catalogShortcut,
        pressed && styles.catalogShortcutPressed,
        disabled && styles.disabledControl,
      ]}
      testID="home-exercise-catalog"
    >
      <View style={styles.catalogShortcutCopy}>
        <Text style={styles.catalogShortcutTitle}>운동 리스트 보기</Text>
      </View>
      <Text style={styles.catalogShortcutArrow}>›</Text>
    </Pressable>
  );
}

/**
 * The guidance card is Home's main call to action: it explains why the check-in
 * exists and carries the check-in entry point at its own bottom, so Home reads
 * greeting -> weekly progress -> guidance -> check-in without a detached button.
 */
export function EmptyRoutineCard({
  baselineReady = false,
  checkinLabel,
  onCheckin,
}: {
  baselineReady?: boolean;
  checkinLabel?: string;
  onCheckin?: () => void;
}) {
  const styles = useHomeStyles();
  return (
    <View
      style={[styles.messageCard, styles.checkinCard]}
      testID="home-empty-state"
    >
      <Text style={styles.messageTitle}>
        {baselineReady ? '운동을 준비해볼까요?' : '아직 추천 운동이 없어요'}
      </Text>
      <Text style={[styles.messageText, styles.checkinDescription]}>
        {baselineReady
          ? '컨디션을 알려주면 나에게 맞게 운동을 조정해드려요.'
          : '체크인을 하면 컨디션에 맞는 추천 루틴을 받아볼 수 있어요.'}
      </Text>
      {onCheckin ? (
        <View style={[styles.messageCardAction, styles.checkinCardAction]}>
          <GradientActionButton
            label={checkinLabel ?? '운동 체크인'}
            labelStyle={styles.sheetSaveLabel}
            onPress={onCheckin}
            style={styles.checkinButton}
            testID="home-checkin"
            trailing={<CheckinChevronIcon />}
          />
        </View>
      ) : null}
    </View>
  );
}

export function RoutineLookupCard({
  loading,
  onRetry,
}: {
  loading: boolean;
  onRetry?: () => void;
}) {
  const styles = useHomeStyles();
  return (
    <View
      style={[styles.messageCard, loading && styles.routineSetupLoadingCard]}
      testID="home-routine-lookup-state"
    >
      {loading ? (
        <ActivityIndicator
          color={colors.primary}
          size="small"
          testID="home-routine-lookup-loading"
        />
      ) : null}
      <Text
        style={[
          styles.messageTitle,
          loading && styles.routineSetupLoadingTitle,
        ]}
      >
        {loading
          ? '헬끼 준비 중이에요 조금만 기다려주세요!'
          : '운동 계획을 준비하지 못했어요'}
      </Text>
      {!loading ? (
        <Text accessibilityRole="alert" style={styles.messageText}>
          {
            '운동 계획을 준비하는 중 문제가 생겼어요.\n잠시 후 다시 시도해 주세요.'
          }
        </Text>
      ) : null}
      {!loading && onRetry ? (
        <View style={styles.routineSetupAction}>
          <GradientActionButton
            label="다시 준비하기"
            labelStyle={styles.routineSetupButtonLabel}
            onPress={onRetry}
            testID="home-reload-routine"
            tone="green"
          />
        </View>
      ) : null}
    </View>
  );
}

export function HomeStateCard({
  actionLabel,
  checkinLabel,
  onAction,
  onCheckin,
  serious = false,
  testID,
  text,
  title,
}: {
  actionLabel?: string;
  checkinLabel?: string;
  onAction?: () => void;
  onCheckin?: () => void;
  serious?: boolean;
  testID?: string;
  text: string;
  title: string;
}) {
  const styles = useHomeStyles();
  return (
    <View
      accessibilityRole={serious ? 'alert' : undefined}
      style={[
        styles.messageCard,
        serious && { borderColor: '#8B3A32', borderWidth: 2 },
      ]}
      testID={testID}
    >
      <Text style={[styles.messageTitle, serious && { color: '#6F2F29' }]}>
        {title}
      </Text>
      <Text style={styles.messageText}>{text}</Text>
      {checkinLabel && onCheckin ? (
        <View style={styles.messageCardAction}>
          <GradientActionButton
            label={checkinLabel}
            labelStyle={styles.sheetSaveLabel}
            onPress={onCheckin}
            style={styles.checkinButton}
            testID="home-checkin"
            trailing={<CheckinChevronIcon />}
          />
        </View>
      ) : null}
      {actionLabel && onAction ? (
        <Pressable
          accessibilityRole="button"
          onPress={onAction}
          style={styles.startButton}
        >
          <Text style={styles.startLabel}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function GeneratingRoutineCard({
  content,
  items,
  phaseCode,
}: {
  content?: React.ReactNode;
  items: readonly HomeRoutineItem[];
  phaseCode?: RoutineGenerationPhaseCode;
}) {
  const styles = useHomeStyles();
  const previewRows = items.length > 0 ? items : [null, null, null];
  return (
    <View style={styles.routineCard} testID="home-loading-state">
      <View style={styles.routineBadge}>
        <Text style={styles.routineBadgeText}>루틴 준비 중</Text>
      </View>
      <Text style={styles.routineTitle}>오늘의 루틴</Text>
      <View style={styles.routineLoadingSlot} testID="routine-loading-slot">
        <RoutineGenerationLoading asset={content} phaseCode={phaseCode} />
      </View>
      <View
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        pointerEvents="none"
        style={[styles.routineList, styles.routineLoadingPreview]}
        testID="routine-loading-preview"
      >
        {previewRows.map((item, index) => (
          <View
            key={item?.id ?? `loading-placeholder-${index}`}
            style={styles.routineLoadingRow}
          >
            {item ? (
              <Text style={styles.routineItemText}>
                {formatRoutineItem(item)}
              </Text>
            ) : (
              <View
                style={styles.routineLoadingPlaceholderLine}
                testID={`routine-loading-placeholder-line-${index}`}
              />
            )}
          </View>
        ))}
      </View>
    </View>
  );
}
