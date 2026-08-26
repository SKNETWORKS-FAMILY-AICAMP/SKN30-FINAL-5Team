import { StatusBar } from 'expo-status-bar';
import { LinearGradient } from 'expo-linear-gradient';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  Animated,
  Easing,
  Image,
  PanResponder,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type GestureResponderEvent,
  type ImageSourcePropType,
  type LayoutChangeEvent,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  type PanResponderGestureState,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, G, Path, Rect } from 'react-native-svg';

import {
  ADVERSE_REACTION_OPTIONS,
  actionLabel,
  agentTypeLabel,
  bodyAreaLabel,
  decisionReasonLabel,
  DEFAULT_BODY_AREA_OPTIONS,
  EXTENDED_BODY_AREA_OPTIONS,
  locationLabel,
  planRevisionReasonLabel,
  sessionStatusLabel,
  SEVERITY_OPTIONS,
} from '../../api/labels';
import type { Api } from '../../api/endpoints';
import type {
  ActionCode,
  DailyContextResponse,
  DecisionResponse,
  DiscomfortSeverityCode,
  RoutineResponse,
  SessionStatusCode,
  WeekResponse,
  WeeklyPlanRevisionResponse,
  WorkoutSessionLogSummary,
} from '../../api/types';
import { moveArrayItem } from '../../api/workoutPlan';
import { imageAssets, weeklyProgressMascotSources } from '../../assets';
import { fontFamilies, useBrandFonts } from '../../app/fonts';
import type { TabId } from '../../components/brand/BrandChrome';
import { ProfileAvatar } from '../../components/profile/ProfileAvatar';
import { useScale } from '../../components/scale';
import { GradientActionButton } from '../../components/primitives';
import { colors } from '../../components/theme';
import { ExerciseDetailSheet } from '../workout/ExerciseDetailSheet';
import {
  HOME_CHECKIN_OPTIONS,
  HOME_DEFAULT_CHECKIN,
  HOME_ROUTINE_VARIANTS,
  HOME_WEEK_DAYS,
  apiCheckinDraft,
  checkinFromContext,
  copyRoutineItems,
  formatHomeDate,
  formatRoutineItem,
  formatWeekRange,
  formatWeekRangeForLocalDate,
  getHomeRoutineVariant,
  getHomeRerollLabel,
  routineFocusFromPlan,
  routineItemsFromPlan,
  routineTitleFromPlan,
  validateAvailabilitySlots,
  weekDaysFromSessions,
  weeklyCompletionPercentage,
  weekStartForLocalDate,
  type HomeCheckin,
  type HomeCheckinDraft,
  type HomeAvailabilitySlot,
  type HomePreviewState,
  type HomeRoutineItem,
} from './homeModel';

export const HOME_BACKGROUND_COLOR = '#FFF8E5';

// Temporarily hide the optional availability-time editor while preserving its
// draft and API values so it can be restored without a contract change.
const CHECKIN_AVAILABILITY_INPUT_ENABLED: boolean = false;

const CHECKIN_DURATION_MINUTES = {
  min: 5,
  max: 180,
  step: 10,
} as const;

export const HOME_LAYOUT = {
  contentHorizontalPadding: 18,
  contentTopPadding: 58,
  headerHorizontalPadding: 4,
  headerBottomPadding: 18,
  cardGap: 14,
  bottomBarHorizontalPadding: 14,
  bottomBarBottomPadding: 26,
  sheetHorizontalPadding: 18,
  sheetBottomPadding: 30,
} as const;

const bottomNavigationShadow =
  Platform.select({
    ios: {
      shadowColor: '#5A4636',
      shadowOffset: { width: 0, height: -2 },
      shadowOpacity: 0.07,
      shadowRadius: 7,
    },
    android: { elevation: 2 },
    default: {
      shadowColor: '#5A4636',
      shadowOffset: { width: 0, height: -2 },
      shadowOpacity: 0.07,
      shadowRadius: 7,
    },
  }) ?? {};

const bottomNavigationStyles = StyleSheet.create({
  bottomBarOuter: {
    flexShrink: 0,
    backgroundColor: HOME_BACKGROUND_COLOR,
    paddingTop: 8,
    paddingHorizontal: HOME_LAYOUT.bottomBarHorizontalPadding,
    paddingBottom: HOME_LAYOUT.bottomBarBottomPadding,
  },
  bottomBar: {
    flexDirection: 'row',
    borderRadius: 22,
    backgroundColor: '#FFFFFF',
    paddingVertical: 10,
    paddingHorizontal: 6,
    ...bottomNavigationShadow,
  },
  tab: {
    minHeight: 48,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 6,
    paddingHorizontal: 2,
  },
  tabLabel: {
    color: '#B0ACA4',
    fontSize: 11.5,
    fontWeight: '700',
    textAlign: 'center',
  },
  tabActive: { color: '#A45F00' },
});

type HomeTab = TabId;
type WeekDay = {
  completed: boolean;
  label: string;
  statusCodes?: readonly SessionStatusCode[];
};
const EMPTY_AVAILABILITY_SLOT: HomeAvailabilitySlot = {
  startTime: '',
  endTime: '',
};
const TIME_WHEEL_ITEM_HEIGHT = 44;
const TIME_WHEEL_GESTURE_IDLE_MS = 45;
const TIME_WHEEL_SINGLE_ITEM_DELTA = 240;
const TIME_WHEEL_ACCELERATION_DELTA = 70;
const TIME_WHEEL_MAX_ITEMS_PER_GESTURE = 18;
const TIME_HOURS = Array.from({ length: 24 }, (_, index) => index);
const TIME_MINUTES = Array.from({ length: 12 }, (_, index) => index * 5);

type TimePickerTarget = {
  field: keyof HomeAvailabilitySlot;
  index: number;
};

type RevisionNotice = {
  serious: boolean;
  text: string;
  title: string;
};

function uniqueText(values: readonly (string | null | undefined)[]): string[] {
  return Array.from(
    new Set(values.filter((value): value is string => Boolean(value))),
  );
}

function revisionNotice(
  revision: WeeklyPlanRevisionResponse | null,
): RevisionNotice | null {
  if (revision === null) {
    return null;
  }
  const reasons = uniqueText([
    ...revision.revision_reason_codes.map(planRevisionReasonLabel),
    ...revision.finalization_reason_codes.map(planRevisionReasonLabel),
  ]);
  const text = reasons.join(' ') || '서버가 루틴 조정 결과를 확인했어요.';
  switch (revision.safety_status_code) {
    case 'NEEDS_INPUT':
      return {
        serious: false,
        text:
          reasons.join(' ') ||
          '루틴을 조정하려면 상태를 조금 더 확인해야 해요.',
        title: '추가 확인이 필요해요',
      };
    case 'BLOCKED':
      return {
        serious: true,
        text:
          reasons.join(' ') || '안전 기준에 따라 이 루틴을 진행하지 않아요.',
        title: '안전하게 진행할 수 없어요',
      };
    case 'FAILED':
      return {
        serious: true,
        text:
          reasons.join(' ') ||
          '안전 확인을 완료하지 못해 루틴을 적용하지 않았어요.',
        title: '루틴을 적용하지 않았어요',
      };
    case 'REVISE':
      return {
        serious: false,
        text,
        title: '안전 기준에 맞춰 조정했어요',
      };
    case 'PASS':
    default:
      return revision.source_code === 'INITIAL'
        ? null
        : { serious: false, text, title: '루틴 조정을 반영했어요' };
  }
}

export type HomeBusyKind = 'checkin' | 'revision' | 'starting';

export type HomeUserEdits = {
  routineId: string;
  locationCode: string;
};

export type HomeScreenProps = {
  actionError?: string | null;
  busy?: HomeBusyKind | null;
  currentDate?: string;
  context?: DailyContextResponse | null;
  decision?: DecisionResponse | null;
  defaultDurationMinutes?: number;
  errorMessage?: string;
  exerciseApi?: Pick<Api, 'getExercise'>;
  hasTodayRoutine?: boolean;
  hasUnreadNotification?: boolean;
  localDate?: string;
  locationCodes?: readonly string[];
  nickname?: string;
  onChooseRest?: () => void;
  onCreateRoutine?: () => void;
  onEditRoutine?: () => void;
  onNavigateTab?: (tab: HomeTab) => void;
  onNotifications?: () => void;
  onOpenCalendar?: () => void;
  onOpenCheckin?: () => void;
  onProfile?: () => void;
  onRequestAiRevision?: () => void;
  onRequestAlternative?: () => void;
  onReorderPlan?: (from: number, to: number) => void;
  onRetry?: () => void;
  onRetryCheckin?: () => void;
  onSaveCheckin?: () => void;
  onSaveEdit?: (items: readonly HomeRoutineItem[]) => void;
  onStartWorkout?: () => void;
  onSubmitCheckin?: (draft: HomeCheckinDraft) => void;
  onSubmitUserEdits?: (edits: HomeUserEdits) => void;
  permissionDenied?: boolean;
  planRevision?: WeeklyPlanRevisionResponse | null;
  previewState?: HomePreviewState;
  profileImageUrl?: string | null;
  restToday?: boolean;
  routine?: RoutineResponse | null;
  sessions?: readonly WorkoutSessionLogSummary[];
  staleContext?: boolean;
  status?: 'loading' | 'error' | 'ready';
  userName?: string;
  week?: WeekResponse | null;
  weekDays?: readonly WeekDay[];
  weeklyCompletedCount?: number;
  weeklyGoalCount?: number;
  weekLabel?: string;
};

type HomeStyles = ReturnType<typeof createHomeStyles>;
const fallbackHomeStyles = createHomeStyles(
  (value) => value,
  (value) => value,
  58,
);
const HomeStyleContext = createContext<HomeStyles>(fallbackHomeStyles);

function useHomeStyles() {
  return useContext(HomeStyleContext);
}

export function HomeScreen({ previewState, ...props }: HomeScreenProps) {
  const initialState = previewState ?? 'pre-checkin';
  return (
    <HomeScreenContent
      key={initialState}
      {...props}
      initialState={initialState}
    />
  );
}

