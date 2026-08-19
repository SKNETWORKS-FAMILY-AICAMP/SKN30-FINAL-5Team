import { LinearGradient } from 'expo-linear-gradient';
import { StatusBar } from 'expo-status-bar';
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
  type LayoutChangeEvent,
  type PanResponderGestureState,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, G, Path, Rect } from 'react-native-svg';

import {
  ADVERSE_REACTION_OPTIONS,
  agentTypeLabel,
  bodyAreaLabel,
  decisionReasonLabel,
  locationLabel,
  planRevisionReasonLabel,
  sessionStatusLabel,
  SEVERITY_OPTIONS,
} from '../../api/labels';
import type { Api } from '../../api/endpoints';
import type {
  DailyContextResponse,
  DecisionResponse,
  DiscomfortSeverityCode,
  RoutineResponse,
  SessionStatusCode,
  WeekResponse,
  WeeklyPlanRevisionResponse,
  WorkoutSessionLogSummary,
} from '../../api/types';
import { imageAssets } from '../../assets';
import { fontFamilies, useBrandFonts } from '../../app/fonts';
import type { TabId } from '../../components/brand/BrandChrome';
import { useScale } from '../../components/scale';
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
  weekDaysFromSessions,
  weekStartForLocalDate,
  type HomeCheckin,
  type HomeCheckinDraft,
  type HomePreviewState,
  type HomeRoutineItem,
} from './homeModel';