function HomeScreenContent({
  actionError = null,
  busy = null,
  context = null,
  currentDate = '2026.08.11 (화)',
  decision = null,
  defaultDurationMinutes = 40,
  errorMessage,
  exerciseApi,
  hasTodayRoutine = true,
  hasUnreadNotification = false,
  initialState,
  localDate,
  locationCodes = [],
  nickname,
  onChooseRest,
  onCreateRoutine,
  onEditRoutine,
  onNavigateTab,
  onNotifications,
  onOpenCalendar,
  onOpenCheckin,
  onProfile,
  onRequestAiRevision,
  onRequestAlternative,
  onReorderPlan,
  onRetry,
  onRetryCheckin,
  onSaveCheckin,
  onSaveEdit,
  onStartWorkout,
  onSubmitCheckin,
  onSubmitUserEdits,
  permissionDenied = false,
  planRevision = null,
  profileImageUrl = null,
  restToday = false,
  routine = null,
  sessions = [],
  staleContext = false,
  status,
  userName = '헬끼',
  week = null,
  weekDays: previewWeekDays = HOME_WEEK_DAYS,
  weeklyCompletedCount = 2,
  weeklyGoalCount = 4,
  weekLabel = '8.11 ~ 8.17 (1주차)',
}: Omit<HomeScreenProps, 'previewState'> & { initialState: HomePreviewState }) {
  const { s, f } = useScale();
  const insets = useSafeAreaInsets();
  const styles = useMemo(
    () => createHomeStyles(s, f, Math.max(insets.top, s(58))),
    [f, insets.top, s],
  );
  const brandFonts = useBrandFonts();
  const useJua = brandFonts.loaded && !brandFonts.failed;
  const apiMode = status !== undefined;
  const startsCheckedIn = apiMode
    ? context !== null
    : initialState !== 'pre-checkin' && initialState !== 'checkin';
  const [checkedIn, setCheckedIn] = useState(startsCheckedIn);
  const [checkinOpen, setCheckinOpen] = useState(initialState === 'checkin');
  const [timePickerTarget, setTimePickerTarget] =
    useState<TimePickerTarget | null>(null);
  const [editOpen, setEditOpen] = useState(initialState === 'editing');
  const [reasonOpen, setReasonOpen] = useState(false);
  const [detailItem, setDetailItem] = useState<HomeRoutineItem | null>(null);
  const [showTip, setShowTip] = useState(false);
  const [rerolling, setRerolling] = useState(initialState === 'generating');
  const [previewRerolls, setPreviewRerolls] = useState(0);
  const [variantIndex, setVariantIndex] = useState(0);
  const [adjustedRoutine, setAdjustedRoutine] = useState(
    initialState === 'adjusted',
  );
  const initialCheckin = useMemo<HomeCheckin>(
    () =>
      apiMode
        ? checkinFromContext(
            context,
            defaultDurationMinutes,
            locationCodes[0] ?? null,
          )
        : initialState === 'adjusted'
          ? {
              ...HOME_DEFAULT_CHECKIN,
              discomforts: { KNEE: 'MILD' },
            }
          : { ...HOME_DEFAULT_CHECKIN, discomforts: {} },
    [apiMode, context, defaultDurationMinutes, initialState, locationCodes],
  );
  const [committedCheckin, setCommittedCheckin] =
    useState<HomeCheckin>(initialCheckin);
  const [checkinDraft, setCheckinDraft] = useState<HomeCheckin>(initialCheckin);
  const serverPlan = decision?.final_plan ?? null;
  const [routineItems, setRoutineItems] = useState<HomeRoutineItem[]>(() =>
    serverPlan === null
      ? copyRoutineItems(getHomeRoutineVariant(0).items)
      : routineItemsFromPlan(serverPlan),
  );
  const serverRoutineItems = useMemo(
    () => (serverPlan === null ? [] : routineItemsFromPlan(serverPlan)),
    [serverPlan],
  );
  const displayedRoutineItems = apiMode ? serverRoutineItems : routineItems;
  const serverCheckin = useMemo(
    () =>
      checkinFromContext(
        context,
        defaultDurationMinutes,
        locationCodes[0] ?? null,
      ),
    [context, defaultDurationMinutes, locationCodes],
  );
  const displayedCheckin = apiMode ? serverCheckin : committedCheckin;
  const [editDraft, setEditDraft] = useState<HomeRoutineItem[]>(() =>
    copyRoutineItems(getHomeRoutineVariant(0).items),
  );
  const [newItem, setNewItem] = useState<HomeRoutineItem>({
    id: 'new',
    name: '',
    sets: '',
    reps: '',
  });
  const newId = useRef(0);
  const rerollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const apiWeekDays = useMemo(() => {
    const weekStart =
      week?.week_start ??
      (localDate === undefined ? null : weekStartForLocalDate(localDate));
    return weekStart === null
      ? Array.from(HOME_WEEK_DAYS, (day) => ({
          ...day,
          completed: false,
          statusCodes: [] as SessionStatusCode[],
        }))
      : weekDaysFromSessions(weekStart, sessions);
  }, [localDate, sessions, week]);
  const weekDays = apiMode ? apiWeekDays : previewWeekDays;
  const goal = Math.max(
    1,
    apiMode ? (week?.target_workout_count ?? weeklyGoalCount) : weeklyGoalCount,
  );
  const serverCompletedCount = sessions.filter(
    (session) => session.status_code === 'COMPLETED',
  ).length;
  const completed = Math.min(
    goal,
    Math.max(0, apiMode ? serverCompletedCount : weeklyCompletedCount),
  );
  const progressDays = useMemo(
    () => Array.from({ length: goal }, (_, index) => index < completed),
    [completed, goal],
  );
  const progressPercent = weeklyCompletionPercentage(completed, goal);
  const effectiveCheckedIn = apiMode ? context !== null : checkedIn;
  const rerolls = apiMode
    ? (planRevision?.ai_revision_count ?? 0)
    : previewRerolls;
  const rerollLoading = apiMode
    ? busy === 'checkin' || busy === 'revision'
    : rerolling && effectiveCheckedIn;
  const seriousDecision =
    decision?.action_code === 'STOP_AND_SEEK_HELP' ||
    decision?.safety_status_code === 'BLOCKED';
  const hasRoutine = apiMode
    ? serverPlan !== null && !rerollLoading && !restToday
    : hasTodayRoutine && effectiveCheckedIn && !rerollLoading;
  const noRoutine = !hasRoutine && !rerollLoading;
  const variant = getHomeRoutineVariant(variantIndex);
  const routineTitle =
    serverPlan === null
      ? adjustedRoutine
        ? '컨디션 맞춤 루틴'
        : variant.title
      : routineTitleFromPlan(serverPlan);
  const routineFocus =
    serverPlan === null ? variant.focus : routineFocusFromPlan(serverPlan);
  const routineMinutes =
    serverPlan === null
      ? displayedCheckin.workoutMinutes
      : String(serverPlan.requested_duration_minutes);
  const routineNotes =
    apiMode && decision !== null
      ? [decision.summary, decision.guidance?.message].filter(
          (note): note is string => Boolean(note),
        )
      : undefined;
  const currentRevisionNotice = revisionNotice(planRevision);
  const recommendationReasons = useMemo(
    () =>
      decision === null
        ? []
        : uniqueText([
            ...decision.reason_codes.map(decisionReasonLabel),
            ...(decision.adjustment_reason_codes ?? []).map(
              decisionReasonLabel,
            ),
            ...(decision.safety_summary?.reason_codes ?? []).map(
              decisionReasonLabel,
            ),
          ]),
    [decision],
  );
  const hasRecommendationDetails =
    decision !== null &&
    (recommendationReasons.length > 0 ||
      Boolean(decision.safety_summary?.summary) ||
      Boolean(decision.public_agent_summaries?.length));
  const blockingRevisionNotice =
    planRevision?.routine === null ? currentRevisionNotice : null;
  const routineRevisionNotice =
    planRevision?.routine !== null ? currentRevisionNotice : null;
  const painPart =
    Object.keys(displayedCheckin.discomforts).map(bodyAreaLabel).join('·') ||
    null;
  const displayDate =
    apiMode && localDate !== undefined
      ? formatHomeDate(localDate)
      : currentDate;
  const displayWeekLabel = apiMode
    ? week !== null
      ? formatWeekRange(week.week_start, week.week_end)
      : localDate
        ? formatWeekRangeForLocalDate(localDate)
        : '이번 주'
    : weekLabel;
  const displayName = nickname ?? userName;

  useEffect(
    () => () => {
      if (rerollTimer.current) {
        clearTimeout(rerollTimer.current);
      }
    },
    [],
  );

  const openCheckin = () => {
    setCheckinDraft({ ...displayedCheckin });
    setCheckinOpen(true);
    onOpenCheckin?.();
  };

  const closeCheckin = () => {
    setCheckinDraft({ ...displayedCheckin });
    setTimePickerTarget(null);
    setCheckinOpen(false);
  };

  const saveCheckin = () => {
    const saved = {
      ...checkinDraft,
      workoutMinutes: clampNumericString(
        checkinDraft.workoutMinutes,
        CHECKIN_DURATION_MINUTES.min,
        CHECKIN_DURATION_MINUTES.max,
      ),
    };
    setCommittedCheckin(saved);
    setCheckinDraft(saved);
    setCheckedIn(true);
    setTimePickerTarget(null);
    setCheckinOpen(false);
    if (apiMode) {
      onSubmitCheckin?.(apiCheckinDraft(saved));
    } else {
      onSaveCheckin?.();
    }
  };

  const openEdit = () => {
    setEditDraft(copyRoutineItems(displayedRoutineItems));
    setNewItem({ id: 'new', name: '', sets: '', reps: '' });
    setEditOpen(true);
    onEditRoutine?.();
  };

  const closeEdit = () => {
    setEditDraft(copyRoutineItems(displayedRoutineItems));
    setEditOpen(false);
  };

  const saveEdit = () => {
    const cleaned = cleanRoutineItems(editDraft);
    const saved = cleaned.length
      ? cleaned
      : copyRoutineItems(getHomeRoutineVariant(variantIndex).items);
    setRoutineItems(saved);
    setEditDraft(copyRoutineItems(saved));
    setEditOpen(false);
    onSaveEdit?.(saved);
  };

  const requestAlternative = () => {
    if (rerolling || rerolls >= 2) {
      return;
    }
    if (apiMode) {
      onRequestAiRevision?.();
      return;
    }
    setRerolling(true);
    onRequestAlternative?.();
    if (rerollTimer.current) {
      clearTimeout(rerollTimer.current);
    }
    rerollTimer.current = setTimeout(() => {
      setPreviewRerolls((current) => {
        const next = current + 1;
        const nextVariant = next % HOME_ROUTINE_VARIANTS.length;
        setVariantIndex(nextVariant);
        setRoutineItems(
          copyRoutineItems(getHomeRoutineVariant(nextVariant).items),
        );
        setAdjustedRoutine(false);
        return next;
      });
      setRerolling(false);
    }, 900);
  };

  const moveRoutineItem = useCallback((from: number, to: number) => {
    setRoutineItems((current) => moveArrayItem(current, from, to));
  }, []);
  const moveEditItem = useCallback((from: number, to: number) => {
    setEditDraft((current) => moveArrayItem(current, from, to));
  }, []);
  const contentReady = !apiMode || status === 'ready';
  const restRecommended = decision?.action_code === 'REST';
  const routineOption = decision?.options.find(
    (option) => option.option_code === 'FINAL_ROUTINE',
  );
  const restOption = decision?.options.find(
    (option) => option.option_code === 'REST',
  );
  const routineBlockedReason =
    routineOption && !routineOption.selectable
      ? ((routineOption.blocked_reason_code
          ? decisionReasonLabel(routineOption.blocked_reason_code)
          : null) ?? '지금은 이 루틴을 시작할 수 없어요.')
      : null;
  const showCheckin =
    contentReady &&
    (!apiMode || routine !== null) &&
    !restToday &&
    !seriousDecision;

  return (
    <HomeStyleContext.Provider value={styles}>
      <View style={styles.screen}>
        <StatusBar style="dark" />
        <View
          style={[styles.gradient, { backgroundColor: HOME_BACKGROUND_COLOR }]}
          testID="home-background"
        >
          <ScrollView
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            style={styles.scroll}
          >
            <HomeHeader
              currentDate={displayDate}
              hasUnreadNotification={hasUnreadNotification}
              onNotifications={onNotifications}
              onProfile={onProfile}
              profileImageUrl={profileImageUrl}
              userName={displayName}
            />
            {contentReady ? (
              <>
                <WeeklyRoutineCard weekDays={weekDays} />
                <WeeklyProgressCard
                  key={displayWeekLabel}
                  completed={completed}
                  goal={goal}
                  onOpenCalendar={onOpenCalendar}
                  onToggleTip={() => setShowTip((current) => !current)}
                  progressDays={progressDays}
                  progressPercent={progressPercent}
                  showTip={showTip}
                  weekLabel={displayWeekLabel}
                />
              </>
            ) : null}
            {showCheckin ? (
              <CheckinButton onPress={openCheckin} useJua={useJua} />
            ) : null}

            {apiMode && status === 'loading' ? (
              <HomeStateCard
                testID="home-loading-state"
                text="잠시만 기다려주세요."
                title="오늘 상태를 불러오는 중이에요"
              />
            ) : null}
            {apiMode && status === 'error' ? (
              <HomeStateCard
                actionLabel={permissionDenied ? undefined : '다시 시도'}
                onAction={permissionDenied ? undefined : onRetry}
                text={
                  permissionDenied
                    ? '계정 상태를 확인한 뒤 다시 이용해주세요.'
                    : (errorMessage ?? '서버에 연결하지 못했어요.')
                }
                title={
                  permissionDenied
                    ? '오늘의 운동 정보에 접근할 권한이 없어요.'
                    : 'Home을 불러오지 못했어요'
                }
              />
            ) : null}
            {contentReady && (actionError || blockingRevisionNotice) ? (
              <HomeStateCard
                actionLabel={staleContext ? '최신 상태로 다시 시도' : undefined}
                onAction={staleContext ? onRetryCheckin : undefined}
                serious={blockingRevisionNotice?.serious}
                testID="home-action-error"
                text={
                  blockingRevisionNotice?.text ??
                  actionError ??
                  '요청 결과를 확인해주세요.'
                }
                title={
                  blockingRevisionNotice?.title ?? '요청을 완료하지 못했어요'
                }
              />
            ) : null}
            {apiMode && contentReady && routine === null ? (
              <HomeStateCard
                actionLabel="기본 루틴 만들기"
                onAction={onCreateRoutine}
                text="프로필 목표를 바탕으로 첫 루틴을 만들 수 있어요."
                title="기본 루틴이 아직 없어요"
              />
            ) : null}
            {apiMode && contentReady && restToday ? (
              <HomeStateCard
                text="오늘은 운동을 권하거나 재촉하지 않을게요."
                title="오늘은 휴식하기로 했어요"
              />
            ) : null}
            {apiMode && contentReady && seriousDecision ? (
              <HomeStateCard
                serious
                text={
                  decision?.guidance?.message ??
                  decision?.summary ??
                  '운동을 진행하지 말고 상태를 확인해주세요.'
                }
                title={
                  decision?.guidance?.title ??
                  (decision?.safety_status_code === 'BLOCKED'
                    ? '오늘은 운동을 진행하지 않아요'
                    : '운동을 멈춰주세요')
                }
              />
            ) : null}
            {apiMode &&
            contentReady &&
            !restToday &&
            !seriousDecision &&
            restRecommended ? (
              <HomeStateCard
                actionLabel={restOption?.selectable ? '오늘은 쉬기' : undefined}
                onAction={restOption?.selectable ? onChooseRest : undefined}
                text={
                  decision?.guidance?.message ??
                  decision?.summary ??
                  '오늘은 회복에 집중하는 것이 좋아요.'
                }
                title="오늘은 휴식을 추천해요"
              />
            ) : null}
            {contentReady &&
            !restToday &&
            !seriousDecision &&
            !restRecommended &&
            noRoutine &&
            !actionError &&
            blockingRevisionNotice === null &&
            (!apiMode || routine !== null) ? (
              <EmptyRoutineCard />
            ) : null}
            {contentReady && !restToday && rerollLoading ? (
              <GeneratingRoutineCard />
            ) : null}
            {contentReady &&
            !restToday &&
            !seriousDecision &&
            blockingRevisionNotice === null &&
            hasRoutine ? (
              <RoutineCard
                actionCode={
                  apiMode
                    ? decision?.action_code
                    : adjustedRoutine
                      ? 'DOWNSHIFT'
                      : 'KEEP'
                }
                editLabel={apiMode ? '운동 장소 변경' : '운동 수정하기'}
                items={displayedRoutineItems}
                minutes={routineMinutes}
                notes={routineNotes}
                onEdit={openEdit}
                onMove={apiMode ? onReorderPlan : moveRoutineItem}
                onOpenExercise={
                  exerciseApi ? (item) => setDetailItem(item) : undefined
                }
                onOpenReasons={
                  hasRecommendationDetails
                    ? () => setReasonOpen(true)
                    : undefined
                }
                onRest={
                  decision?.options.some(
                    (option) =>
                      option.option_code === 'REST' && option.selectable,
                  )
                    ? onChooseRest
                    : undefined
                }
                onRequestAlternative={requestAlternative}
                onStart={
                  !apiMode || routineOption?.selectable
                    ? onStartWorkout
                    : undefined
                }
                painPart={painPart}
                pending={busy !== null}
                rerolling={apiMode ? busy === 'revision' : rerolling}
                rerolls={rerolls}
                revisionNotice={routineRevisionNotice?.text}
                startBlockedReason={routineBlockedReason}
                title={routineTitle}
                focus={routineFocus}
                useJua={useJua}
              />
            ) : null}
          </ScrollView>
        </View>

        <HomeBottomNavigation activeTab="home" onNavigate={onNavigateTab} />

        {checkinOpen ? (
          <CheckinSheet
            draft={checkinDraft}
            locationCodes={apiMode ? locationCodes : []}
            onAddAvailabilitySlot={() =>
              setCheckinDraft((current) => ({
                ...current,
                availableSlots:
                  current.availableSlots && current.availableSlots.length > 0
                    ? [
                        ...current.availableSlots,
                        { ...EMPTY_AVAILABILITY_SLOT },
                      ]
                    : [
                        { ...EMPTY_AVAILABILITY_SLOT },
                        { ...EMPTY_AVAILABILITY_SLOT },
                      ],
              }))
            }
            onChangeLocation={(locationCode) =>
              setCheckinDraft((current) => ({
                ...current,
                locationCode,
              }))
            }
            onChangeFatigue={(fatigue) =>
              setCheckinDraft((current) => ({ ...current, fatigue }))
            }
            onChangeSleepHours={(sleepHours) =>
              setCheckinDraft((current) => ({ ...current, sleepHours }))
            }
            onChangeSeverity={(bodyAreaCode, severity) =>
              setCheckinDraft((current) => ({
                ...current,
                discomforts: {
                  ...current.discomforts,
                  [bodyAreaCode]: severity,
                },
              }))
            }
            onChangeWorkoutMinutes={(workoutMinutes) =>
              setCheckinDraft((current) => ({
                ...current,
                workoutMinutes,
              }))
            }
            onClose={closeCheckin}
            onClearAdverseReactions={() =>
              setCheckinDraft((current) => ({
                ...current,
                adverseReactionCodes: [],
              }))
            }
            onClearDiscomforts={() =>
              setCheckinDraft((current) => ({
                ...current,
                discomforts: {},
              }))
            }
            onSave={saveCheckin}
            onOpenTimePicker={(index, field) =>
              setTimePickerTarget({ index, field })
            }
            onRemoveAvailabilitySlot={(index) =>
              setCheckinDraft((current) => ({
                ...current,
                availableSlots: (current.availableSlots ?? []).filter(
                  (_, slotIndex) => slotIndex !== index,
                ),
              }))
            }
            onToggleAdverseReaction={(code) =>
              setCheckinDraft((current) => ({
                ...current,
                adverseReactionCodes: current.adverseReactionCodes.includes(
                  code,
                )
                  ? current.adverseReactionCodes.filter(
                      (entry) => entry !== code,
                    )
                  : [...current.adverseReactionCodes, code],
              }))
            }
            onToggleBodyArea={(code) =>
              setCheckinDraft((current) => {
                const discomforts = { ...current.discomforts };
                if (discomforts[code] === undefined) {
                  discomforts[code] = 'MILD';
                } else {
                  delete discomforts[code];
                }
                return { ...current, discomforts };
              })
            }
            pending={busy === 'checkin'}
            useJua={useJua}
          />
        ) : null}

        {CHECKIN_AVAILABILITY_INPUT_ENABLED && timePickerTarget ? (
          <TimePickerSheet
            initialValue={
              checkinDraft.availableSlots?.[timePickerTarget.index]?.[
                timePickerTarget.field
              ] ?? ''
            }
            key={`${timePickerTarget.index}-${timePickerTarget.field}`}
            onClose={() => setTimePickerTarget(null)}
            onConfirm={(value) => {
              setCheckinDraft((current) => {
                const availableSlots =
                  current.availableSlots && current.availableSlots.length > 0
                    ? current.availableSlots.map((slot) => ({ ...slot }))
                    : [{ ...EMPTY_AVAILABILITY_SLOT }];
                const slot = availableSlots[timePickerTarget.index];
                if (slot) {
                  slot[timePickerTarget.field] = value;
                }
                return { ...current, availableSlots };
              });
              setTimePickerTarget(null);
            }}
            targetField={timePickerTarget.field}
          />
        ) : null}

        {editOpen && apiMode ? (
          <ApiEditRoutineSheet
            items={displayedRoutineItems}
            locationCodes={locationCodes}
            onClose={closeEdit}
            onSave={(edits) => {
              onSubmitUserEdits?.(edits);
              setEditOpen(false);
            }}
            pending={busy === 'revision'}
            routine={routine}
            selectedLocationCode={
              planRevision?.selected_location_code ??
              context?.location_code ??
              null
            }
            useJua={useJua}
          />
        ) : null}

        {reasonOpen && decision !== null ? (
          <RecommendationReasonSheet
            decision={decision}
            onClose={() => setReasonOpen(false)}
            reasons={recommendationReasons}
          />
        ) : null}

        {detailItem?.exerciseId && exerciseApi ? (
          <SheetFrame
            onClose={() => setDetailItem(null)}
            title={detailItem.name}
            zIndex={25}
          >
            <ExerciseDetailSheet
              api={exerciseApi}
              exerciseId={detailItem.exerciseId}
            />
          </SheetFrame>
        ) : null}

        {editOpen && !apiMode ? (
          <EditRoutineSheet
            items={editDraft}
            newItem={newItem}
            onAdd={() => {
              const name = newItem.name.trim();
              if (!name) {
                return;
              }
              newId.current += 1;
              setEditDraft((current) => [
                ...current,
                {
                  ...newItem,
                  id: `custom-${newId.current}`,
                  name,
                  sets: digitsOnly(newItem.sets),
                  reps: digitsOnly(newItem.reps),
                },
              ]);
              setNewItem({ id: 'new', name: '', sets: '', reps: '' });
            }}
            onChangeItems={setEditDraft}
            onChangeNew={setNewItem}
            onClose={closeEdit}
            onMove={moveEditItem}
            onReset={() => {
              setEditDraft(
                copyRoutineItems(getHomeRoutineVariant(variantIndex).items),
              );
              setNewItem({ id: 'new', name: '', sets: '', reps: '' });
            }}
            onSave={saveEdit}
            useJua={useJua}
          />
        ) : null}
      </View>
    </HomeStyleContext.Provider>
  );
}

function HomeHeader({
  currentDate,
  hasUnreadNotification,
  onNotifications,
  onProfile,
  profileImageUrl,
  userName,
}: {
  currentDate: string;
  hasUnreadNotification: boolean;
  onNotifications?: () => void;
  onProfile?: () => void;
  profileImageUrl?: string | null;
  userName: string;
}) {
  const styles = useHomeStyles();
  const { s } = useScale();
  return (
    <View style={styles.header}>
      <View style={styles.headerCopy}>
        <Text accessibilityRole="header" style={styles.greeting}>
          안녕하세요, <Text style={styles.greetingName}>{userName}님!</Text>
        </Text>
        <Text style={styles.date}>{currentDate}</Text>
      </View>
      <View style={styles.headerActions}>
        <Pressable
          accessibilityLabel="알림 보기"
          accessibilityRole="button"
          accessibilityState={{ disabled: onNotifications === undefined }}
          disabled={onNotifications === undefined}
          onPress={onNotifications}
          style={styles.notificationButton}
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
          onPress={onProfile}
          style={styles.profileButton}
        >
          <ProfileAvatar
            accessibilityLabel={`${userName}님의 프로필 이미지`}
            profileImageUrl={profileImageUrl}
            size={s(48)}
            style={styles.profileAvatar}
            testID="home-profile-avatar"
          />
        </Pressable>
      </View>
    </View>
  );
}

function WeeklyRoutineCard({ weekDays }: { weekDays: readonly WeekDay[] }) {
  const styles = useHomeStyles();
  return (
    <View style={styles.summaryCard}>
      <Text style={styles.cardTitle}>요일별 진행 상태</Text>
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
              <View style={!day.completed && styles.hidden}>
                <DayCheckIcon />
              </View>
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

function weekdayAccessibilityLabel(day: WeekDay): string {
  const statuses = day.statusCodes ?? (day.completed ? ['COMPLETED'] : []);
  if (statuses.length === 0) {
    return `${day.label}요일 기록 없음`;
  }
  return `${day.label}요일 ${statuses.map(sessionStatusLabel).join(', ')}`;
}

function randomizedWeeklyProgressMascots(): ImageSourcePropType[] {
  const sources = Array.from(weeklyProgressMascotSources);
  for (let index = sources.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1));
    [sources[index], sources[randomIndex]] = [
      sources[randomIndex]!,
      sources[index]!,
    ];
  }
  return sources;
}