export const HOME_GRADIENT = {
  colors: ['#8ECB4E', '#A8D66A', '#D8E6B4', '#F2EFE2', '#FAF7F1'] as const,
  locations: [0, 0.22, 0.46, 0.66, 0.82] as const,
  start: { x: 0.5, y: 0 },
  end: { x: 0.5, y: 1 },
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

type HomeTab = TabId;
type WeekDay = {
  completed: boolean;
  label: string;
  statusCodes?: readonly SessionStatusCode[];
};
const PREVIEW_DISCOMFORT_CODES = ['SHOULDER', 'LOWER_BACK', 'KNEE'] as const;

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
  attentionAreaCodes?: readonly string[];
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
  attentionAreaCodes = [],
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
  onRetry,
  onRetryCheckin,
  onSaveCheckin,
  onSaveEdit,
  onStartWorkout,
  onSubmitCheckin,
  onSubmitUserEdits,
  permissionDenied = false,
  planRevision = null,
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
  const completedWeekDays = Array.from(weekDays).filter(
    (day) => day.completed,
  ).length;
  const remainingCount = Math.max(0, goal - completedWeekDays);
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
    setCheckinOpen(false);
  };

  const saveCheckin = () => {
    const saved = {
      ...checkinDraft,
      workoutMinutes: clampNumericString(checkinDraft.workoutMinutes, 5, 180),
    };
    setCommittedCheckin(saved);
    setCheckinDraft(saved);
    setCheckedIn(true);
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
    setRoutineItems((current) => moveItem(current, from, to));
  }, []);
  const moveEditItem = useCallback((from: number, to: number) => {
    setEditDraft((current) => moveItem(current, from, to));
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
        <StatusBar style="light" />
        <LinearGradient
          testID="home-gradient"
          colors={HOME_GRADIENT.colors}
          locations={HOME_GRADIENT.locations}
          start={HOME_GRADIENT.start}
          end={HOME_GRADIENT.end}
          style={styles.gradient}
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
              userName={displayName}
            />
            {contentReady ? (
              <>
                <WeeklyRoutineCard
                  remainingCount={remainingCount}
                  weekDays={weekDays}
                />
                <WeeklyProgressCard
                  completed={completed}
                  goal={goal}
                  onOpenCalendar={onOpenCalendar}
                  onToggleTip={() => setShowTip((current) => !current)}
                  progressDays={progressDays}
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
                editLabel={apiMode ? '운동 장소 변경' : '운동 수정하기'}
                items={displayedRoutineItems}
                minutes={routineMinutes}
                notes={routineNotes}
                onEdit={openEdit}
                onMove={apiMode ? undefined : moveRoutineItem}
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
        </LinearGradient>

        <HomeBottomNavigation activeTab="home" onNavigate={onNavigateTab} />

        {checkinOpen ? (
          <CheckinSheet
            attentionAreaCodes={
              apiMode ? attentionAreaCodes : PREVIEW_DISCOMFORT_CODES
            }
            draft={checkinDraft}
            locationCodes={apiMode ? locationCodes : []}
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
  userName,
}: {
  currentDate: string;
  hasUnreadNotification: boolean;
  onNotifications?: () => void;
  onProfile?: () => void;
  userName: string;
}) {
  const styles = useHomeStyles();
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
          <View
            testID="header-mascot-placeholder"
            style={styles.profilePlaceholder}
          />
        </Pressable>
      </View>
    </View>
  );
}

function WeeklyRoutineCard({
  remainingCount,
  weekDays,
}: {
  remainingCount: number;
  weekDays: readonly WeekDay[];
}) {
  const styles = useHomeStyles();
  return (
    <View style={styles.summaryCard}>
      <Text style={styles.cardTitle}>
        이번 주 남은 루틴은{' '}
        <Text style={styles.greenText}>{remainingCount}회</Text>예요
      </Text>
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

function WeeklyProgressCard({
  completed,
  goal,
  onOpenCalendar,
  onToggleTip,
  progressDays,
  showTip,
  weekLabel,
}: {
  completed: number;
  goal: number;
  onOpenCalendar?: () => void;
  onToggleTip: () => void;
  progressDays: readonly boolean[];
  showTip: boolean;
  weekLabel: string;
}) {
  const styles = useHomeStyles();
  return (
    <View style={styles.progressCard}>
      <View style={styles.progressHeader}>
        <View style={styles.progressTitleRow}>
          <Text numberOfLines={1} style={styles.cardTitle}>
            주간 진행 현황
          </Text>
          <Pressable
            accessibilityLabel="주간 진행 현황 설명 보기"
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
            이번 주에 완료한 운동 횟수예요. 목표만큼 채우면 한 주가 마무리돼요.
          </Text>
        </View>
      ) : null}

      <View style={styles.countRow}>
        <Text style={styles.countLabel}>
          목표 <Text style={styles.countValue}>{goal}</Text> 회
        </Text>
        <Text style={styles.countLabel}>
          완료 <Text style={styles.countValue}>{completed}</Text> 회
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
              source={isDone ? imageAssets.mascotComplete : imageAssets.dayTodo}
              style={[styles.progressImage, !isDone && styles.todoImage]}
              testID={isDone ? 'day-done-image' : 'day-todo-image'}
            />
            {isDone ? (
              <View
                style={styles.progressBadge}
                testID="progress-complete-badge"
              >
                <ProgressCheckIcon />
              </View>
            ) : null}
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
      <Pressable
        accessibilityLabel="오늘 루틴 체크인"
        accessibilityRole="button"
        onPress={onPress}
        style={({ pressed }) => [
          styles.checkinButton,
          pressed ? styles.checkinButtonPressed : styles.checkinButtonIdle,
        ]}
      >
        <OutlinedLabel
          label="오늘 루틴 체크인"
          outlineColor="#FFF0B8"
          style={[styles.checkinLabel, useJua && styles.juaLabel]}
          suffix="🍌"
          suffixStyle={styles.checkinSuffix}
        />
        <CheckinChevronIcon />
      </Pressable>
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
  return (
    <View style={styles.routineCard} testID="home-routine-state">
      <View style={styles.routineBadge}>
        <Text style={styles.routineBadgeText}>오늘의 운동</Text>
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
          const active = drag.activeIndex === index;
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
              <Animated.View
                style={[
                  styles.routineRow,
                  active && styles.dragInnerRoutineActive,
                  active && { transform: [{ translateY: drag.dragY }] },
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
        <OutlinedLabel
          label="운동 시작하기"
          outlineColor="#2F5233"
          style={[styles.startLabel, useJua && styles.juaLabel]}
        />
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
          <RerollIcon color={rerolls >= 2 ? '#B0ACA4' : '#3E7A32'} />
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
  const styles = useHomeStyles();
  const homeColor = activeTab === 'home' ? '#3E7A32' : '#B0ACA4';
  const logColor = activeTab === 'house' ? '#3E7A32' : '#B0ACA4';
  const reportColor = activeTab === 'report' ? '#3E7A32' : '#B0ACA4';
  const myColor = activeTab === 'my' ? '#3E7A32' : '#B0ACA4';
  return (
    <View style={styles.bottomBarOuter}>
      <View accessibilityRole="tablist" style={styles.bottomBar}>
        <TabButton
          active={activeTab === 'home'}
          icon={<HomeTabIcon color={homeColor} />}
          label="홈"
          onPress={() => onNavigate?.('home')}
        />
        <TabButton
          active={activeTab === 'house'}
          icon={<LogTabIcon color={logColor} />}
          label="헬끼의 집"
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
  const styles = useHomeStyles();
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="tab"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={styles.tab}
    >
      {icon}
      <Text style={[styles.tabLabel, active && styles.tabActive]}>{label}</Text>
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
  attentionAreaCodes,
  draft,
  onChangeFatigue,
  onChangeLocation,
  onChangeSeverity,
  onChangeSleepHours,
  onChangeWorkoutMinutes,
  onClearAdverseReactions,
  onClearDiscomforts,
  onClose,
  onSave,
  onToggleAdverseReaction,
  onToggleBodyArea,
  locationCodes,
  pending,
  useJua,
}: {
  attentionAreaCodes: readonly string[];
  draft: HomeCheckin;
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
  onSave: () => void;
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
  const sleepHours = draft.sleepHours.trim();
  const sleepInvalid =
    sleepHours !== '' &&
    (!Number.isFinite(Number(sleepHours)) ||
      Number(sleepHours) < 0 ||
      Number(sleepHours) > 24);
  const durationInvalid =
    !/^\d+$/.test(draft.workoutMinutes) ||
    Number(draft.workoutMinutes) < 5 ||
    Number(draft.workoutMinutes) > 180;
  const adverseSelectionMissing =
    showAdverseDetails && draft.adverseReactionCodes.length === 0;
  const saveDisabled =
    pending || sleepInvalid || durationInvalid || adverseSelectionMissing;
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
          <View style={styles.numberInputGroup}>
            <TextInput
              accessibilityLabel="원하는 운동 시간 (분)"
              inputMode="numeric"
              onChangeText={(value) =>
                onChangeWorkoutMinutes(digitsOnly(value))
              }
              style={styles.numberInput}
              value={draft.workoutMinutes}
            />
            <Text style={styles.numberSuffix}>분</Text>
          </View>
        </View>
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
        <ChoiceBlock label="통증 부위">
          <ChoiceButton
            label="없음"
            onPress={onClearDiscomforts}
            selected={Object.keys(draft.discomforts).length === 0}
          />
          {attentionAreaCodes.map((code) => (
            <ChoiceButton
              key={code}
              label={bodyAreaLabel(code)}
              onPress={() => onToggleBodyArea(code)}
              selected={draft.discomforts[code] !== undefined}
            />
          ))}
        </ChoiceBlock>
        {attentionAreaCodes.length === 0 ? (
          <Text style={styles.messageText}>
            온보딩에서 등록한 주의 부위가 없어요.
          </Text>
        ) : null}
        {attentionAreaCodes
          .filter((code) => draft.discomforts[code] !== undefined)
          .map((code) => (
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
          <Text style={[styles.sheetSaveLabel, useJua && styles.juaLabel]}>
            {pending ? '보내는 중…' : '체크인 !'}
          </Text>
        </Pressable>
      </ScrollView>
    </SheetFrame>
  );
}

function ChoiceBlock({
  children,
  label,
}: {
  children: React.ReactNode;
  label: string;
}) {
  const styles = useHomeStyles();
  return (
    <View style={styles.checkinSection}>
      <Text style={styles.checkinSectionTitle}>{label}</Text>
      <View style={styles.choiceRow}>{children}</View>
    </View>
  );
}

function ChoiceButton({
  label,
  numberOfLines = 1,
  onPress,
  selected,
}: {
  label: string;
  numberOfLines?: number;
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
      style={[styles.choiceButton, selected && styles.choiceButtonSelected]}
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
            const active = drag.activeIndex === index;
            return (
              <View
                key={item.id}
                onLayout={(event) => drag.register(index, event)}
                style={[styles.dragOuterEdit, active && styles.dragOuterActive]}
              >
                <Animated.View
                  style={[
                    styles.editRow,
                    active && styles.dragInnerEditActive,
                    active && { transform: [{ translateY: drag.dragY }] },
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
                    placeholderTextColor="#B5B0A6"
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
                    placeholderTextColor="#B5B0A6"
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
                    placeholderTextColor="#B5B0A6"
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
              placeholderTextColor="#B5B0A6"
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
              placeholderTextColor="#B5B0A6"
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
              placeholderTextColor="#B5B0A6"
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
        onMoveShouldSetPanResponder: (
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
      }),
    [index, onEnd, onMove, onStart],
  );
  return (
    <Pressable
      {...responder.panHandlers}
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
      style={style}
      testID={testID}
    >
      {children}
    </Pressable>
  );
}

function useDragController(onMoveItem: (from: number, to: number) => void) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const activeRef = useRef<number | null>(null);
  const originCenter = useRef(0);
  const centers = useRef<number[]>([]);
  const [dragY] = useState(() => new Animated.Value(0));
  const register = useCallback((index: number, event: LayoutChangeEvent) => {
    const { height, y } = event.nativeEvent.layout;
    centers.current[index] = y + height / 2;
  }, []);
  const start = useCallback(
    (index: number) => {
      activeRef.current = index;
      originCenter.current = centers.current[index] ?? index * 60 + 30;
      dragY.setValue(0);
      setActiveIndex(index);
    },
    [dragY],
  );
  const move = useCallback(
    (dy: number) => {
      const from = activeRef.current;
      if (from === null) {
        return;
      }
      const pointerY = originCenter.current + dy;
      let target = Math.max(0, centers.current.length - 1);
      for (let index = 0; index < centers.current.length; index += 1) {
        const center = centers.current[index];
        if (center !== undefined && pointerY < center) {
          target = index;
          break;
        }
      }
      if (target !== from) {
        onMoveItem(from, target);
        activeRef.current = target;
        setActiveIndex(target);
      }
      const slotCenter = centers.current[target] ?? pointerY;
      dragY.setValue(pointerY - slotCenter);
    },
    [dragY, onMoveItem],
  );
  const end = useCallback(() => {
    activeRef.current = null;
    setActiveIndex(null);
    dragY.setValue(0);
  }, [dragY]);
  const keyboardMove = useCallback(
    (index: number, direction: -1 | 1, length: number) => {
      const target = Math.max(0, Math.min(length - 1, index + direction));
      if (target !== index) {
        onMoveItem(index, target);
      }
    },
    [onMoveItem],
  );
  return { activeIndex, dragY, end, keyboardMove, move, register, start };
}

function OutlinedLabel({
  label,
  outlineColor,
  style,
  suffix,
  suffixStyle,
}: {
  label: string;
  outlineColor: string;
  style: StyleProp<TextStyle>;
  suffix?: string;
  suffixStyle?: StyleProp<TextStyle>;
}) {
  const styles = useHomeStyles();
  const outlineStyle = [styles.outlineText, style, { color: outlineColor }];
  return (
    <View accessible={false} style={styles.outlineContainer}>
      <View style={styles.outlineTextContainer}>
        <Text style={[outlineStyle, styles.outlineLeft]}>{label}</Text>
        <Text style={[outlineStyle, styles.outlineRight]}>{label}</Text>
        <Text style={[outlineStyle, styles.outlineTop]}>{label}</Text>
        <Text style={[outlineStyle, styles.outlineBottom]}>{label}</Text>
        <Text style={[outlineStyle, styles.outlineTopLeft]}>{label}</Text>
        <Text style={[outlineStyle, styles.outlineTopRight]}>{label}</Text>
        <Text style={[outlineStyle, styles.outlineBottomLeft]}>{label}</Text>
        <Text style={[outlineStyle, styles.outlineBottomRight]}>{label}</Text>
        <Text style={style}>{label}</Text>
      </View>
      {suffix ? <Text style={suffixStyle}>{suffix}</Text> : null}
    </View>
  );
}

function NotificationIcon() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 3.5a5.5 5.5 0 0 0-5.5 5.5v3.2L5 15.5h14l-1.5-3.3V9A5.5 5.5 0 0 0 12 3.5Z"
        stroke="#2A2A26"
        strokeWidth={1.7}
        strokeLinejoin="round"
      />
      <Path
        d="M10 18.2a2 2 0 0 0 4 0"
        stroke="#2A2A26"
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
        stroke="#FFFFFF"
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
      <Circle cx={12} cy={12} r={9} stroke="#9A968E" strokeWidth={1.6} />
      <Path
        d="M12 10.6v6"
        stroke="#9A968E"
        strokeWidth={1.8}
        strokeLinecap="round"
      />
      <Circle cx={12} cy={7.6} r={1.1} fill="#9A968E" />
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
        stroke="#4E8B3A"
        strokeWidth={1.7}
      />
      <Path
        d="M3.5 10h17M8.5 3.5v4M15.5 3.5v4"
        stroke="#4E8B3A"
        strokeWidth={1.7}
        strokeLinecap="round"
      />
      <Circle cx={8.5} cy={14} r={1.2} fill="#4E8B3A" />
      <Circle cx={12.5} cy={14} r={1.2} fill="#4E8B3A" />
    </Svg>
  );
}

function ProgressCheckIcon() {
  return (
    <Svg width={12} height={12} viewBox="0 0 24 24" fill="none">
      <Path
        d="M6 12.5l4 4 8-9"
        stroke="#FFFFFF"
        strokeWidth={3.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

function CheckinChevronIcon() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path
        d="M9 5.5L16 12l-7 6.5"
        stroke="#2A2A26"
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
        stroke="#FFFFFF"
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
        stroke="#3E7A32"
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

function moveItem<T>(items: readonly T[], from: number, to: number): T[] {
  const next = Array.from(items);
  const removed = next.splice(from, 1)[0];
  if (removed === undefined) {
    return next;
  }
  next.splice(to, 0, removed);
  return next;
}

function createHomeStyles(
  s: (value: number) => number,
  f: (value: number) => number,
  topPadding: number,
) {
  const shadow = (y: number, blur: number, opacity: number) => ({
    ...Platform.select({
      ios: {
        shadowColor: '#2F5233',
        shadowOffset: { width: 0, height: s(y) },
        shadowOpacity: opacity,
        shadowRadius: s(blur / 2),
      },
      android: { elevation: y <= 4 ? 2 : 3 },
      default: {
        shadowColor: '#2F5233',
        shadowOffset: { width: 0, height: s(y) },
        shadowOpacity: opacity,
        shadowRadius: s(blur / 2),
      },
    }),
  });
  return StyleSheet.create({
    screen: { flex: 1, overflow: 'hidden', backgroundColor: '#FAF7F1' },
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
      color: '#FFFFFF',
      fontSize: f(22),
      fontWeight: '800',
      lineHeight: f(27.5),
      textShadowColor: 'rgba(47,82,51,.18)',
      textShadowOffset: { width: 0, height: s(1) },
      textShadowRadius: s(2),
    },
    greetingName: { color: '#FFD84D' },
    date: {
      marginTop: s(6),
      color: '#F3FBE4',
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
      backgroundColor: '#FBF6DF',
      ...shadow(4, 10, 0.14),
    },
    notificationDot: {
      position: 'absolute',
      top: s(8),
      right: s(8),
      width: s(9),
      height: s(9),
      borderRadius: s(4.5),
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
    profilePlaceholder: {
      width: '100%',
      height: '100%',
      borderRadius: s(24),
      backgroundColor: '#F1F6E7',
    },
    summaryCard: {
      marginBottom: s(14),
      borderRadius: s(22),
      backgroundColor: '#FFFFFF',
      padding: s(16),
      ...shadow(6, 18, 0.1),
    },
    cardTitle: { color: '#2A2A26', fontSize: f(15), fontWeight: '800' },
    greenText: { color: '#3E7A32' },
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
    weekCircleCompleted: { borderColor: '#4E8B3A', backgroundColor: '#4E8B3A' },
    weekCircleIncomplete: {
      borderColor: '#D8D4CB',
      borderStyle: 'dashed',
      backgroundColor: '#FFFFFF',
    },
    weekLabel: { fontSize: f(11.5), fontWeight: '700' },
    weekLabelCompleted: { color: '#3E7A32' },
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
    weekRange: { color: '#8B8780', fontSize: f(12), fontWeight: '600' },
    tip: {
      marginTop: s(10),
      borderRadius: s(12),
      backgroundColor: '#F1F6E7',
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
    countLabel: { color: '#2A2A26', fontSize: f(15), fontWeight: '800' },
    countValue: { color: '#3E7A32', fontSize: f(22) },
    progressCells: { flexDirection: 'row', gap: s(8), marginTop: s(12) },
    progressCell: {
      position: 'relative',
      minWidth: 0,
      flex: 1,
      aspectRatio: 1,
      borderRadius: s(14),
      padding: s(5),
    },
    progressCellCompleted: { backgroundColor: '#EDF5E2', opacity: 1 },
    progressCellIncomplete: { backgroundColor: '#F3F1EB', opacity: 0.55 },
    progressImage: { width: '100%', height: '100%' },
    todoImage: { opacity: 1 },
    progressBadge: {
      position: 'absolute',
      top: s(-4),
      right: s(-4),
      width: s(20),
      height: s(20),
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(2),
      borderColor: '#FFFFFF',
      borderRadius: s(10),
      backgroundColor: '#4E8B3A',
    },
    checkinWrapper: { marginBottom: s(16) },
    checkinButton: {
      width: '100%',
      minHeight: s(64),
      flexDirection: 'row',
      alignItems: 'center',
      gap: s(6),
      borderRadius: s(20),
      paddingVertical: s(19),
      paddingHorizontal: s(20),
    },
    checkinButtonIdle: {
      borderBottomWidth: s(6),
      borderBottomColor: '#E0AF25',
      backgroundColor: '#FBD24E',
    },
    checkinButtonPressed: {
      transform: [{ translateY: s(3) }],
      borderBottomWidth: s(2),
      borderBottomColor: 'rgba(47,82,51,.18)',
      backgroundColor: '#EFC02F',
    },
    checkinLabel: {
      paddingLeft: s(22),
      color: '#342E17',
      fontSize: f(21),
      fontWeight: '400',
      letterSpacing: s(0.5),
      textAlign: 'center',
    },
    checkinSuffix: { fontSize: f(21) },
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
      color: '#2A2A26',
      fontSize: f(15),
      fontWeight: '800',
      textAlign: 'center',
    },
    loadingTitle: { marginTop: s(14) },
    messageText: {
      marginTop: s(8),
      color: '#8B8780',
      fontSize: f(13),
      lineHeight: f(19.5),
      textAlign: 'center',
    },
    loadingRing: {
      width: s(26),
      height: s(26),
      borderWidth: s(3),
      borderColor: '#E3EDD3',
      borderTopColor: '#4E8B3A',
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
    routineBadge: {
      alignSelf: 'flex-start',
      borderRadius: 999,
      backgroundColor: '#4E8B3A',
      paddingVertical: s(6),
      paddingHorizontal: s(12),
    },
    routineBadgeText: { color: '#FFFFFF', fontSize: f(12), fontWeight: '700' },
    routineTitle: {
      marginTop: s(12),
      color: '#2A2A26',
      fontSize: f(26),
      fontWeight: '800',
      letterSpacing: s(-0.5),
    },
    routineSummary: {
      marginTop: s(10),
      color: '#3E7A32',
      fontSize: f(14),
      fontWeight: '700',
    },
    routineNotes: { gap: s(4), marginTop: s(10) },
    routineNote: {
      color: '#6F6B63',
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
      color: '#3E7A32',
      fontSize: f(12.5),
      fontWeight: '700',
      textDecorationLine: 'underline',
    },
    routineList: {
      gap: s(8),
      marginTop: s(14),
      borderTopWidth: s(1),
      borderTopColor: '#E2DED4',
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
      borderWidth: s(1.5),
      borderColor: 'transparent',
      borderRadius: s(12),
      backgroundColor: 'transparent',
    },
    dragOuterEdit: {
      borderWidth: s(1.5),
      borderColor: 'transparent',
      borderRadius: s(16),
      backgroundColor: 'transparent',
    },
    dragOuterActive: {
      borderColor: '#7FAE5C',
      borderStyle: 'dashed',
      backgroundColor: '#EDF5E2',
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
      color: '#2A2A26',
      fontSize: f(13.5),
      fontWeight: '700',
      lineHeight: f(19.575),
    },
    routineDot: {
      width: s(6),
      height: s(6),
      borderRadius: s(3),
      backgroundColor: '#4E8B3A',
    },
    adjustmentNote: {
      marginTop: s(12),
      borderRadius: s(12),
      backgroundColor: '#F1F6E7',
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
      backgroundColor: '#4E8B3A',
      padding: s(16),
    },
    startLabel: { color: '#FFFFFF', fontSize: f(17), fontWeight: '400' },
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
      borderColor: '#CBDDB4',
      borderRadius: s(16),
      backgroundColor: '#FFFFFF',
      paddingVertical: s(14),
      paddingHorizontal: s(6),
    },
    routineActionDisabled: { borderColor: '#E7E3DB' },
    editActionLabel: { color: '#3E7A32', fontSize: f(13.5), fontWeight: '700' },
    rerollActionLabel: {
      color: '#3E7A32',
      fontSize: f(12.5),
      fontWeight: '700',
    },
    rerollActionLabelDisabled: { color: '#B0ACA4' },
    bottomBarOuter: {
      flexShrink: 0,
      backgroundColor: '#FAF7F1',
      paddingTop: s(8),
      paddingHorizontal: s(14),
      paddingBottom: s(26),
    },
    bottomBar: {
      flexDirection: 'row',
      borderRadius: s(22),
      backgroundColor: '#FFFFFF',
      paddingVertical: s(10),
      paddingHorizontal: s(6),
      ...shadow(-2, 14, 0.07),
    },
    tab: {
      minHeight: s(48),
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      gap: s(4),
      paddingVertical: s(6),
      paddingHorizontal: s(2),
    },
    tabLabel: {
      color: '#B0ACA4',
      fontSize: f(11.5),
      fontWeight: '700',
      textAlign: 'center',
    },
    tabActive: { color: '#3E7A32' },
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
      backgroundColor: '#FAF7F1',
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
    sheetTitle: { color: '#2A2A26', fontSize: f(18), fontWeight: '800' },
    closeButton: {
      width: s(44),
      height: s(44),
      alignItems: 'center',
      justifyContent: 'center',
      marginTop: s(-10),
      marginRight: s(-12),
      marginBottom: s(-10),
    },
    closeText: { color: '#8B8780', fontSize: f(22) },
    sheetIntro: {
      marginTop: s(4),
      color: '#8B8780',
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
    reasonBullet: { color: '#4E8B3A', fontSize: f(14), lineHeight: f(20) },
    reasonText: {
      minWidth: 0,
      flex: 1,
      color: '#6F6B63',
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
      color: '#3E7A32',
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
      color: '#2A2A26',
      fontSize: f(14),
      fontWeight: '700',
    },
    choiceRow: { flexDirection: 'row', gap: s(6), marginTop: s(10) },
    choiceButton: {
      minWidth: 0,
      minHeight: s(44),
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(1.5),
      borderColor: '#E7E3DB',
      borderRadius: s(12),
      backgroundColor: '#FAF7F1',
      paddingVertical: s(9),
      paddingHorizontal: s(6),
    },
    choiceButtonSelected: {
      borderColor: '#4E8B3A',
      backgroundColor: '#4E8B3A',
    },
    choiceButtonText: { color: '#2A2A26', fontSize: f(13), fontWeight: '700' },
    choiceButtonTextSelected: { color: '#FFFFFF' },
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
    numberLabel: { color: '#2A2A26', fontSize: f(14), fontWeight: '700' },
    optionalText: { color: '#8B8780', fontWeight: '500' },
    numberInputGroup: { flexDirection: 'row', alignItems: 'center', gap: s(6) },
    numberInput: {
      width: s(84),
      borderWidth: s(1),
      borderColor: '#E7E3DB',
      borderRadius: s(12),
      backgroundColor: '#FAF7F1',
      color: '#2A2A26',
      fontSize: f(14),
      fontWeight: '700',
      paddingVertical: s(11),
      paddingHorizontal: s(12),
      textAlign: 'right',
    },
    stepsInput: { width: s(110) },
    numberSuffix: { color: '#8B8780', fontSize: f(13) },
    sheetSaveButton: {
      width: '100%',
      alignItems: 'center',
      justifyContent: 'center',
      marginTop: s(8),
      borderBottomWidth: s(5),
      borderBottomColor: '#E0AF25',
      borderRadius: s(18),
      backgroundColor: '#FBD24E',
      padding: s(17),
    },
    sheetSaveLabel: { color: '#2A2A26', fontSize: f(18), fontWeight: '400' },
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
      color: '#2A2A26',
      fontSize: f(13.5),
      fontWeight: '700',
      paddingVertical: s(6),
    },
    editSetsInput: {
      width: s(38),
      borderWidth: s(1),
      borderColor: '#E7E3DB',
      borderRadius: s(10),
      backgroundColor: '#FAF7F1',
      color: '#2A2A26',
      fontSize: f(13),
      fontWeight: '700',
      paddingVertical: s(8),
      paddingHorizontal: s(2),
      textAlign: 'center',
    },
    editRepsInput: {
      width: s(44),
      borderWidth: s(1),
      borderColor: '#E7E3DB',
      borderRadius: s(10),
      backgroundColor: '#FAF7F1',
      color: '#2A2A26',
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
      borderColor: '#CBDDB4',
      borderStyle: 'dashed',
      borderRadius: s(16),
      backgroundColor: '#FFFFFF',
      padding: s(12),
    },
    addTitle: { color: '#3E7A32', fontSize: f(12), fontWeight: '700' },
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
      borderColor: '#E7E3DB',
      borderRadius: s(10),
      backgroundColor: '#FAF7F1',
      color: '#2A2A26',
      fontSize: f(13.5),
      fontWeight: '700',
      padding: s(10),
    },
    addSetsInput: {
      width: s(38),
      borderWidth: s(1),
      borderColor: '#E7E3DB',
      borderRadius: s(10),
      backgroundColor: '#FAF7F1',
      color: '#2A2A26',
      fontSize: f(13),
      fontWeight: '700',
      paddingVertical: s(10),
      paddingHorizontal: s(2),
      textAlign: 'center',
    },
    addRepsInput: {
      width: s(44),
      borderWidth: s(1),
      borderColor: '#E7E3DB',
      borderRadius: s(10),
      backgroundColor: '#FAF7F1',
      color: '#2A2A26',
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
    addButtonEnabled: { backgroundColor: '#4E8B3A' },
    addButtonDisabled: { backgroundColor: '#E7E3DB' },
    addButtonText: {
      fontSize: f(13.5),
      fontWeight: '700',
      textAlign: 'center',
    },
    addButtonTextEnabled: { color: '#FFFFFF' },
    addButtonTextDisabled: { color: '#B0ACA4' },
    editActions: { flexDirection: 'row', gap: s(8), marginTop: s(16) },
    resetButton: {
      width: s(112),
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(1.5),
      borderColor: '#E7E3DB',
      borderRadius: s(18),
      backgroundColor: '#FFFFFF',
      paddingVertical: s(16),
      paddingHorizontal: s(8),
    },
    resetLabel: { color: '#8B8780', fontSize: f(12.5), fontWeight: '700' },
    editSaveButton: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      borderBottomWidth: s(5),
      borderBottomColor: '#E0AF25',
      borderRadius: s(18),
      backgroundColor: '#FBD24E',
      padding: s(16),
    },
    outlineContainer: {
      minWidth: 0,
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
    },
    outlineTextContainer: {
      alignItems: 'center',
      justifyContent: 'center',
    },
    outlineText: {
      position: 'absolute',
    },
    outlineLeft: { transform: [{ translateX: s(-1) }] },
    outlineRight: { transform: [{ translateX: s(1) }] },
    outlineTop: { transform: [{ translateY: s(-1) }] },
    outlineBottom: { transform: [{ translateY: s(1) }] },
    outlineTopLeft: {
      transform: [{ translateX: s(-1) }, { translateY: s(-1) }],
    },
    outlineTopRight: {
      transform: [{ translateX: s(1) }, { translateY: s(-1) }],
    },
    outlineBottomLeft: {
      transform: [{ translateX: s(-1) }, { translateY: s(1) }],
    },
    outlineBottomRight: {
      transform: [{ translateX: s(1) }, { translateY: s(1) }],
    },
  });
}