function WeeklyProgressCard({
  completed,
  goal,
  onOpenCalendar,
  onToggleTip,
  progressDays,
  progressPercent,
  showTip,
  weekLabel,
}: {
  completed: number;
  goal: number;
  onOpenCalendar?: () => void;
  onToggleTip: () => void;
  progressDays: readonly boolean[];
  progressPercent: number;
  showTip: boolean;
  weekLabel: string;
}) {
  const styles = useHomeStyles();
  const [completedMascots] = useState(randomizedWeeklyProgressMascots);
  return (
    <View style={styles.progressCard}>
      <View style={styles.progressHeader}>
        <View style={styles.progressTitleRow}>
          <Text numberOfLines={1} style={styles.cardTitle}>
            이번 주 진행률
          </Text>
          <Pressable
            accessibilityLabel="이번 주 진행률 설명 보기"
            accessibilityRole="button"
            hitSlop={14}
            onPress={onToggleTip}
            style={styles.iconButton}
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
            hitSlop={13}
            onPress={onOpenCalendar}
            style={styles.iconButton}
          >
            <CalendarIcon />
          </Pressable>
        </View>
      </View>

      {showTip ? (
        <View accessibilityLiveRegion="polite" style={styles.tip}>
          <Text style={styles.tipText}>
            완료한 루틴 수를 이번 주 목표 횟수로 나눈 진행률이에요.
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
      <View style={styles.progressCells} testID="weekly-progress-cells">
        {progressDays.map((isDone, index) => (
          <View
            accessibilityLabel={`${index + 1}번째 주간 진행 ${isDone ? '완료' : '미완료'}`}
            key={`progress-${index}`}
            style={[
              styles.progressCell,
              isDone
                ? styles.progressCellCompleted
                : styles.progressCellIncomplete,
            ]}
          >
            <Image
              resizeMode="contain"
              source={
                isDone
                  ? completedMascots[index]
                  : imageAssets.weeklyProgressIncomplete
              }
              style={[styles.progressImage, !isDone && styles.todoImage]}
              testID={isDone ? 'day-done-image' : 'day-todo-image'}
            />
          </View>
        ))}
      </View>
    </View>
  );
}

function CheckinButton({
  onPress,
  useJua,
}: {
  onPress: () => void;
  useJua: boolean;
}) {
  const styles = useHomeStyles();
  return (
    <View style={styles.checkinWrapper}>
      <GradientActionButton
        label="오늘 루틴 체크인"
        labelStyle={[styles.sheetSaveLabel, useJua && styles.juaLabel]}
        onPress={onPress}
        testID="home-checkin"
        trailing={<CheckinChevronIcon />}
      />
    </View>
  );
}

function EmptyRoutineCard() {
  const styles = useHomeStyles();
  return (
    <View style={styles.messageCard} testID="home-empty-state">
      <Text style={styles.messageTitle}>아직 오늘의 운동이 없어요</Text>
      <Text style={styles.messageText}>
        오늘 체크인을 하면 컨디션에 맞는 추천 루틴을 받아볼 수 있어요.
      </Text>
    </View>
  );
}

function HomeStateCard({
  actionLabel,
  onAction,
  serious = false,
  testID,
  text,
  title,
}: {
  actionLabel?: string;
  onAction?: () => void;
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

function GeneratingRoutineCard() {
  const styles = useHomeStyles();
  const [spin] = useState(() => new Animated.Value(0));
  useEffect(() => {
    const animation = Animated.loop(
      Animated.timing(spin, {
        duration: 800,
        toValue: 1,
        useNativeDriver: true,
      }),
    );
    animation.start();
    return () => animation.stop();
  }, [spin]);
  const rotate = spin.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });
  return (
    <View style={styles.messageCard} testID="home-loading-state">
      <Animated.View
        style={[styles.loadingRing, { transform: [{ rotate }] }]}
        testID="home-loading-ring"
      />
      <Text style={[styles.messageTitle, styles.loadingTitle]}>
        새로운 루틴을 받고 있어요
      </Text>
      <Text style={styles.messageText}>
        요청한 운동 시간에 맞춰 다시 구성하는 중이에요.
      </Text>
    </View>
  );
}

const ROUTINE_NOTES = [
  '오늘 컨디션과 운동 목표를 반영했어요.',
  '현재 장소와 장비로 진행할 수 있는 구성이에요.',
] as const;

function RoutineCard({
  actionCode,
  editLabel,
  focus,
  items,
  minutes,
  notes = ROUTINE_NOTES,
  onEdit,
  onMove,
  onOpenExercise,
  onOpenReasons,
  onRest,
  onRequestAlternative,
  onStart,
  painPart,
  pending,
  rerolling,
  rerolls,
  revisionNotice,
  startBlockedReason,
  title,
  useJua,
}: {
  actionCode?: ActionCode;
  editLabel: string;
  focus: string;
  items: readonly HomeRoutineItem[];
  minutes: string;
  notes?: readonly string[];
  onEdit: () => void;
  onMove?: (from: number, to: number) => void;
  onOpenExercise?: (item: HomeRoutineItem) => void;
  onOpenReasons?: () => void;
  onRest?: () => void;
  onRequestAlternative: () => void;
  onStart?: () => void;
  painPart: string | null;
  pending: boolean;
  rerolling: boolean;
  rerolls: number;
  revisionNotice?: string;
  startBlockedReason?: string | null;
  title: string;
  useJua: boolean;
}) {
  const styles = useHomeStyles();
  const drag = useDragController(onMove ?? (() => undefined));
  const rerollLabel = getHomeRerollLabel(rerolls, rerolling);
  const routineActionLabel =
    actionCode === undefined ? null : actionLabel(actionCode);
  const adjustedAction =
    actionCode === 'DOWNSHIFT' ||
    actionCode === 'CHANGE' ||
    actionCode === 'RECOVERY';
  return (
    <View style={styles.routineCard} testID="home-routine-state">
      <View style={styles.routineBadgeRow}>
        <View style={styles.routineBadge}>
          <Text style={styles.routineBadgeText}>오늘의 운동</Text>
        </View>
        {routineActionLabel === null ? null : (
          <View
            accessible
            accessibilityLabel={`루틴 진행 방식: ${routineActionLabel}`}
            style={[
              styles.routineActionBadge,
              adjustedAction && styles.routineActionBadgeAdjusted,
            ]}
          >
            <Text style={styles.routineActionBadgeText}>
              {routineActionLabel}
            </Text>
          </View>
        )}
      </View>
      <Text style={styles.routineTitle}>{title}</Text>
      <Text style={styles.routineSummary}>
        {focus} · 희망 운동 시간 {minutes}분
      </Text>
      <View style={styles.routineNotes}>
        {notes.map((note) => (
          <Text key={note} style={styles.routineNote}>
            {note}
          </Text>
        ))}
      </View>
      {onOpenReasons ? (
        <Pressable
          accessibilityRole="button"
          onPress={onOpenReasons}
          style={styles.reasonLink}
        >
          <Text style={styles.reasonLinkText}>추천 이유 보기</Text>
        </Pressable>
      ) : null}
      <View style={styles.routineList}>
        {onMove ? (
          <Text style={styles.orderHint}>핸들을 끌어 순서를 바꿔보세요</Text>
        ) : null}
        {items.map((item, index) => {
          const { activeIndex, targetIndex } = drag;
          const active = activeIndex === index;
          const dropTarget =
            activeIndex !== null &&
            targetIndex !== null &&
            targetIndex !== activeIndex &&
            targetIndex === index;
          return (
            <View
              key={item.id}
              onLayout={(event) => drag.register(index, event)}
              style={[
                styles.dragOuterRoutine,
                active && styles.dragOuterActive,
              ]}
              testID={`routine-row-${item.id}`}
            >
              {dropTarget ? (
                <View
                  pointerEvents="none"
                  style={styles.dropPlaceholder}
                  testID={`routine-drop-placeholder-${item.id}`}
                />
              ) : null}
              <Animated.View
                style={[
                  styles.routineRow,
                  active && styles.dragInnerRoutineActive,
                  {
                    transform: [
                      {
                        translateY: active
                          ? drag.dragY
                          : drag.getItemShift(index),
                      },
                    ],
                  },
                ]}
              >
                {onMove ? (
                  <DragHandle
                    index={index}
                    onEnd={drag.end}
                    onKeyboardMove={(direction) =>
                      drag.keyboardMove(index, direction, items.length)
                    }
                    onMove={drag.move}
                    onStart={drag.start}
                    style={styles.routineHandle}
                    testID={`routine-drag-${item.id}`}
                  >
                    <RoutineDragIcon />
                  </DragHandle>
                ) : null}
                {onOpenExercise &&
                item.exerciseId &&
                item.instructionAvailable ? (
                  <Pressable
                    accessibilityLabel={`${item.name} 운동 설명 보기`}
                    accessibilityRole="button"
                    onPress={() => onOpenExercise(item)}
                    style={styles.routineItemButton}
                  >
                    <Text style={styles.routineItemText}>
                      {formatRoutineItem(item)}
                    </Text>
                  </Pressable>
                ) : (
                  <Text style={styles.routineItemText}>
                    {formatRoutineItem(item)}
                  </Text>
                )}
                <View style={styles.routineDot} />
              </Animated.View>
            </View>
          );
        })}
      </View>

      {painPart ? (
        <View style={styles.adjustmentNote}>
          <Text style={styles.adjustmentText}>
            {painPart} 부담을 줄이도록 강도를 조정했어요.
          </Text>
        </View>
      ) : null}

      {revisionNotice ? (
        <View style={styles.adjustmentNote}>
          <Text style={styles.adjustmentText}>{revisionNotice}</Text>
        </View>
      ) : null}

      {startBlockedReason ? (
        <Text accessibilityRole="alert" style={styles.messageText}>
          {startBlockedReason}
        </Text>
      ) : null}

      <Pressable
        accessibilityLabel="운동 시작하기"
        accessibilityRole="button"
        accessibilityState={{ disabled: pending || !onStart }}
        disabled={pending || !onStart}
        onPress={onStart}
        style={[
          styles.startButton,
          (pending || !onStart) && styles.routineActionDisabled,
        ]}
      >
        <Text style={[styles.startLabel, useJua && styles.juaLabel]}>
          운동 시작하기
        </Text>
        <StartChevronIcon />
      </Pressable>
      <View style={styles.routineActions}>
        <Pressable
          accessibilityLabel={editLabel}
          accessibilityRole="button"
          onPress={onEdit}
          style={styles.routineAction}
        >
          <EditIcon />
          <Text style={styles.editActionLabel}>{editLabel}</Text>
        </Pressable>
        <Pressable
          accessibilityLabel="다른 루틴 추천 받기"
          accessibilityRole="button"
          accessibilityState={{
            disabled: pending || rerolling || rerolls >= 2,
          }}
          disabled={pending || rerolling || rerolls >= 2}
          onPress={onRequestAlternative}
          style={[
            styles.routineAction,
            rerolls >= 2 && styles.routineActionDisabled,
          ]}
        >
          <RerollIcon color={rerolls >= 2 ? '#B0ACA4' : '#A45F00'} />
          <Text
            numberOfLines={1}
            style={[
              styles.rerollActionLabel,
              rerolls >= 2 && styles.rerollActionLabelDisabled,
            ]}
          >
            {rerollLabel}
          </Text>
        </Pressable>
      </View>
      {onRest ? (
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: pending }}
          disabled={pending}
          onPress={onRest}
          style={styles.routineAction}
        >
          <Text style={styles.editActionLabel}>오늘은 쉬기</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function HomeBottomNavigation({
  activeTab,
  onNavigate,
}: {
  activeTab: HomeTab;
  onNavigate?: (tab: HomeTab) => void;
}) {
  const insets = useSafeAreaInsets();
  const homeColor = activeTab === 'home' ? '#A45F00' : '#B0ACA4';
  const logColor = activeTab === 'house' ? '#A45F00' : '#B0ACA4';
  const reportColor = activeTab === 'report' ? '#A45F00' : '#B0ACA4';
  const myColor = activeTab === 'my' ? '#A45F00' : '#B0ACA4';
  return (
    <View
      style={[
        bottomNavigationStyles.bottomBarOuter,
        { paddingBottom: bottomNavigationBottomPadding(insets.bottom) },
      ]}
      testID="bottom-navigation"
    >
      <View
        accessibilityRole="tablist"
        style={bottomNavigationStyles.bottomBar}
      >
        <TabButton
          active={activeTab === 'home'}
          icon={<HomeTabIcon color={homeColor} />}
          label="홈"
          onPress={() => onNavigate?.('home')}
        />
        <TabButton
          active={activeTab === 'house'}
          icon={<LogTabIcon color={logColor} />}
          label="끼끼의 집"
          onPress={() => onNavigate?.('house')}
        />
        <TabButton
          active={activeTab === 'report'}
          icon={<ReportTabIcon color={reportColor} />}
          label="리포트"
          onPress={() => onNavigate?.('report')}
        />
        <TabButton
          active={activeTab === 'my'}
          icon={<MyTabIcon color={myColor} />}
          label="마이페이지"
          onPress={() => onNavigate?.('my')}
        />
      </View>
    </View>
  );
}

export function bottomNavigationBottomPadding(safeAreaBottom: number) {
  return Math.max(HOME_LAYOUT.bottomBarBottomPadding, safeAreaBottom);
}

function TabButton({
  active,
  icon,
  label,
  onPress,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="tab"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={bottomNavigationStyles.tab}
    >
      {icon}
      <Text
        style={[
          bottomNavigationStyles.tabLabel,
          active && bottomNavigationStyles.tabActive,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function SheetFrame({
  children,
  onClose,
  title,
  zIndex,
}: {
  children: React.ReactNode;
  onClose: () => void;
  title: string;
  zIndex: number;
}) {
  const styles = useHomeStyles();
  const stopPropagation = (event: GestureResponderEvent) =>
    event.stopPropagation();
  return (
    <Pressable
      accessibilityViewIsModal
      onPress={onClose}
      style={[styles.sheetOverlay, { zIndex }]}
    >
      <Pressable onPress={stopPropagation} style={styles.sheet}>
        <View style={styles.sheetHeader}>
          <Text accessibilityRole="header" style={styles.sheetTitle}>
            {title}
          </Text>
          <Pressable
            accessibilityLabel="닫기"
            accessibilityRole="button"
            onPress={onClose}
            style={styles.closeButton}
          >
            <Text style={styles.closeText}>×</Text>
          </Pressable>
        </View>
        {children}
      </Pressable>
    </Pressable>
  );
}

function RecommendationReasonSheet({
  decision,
  onClose,
  reasons,
}: {
  decision: DecisionResponse;
  onClose: () => void;
  reasons: readonly string[];
}) {
  const styles = useHomeStyles();
  const agentSummaries = decision.public_agent_summaries ?? [];
  return (
    <SheetFrame onClose={onClose} title="추천 이유" zIndex={24}>
      <Text style={styles.sheetIntro}>
        저장된 체크인과 안전 기준을 바탕으로 서버가 결정한 내용이에요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.reasonSheetContent}
        showsVerticalScrollIndicator={false}
      >
        {reasons.length > 0 ? (
          <View style={styles.reasonSection}>
            <Text style={styles.checkinSectionTitle}>반영한 기준</Text>
            {reasons.map((reason) => (
              <View key={reason} style={styles.reasonRow}>
                <Text style={styles.reasonBullet}>•</Text>
                <Text style={styles.reasonText}>{reason}</Text>
              </View>
            ))}
          </View>
        ) : null}

        {decision.safety_summary?.summary ? (
          <View
            accessibilityRole={
              decision.safety_summary.vetoed ? 'alert' : undefined
            }
            style={[
              styles.reasonSection,
              decision.safety_summary.vetoed && styles.safetyReasonSection,
            ]}
          >
            <Text
              style={[
                styles.checkinSectionTitle,
                decision.safety_summary.vetoed && styles.safetyReasonTitle,
              ]}
            >
              안전 확인
            </Text>
            <Text
              style={[
                styles.reasonText,
                decision.safety_summary.vetoed && styles.safetyReasonText,
              ]}
            >
              {decision.safety_summary.summary}
            </Text>
          </View>
        ) : null}

        {agentSummaries.length > 0 ? (
          <View style={styles.reasonSection}>
            <Text style={styles.checkinSectionTitle}>상세 판단</Text>
            {agentSummaries.map((summary) => (
              <View
                key={`${summary.agent_type_code}-${summary.summary}`}
                style={styles.agentSummary}
              >
                <Text style={styles.agentSummaryLabel}>
                  {agentTypeLabel(summary.agent_type_code)}
                </Text>
                <Text style={styles.reasonText}>{summary.summary}</Text>
              </View>
            ))}
          </View>
        ) : null}
      </ScrollView>
    </SheetFrame>
  );
}

function CheckinSheet({
  draft,
  onAddAvailabilitySlot,
  onChangeFatigue,
  onChangeLocation,
  onChangeSeverity,
  onChangeSleepHours,
  onChangeWorkoutMinutes,
  onClearAdverseReactions,
  onClearDiscomforts,
  onClose,
  onOpenTimePicker,
  onSave,
  onRemoveAvailabilitySlot,
  onToggleAdverseReaction,
  onToggleBodyArea,
  locationCodes,
  pending,
  useJua,
}: {
  draft: HomeCheckin;
  onAddAvailabilitySlot: () => void;
  onChangeFatigue: (value: string) => void;
  onChangeLocation: (code: string) => void;
  onChangeSeverity: (
    bodyAreaCode: string,
    severity: DiscomfortSeverityCode,
  ) => void;
  onChangeSleepHours: (value: string) => void;
  onChangeWorkoutMinutes: (value: string) => void;
  onClearAdverseReactions: () => void;
  onClearDiscomforts: () => void;
  onClose: () => void;
  onOpenTimePicker: (index: number, field: keyof HomeAvailabilitySlot) => void;
  onSave: () => void;
  onRemoveAvailabilitySlot: (index: number) => void;
  onToggleAdverseReaction: (code: string) => void;
  onToggleBodyArea: (code: string) => void;
  locationCodes: readonly string[];
  pending: boolean;
  useJua: boolean;
}) {
  const styles = useHomeStyles();
  const [showAdverseDetails, setShowAdverseDetails] = useState(
    draft.adverseReactionCodes.length > 0,
  );
  const [showDiscomfortDetails, setShowDiscomfortDetails] = useState(
    Object.keys(draft.discomforts).length > 0,
  );
  const selectedDiscomfortCodes = Object.keys(draft.discomforts);
  const [showExtendedAreas, setShowExtendedAreas] = useState(() =>
    selectedDiscomfortCodes.some((code) =>
      EXTENDED_BODY_AREA_OPTIONS.some((option) => option.code === code),
    ),
  );
  const selectableCodes = new Set<string>(
    [...DEFAULT_BODY_AREA_OPTIONS, ...EXTENDED_BODY_AREA_OPTIONS].map(
      (option) => option.code,
    ),
  );
  const legacySelectedCodes = selectedDiscomfortCodes.filter(
    (code) => !selectableCodes.has(code),
  );
  const sleepHours = draft.sleepHours.trim();
  const sleepInvalid =
    sleepHours !== '' &&
    (!Number.isFinite(Number(sleepHours)) ||
      Number(sleepHours) < 0 ||
      Number(sleepHours) > 24);
  const durationInvalid =
    !/^\d+$/.test(draft.workoutMinutes) ||
    Number(draft.workoutMinutes) < CHECKIN_DURATION_MINUTES.min ||
    Number(draft.workoutMinutes) > CHECKIN_DURATION_MINUTES.max;
  const durationMinutes = Number(draft.workoutMinutes);
  const canDecreaseDuration =
    !pending &&
    !durationInvalid &&
    durationMinutes > CHECKIN_DURATION_MINUTES.min;
  const canIncreaseDuration =
    !pending &&
    !durationInvalid &&
    durationMinutes < CHECKIN_DURATION_MINUTES.max;
  const availabilityError = CHECKIN_AVAILABILITY_INPUT_ENABLED
    ? validateAvailabilitySlots(draft.availableSlots)
    : null;
  const availabilitySlots =
    draft.availableSlots && draft.availableSlots.length > 0
      ? draft.availableSlots
      : [EMPTY_AVAILABILITY_SLOT];
  const adverseSelectionMissing =
    showAdverseDetails && draft.adverseReactionCodes.length === 0;
  const discomfortSelectionMissing =
    showDiscomfortDetails && Object.keys(draft.discomforts).length === 0;
  const saveDisabled =
    pending ||
    sleepInvalid ||
    durationInvalid ||
    availabilityError !== null ||
    adverseSelectionMissing ||
    discomfortSelectionMissing;
  return (
    <SheetFrame onClose={onClose} title="오늘 컨디션 체크" zIndex={20}>
      <Text style={styles.sheetIntro}>
        오늘 상태를 알려주면 루틴을 맞춰 조정해드려요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.sheetScrollContent}
        showsVerticalScrollIndicator={false}
      >
        <ChoiceBlock label="피로도">
          {HOME_CHECKIN_OPTIONS.fatigue.map((option) => (
            <ChoiceButton
              key={option}
              label={option}
              onPress={() => onChangeFatigue(option)}
              selected={draft.fatigue === option}
            />
          ))}
        </ChoiceBlock>
        <View style={styles.numberRow}>
          <Text style={styles.numberLabel}>원하는 운동 시간</Text>
          <View style={styles.durationStepper}>
            <Pressable
              accessibilityLabel="운동 시간 10분 줄이기"
              accessibilityRole="button"
              accessibilityState={{ disabled: !canDecreaseDuration }}
              disabled={!canDecreaseDuration}
              onPress={() =>
                onChangeWorkoutMinutes(
                  String(
                    Math.max(
                      CHECKIN_DURATION_MINUTES.min,
                      durationMinutes - CHECKIN_DURATION_MINUTES.step,
                    ),
                  ),
                )
              }
              style={[
                styles.durationStepButton,
                !canDecreaseDuration && styles.durationStepButtonDisabled,
              ]}
            >
              <Text style={styles.durationStepButtonText}>−</Text>
            </Pressable>
            <Text
              accessibilityLabel={`원하는 운동 시간 ${draft.workoutMinutes}분`}
              accessibilityLiveRegion="polite"
              style={styles.durationStepValue}
            >
              {draft.workoutMinutes}분
            </Text>
            <Pressable
              accessibilityLabel="운동 시간 10분 늘리기"
              accessibilityRole="button"
              accessibilityState={{ disabled: !canIncreaseDuration }}
              disabled={!canIncreaseDuration}
              onPress={() =>
                onChangeWorkoutMinutes(
                  String(
                    Math.min(
                      CHECKIN_DURATION_MINUTES.max,
                      durationMinutes + CHECKIN_DURATION_MINUTES.step,
                    ),
                  ),
                )
              }
              style={[
                styles.durationStepButton,
                !canIncreaseDuration && styles.durationStepButtonDisabled,
              ]}
            >
              <Text style={styles.durationStepButtonText}>+</Text>
            </Pressable>
          </View>
        </View>
        {CHECKIN_AVAILABILITY_INPUT_ENABLED ? (
          <>
            <View style={styles.availabilitySection}>
              <View style={styles.availabilityHeader}>
                <Text style={styles.numberLabel}>오늘 운동 가능한 시간대</Text>
                <Text style={styles.optionalText}>(선택)</Text>
              </View>
              {availabilitySlots.map((slot, index) => (
                <View key={index} style={styles.availabilitySlotRow}>
                  <Pressable
                    accessibilityLabel={`${index + 1}번째 가능 시간 시작 ${slot.startTime || '미선택'} 선택`}
                    accessibilityRole="button"
                    disabled={pending}
                    onPress={() => onOpenTimePicker(index, 'startTime')}
                    style={styles.availabilityTimeButton}
                  >
                    <Text
                      style={[
                        styles.availabilityTimeText,
                        !slot.startTime && styles.availabilityTimePlaceholder,
                      ]}
                    >
                      {slot.startTime || '시간:분'}
                    </Text>
                  </Pressable>
                  <Text style={styles.availabilitySeparator}>~</Text>
                  <Pressable
                    accessibilityLabel={`${index + 1}번째 가능 시간 종료 ${slot.endTime || '미선택'} 선택`}
                    accessibilityRole="button"
                    disabled={pending}
                    onPress={() => onOpenTimePicker(index, 'endTime')}
                    style={styles.availabilityTimeButton}
                  >
                    <Text
                      style={[
                        styles.availabilityTimeText,
                        !slot.endTime && styles.availabilityTimePlaceholder,
                      ]}
                    >
                      {slot.endTime || '시간:분'}
                    </Text>
                  </Pressable>
                  {availabilitySlots.length > 1 ? (
                    <Pressable
                      accessibilityLabel={`${index + 1}번째 가능 시간대 삭제`}
                      accessibilityRole="button"
                      hitSlop={8}
                      onPress={() => onRemoveAvailabilitySlot(index)}
                      style={styles.availabilityRemoveButton}
                    >
                      <DeleteIcon />
                    </Pressable>
                  ) : null}
                </View>
              ))}
              <Pressable
                accessibilityLabel="가능 시간대 추가"
                accessibilityRole="button"
                accessibilityState={{
                  disabled: availabilitySlots.length >= 8,
                }}
                disabled={availabilitySlots.length >= 8}
                onPress={onAddAvailabilitySlot}
                style={[
                  styles.availabilityAddButton,
                  availabilitySlots.length >= 8 && styles.routineActionDisabled,
                ]}
              >
                <Text style={styles.availabilityAddLabel}>＋ 시간대 추가</Text>
              </Pressable>
              <Text style={styles.availabilityHelpText}>
                운동을 시작할 수 있는 시간 범위를 입력해주세요.
              </Text>
            </View>
            {availabilityError ? (
              <Text accessibilityRole="alert" style={styles.messageText}>
                {availabilityError}
              </Text>
            ) : null}
          </>
        ) : null}
        <View style={styles.numberRow}>
          <Text style={styles.numberLabel}>
            어젯밤 수면 시간 <Text style={styles.optionalText}>(선택)</Text>
          </Text>
          <View style={styles.numberInputGroup}>
            <TextInput
              accessibilityLabel="어젯밤 수면 시간 (시간)"
              inputMode="decimal"
              onChangeText={onChangeSleepHours}
              style={styles.numberInput}
              value={draft.sleepHours}
            />
            <Text style={styles.numberSuffix}>시간</Text>
          </View>
        </View>
        {sleepInvalid ? (
          <Text accessibilityRole="alert" style={styles.messageText}>
            수면 시간은 0~24 사이로 입력해주세요.
          </Text>
        ) : null}
        {locationCodes.length > 1 ? (
          <ChoiceBlock label="오늘 운동 장소">
            {locationCodes.map((code) => (
              <ChoiceButton
                key={code}
                label={locationLabel(code)}
                onPress={() => onChangeLocation(code)}
                selected={draft.locationCode === code}
              />
            ))}
          </ChoiceBlock>
        ) : null}
        <ChoiceBlock label="오늘 불편한 부위가 있나요?">
          <ChoiceButton
            label="없음"
            onPress={() => {
              setShowDiscomfortDetails(false);
              onClearDiscomforts();
            }}
            selected={!showDiscomfortDetails}
          />
          <ChoiceButton
            label="있음"
            onPress={() => setShowDiscomfortDetails(true)}
            selected={showDiscomfortDetails}
          />
        </ChoiceBlock>
        {showDiscomfortDetails ? (
          <>
            <ChoiceBlock label="오늘 불편한 부위를 모두 선택해주세요" twoColumn>
              {DEFAULT_BODY_AREA_OPTIONS.map((option) => (
                <ChoiceButton
                  key={option.code}
                  label={option.label}
                  numberOfLines={2}
                  onPress={() => onToggleBodyArea(option.code)}
                  selected={draft.discomforts[option.code] !== undefined}
                  twoColumn
                />
              ))}
              <ChoiceButton
                label={
                  showExtendedAreas ? '다른 부위 접기' : '다른 부위 더 보기'
                }
                numberOfLines={2}
                onPress={() => setShowExtendedAreas((visible) => !visible)}
                selected={showExtendedAreas}
                twoColumn
              />
              {showExtendedAreas
                ? EXTENDED_BODY_AREA_OPTIONS.map((option) => (
                    <ChoiceButton
                      key={option.code}
                      label={option.label}
                      numberOfLines={2}
                      onPress={() => onToggleBodyArea(option.code)}
                      selected={draft.discomforts[option.code] !== undefined}
                      twoColumn
                    />
                  ))
                : null}
            </ChoiceBlock>
            {legacySelectedCodes.length > 0 ? (
              <ChoiceBlock label="이전에 저장된 부위 (해제만 가능)" twoColumn>
                {legacySelectedCodes.map((code) => (
                  <ChoiceButton
                    key={code}
                    label={bodyAreaLabel(code)}
                    numberOfLines={2}
                    onPress={() => onToggleBodyArea(code)}
                    selected
                    twoColumn
                  />
                ))}
              </ChoiceBlock>
            ) : null}
          </>
        ) : null}
        {discomfortSelectionMissing ? (
          <Text accessibilityRole="alert" style={styles.messageText}>
            불편한 부위를 한 곳 이상 선택해주세요.
          </Text>
        ) : null}
        {selectedDiscomfortCodes.map((code) => (
          <ChoiceBlock key={code} label={`${bodyAreaLabel(code)} 통증 정도`}>
            {SEVERITY_OPTIONS.map((option) => (
              <ChoiceButton
                key={option.code}
                label={option.label}
                onPress={() => onChangeSeverity(code, option.code)}
                selected={draft.discomforts[code] === option.code}
              />
            ))}
          </ChoiceBlock>
        ))}
        <ChoiceBlock label="운동을 멈춰야 할 이상 반응">
          <ChoiceButton
            label="없어요"
            onPress={() => {
              setShowAdverseDetails(false);
              onClearAdverseReactions();
            }}
            selected={
              !showAdverseDetails && draft.adverseReactionCodes.length === 0
            }
          />
          <ChoiceButton
            label="있어요"
            onPress={() => setShowAdverseDetails(true)}
            selected={showAdverseDetails}
          />
        </ChoiceBlock>
        {showAdverseDetails ? (
          <View style={styles.adverseSection}>
            <Text style={styles.adverseTitle}>이런 증상이 있나요?</Text>
            <Text style={styles.adverseBody}>
              해당하는 항목이 있으면 선택해주세요. 안전을 위해 운동을 중단하도록
              안내할 수 있어요.
            </Text>
            <View style={styles.adverseChoiceList}>
              {ADVERSE_REACTION_OPTIONS.map((option) => (
                <AdverseReactionButton
                  key={option.code}
                  label={option.label}
                  onPress={() => onToggleAdverseReaction(option.code)}
                  selected={draft.adverseReactionCodes.includes(option.code)}
                />
              ))}
            </View>
          </View>
        ) : null}
        {adverseSelectionMissing ? (
          <Text accessibilityRole="alert" style={styles.messageText}>
            해당하는 이상 반응을 하나 이상 선택해주세요.
          </Text>
        ) : null}
        <Pressable
          accessibilityLabel="체크인 !"
          accessibilityRole="button"
          accessibilityState={{ disabled: saveDisabled }}
          disabled={saveDisabled}
          onPress={onSave}
          style={[
            styles.sheetSaveButton,
            saveDisabled && styles.routineActionDisabled,
          ]}
        >
          <LinearGradient
            colors={['#FEE8B1', '#FEDA99', '#FFD790']}
            end={{ x: 0.5, y: 1 }}
            locations={[0, 0.55, 1]}
            pointerEvents="none"
            start={{ x: 0.5, y: 0 }}
            style={styles.sheetSaveGradient}
            testID="home-checkin-submit-gradient"
          />
          <Text style={[styles.sheetSaveLabel, useJua && styles.juaLabel]}>
            {pending ? '보내는 중…' : '체크인 !'}
          </Text>
        </Pressable>
      </ScrollView>
    </SheetFrame>
  );
}

function TimePickerSheet({
  initialValue,
  onClose,
  onConfirm,
  targetField,
}: {
  initialValue: string;
  onClose: () => void;
  onConfirm: (value: string) => void;
  targetField: keyof HomeAvailabilitySlot;
}) {
  const styles = useHomeStyles();
  const match = /^(\d{2}):(\d{2})$/.exec(initialValue);
  const parsedMinute = match ? Number(match[2]) : 0;
  const normalizedMinute = Math.min(55, Math.round(parsedMinute / 5) * 5);
  const [hour, setHour] = useState(
    match ? Number(match[1]) : targetField === 'startTime' ? 0 : 12,
  );
  const [minute, setMinute] = useState(normalizedMinute);
  const title =
    targetField === 'startTime' ? '시작 시간 선택' : '종료 시간 선택';

  return (
    <SheetFrame onClose={onClose} title={title} zIndex={30}>
      <Text style={styles.timePickerIntro}>
        시간과 분을 스크롤해 선택해주세요.
      </Text>
      <View style={styles.timePickerRow}>
        <TimeWheelColumn
          accessibilityLabel="시간 선택 스크롤"
          onChange={setHour}
          options={TIME_HOURS}
          selected={hour}
          suffix="시"
        />
        <Text style={styles.timePickerColon}>:</Text>
        <TimeWheelColumn
          accessibilityLabel="분 선택 스크롤"
          onChange={setMinute}
          options={TIME_MINUTES}
          selected={minute}
          suffix="분"
        />
      </View>
      <View style={styles.timePickerActions}>
        <Pressable
          accessibilityRole="button"
          onPress={onClose}
          style={styles.timePickerCancelButton}
        >
          <Text style={styles.timePickerCancelLabel}>취소</Text>
        </Pressable>
        <Pressable
          accessibilityLabel="시간 선택 완료"
          accessibilityRole="button"
          onPress={() =>
            onConfirm(
              `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`,
            )
          }
          style={styles.timePickerConfirmButton}
        >
          <Text style={styles.timePickerConfirmLabel}>선택</Text>
        </Pressable>
      </View>
    </SheetFrame>
  );
}

function TimeWheelColumn({
  accessibilityLabel,
  onChange,
  options,
  selected,
  suffix,
}: {
  accessibilityLabel: string;
  onChange: (value: number) => void;
  options: readonly number[];
  selected: number;
  suffix: string;
}) {
  const styles = useHomeStyles();
  const scrollRef = useRef<ScrollView>(null);
  const selectedIndex = Math.max(0, options.indexOf(selected));
  const currentIndexRef = useRef(selectedIndex);
  const pendingInternalSelectionRef = useRef<number | null>(null);
  const webSettleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const webWheelGestureTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const webWheelDeltaRef = useRef(0);
  const draggingRef = useRef(false);

  const clearWebSettleTimer = useCallback(() => {
    if (webSettleTimerRef.current !== null) {
      clearTimeout(webSettleTimerRef.current);
      webSettleTimerRef.current = null;
    }
  }, []);

  const clearWebWheelGestureTimer = useCallback(() => {
    if (webWheelGestureTimerRef.current !== null) {
      clearTimeout(webWheelGestureTimerRef.current);
      webWheelGestureTimerRef.current = null;
    }
  }, []);

  const scrollToIndex = useCallback((index: number, animated: boolean) => {
    scrollRef.current?.scrollTo({
      animated,
      y: index * TIME_WHEEL_ITEM_HEIGHT,
    });
  }, []);

  const commitIndex = useCallback(
    (index: number) => {
      const boundedIndex = Math.max(0, Math.min(options.length - 1, index));
      const value = options[boundedIndex];
      if (value === undefined) return;
      currentIndexRef.current = boundedIndex;
      if (value !== selected) {
        pendingInternalSelectionRef.current = value;
        onChange(value);
      }
    },
    [onChange, options, selected],
  );

  const selectIndex = useCallback(
    (index: number, animated = true) => {
      const boundedIndex = Math.max(0, Math.min(options.length - 1, index));
      scrollToIndex(boundedIndex, animated);
      commitIndex(boundedIndex);
    },
    [commitIndex, options.length, scrollToIndex],
  );

  const settleAtOffset = useCallback(
    (offsetY: number, align = true) => {
      const index = Math.max(
        0,
        Math.min(
          options.length - 1,
          Math.round(offsetY / TIME_WHEEL_ITEM_HEIGHT),
        ),
      );
      const targetOffset = index * TIME_WHEEL_ITEM_HEIGHT;
      if (align && Math.abs(offsetY - targetOffset) > 1) {
        scrollToIndex(index, true);
      }
      commitIndex(index);
    },
    [commitIndex, options.length, scrollToIndex],
  );

  useEffect(() => {
    currentIndexRef.current = selectedIndex;
    if (pendingInternalSelectionRef.current === selected) {
      pendingInternalSelectionRef.current = null;
      return;
    }
    pendingInternalSelectionRef.current = null;
    scrollToIndex(selectedIndex, false);
  }, [scrollToIndex, selected, selectedIndex]);

  useEffect(
    () => () => {
      clearWebSettleTimer();
      clearWebWheelGestureTimer();
    },
    [clearWebSettleTimer, clearWebWheelGestureTimer],
  );

  const settleFromScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    clearWebSettleTimer();
    draggingRef.current = false;
    settleAtOffset(event.nativeEvent.contentOffset.y, false);
  };

  const handleScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (Platform.OS !== 'web' || draggingRef.current) return;
    const offsetY = event.nativeEvent.contentOffset.y;
    clearWebSettleTimer();
    webSettleTimerRef.current = setTimeout(() => {
      settleAtOffset(offsetY);
      webSettleTimerRef.current = null;
    }, 90);
  };

  const queueWheelDelta = useCallback(
    (deltaY: number, deltaMode = 0) => {
      clearWebSettleTimer();
      if (deltaY === 0) return;
      const modeMultiplier =
        deltaMode === 1 ? 16 : deltaMode === 2 ? TIME_WHEEL_ITEM_HEIGHT * 3 : 1;
      const normalizedDelta = deltaY * modeMultiplier;
      if (
        webWheelDeltaRef.current !== 0 &&
        Math.sign(webWheelDeltaRef.current) !== Math.sign(normalizedDelta)
      ) {
        webWheelDeltaRef.current = 0;
      }
      webWheelDeltaRef.current += normalizedDelta;
      clearWebWheelGestureTimer();
      webWheelGestureTimerRef.current = setTimeout(() => {
        const accumulatedDelta = webWheelDeltaRef.current;
        webWheelDeltaRef.current = 0;
        webWheelGestureTimerRef.current = null;
        const magnitude = Math.abs(accumulatedDelta);
        const steps =
          magnitude <= TIME_WHEEL_SINGLE_ITEM_DELTA
            ? 1
            : Math.min(
                TIME_WHEEL_MAX_ITEMS_PER_GESTURE,
                1 +
                  Math.round(
                    (magnitude - TIME_WHEEL_SINGLE_ITEM_DELTA) /
                      TIME_WHEEL_ACCELERATION_DELTA,
                  ),
              );
        selectIndex(
          currentIndexRef.current + Math.sign(accumulatedDelta) * steps,
        );
      }, TIME_WHEEL_GESTURE_IDLE_MS);
    },
    [clearWebSettleTimer, clearWebWheelGestureTimer, selectIndex],
  );

  const handleWheel = (
    event: NativeSyntheticEvent<{
      deltaMode?: number;
      deltaY: number;
    }>,
  ) => {
    event.preventDefault();
    queueWheelDelta(event.nativeEvent.deltaY, event.nativeEvent.deltaMode);
  };

  useEffect(() => {
    if (Platform.OS !== 'web' || scrollRef.current === null) return;
    const scrollNode = scrollRef.current.getScrollableNode?.() as
      HTMLElement | undefined;
    if (scrollNode?.addEventListener === undefined) return;
    const preventNativeWheelScroll = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      queueWheelDelta(event.deltaY, event.deltaMode);
    };
    scrollNode.addEventListener('wheel', preventNativeWheelScroll, {
      passive: false,
    });
    return () => {
      scrollNode.removeEventListener('wheel', preventNativeWheelScroll);
    };
  }, [queueWheelDelta]);

  const webWheelProps =
    Platform.OS === 'web' ? { onWheel: handleWheel } : undefined;

  return (
    <View style={styles.timeWheelColumn}>
      <ScrollView
        ref={scrollRef}
        accessibilityLabel={accessibilityLabel}
        contentContainerStyle={styles.timeWheelContent}
        decelerationRate="fast"
        disableIntervalMomentum
        nestedScrollEnabled
        onMomentumScrollBegin={() => {
          draggingRef.current = true;
          clearWebSettleTimer();
        }}
        onMomentumScrollEnd={settleFromScroll}
        onScroll={handleScroll}
        onScrollBeginDrag={() => {
          draggingRef.current = true;
          clearWebSettleTimer();
        }}
        onScrollEndDrag={(event) => {
          draggingRef.current = false;
          const velocity = event.nativeEvent.velocity?.y;
          if (velocity !== undefined && Math.abs(velocity) < 0.1) {
            settleFromScroll(event);
            return;
          }
          const offsetY = event.nativeEvent.contentOffset.y;
          clearWebSettleTimer();
          webSettleTimerRef.current = setTimeout(() => {
            settleAtOffset(offsetY);
            webSettleTimerRef.current = null;
          }, 120);
        }}
        scrollEventThrottle={16}
        showsVerticalScrollIndicator={false}
        snapToAlignment="start"
        snapToInterval={TIME_WHEEL_ITEM_HEIGHT}
        style={styles.timeWheelScroll}
        {...webWheelProps}
      >
        {options.map((value, index) => {
          const selectedOption = selected === value;
          const padded = String(value).padStart(2, '0');
          return (
            <Pressable
              accessibilityLabel={`${accessibilityLabel.startsWith('시간') ? '시간' : '분'} ${padded}${suffix}`}
              accessibilityRole="button"
              accessibilityState={{ selected: selectedOption }}
              key={value}
              onPress={() => selectIndex(index)}
              style={styles.timeWheelItem}
            >
              <Text
                style={[
                  styles.timeWheelItemText,
                  selectedOption && styles.timeWheelItemTextSelected,
                ]}
              >
                {padded}
                <Text style={styles.timeWheelItemSuffix}> {suffix}</Text>
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
      <View pointerEvents="none" style={styles.timeWheelSelection} />
    </View>
  );
}

function ChoiceBlock({
  children,
  label,
  twoColumn = false,
}: {
  children: React.ReactNode;
  label: string;
  twoColumn?: boolean;
}) {
  const styles = useHomeStyles();
  return (
    <View style={styles.checkinSection}>
      <Text style={styles.checkinSectionTitle}>{label}</Text>
      <View style={[styles.choiceRow, twoColumn && styles.choiceRowTwoColumn]}>
        {children}
      </View>
    </View>
  );
}

function ChoiceButton({
  label,
  numberOfLines = 1,
  onPress,
  selected,
  twoColumn = false,
}: {
  label: string;
  numberOfLines?: number;
  onPress: () => void;
  selected: boolean;
  twoColumn?: boolean;
}) {
  const styles = useHomeStyles();
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.choiceButton,
        twoColumn && styles.choiceButtonTwoColumn,
        selected && styles.choiceButtonSelected,
      ]}
    >
      <Text
        numberOfLines={numberOfLines}
        style={[
          styles.choiceButtonText,
          selected && styles.choiceButtonTextSelected,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function AdverseReactionButton({
  label,
  onPress,
  selected,
}: {
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  const styles = useHomeStyles();
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.adverseChoiceButton,
        selected && styles.adverseChoiceButtonSelected,
      ]}
    >
      <Text
        style={[
          styles.adverseChoiceText,
          selected && styles.adverseChoiceTextSelected,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function ApiEditRoutineSheet({
  items,
  locationCodes,
  onClose,
  onSave,
  pending,
  routine,
  selectedLocationCode,
  useJua,
}: {
  items: readonly HomeRoutineItem[];
  locationCodes: readonly string[];
  onClose: () => void;
  onSave: (edits: HomeUserEdits) => void;
  pending: boolean;
  routine: RoutineResponse | null;
  selectedLocationCode: string | null;
  useJua: boolean;
}) {
  const styles = useHomeStyles();
  const [locationCode, setLocationCode] = useState<string | null>(
    selectedLocationCode ?? locationCodes[0] ?? null,
  );
  const canSave = routine !== null && locationCode !== null && !pending;
  return (
    <SheetFrame onClose={onClose} title="운동 장소 변경" zIndex={22}>
      <Text style={styles.sheetIntro}>
        운동할 장소를 고르면 서버가 시간·장비·안전 기준을 다시 확인해 계획을
        수정해요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.editScrollContent}
        showsVerticalScrollIndicator={false}
      >
        <ChoiceBlock label="운동 장소">
          {locationCodes.map((code) => (
            <ChoiceButton
              key={code}
              label={locationLabel(code)}
              onPress={() => setLocationCode(code)}
              selected={locationCode === code}
            />
          ))}
        </ChoiceBlock>
        {locationCodes.length === 0 ? (
          <Text style={styles.messageText}>
            프로필에 저장된 운동 장소가 없어요.
          </Text>
        ) : null}
        <View style={styles.editList}>
          <Text style={styles.checkinSectionTitle}>
            현재 계획 {routine === null ? '' : `v${routine.version}`}
          </Text>
          {items.map((item) => (
            <View key={item.id} style={styles.routineRow}>
              <Text style={styles.routineItemText}>
                {formatRoutineItem(item)}
              </Text>
            </View>
          ))}
          <Text style={styles.messageText}>
            운동 구성과 순서는 안전 기준에 따라 서버가 결정해요. 장소를 바꾸면
            가능한 구성으로 다시 확인합니다.
          </Text>
        </View>
        <View style={styles.editActions}>
          <Pressable
            accessibilityRole="button"
            onPress={onClose}
            style={styles.resetButton}
          >
            <Text style={styles.resetLabel}>닫기</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: !canSave }}
            disabled={!canSave}
            onPress={() =>
              routine !== null && locationCode !== null
                ? onSave({ routineId: routine.id, locationCode })
                : undefined
            }
            style={[
              styles.editSaveButton,
              !canSave && styles.routineActionDisabled,
            ]}
          >
            <Text style={[styles.sheetSaveLabel, useJua && styles.juaLabel]}>
              {pending ? '저장 중…' : '저장하기'}
            </Text>
          </Pressable>
        </View>
      </ScrollView>
    </SheetFrame>
  );
}

function EditRoutineSheet({
  items,
  newItem,
  onAdd,
  onChangeItems,
  onChangeNew,
  onClose,
  onMove,
  onReset,
  onSave,
  useJua,
}: {
  items: HomeRoutineItem[];
  newItem: HomeRoutineItem;
  onAdd: () => void;
  onChangeItems: (items: HomeRoutineItem[]) => void;
  onChangeNew: (item: HomeRoutineItem) => void;
  onClose: () => void;
  onMove: (from: number, to: number) => void;
  onReset: () => void;
  onSave: () => void;
  useJua: boolean;
}) {
  const styles = useHomeStyles();
  const drag = useDragController(onMove);
  const patchItem = (id: string, patch: Partial<HomeRoutineItem>) => {
    const next: HomeRoutineItem[] = [];
    for (const item of items) {
      next.push(item.id === id ? { ...item, ...patch } : item);
    }
    onChangeItems(next);
  };
  const removeItem = (id: string) => {
    const next: HomeRoutineItem[] = [];
    for (const item of items) {
      if (item.id !== id) {
        next.push(item);
      }
    }
    onChangeItems(next);
  };
  return (
    <SheetFrame onClose={onClose} title="오늘의 운동 수정" zIndex={22}>
      <Text style={styles.sheetIntro}>
        항목을 직접 고치거나 추가하고, 핸들을 끌어 순서를 바꿀 수 있어요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.editScrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.editList}>
          {items.map((item, index) => {
            const { activeIndex, targetIndex } = drag;
            const active = activeIndex === index;
            const dropTarget =
              activeIndex !== null &&
              targetIndex !== null &&
              targetIndex !== activeIndex &&
              targetIndex === index;
            return (
              <View
                key={item.id}
                onLayout={(event) => drag.register(index, event)}
                style={[styles.dragOuterEdit, active && styles.dragOuterActive]}
              >
                {dropTarget ? (
                  <View
                    pointerEvents="none"
                    style={styles.dropPlaceholder}
                    testID={`edit-drop-placeholder-${item.id}`}
                  />
                ) : null}
                <Animated.View
                  style={[
                    styles.editRow,
                    active && styles.dragInnerEditActive,
                    {
                      transform: [
                        {
                          translateY: active
                            ? drag.dragY
                            : drag.getItemShift(index),
                        },
                      ],
                    },
                  ]}
                >
                  <DragHandle
                    index={index}
                    onEnd={drag.end}
                    onKeyboardMove={(direction) =>
                      drag.keyboardMove(index, direction, items.length)
                    }
                    onMove={drag.move}
                    onStart={drag.start}
                    style={styles.editHandle}
                    testID={`edit-drag-${item.id}`}
                  >
                    <EditDragIcon />
                  </DragHandle>
                  <TextInput
                    accessibilityLabel={`${item.name || '빈 항목'} 운동명`}
                    onChangeText={(name) => patchItem(item.id, { name })}
                    placeholder="운동명"
                    placeholderTextColor="#B8AA9E"
                    style={styles.editNameInput}
                    value={item.name}
                  />
                  <TextInput
                    accessibilityLabel={`${item.name || '항목'} 세트 수`}
                    inputMode="numeric"
                    onChangeText={(sets) =>
                      patchItem(item.id, { sets: digitsOnly(sets) })
                    }
                    placeholder="0"
                    placeholderTextColor="#B8AA9E"
                    style={styles.editSetsInput}
                    value={item.sets ?? ''}
                  />
                  <Text style={styles.editUnit}>세트</Text>
                  <TextInput
                    accessibilityLabel={`${item.name || '항목'} 횟수`}
                    inputMode="numeric"
                    onChangeText={(reps) =>
                      patchItem(item.id, { reps: digitsOnly(reps) })
                    }
                    placeholder="0"
                    placeholderTextColor="#B8AA9E"
                    style={styles.editRepsInput}
                    value={item.reps ?? ''}
                  />
                  <Text style={styles.editUnit}>회</Text>
                  <Pressable
                    accessibilityLabel="항목 삭제"
                    accessibilityRole="button"
                    onPress={() => removeItem(item.id)}
                    style={styles.deleteButton}
                  >
                    <DeleteIcon />
                  </Pressable>
                </Animated.View>
              </View>
            );
          })}
        </View>
        <View style={styles.addBox}>
          <Text style={styles.addTitle}>운동 직접 추가</Text>
          <View style={styles.addInputRow}>
            <TextInput
              accessibilityLabel="추가할 운동명"
              onChangeText={(name) => onChangeNew({ ...newItem, name })}
              placeholder="운동명"
              placeholderTextColor="#B8AA9E"
              style={styles.addNameInput}
              value={newItem.name}
            />
            <TextInput
              accessibilityLabel="추가할 세트 수"
              inputMode="numeric"
              onChangeText={(sets) =>
                onChangeNew({ ...newItem, sets: digitsOnly(sets) })
              }
              placeholder="0"
              placeholderTextColor="#B8AA9E"
              style={styles.addSetsInput}
              value={newItem.sets ?? ''}
            />
            <Text style={styles.editUnit}>세트</Text>
            <TextInput
              accessibilityLabel="추가할 횟수"
              inputMode="numeric"
              onChangeText={(reps) =>
                onChangeNew({ ...newItem, reps: digitsOnly(reps) })
              }
              placeholder="0"
              placeholderTextColor="#B8AA9E"
              style={styles.addRepsInput}
              value={newItem.reps ?? ''}
            />
            <Text style={styles.editUnit}>회</Text>
          </View>
          <Pressable
            accessibilityLabel="운동 추가하기"
            accessibilityRole="button"
            accessibilityState={{ disabled: !newItem.name.trim() }}
            disabled={!newItem.name.trim()}
            onPress={onAdd}
            style={[
              styles.addButton,
              newItem.name.trim()
                ? styles.addButtonEnabled
                : styles.addButtonDisabled,
            ]}
          >
            <Text
              style={[
                styles.addButtonText,
                newItem.name.trim()
                  ? styles.addButtonTextEnabled
                  : styles.addButtonTextDisabled,
              ]}
            >
              + 운동 추가하기
            </Text>
          </Pressable>
        </View>
        <View style={styles.editActions}>
          <Pressable
            accessibilityLabel="추천으로 되돌리기"
            accessibilityRole="button"
            onPress={onReset}
            style={styles.resetButton}
          >
            <Text numberOfLines={1} style={styles.resetLabel}>
              추천으로 되돌리기
            </Text>
          </Pressable>
          <Pressable
            accessibilityLabel="저장하기"
            accessibilityRole="button"
            onPress={onSave}
            style={styles.editSaveButton}
          >
            <Text style={[styles.sheetSaveLabel, useJua && styles.juaLabel]}>
              저장하기
            </Text>
          </Pressable>
        </View>
      </ScrollView>
    </SheetFrame>
  );
}

function DragHandle({
  children,
  index,
  onEnd,
  onKeyboardMove,
  onMove,
  onStart,
  style,
  testID,
}: {
  children: React.ReactNode;
  index: number;
  onEnd: () => void;
  onKeyboardMove: (direction: -1 | 1) => void;
  onMove: (dy: number) => void;
  onStart: (index: number) => void;
  style: StyleProp<ViewStyle>;
  testID: string;
}) {
  const responder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onStartShouldSetPanResponderCapture: () => true,
        onMoveShouldSetPanResponder: (
          _event: GestureResponderEvent,
          gesture: PanResponderGestureState,
        ) => Math.abs(gesture.dy) > 2,
        onMoveShouldSetPanResponderCapture: (
          _event: GestureResponderEvent,
          gesture: PanResponderGestureState,
        ) => Math.abs(gesture.dy) > 2,
        onPanResponderGrant: () => onStart(index),
        onPanResponderMove: (
          _event: GestureResponderEvent,
          gesture: PanResponderGestureState,
        ) => onMove(gesture.dy),
        onPanResponderRelease: onEnd,
        onPanResponderTerminate: onEnd,
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
      }),
    [index, onEnd, onMove, onStart],
  );
  return (
    <View
      {...responder.panHandlers}
      accessible
      accessibilityActions={[
        { name: 'increment', label: '아래로 이동' },
        { name: 'decrement', label: '위로 이동' },
      ]}
      accessibilityLabel="순서 변경 핸들"
      accessibilityRole="adjustable"
      onAccessibilityAction={(event) => {
        if (event.nativeEvent.actionName === 'increment') {
          onKeyboardMove(1);
        }
        if (event.nativeEvent.actionName === 'decrement') {
          onKeyboardMove(-1);
        }
      }}
      style={[
        style,
        Platform.OS === 'web'
          ? ({ touchAction: 'none' } as unknown as ViewStyle)
          : undefined,
      ]}
      testID={testID}
    >
      {children}
    </View>
  );
}

function useDragController(onMoveItem: (from: number, to: number) => void) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [targetIndex, setTargetIndex] = useState<number | null>(null);
  const activeRef = useRef<number | null>(null);
  const targetRef = useRef<number | null>(null);
  const originCenter = useRef(0);
  const dragOffset = useRef(0);
  const centers = useRef<number[]>([]);
  const [dragY] = useState(() => new Animated.Value(0));
  const itemShifts = useRef<Animated.Value[]>([]);
  const shiftAnimations = useRef<Animated.CompositeAnimation[]>([]);
  const settleAnimation = useRef<Animated.CompositeAnimation | null>(null);
  const getItemShift = useCallback((index: number) => {
    while (itemShifts.current.length <= index) {
      itemShifts.current.push(new Animated.Value(0));
    }
    return itemShifts.current[index]!;
  }, []);
  const stopShiftAnimations = useCallback(() => {
    for (const animation of shiftAnimations.current) {
      animation.stop();
    }
    shiftAnimations.current = [];
  }, []);
  const resetItemShifts = useCallback(() => {
    stopShiftAnimations();
    for (const shift of itemShifts.current) {
      shift.setValue(0);
    }
  }, [stopShiftAnimations]);
  const animateItemShifts = useCallback(
    (from: number, target: number) => {
      stopShiftAnimations();
      shiftAnimations.current = itemShifts.current.map((shift, index) => {
        let toValue = 0;
        if (from < target && index > from && index <= target) {
          const currentCenter = centers.current[index] ?? index * 60 + 30;
          const previousCenter =
            centers.current[index - 1] ?? (index - 1) * 60 + 30;
          toValue = previousCenter - currentCenter;
        } else if (from > target && index >= target && index < from) {
          const currentCenter = centers.current[index] ?? index * 60 + 30;
          const nextCenter =
            centers.current[index + 1] ?? (index + 1) * 60 + 30;
          toValue = nextCenter - currentCenter;
        }
        return Animated.timing(shift, {
          toValue,
          duration: 85,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true,
        });
      });
      for (const animation of shiftAnimations.current) {
        animation.start();
      }
    },
    [stopShiftAnimations],
  );
  const register = useCallback((index: number, event: LayoutChangeEvent) => {
    const { height, y } = event.nativeEvent.layout;
    centers.current[index] = y + height / 2;
  }, []);
  const start = useCallback(
    (index: number) => {
      settleAnimation.current?.stop();
      settleAnimation.current = null;
      resetItemShifts();
      activeRef.current = index;
      targetRef.current = index;
      originCenter.current = centers.current[index] ?? index * 60 + 30;
      dragOffset.current = 0;
      dragY.setValue(0);
      setActiveIndex(index);
      setTargetIndex(index);
    },
    [dragY, resetItemShifts],
  );
  const move = useCallback(
    (dy: number) => {
      const from = activeRef.current;
      if (from === null) {
        return;
      }
      const pointerY = originCenter.current + dy;
      let target = from;
      let closestDistance = Number.POSITIVE_INFINITY;
      for (let index = 0; index < centers.current.length; index += 1) {
        const center = centers.current[index];
        if (center === undefined) {
          continue;
        }
        const distance = Math.abs(pointerY - center);
        if (distance < closestDistance) {
          closestDistance = distance;
          target = index;
        }
      }
      if (targetRef.current !== target) {
        targetRef.current = target;
        setTargetIndex(target);
        animateItemShifts(from, target);
      }
      dragOffset.current = dy;
      dragY.setValue(dy);
    },
    [animateItemShifts, dragY],
  );
  const end = useCallback(() => {
    const from = activeRef.current;
    const target = targetRef.current;
    if (from === null || target === null) {
      return;
    }
    activeRef.current = null;
    targetRef.current = null;
    const targetCenter =
      centers.current[target] ?? originCenter.current + (target - from) * 60;
    const remainingOffset =
      dragOffset.current - (targetCenter - originCenter.current);
    resetItemShifts();
    dragY.setValue(remainingOffset);
    setActiveIndex(target);
    setTargetIndex(target);
    if (target !== from) {
      onMoveItem(from, target);
    }
    const animation = Animated.timing(dragY, {
      toValue: 0,
      duration: 80,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    });
    settleAnimation.current = animation;
    animation.start(({ finished }) => {
      if (settleAnimation.current === animation) {
        settleAnimation.current = null;
      }
      if (finished) {
        dragY.setValue(0);
        setActiveIndex(null);
        setTargetIndex(null);
      }
    });
  }, [dragY, onMoveItem, resetItemShifts]);
  useEffect(
    () => () => {
      settleAnimation.current?.stop();
      stopShiftAnimations();
    },
    [stopShiftAnimations],
  );
  const keyboardMove = useCallback(
    (index: number, direction: -1 | 1, length: number) => {
      const target = Math.max(0, Math.min(length - 1, index + direction));
      if (target !== index) {
        onMoveItem(index, target);
      }
    },
    [onMoveItem],
  );
  return {
    activeIndex,
    dragY,
    end,
    getItemShift,
    keyboardMove,
    move,
    register,
    start,
    targetIndex,
  };
}

function NotificationIcon() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 3.5a5.5 5.5 0 0 0-5.5 5.5v3.2L5 15.5h14l-1.5-3.3V9A5.5 5.5 0 0 0 12 3.5Z"
        stroke={colors.surface}
        strokeWidth={1.7}
        strokeLinejoin="round"
      />
      <Path
        d="M10 18.2a2 2 0 0 0 4 0"
        stroke={colors.surface}
        strokeWidth={1.7}
        strokeLinecap="round"
      />
    </Svg>
  );
}

function DayCheckIcon() {
  return (
    <Svg width={14} height={14} viewBox="0 0 24 24" fill="none">
      <Path
        d="M6 12.5l4 4 8-9"
        stroke="#5A4636"
        strokeWidth={3.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

function InfoIcon() {
  return (
    <Svg width={16} height={16} viewBox="0 0 24 24" fill="none">
      <Circle cx={12} cy={12} r={9} stroke="#AA9A8D" strokeWidth={1.6} />
      <Path
        d="M12 10.6v6"
        stroke="#AA9A8D"
        strokeWidth={1.8}
        strokeLinecap="round"
      />
      <Circle cx={12} cy={7.6} r={1.1} fill="#AA9A8D" />
    </Svg>
  );
}

function CalendarIcon() {
  return (
    <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
      <Rect
        x={3.5}
        y={5.5}
        width={17}
        height={15}
        rx={3.5}
        stroke="#F6BA50"
        strokeWidth={1.7}
      />
      <Path
        d="M3.5 10h17M8.5 3.5v4M15.5 3.5v4"
        stroke="#F6BA50"
        strokeWidth={1.7}
        strokeLinecap="round"
      />
      <Circle cx={8.5} cy={14} r={1.2} fill="#F6BA50" />
      <Circle cx={12.5} cy={14} r={1.2} fill="#F6BA50" />
    </Svg>
  );
}

function CheckinChevronIcon() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path
        d="M9 5.5L16 12l-7 6.5"
        stroke="#5A4636"
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

function RoutineDragIcon() {
  return (
    <Svg width={18} height={14} viewBox="0 0 18 14" fill="none">
      <G stroke="#B4AEA2" strokeWidth={2} strokeLinecap="round">
        <Path d="M2 3h14" />
        <Path d="M2 7h14" />
        <Path d="M2 11h14" />
      </G>
    </Svg>
  );
}

function StartChevronIcon() {
  return (
    <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
      <Path
        d="M9 5.5L16 12l-7 6.5"
        stroke="#5A4636"
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

function EditIcon() {
  return (
    <Svg width={16} height={16} viewBox="0 0 24 24" fill="none">
      <Path
        d="M4 16.5 15.5 5l3.5 3.5L7.5 20H4v-3.5Z"
        stroke="#A45F00"
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
    </Svg>
  );
}

function RerollIcon({ color }: { color: string }) {
  return (
    <Svg width={16} height={16} viewBox="0 0 24 24" fill="none">
      <Path
        d="M20 11a8 8 0 1 0-.8 4.5"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
      />
      <Path
        d="M20 4.5V11h-6"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

function HomeTabIcon({ color }: { color: string }) {
  return (
    <Svg width={22} height={22} viewBox="0 0 24 24" fill="none">
      <Path
        d="M4 11.2 12 4.5l8 6.7V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1v-7.8Z"
        fill={color}
      />
    </Svg>
  );
}

function LogTabIcon({ color }: { color: string }) {
  return (
    <Svg width={22} height={22} viewBox="0 0 24 24" fill="none">
      <Path
        d="M3.5 10v4M20.5 10v4M7 7.5v9M17 7.5v9M7 12h10"
        stroke={color}
        strokeWidth={2.2}
        strokeLinecap="round"
      />
    </Svg>
  );
}

function ReportTabIcon({ color }: { color: string }) {
  return (
    <Svg width={22} height={22} viewBox="0 0 24 24" fill="none">
      <Rect x={4} y={12} width={3.6} height={7} rx={1.6} fill={color} />
      <Rect x={10.2} y={6} width={3.6} height={13} rx={1.6} fill={color} />
      <Rect x={16.4} y={9.5} width={3.6} height={9.5} rx={1.6} fill={color} />
    </Svg>
  );
}

function MyTabIcon({ color }: { color: string }) {
  return (
    <Svg width={22} height={22} viewBox="0 0 24 24" fill="none">
      <Circle cx={12} cy={8} r={3.8} fill={color} />
      <Path d="M5 20c0-3.6 3.1-5.6 7-5.6s7 2 7 5.6" fill={color} />
    </Svg>
  );
}

function EditDragIcon() {
  return (
    <Svg width={14} height={12} viewBox="0 0 18 14" fill="none">
      <G stroke="#B4AEA2" strokeWidth={2} strokeLinecap="round">
        <Path d="M2 3h14" />
        <Path d="M2 7h14" />
        <Path d="M2 11h14" />
      </G>
    </Svg>
  );
}

function DeleteIcon() {
  return (
    <Svg width={15} height={15} viewBox="0 0 24 24" fill="none">
      <Path
        d="M6 6l12 12M18 6L6 18"
        stroke="#B4AEA2"
        strokeWidth={2.2}
        strokeLinecap="round"
      />
    </Svg>
  );
}

function digitsOnly(value: string | undefined) {
  return String(value ?? '').replace(/[^0-9]/g, '');
}

function clampNumericString(value: string, min: number, max?: number) {
  const parsed = Number.parseInt(digitsOnly(value), 10);
  const safe = Number.isFinite(parsed) ? parsed : min;
  return String(Math.max(min, max === undefined ? safe : Math.min(max, safe)));
}

function cleanRoutineItems(items: readonly HomeRoutineItem[]) {
  const cleaned: HomeRoutineItem[] = [];
  for (const item of items) {
    const name = item.name.trim();
    if (!name) {
      continue;
    }
    cleaned.push({
      ...item,
      name,
      sets: item.sets ? clampNumericString(item.sets, 1, 20) : '',
      reps: item.reps ? clampNumericString(item.reps, 1, 200) : '',
    });
  }
  return cleaned;
}

function createHomeStyles(
  s: (value: number) => number,
  f: (value: number) => number,
  topPadding: number,
) {
  const shadow = (y: number, blur: number, opacity: number) => ({
    ...Platform.select({
      ios: {
        shadowColor: '#5A4636',
        shadowOffset: { width: 0, height: s(y) },
        shadowOpacity: opacity,
        shadowRadius: s(blur / 2),
      },
      android: { elevation: y <= 4 ? 2 : 3 },
      default: {
        shadowColor: '#5A4636',
        shadowOffset: { width: 0, height: s(y) },
        shadowOpacity: opacity,
        shadowRadius: s(blur / 2),
      },
    }),
  });
  return StyleSheet.create({
    screen: { flex: 1, overflow: 'hidden', backgroundColor: '#FFF8E5' },
    gradient: { flex: 1 },
    scroll: { flex: 1 },
    scrollContent: {
      paddingTop: topPadding,
      paddingHorizontal: s(18),
      paddingBottom: s(14),
    },
    header: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: s(12),
      paddingTop: s(4),
      paddingHorizontal: s(4),
      paddingBottom: s(18),
    },
    headerCopy: { minWidth: 0, flex: 1 },
    greeting: {
      color: '#5A4636',
      fontSize: f(22),
      fontWeight: '800',
      lineHeight: f(27.5),
      textShadowColor: 'rgba(47,82,51,.18)',
      textShadowOffset: { width: 0, height: s(1) },
      textShadowRadius: s(2),
    },
    greetingName: { color: colors.greenText },
    date: {
      marginTop: s(6),
      color: colors.text,
      fontSize: f(13),
      fontWeight: '600',
      opacity: 0.95,
    },
    headerActions: { flexDirection: 'row', alignItems: 'center', gap: s(10) },
    notificationButton: {
      position: 'relative',
      width: s(44),
      height: s(44),
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: s(14),
      backgroundColor: colors.text,
      ...shadow(4, 10, 0.14),
    },
    notificationDot: {
      position: 'absolute',
      top: s(8),
      right: s(8),
      width: s(9),
      height: s(9),
      borderRadius: s(4.5),
      borderWidth: s(1.5),
      borderColor: colors.surface,
      backgroundColor: '#E9503F',
    },
    hidden: { display: 'none' },
    profileButton: {
      width: s(48),
      height: s(48),
      overflow: 'hidden',
      borderRadius: s(24),
      backgroundColor: '#FFFFFF',
      ...shadow(4, 12, 0.18),
    },
    profileAvatar: { width: '100%', height: '100%' },
    summaryCard: {
      marginBottom: s(14),
      borderRadius: s(22),
      backgroundColor: '#FFFFFF',
      padding: s(16),
      ...shadow(6, 18, 0.1),
    },
    cardTitle: { color: '#5A4636', fontSize: f(15), fontWeight: '800' },
    greenText: { color: '#A45F00' },
    weekRow: { flexDirection: 'row', gap: s(6), marginTop: s(14) },
    weekDay: { minWidth: 0, flex: 1, alignItems: 'center', gap: s(6) },
    weekCircle: {
      width: s(32),
      height: s(32),
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(2),
      borderRadius: s(16),
    },
    weekCircleCompleted: { borderColor: '#F6BA50', backgroundColor: '#F6BA50' },
    weekCircleIncomplete: {
      borderColor: '#D8D4CB',
      borderStyle: 'dashed',
      backgroundColor: '#FFFFFF',
    },
    weekLabel: { fontSize: f(11.5), fontWeight: '700' },
    weekLabelCompleted: { color: '#A45F00' },
    weekLabelIncomplete: { color: '#B0ACA4' },
    progressCard: {
      marginBottom: s(14),
      borderRadius: s(22),
      backgroundColor: '#FFFFFF',
      paddingTop: s(16),
      paddingHorizontal: s(16),
      paddingBottom: s(18),
      ...shadow(6, 18, 0.1),
    },
    progressHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: s(6),
    },
    progressTitleRow: {
      minWidth: 0,
      flexDirection: 'row',
      alignItems: 'center',
      gap: s(2),
    },
    iconButton: { alignItems: 'center', justifyContent: 'center' },
    weekRange: { color: '#958476', fontSize: f(12), fontWeight: '600' },
    tip: {
      marginTop: s(10),
      borderRadius: s(12),
      backgroundColor: '#FFF8E5',
      paddingVertical: s(10),
      paddingHorizontal: s(12),
    },
    tipText: { color: '#4A5B44', fontSize: f(12.5), lineHeight: f(18.75) },
    countRow: {
      flexDirection: 'row',
      alignItems: 'baseline',
      justifyContent: 'space-between',
      gap: s(10),
      marginTop: s(14),
    },
    countLabel: { color: '#5A4636', fontSize: f(15), fontWeight: '800' },
    countValue: { color: '#A45F00', fontSize: f(15) },
    completedCountValue: { color: '#A45F00', fontSize: f(22) },
    progressPercent: { color: '#A45F00', fontSize: f(22), fontWeight: '800' },
    progressCells: { flexDirection: 'row', gap: s(8), marginTop: s(12) },
    progressCell: {
      position: 'relative',
      minWidth: 0,
      flex: 1,
      aspectRatio: 1,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: s(14),
      padding: s(5),
    },
    progressCellCompleted: { backgroundColor: '#FFF3D4', opacity: 1 },
    progressCellIncomplete: { backgroundColor: '#F3F1EB', opacity: 0.55 },
    progressImage: { width: '78%', height: '78%' },
    todoImage: { opacity: 1 },
    checkinWrapper: { marginBottom: s(16) },
    juaLabel: { fontFamily: fontFamilies.slogan, fontWeight: '400' },
    messageCard: {
      alignItems: 'center',
      marginBottom: s(16),
      borderRadius: s(24),
      backgroundColor: '#FFFFFF',
      paddingVertical: s(28),
      paddingHorizontal: s(20),
      ...shadow(6, 18, 0.1),
    },
    messageTitle: {
      color: '#5A4636',
      fontSize: f(15),
      fontWeight: '800',
      textAlign: 'center',
    },
    loadingTitle: { marginTop: s(14) },
    messageText: {
      marginTop: s(8),
      color: '#958476',
      fontSize: f(13),
      lineHeight: f(19.5),
      textAlign: 'center',
    },
    loadingRing: {
      width: s(26),
      height: s(26),
      borderWidth: s(3),
      borderColor: '#F1D39A',
      borderTopColor: '#F6BA50',
      borderRadius: s(13),
    },
    routineCard: {
      position: 'relative',
      overflow: 'hidden',
      marginBottom: s(16),
      borderRadius: s(24),
      backgroundColor: '#FFFFFF',
      paddingTop: s(18),
      paddingHorizontal: s(18),
      paddingBottom: s(8),
      ...shadow(6, 18, 0.1),
    },
    routineBadgeRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      alignItems: 'center',
      gap: s(8),
    },
    routineBadge: {
      alignSelf: 'flex-start',
      borderRadius: 999,
      backgroundColor: '#F6BA50',
      paddingVertical: s(6),
      paddingHorizontal: s(12),
    },
    routineBadgeText: { color: '#5A4636', fontSize: f(12), fontWeight: '700' },
    routineActionBadge: {
      alignSelf: 'flex-start',
      borderWidth: s(1.5),
      borderColor: '#F1D39A',
      borderRadius: 999,
      backgroundColor: '#FFFFFF',
      paddingVertical: s(4.5),
      paddingHorizontal: s(11),
    },
    routineActionBadgeAdjusted: {
      borderColor: '#F6BA50',
      backgroundColor: '#FFF8E5',
    },
    routineActionBadgeText: {
      color: '#A45F00',
      fontSize: f(12),
      fontWeight: '700',
    },
    routineTitle: {
      marginTop: s(12),
      color: '#5A4636',
      fontSize: f(26),
      fontWeight: '800',
      letterSpacing: s(-0.5),
    },
    routineSummary: {
      marginTop: s(10),
      color: '#A45F00',
      fontSize: f(14),
      fontWeight: '700',
    },
    routineNotes: { gap: s(4), marginTop: s(10) },
    routineNote: {
      color: '#7B695B',
      fontSize: f(13.5),
      fontWeight: '500',
      lineHeight: f(20.925),
    },
    reasonLink: {
      alignSelf: 'flex-start',
      minHeight: s(40),
      justifyContent: 'center',
      marginTop: s(2),
      paddingRight: s(12),
    },
    reasonLinkText: {
      color: '#A45F00',
      fontSize: f(12.5),
      fontWeight: '700',
      textDecorationLine: 'underline',
    },
    routineList: {
      gap: s(8),
      marginTop: s(14),
      borderTopWidth: s(1),
      borderTopColor: '#E8D8C2',
      borderStyle: 'dashed',
      paddingTop: s(12),
    },
    orderHint: {
      color: '#A29B8E',
      fontSize: f(11.5),
      fontWeight: '700',
      letterSpacing: s(0.23),
    },
    dragOuterRoutine: {
      position: 'relative',
      borderWidth: s(1.5),
      borderColor: 'transparent',
      borderRadius: s(12),
      backgroundColor: 'transparent',
    },
    dropPlaceholder: {
      position: 'absolute',
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
      borderWidth: s(1.5),
      borderColor: '#E0A742',
      borderRadius: s(12),
      borderStyle: 'dashed',
      backgroundColor: '#FFF3D4',
    },
    dragOuterEdit: {
      position: 'relative',
      borderWidth: s(1.5),
      borderColor: 'transparent',
      borderRadius: s(16),
      backgroundColor: 'transparent',
    },
    dragOuterActive: {
      zIndex: 10,
      elevation: 4,
    },
    routineRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: s(10),
      borderRadius: s(11),
      backgroundColor: 'transparent',
      paddingVertical: s(7),
      paddingHorizontal: s(8),
    },
    dragInnerRoutineActive: {
      zIndex: 6,
      backgroundColor: '#FFFFFF',
      ...shadow(10, 20, 0.22),
    },
    dragInnerEditActive: { zIndex: 6, opacity: 0.97, ...shadow(10, 20, 0.22) },
    routineHandle: {
      width: s(44),
      height: s(44),
      alignItems: 'center',
      justifyContent: 'center',
      marginTop: s(-11),
      marginRight: 0,
      marginBottom: s(-11),
      marginLeft: s(-8),
    },
    routineItemButton: {
      minWidth: 0,
      flex: 1,
    },
    routineItemText: {
      minWidth: 0,
      flex: 1,
      color: '#5A4636',
      fontSize: f(13.5),
      fontWeight: '700',
      lineHeight: f(19.575),
    },
    routineDot: {
      width: s(6),
      height: s(6),
      borderRadius: s(3),
      backgroundColor: '#F6BA50',
    },
    adjustmentNote: {
      marginTop: s(12),
      borderRadius: s(12),
      backgroundColor: '#FFF8E5',
      paddingVertical: s(10),
      paddingHorizontal: s(12),
    },
    adjustmentText: {
      color: '#4A5B44',
      fontSize: f(12.5),
      lineHeight: f(18.75),
    },
    startButton: {
      width: '100%',
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: s(8),
      marginTop: s(16),
      marginBottom: s(10),
      borderRadius: s(16),
      backgroundColor: '#F6BA50',
      padding: s(16),
    },
    startLabel: {
      color: colors.text,
      fontSize: f(17),
      fontWeight: '400',
      textAlign: 'center',
    },
    routineActions: {
      flexDirection: 'row',
      gap: s(8),
      marginTop: s(8),
      marginBottom: s(10),
    },
    routineAction: {
      minWidth: 0,
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: s(6),
      borderWidth: s(1.5),
      borderColor: '#F1D39A',
      borderRadius: s(16),
      backgroundColor: '#FFFFFF',
      paddingVertical: s(14),
      paddingHorizontal: s(6),
    },
    routineActionDisabled: { borderColor: '#EEDFCB' },
    editActionLabel: { color: '#A45F00', fontSize: f(13.5), fontWeight: '700' },
    rerollActionLabel: {
      color: '#A45F00',
      fontSize: f(12.5),
      fontWeight: '700',
    },
    rerollActionLabelDisabled: { color: '#B0ACA4' },
    sheetOverlay: {
      position: 'absolute',
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
      justifyContent: 'flex-end',
      backgroundColor: 'rgba(20,32,16,.42)',
    },
    sheet: {
      width: '100%',
      maxHeight: '88%',
      borderTopLeftRadius: s(28),
      borderTopRightRadius: s(28),
      backgroundColor: '#FFF8E5',
      paddingTop: s(20),
      paddingHorizontal: s(18),
      paddingBottom: s(30),
    },
    sheetHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: s(10),
    },
    sheetTitle: { color: '#5A4636', fontSize: f(18), fontWeight: '800' },
    closeButton: {
      width: s(44),
      height: s(44),
      alignItems: 'center',
      justifyContent: 'center',
      marginTop: s(-10),
      marginRight: s(-12),
      marginBottom: s(-10),
    },
    closeText: { color: '#958476', fontSize: f(22) },
    sheetIntro: {
      marginTop: s(4),
      color: '#958476',
      fontSize: f(13),
      lineHeight: f(19.5),
    },
    reasonSheetContent: { gap: s(10), paddingTop: s(14), paddingBottom: s(5) },
    reasonSection: {
      gap: s(9),
      borderRadius: s(18),
      backgroundColor: '#FFFFFF',
      padding: s(16),
    },
    reasonRow: { flexDirection: 'row', alignItems: 'flex-start', gap: s(7) },
    reasonBullet: { color: '#F6BA50', fontSize: f(14), lineHeight: f(20) },
    reasonText: {
      minWidth: 0,
      flex: 1,
      color: '#7B695B',
      fontSize: f(13),
      lineHeight: f(19.5),
    },
    safetyReasonSection: {
      borderWidth: s(1.5),
      borderColor: '#E8C3B8',
      backgroundColor: '#FFF7F4',
    },
    safetyReasonTitle: { color: '#8B3A32' },
    safetyReasonText: { color: '#6F2F29' },
    agentSummary: { gap: s(4) },
    agentSummaryLabel: {
      color: '#A45F00',
      fontSize: f(12),
      fontWeight: '800',
    },
    sheetScrollContent: { gap: s(10), paddingTop: s(14), paddingBottom: s(5) },
    checkinSection: {
      borderRadius: s(18),
      backgroundColor: '#FFFFFF',
      padding: s(16),
    },
    checkinSectionTitle: {
      color: '#5A4636',
      fontSize: f(14),
      fontWeight: '700',
    },
    choiceRow: { flexDirection: 'row', gap: s(6), marginTop: s(10) },
    choiceRowTwoColumn: { flexWrap: 'wrap' },
    choiceButton: {
      minWidth: 0,
      minHeight: s(44),
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(1.5),
      borderColor: '#EEDFCB',
      borderRadius: s(12),
      backgroundColor: '#FFF8E5',
      paddingVertical: s(9),
      paddingHorizontal: s(6),
    },
    choiceButtonTwoColumn: {
      minHeight: s(48),
      flexBasis: '48%',
      flexGrow: 1,
    },
    choiceButtonSelected: {
      borderColor: '#F6BA50',
      backgroundColor: '#F6BA50',
    },
    choiceButtonText: { color: '#5A4636', fontSize: f(13), fontWeight: '700' },
    choiceButtonTextSelected: { color: '#5A4636' },
    adverseSection: {
      gap: s(8),
      borderWidth: s(1),
      borderColor: '#E8C3B8',
      borderRadius: s(14),
      backgroundColor: '#FBECE8',
      padding: s(16),
    },
    adverseTitle: {
      color: '#B04A2C',
      fontSize: f(15),
      fontWeight: '700',
    },
    adverseBody: {
      color: '#B04A2C',
      fontSize: f(13),
      lineHeight: f(19),
    },
    adverseChoiceList: { gap: s(7), marginTop: s(2) },
    adverseChoiceButton: {
      minHeight: s(44),
      alignItems: 'flex-start',
      justifyContent: 'center',
      borderWidth: s(1.5),
      borderColor: '#E8C3B8',
      borderRadius: s(12),
      backgroundColor: '#FFFDFC',
      paddingVertical: s(10),
      paddingHorizontal: s(12),
    },
    adverseChoiceButtonSelected: {
      borderColor: '#C2402F',
      backgroundColor: '#C2402F',
    },
    adverseChoiceText: {
      color: '#B04A2C',
      fontSize: f(13),
      fontWeight: '700',
      lineHeight: f(19),
    },
    adverseChoiceTextSelected: { color: '#FFFFFF' },
    numberRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: s(12),
      borderRadius: s(18),
      backgroundColor: '#FFFFFF',
      padding: s(16),
    },
    numberLabel: { color: '#5A4636', fontSize: f(14), fontWeight: '700' },
    optionalText: { color: '#958476', fontWeight: '500' },
    durationStepper: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: s(10),
    },
    durationStepButton: {
      width: s(44),
      height: s(44),
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(1),
      borderColor: '#EEDFCB',
      borderRadius: s(12),
      backgroundColor: '#FFF8E5',
    },
    durationStepButtonDisabled: { opacity: 0.4 },
    durationStepButtonText: {
      color: '#5A4636',
      fontSize: f(22),
      fontWeight: '800',
      lineHeight: f(24),
    },
    durationStepValue: {
      minWidth: s(46),
      color: '#5A4636',
      fontSize: f(15),
      fontWeight: '800',
      textAlign: 'center',
    },
    numberInputGroup: { flexDirection: 'row', alignItems: 'center', gap: s(6) },
    numberInput: {
      width: s(84),
      borderWidth: s(1),
      borderColor: '#EEDFCB',
      borderRadius: s(12),
      backgroundColor: '#FFF8E5',
      color: '#5A4636',
      fontSize: f(14),
      fontWeight: '700',
      paddingVertical: s(11),
      paddingHorizontal: s(12),
      textAlign: 'right',
    },
    availabilitySection: {
      gap: s(10),
      borderRadius: s(18),
      backgroundColor: '#FFFFFF',
      padding: s(16),
    },
    availabilityHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: s(5),
    },
    availabilitySlotRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: s(8),
    },
    availabilityTimeButton: {
      flex: 1,
      minWidth: 0,
      minHeight: s(44),
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(1),
      borderColor: '#EEDFCB',
      borderRadius: s(12),
      backgroundColor: '#FFF8E5',
      paddingVertical: s(11),
      paddingHorizontal: s(10),
    },
    availabilityTimeText: {
      color: '#5A4636',
      fontSize: f(14),
      fontWeight: '700',
      textAlign: 'center',
    },
    availabilityTimePlaceholder: { color: '#AAA69F', fontWeight: '600' },
    availabilitySeparator: {
      color: '#958476',
      fontSize: f(15),
      fontWeight: '700',
    },
    availabilityRemoveButton: {
      width: s(28),
      height: s(42),
      alignItems: 'center',
      justifyContent: 'center',
    },
    availabilityAddButton: {
      minHeight: s(44),
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(1),
      borderColor: '#E0A742',
      borderStyle: 'dashed',
      borderRadius: s(12),
      backgroundColor: '#FFF8E5',
    },
    availabilityAddLabel: {
      color: '#A45F00',
      fontSize: f(13),
      fontWeight: '700',
    },
    availabilityHelpText: {
      color: '#958476',
      fontSize: f(12),
      lineHeight: f(18),
    },
    timePickerIntro: {
      marginTop: s(2),
      color: '#958476',
      fontSize: f(13),
      lineHeight: f(19),
    },
    timePickerRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: s(10),
      marginTop: s(16),
    },
    timePickerColon: {
      color: '#5A4636',
      fontSize: f(24),
      fontWeight: '800',
    },
    timeWheelColumn: {
      position: 'relative',
      minWidth: 0,
      height: TIME_WHEEL_ITEM_HEIGHT * 3,
      flex: 1,
      overflow: 'hidden',
      borderWidth: s(1),
      borderColor: '#EEDFCB',
      borderRadius: s(14),
      backgroundColor: '#FFFFFF',
    },
    timeWheelScroll: { zIndex: 2 },
    timeWheelContent: { paddingVertical: TIME_WHEEL_ITEM_HEIGHT },
    timeWheelSelection: {
      position: 'absolute',
      top: TIME_WHEEL_ITEM_HEIGHT,
      right: s(5),
      left: s(5),
      height: TIME_WHEEL_ITEM_HEIGHT,
      borderRadius: s(9),
      backgroundColor: '#FFF3D4',
    },
    timeWheelItem: {
      height: TIME_WHEEL_ITEM_HEIGHT,
      alignItems: 'center',
      justifyContent: 'center',
    },
    timeWheelItemText: {
      color: '#958476',
      fontSize: f(17),
      fontWeight: '600',
    },
    timeWheelItemTextSelected: { color: '#A45F00', fontWeight: '800' },
    timeWheelItemSuffix: { fontSize: f(12), fontWeight: '600' },
    timePickerActions: {
      flexDirection: 'row',
      gap: s(10),
      marginTop: s(18),
    },
    timePickerCancelButton: {
      minHeight: s(48),
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(1),
      borderColor: '#D8D4CB',
      borderRadius: s(14),
      backgroundColor: '#FFFFFF',
    },
    timePickerCancelLabel: {
      color: '#6F6B64',
      fontSize: f(15),
      fontWeight: '700',
    },
    timePickerConfirmButton: {
      minHeight: s(48),
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: s(14),
      backgroundColor: '#F6BA50',
    },
    timePickerConfirmLabel: {
      color: '#5A4636',
      fontSize: f(15),
      fontWeight: '800',
    },
    stepsInput: { width: s(110) },
    numberSuffix: { color: '#958476', fontSize: f(13) },
    sheetSaveButton: {
      position: 'relative',
      width: '100%',
      alignItems: 'center',
      justifyContent: 'center',
      marginTop: s(8),
      borderWidth: s(1),
      borderColor: 'rgba(244, 166, 42, 0.8)',
      borderRadius: s(18),
      padding: s(17),
      shadowColor: '#AD741D',
      shadowOffset: { width: 0, height: s(5) },
      shadowOpacity: 0.11,
      shadowRadius: s(6),
      elevation: 3,
    },
    sheetSaveGradient: {
      position: 'absolute',
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
      borderRadius: s(18),
    },
    sheetSaveLabel: { color: '#5A4636', fontSize: f(18), fontWeight: '400' },
    editScrollContent: { paddingBottom: s(5) },
    editList: { gap: s(8), marginTop: s(14) },
    editRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: s(6),
      borderRadius: s(14),
      backgroundColor: '#FFFFFF',
      paddingTop: s(8),
      paddingRight: s(6),
      paddingBottom: s(8),
      paddingLeft: s(10),
    },
    editHandle: {
      width: s(26),
      height: s(40),
      alignItems: 'center',
      justifyContent: 'center',
      marginLeft: s(-4),
    },
    editNameInput: {
      minWidth: 0,
      flex: 1,
      color: '#5A4636',
      fontSize: f(13.5),
      fontWeight: '700',
      paddingVertical: s(6),
    },
    editSetsInput: {
      width: s(38),
      borderWidth: s(1),
      borderColor: '#EEDFCB',
      borderRadius: s(10),
      backgroundColor: '#FFF8E5',
      color: '#5A4636',
      fontSize: f(13),
      fontWeight: '700',
      paddingVertical: s(8),
      paddingHorizontal: s(2),
      textAlign: 'center',
    },
    editRepsInput: {
      width: s(44),
      borderWidth: s(1),
      borderColor: '#EEDFCB',
      borderRadius: s(10),
      backgroundColor: '#FFF8E5',
      color: '#5A4636',
      fontSize: f(13),
      fontWeight: '700',
      paddingVertical: s(8),
      paddingHorizontal: s(2),
      textAlign: 'center',
    },
    editUnit: { color: '#B0ACA4', fontSize: f(11.5), fontWeight: '700' },
    deleteButton: {
      width: s(32),
      height: s(44),
      alignItems: 'center',
      justifyContent: 'center',
    },
    addBox: {
      marginTop: s(12),
      borderWidth: s(1.5),
      borderColor: '#F1D39A',
      borderStyle: 'dashed',
      borderRadius: s(16),
      backgroundColor: '#FFFFFF',
      padding: s(12),
    },
    addTitle: { color: '#A45F00', fontSize: f(12), fontWeight: '700' },
    addInputRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: s(6),
      marginTop: s(8),
    },
    addNameInput: {
      minWidth: 0,
      flex: 1,
      borderWidth: s(1),
      borderColor: '#EEDFCB',
      borderRadius: s(10),
      backgroundColor: '#FFF8E5',
      color: '#5A4636',
      fontSize: f(13.5),
      fontWeight: '700',
      padding: s(10),
    },
    addSetsInput: {
      width: s(38),
      borderWidth: s(1),
      borderColor: '#EEDFCB',
      borderRadius: s(10),
      backgroundColor: '#FFF8E5',
      color: '#5A4636',
      fontSize: f(13),
      fontWeight: '700',
      paddingVertical: s(10),
      paddingHorizontal: s(2),
      textAlign: 'center',
    },
    addRepsInput: {
      width: s(44),
      borderWidth: s(1),
      borderColor: '#EEDFCB',
      borderRadius: s(10),
      backgroundColor: '#FFF8E5',
      color: '#5A4636',
      fontSize: f(13),
      fontWeight: '700',
      paddingVertical: s(10),
      paddingHorizontal: s(2),
      textAlign: 'center',
    },
    addButton: {
      width: '100%',
      marginTop: s(10),
      borderRadius: s(12),
      padding: s(12),
    },
    addButtonEnabled: { backgroundColor: '#F6BA50' },
    addButtonDisabled: { backgroundColor: '#EEDFCB' },
    addButtonText: {
      fontSize: f(13.5),
      fontWeight: '700',
      textAlign: 'center',
    },
    addButtonTextEnabled: { color: '#5A4636' },
    addButtonTextDisabled: { color: '#B0ACA4' },
    editActions: { flexDirection: 'row', gap: s(8), marginTop: s(16) },
    resetButton: {
      width: s(112),
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(1.5),
      borderColor: '#EEDFCB',
      borderRadius: s(18),
      backgroundColor: '#FFFFFF',
      paddingVertical: s(16),
      paddingHorizontal: s(8),
    },
    resetLabel: { color: '#958476', fontSize: f(12.5), fontWeight: '700' },
    editSaveButton: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      borderBottomWidth: s(5),
      borderBottomColor: '#D98B16',
      borderRadius: s(18),
      backgroundColor: '#F6BA50',
      padding: s(16),
    },
  });
}
