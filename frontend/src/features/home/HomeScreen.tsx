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
  ActivityIndicator,
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
  actionLabel,
  agentTypeLabel,
  bodyAreaLabel,
  decisionReasonLabel,
  DEFAULT_BODY_AREA_OPTIONS,
  EXTENDED_BODY_AREA_OPTIONS,
  locationLabel,
  planRevisionReasonLabel,
  sessionStatusLabel,
} from '../../api/labels';
import type { Api } from '../../api/endpoints';
import type {
  ActionCode,
  DailyContextResponse,
  DecisionResponse,
  ExerciseVariantsResponse,
  PainAreaInput,
  RoutineResponse,
  SessionStatusCode,
  WeekResponse,
  WeeklyPlanRevisionResponse,
  WorkoutPlan,
  WorkoutSessionDetailResponse,
  WorkoutSessionLogSummary,
} from '../../api/types';
import { moveArrayItem } from '../../api/workoutPlan';
import { imageAssets } from '../../assets';
import { fontFamilies, useBrandFonts } from '../../app/fonts';
import type { TabId } from '../../components/brand/BrandChrome';
import { ProfileAvatar } from '../../components/profile/ProfileAvatar';
import { PainIntensitySlider } from '../../components/profile/PainIntensitySlider';
import { getContainedInterfaceScale, useScale } from '../../components/scale';
import { GradientActionButton } from '../../components/primitives';
import { colors } from '../../components/theme';
import { ExerciseDetailSheet } from '../workout/ExerciseDetailSheet';
import {
  ExerciseVariantsAction,
  ExerciseVariantsContent,
} from '../workout/ExerciseVariants';
import {
  HOME_CHECKIN_OPTIONS,
  HOME_DEFAULT_CHECKIN,
  HOME_ROUTINE_VARIANTS,
  HOME_WEEK_DAYS,
  apiCheckinDraft,
  applyRoutineItemOverrides,
  checkinFromContext,
  copyRoutineItems,
  formatHomeDate,
  formatRoutineItem,
  formatWeekRange,
  formatWeekRangeForLocalDate,
  getHomeRoutineVariant,
  getHomeRerollLabel,
  homeCheckinDraftsEqual,
  deriveTodayRoutineViewState,
  routineItemOverrides,
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
  type LocalWorkoutPresentationState,
  type RoutineItemDraftOverride,
  type TodayRoutinePhase,
} from './homeModel';
import {
  RoutineGenerationLoading,
  type RoutineGenerationPhaseCode,
} from './RoutineGenerationLoading';

export const HOME_BACKGROUND_COLOR = '#FFF8E5';

// Temporarily hide the optional availability-time editor while preserving its
// draft and API values so it can be restored without a contract change.
const CHECKIN_AVAILABILITY_INPUT_ENABLED: boolean = false;

const CHECKIN_DURATION_MINUTES = {
  min: 10,
  max: 60,
  step: 10,
} as const;
const EMPTY_PERSISTENT_PAINS: readonly PainAreaInput[] = [];
const EMPTY_ITEM_OVERRIDES: readonly RoutineItemDraftOverride[] = [];

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

export type HomeBusyKind =
  'decision-generation' | 'regeneration' | 'revision' | 'starting';

export type HomeUserEdits = {
  itemOverrides: readonly RoutineItemDraftOverride[];
};

export type HomeScreenProps = {
  actionError?: string | null;
  alternativeUsedCount?: number;
  busy?: HomeBusyKind | null;
  currentDate?: string;
  context?: DailyContextResponse | null;
  decision?: DecisionResponse | null;
  errorMessage?: string;
  exerciseApi?: Pick<Api, 'getExercise'> &
    Partial<Pick<Api, 'getExerciseVariants'>>;
  hasTodayRoutine?: boolean;
  hasUnreadNotification?: boolean;
  localDate?: string;
  locationCodes?: readonly string[];
  nickname?: string;
  onChooseRest?: () => void;
  onEditRoutine?: () => void;
  onNavigateTab?: (tab: HomeTab) => void;
  onNotifications?: () => void;
  onOpenCalendar?: () => void;
  onOpenCheckin?: () => void;
  onProfile?: () => void;
  onRegenerateDecision?: () => void;
  onRequestAlternativeCheckin?: (
    draft: HomeCheckinDraft,
    changed: boolean,
  ) => void;
  onRequestAlternative?: () => void;
  onReorderPlan?: (from: number, to: number) => void;
  onRetry?: () => void;
  onRetryDecision?: () => void;
  onRetryCheckin?: () => void;
  onSaveCheckin?: () => void;
  onSaveEdit?: (items: readonly HomeRoutineItem[]) => void;
  onStartWorkout?: () => void;
  onResumeWorkout?: () => void;
  onSubmitCheckin?: (draft: HomeCheckinDraft) => void;
  onSubmitUserEdits?: (edits: HomeUserEdits) => void;
  permissionDenied?: boolean;
  planRevision?: WeeklyPlanRevisionResponse | null;
  persistentPains?: readonly PainAreaInput[];
  previewState?: HomePreviewState;
  profileImageUrl?: string | null;
  restToday?: boolean;
  routine?: RoutineResponse | null;
  /** Animated artwork slot. The generation component supplies a placeholder until provided. */
  routineLoadingContent?: React.ReactNode;
  /** Optional future server-owned progress code; omitted while the API is synchronous. */
  routineLoadingPhaseCode?: RoutineGenerationPhaseCode;
  sessions?: readonly WorkoutSessionLogSummary[];
  staleContext?: boolean;
  status?: 'loading' | 'error' | 'ready';
  todaySession?: WorkoutSessionDetailResponse | null;
  localSessionState?: LocalWorkoutPresentationState;
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
  alternativeUsedCount = 0,
  busy = null,
  context = null,
  currentDate = '2026.08.11 (화)',
  decision = null,
  errorMessage,
  exerciseApi,
  hasTodayRoutine = true,
  hasUnreadNotification = false,
  initialState,
  localDate,
  locationCodes = [],
  nickname,
  onChooseRest,
  onEditRoutine,
  onNavigateTab,
  onNotifications,
  onOpenCalendar,
  onOpenCheckin,
  onProfile,
  onRegenerateDecision,
  onRequestAlternativeCheckin,
  onRequestAlternative,
  onReorderPlan,
  onRetry,
  onRetryDecision,
  onRetryCheckin,
  onSaveCheckin,
  onSaveEdit,
  onStartWorkout,
  onResumeWorkout,
  onSubmitCheckin,
  onSubmitUserEdits,
  permissionDenied = false,
  planRevision = null,
  persistentPains = EMPTY_PERSISTENT_PAINS,
  profileImageUrl = null,
  restToday = false,
  routine = null,
  routineLoadingContent,
  routineLoadingPhaseCode,
  sessions = [],
  staleContext = false,
  status,
  todaySession = null,
  localSessionState = 'ACTIVE',
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
  const [checkinIntent, setCheckinIntent] = useState<'INITIAL' | 'ALTERNATIVE'>(
    'INITIAL',
  );
  const [timePickerTarget, setTimePickerTarget] =
    useState<TimePickerTarget | null>(null);
  const [editOpen, setEditOpen] = useState(
    initialState === 'editing' && !apiMode,
  );
  const [inlineEditing, setInlineEditing] = useState(
    initialState === 'editing' && apiMode,
  );
  const [reasonOpen, setReasonOpen] = useState(false);
  const [exerciseGuide, setExerciseGuide] = useState<HomeRoutineItem | null>(
    null,
  );
  const [variantGuide, setVariantGuide] = useState<{
    exerciseName: string;
    response: ExerciseVariantsResponse;
  } | null>(null);
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
        ? checkinFromContext(context, persistentPains, locationCodes[0] ?? null)
        : initialState === 'adjusted'
          ? {
              ...HOME_DEFAULT_CHECKIN,
              pains: { KNEE: 3 },
              redFlagPresent: false,
              workoutMinutes: '40',
            }
          : initialState === 'pre-checkin' || initialState === 'checkin'
            ? { ...HOME_DEFAULT_CHECKIN, pains: {} }
            : {
                ...HOME_DEFAULT_CHECKIN,
                pains: {},
                redFlagPresent: false,
                workoutMinutes: '40',
              },
    [apiMode, context, initialState, locationCodes, persistentPains],
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
  // The override is tied to the plan it was made against. Any new plan from the
  // flow above — the stored edit, a reorder, a rejected edit rolled back, a
  // regenerated routine — is the answer to it, so it stops applying.
  const [presentationOverrides, setPresentationOverrides] = useState<{
    plan: WorkoutPlan | null;
    overrides: readonly RoutineItemDraftOverride[];
  }>({ plan: null, overrides: EMPTY_ITEM_OVERRIDES });
  const activeOverrides =
    presentationOverrides.plan === serverPlan
      ? presentationOverrides.overrides
      : EMPTY_ITEM_OVERRIDES;
  const presentedServerRoutineItems = useMemo(
    () => applyRoutineItemOverrides(serverRoutineItems, activeOverrides),
    [activeOverrides, serverRoutineItems],
  );
  const displayedRoutineItems = apiMode
    ? presentedServerRoutineItems
    : routineItems;
  const serverCheckin = useMemo(
    () =>
      checkinFromContext(context, persistentPains, locationCodes[0] ?? null),
    [context, locationCodes, persistentPains],
  );
  const displayedCheckin = apiMode ? serverCheckin : committedCheckin;
  const [editDraft, setEditDraft] = useState<HomeRoutineItem[]>(() =>
    copyRoutineItems(displayedRoutineItems),
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
  const progressPercent = weeklyCompletionPercentage(completed, goal);
  const effectiveCheckedIn = apiMode ? context !== null : checkedIn;
  const rerolls = apiMode
    ? Math.max(alternativeUsedCount, decision?.regeneration_sequence ?? 0)
    : previewRerolls;
  const rerollLoading = apiMode
    ? busy === 'regeneration'
    : rerolling && effectiveCheckedIn;
  const routineGenerationPending = apiMode
    ? busy === 'decision-generation' ||
      busy === 'regeneration' ||
      busy === 'revision'
    : rerollLoading;
  const generationPreviewItems = displayedRoutineItems;
  const seriousDecision =
    decision?.action_code === 'STOP_AND_SEEK_HELP' ||
    decision?.safety_status_code === 'BLOCKED';
  const hasVisibleSession = todaySession !== null && serverPlan !== null;
  const hasRoutine = apiMode
    ? serverPlan !== null &&
      !routineGenerationPending &&
      (hasVisibleSession || !restToday)
    : hasTodayRoutine && effectiveCheckedIn && !routineGenerationPending;
  const noRoutine = !hasRoutine && !routineGenerationPending;
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
      Boolean(decision.public_agent_summaries?.length));
  const blockingRevisionNotice =
    planRevision?.routine === null ? currentRevisionNotice : null;
  const routineRevisionNotice =
    planRevision?.routine !== null ? currentRevisionNotice : null;
  const painPart =
    Object.keys(displayedCheckin.pains).map(bodyAreaLabel).join('·') || null;
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

  const openCheckin = (intent: 'INITIAL' | 'ALTERNATIVE' = 'INITIAL') => {
    setCheckinDraft({ ...displayedCheckin });
    setCheckinIntent(intent);
    setCheckinOpen(true);
    onOpenCheckin?.();
  };

  const closeCheckin = () => {
    setCheckinDraft({ ...displayedCheckin });
    setTimePickerTarget(null);
    setCheckinOpen(false);
    setCheckinIntent('INITIAL');
  };

  const runPreviewAlternative = () => {
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

  const saveCheckin = () => {
    const saved = {
      ...checkinDraft,
      workoutMinutes: clampNumericString(
        checkinDraft.workoutMinutes,
        CHECKIN_DURATION_MINUTES.min,
        CHECKIN_DURATION_MINUTES.max,
      ),
    };
    const savedDraft = apiCheckinDraft(saved);
    const changed = !homeCheckinDraftsEqual(
      savedDraft,
      apiCheckinDraft(displayedCheckin),
    );
    setCommittedCheckin(saved);
    setCheckinDraft(saved);
    setCheckedIn(true);
    setTimePickerTarget(null);
    setCheckinOpen(false);
    if (checkinIntent === 'ALTERNATIVE') {
      setCheckinIntent('INITIAL');
      if (apiMode) {
        if (onRequestAlternativeCheckin) {
          onRequestAlternativeCheckin(savedDraft, changed);
        } else {
          onRegenerateDecision?.();
        }
      } else {
        runPreviewAlternative();
      }
      return;
    }
    if (apiMode) {
      onSubmitCheckin?.(savedDraft);
    } else {
      onSaveCheckin?.();
    }
  };

  const openEdit = () => {
    setEditDraft(copyRoutineItems(displayedRoutineItems));
    setNewItem({ id: 'new', name: '', sets: '', reps: '' });
    if (apiMode) {
      setInlineEditing(true);
    } else {
      setEditOpen(true);
    }
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

  const inlineEditInvalid = editDraft.some((item) => {
    const sets = Number(item.sets);
    const reps = item.reps === undefined ? null : Number(item.reps);
    return (
      !Number.isInteger(sets) ||
      sets < 1 ||
      (reps !== null && (!Number.isInteger(reps) || reps < 1))
    );
  });

  // The override shows the edit immediately; the container applies the same
  // edit to today's plan and asks the server to store it. Whatever comes back
  // replaces the override, so a rejected edit does not keep being displayed.
  const saveInlineEdit = () => {
    if (inlineEditInvalid) {
      return;
    }
    const itemOverrides = routineItemOverrides(serverRoutineItems, editDraft);
    setPresentationOverrides({ plan: serverPlan, overrides: itemOverrides });
    setInlineEditing(false);
    onSubmitUserEdits?.({ itemOverrides });
  };

  const patchInlinePrescription = (
    id: string,
    patch: Pick<Partial<HomeRoutineItem>, 'sets' | 'reps'>,
  ) =>
    setEditDraft((current) =>
      current.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    );

  const navigateFromHome = (tab: HomeTab) => {
    if (inlineEditing) {
      setEditDraft(copyRoutineItems(displayedRoutineItems));
      setInlineEditing(false);
    }
    onNavigateTab?.(tab);
  };

  const requestAlternative = () => {
    if (rerolling || rerolls >= 2) {
      return;
    }
    if (apiMode) {
      openCheckin('ALTERNATIVE');
    } else {
      runPreviewAlternative();
    }
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
  const recheckMode =
    apiMode && (restToday || restRecommended || seriousDecision);
  const todayRoutineState = deriveTodayRoutineViewState({
    alternativeUsedCount: rerolls,
    contextExists: effectiveCheckedIn,
    decisionError: Boolean(actionError || blockingRevisionNotice),
    decisionHasPlan: apiMode
      ? serverPlan !== null
      : hasTodayRoutine && effectiveCheckedIn,
    decisionIsBlocked: Boolean(restToday || restRecommended || seriousDecision),
    generationPending: routineGenerationPending,
    localSessionState,
    session: todaySession,
  });
  const completedPlanItemIds =
    todayRoutineState.progress?.completedPlanItemIds ?? [];
  const reorderUnfinishedPlan = (from: number, to: number) => {
    const items = inlineEditing ? editDraft : displayedRoutineItems;
    const source = items[from];
    const target = items[to];
    if (
      source === undefined ||
      target === undefined ||
      completedPlanItemIds.includes(source.id) ||
      completedPlanItemIds.includes(target.id) ||
      // Warm-up, main and cool-down keep their own order (ADR-0018 D5).
      (source.phaseCode ?? 'MAIN') !== (target.phaseCode ?? 'MAIN')
    ) {
      return;
    }
    if (inlineEditing) {
      setEditDraft((current) => moveArrayItem(current, from, to));
    }
    onReorderPlan?.(from, to);
  };
  const routineBlockedReason =
    routineOption && !routineOption.selectable
      ? ((routineOption.blocked_reason_code
          ? decisionReasonLabel(routineOption.blocked_reason_code)
          : null) ?? '지금은 이 루틴을 시작할 수 없어요.')
      : null;
  const showCheckin =
    contentReady &&
    (!apiMode || routine !== null) &&
    !routineGenerationPending &&
    !staleContext &&
    (!apiMode || todayRoutineState.capabilities.canCheckIn);
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
              disabled={inlineEditing}
              hasUnreadNotification={hasUnreadNotification}
              onNotifications={onNotifications}
              onProfile={onProfile}
              profileImageUrl={profileImageUrl}
              useJua={useJua}
              userName={displayName}
            />
            {contentReady ? (
              <WeeklyOverviewCard
                completed={completed}
                disabled={inlineEditing}
                goal={goal}
                onOpenCalendar={onOpenCalendar}
                onToggleTip={() => setShowTip((current) => !current)}
                progressPercent={progressPercent}
                showTip={showTip}
                weekDays={weekDays}
                weekLabel={displayWeekLabel}
              />
            ) : null}
            {showCheckin ? (
              <CheckinButton
                label={recheckMode ? '다시 체크인하기' : undefined}
                onPress={() => openCheckin('INITIAL')}
              />
            ) : null}

            {apiMode && status === 'loading' ? (
              <RoutineLookupCard loading />
            ) : null}
            {apiMode && status === 'error' ? (
              permissionDenied ? (
                <HomeStateCard
                  text="계정 상태를 확인한 뒤 다시 이용해주세요."
                  title="오늘의 운동 정보에 접근할 권한이 없어요."
                />
              ) : (
                <RoutineLookupCard loading={false} onRetry={onRetry} />
              )
            ) : null}
            {contentReady && (actionError || blockingRevisionNotice) ? (
              <HomeStateCard
                actionLabel={
                  staleContext
                    ? '최신 상태로 다시 시도'
                    : onRetryDecision
                      ? '루틴 생성 다시 시도'
                      : undefined
                }
                onAction={staleContext ? onRetryCheckin : onRetryDecision}
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
            {apiMode &&
            contentReady &&
            restToday &&
            !routineGenerationPending ? (
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
              <EmptyRoutineCard baselineReady={apiMode && routine !== null} />
            ) : null}
            {contentReady && routineGenerationPending ? (
              <GeneratingRoutineCard
                content={routineLoadingContent}
                items={generationPreviewItems}
                phaseCode={routineLoadingPhaseCode}
              />
            ) : null}
            {contentReady &&
            (!restToday || hasVisibleSession) &&
            (!seriousDecision || hasVisibleSession) &&
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
                completedItemIds={completedPlanItemIds}
                currentPlanItemId={
                  todayRoutineState.progress?.currentPlanItemId ?? null
                }
                editDisabled={inlineEditing && inlineEditInvalid}
                editing={apiMode && inlineEditing}
                editLabel={
                  apiMode
                    ? inlineEditing
                      ? '저장하기'
                      : '세트·횟수 수정'
                    : '운동 수정하기'
                }
                items={
                  apiMode && inlineEditing ? editDraft : displayedRoutineItems
                }
                minutes={routineMinutes}
                notes={routineNotes}
                onEdit={
                  todayRoutineState.capabilities.canEditRoutine
                    ? inlineEditing
                      ? saveInlineEdit
                      : openEdit
                    : undefined
                }
                onMove={
                  todayRoutineState.capabilities.canReorderRoutine
                    ? apiMode
                      ? reorderUnfinishedPlan
                      : moveRoutineItem
                    : undefined
                }
                onChangePrescription={patchInlinePrescription}
                onOpenExerciseGuide={
                  exerciseApi ? (item) => setExerciseGuide(item) : undefined
                }
                onOpenExerciseVariants={(item, response) =>
                  setVariantGuide({
                    exerciseName: item.name,
                    response,
                  })
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
                onRequestAlternative={
                  todayRoutineState.phase === 'READY' &&
                  (!apiMode || decision?.regeneration_sequence != null)
                    ? requestAlternative
                    : undefined
                }
                onStart={
                  todayRoutineState.capabilities.canResume
                    ? onResumeWorkout
                    : todayRoutineState.capabilities.canStart &&
                        (!apiMode || routineOption?.selectable)
                      ? onStartWorkout
                      : undefined
                }
                painPart={painPart}
                phase={todayRoutineState.phase}
                pending={busy !== null}
                rerolling={apiMode ? busy === 'regeneration' : rerolling}
                rerolls={rerolls}
                revisionNotice={routineRevisionNotice?.text}
                startBlockedReason={routineBlockedReason}
                title={routineTitle}
                focus={routineFocus}
                variantApi={exerciseApi}
              />
            ) : null}
          </ScrollView>
        </View>

        <HomeBottomNavigation activeTab="home" onNavigate={navigateFromHome} />

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
            onChangePainIntensity={(bodyAreaCode, intensityScore) =>
              setCheckinDraft((current) => ({
                ...current,
                pains: {
                  ...current.pains,
                  [bodyAreaCode]: intensityScore,
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
            onClearPains={() =>
              setCheckinDraft((current) => ({
                ...current,
                pains: {},
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
            onSetRedFlag={(redFlagPresent) =>
              setCheckinDraft((current) => ({
                ...current,
                redFlagPresent,
              }))
            }
            onToggleBodyArea={(code) =>
              setCheckinDraft((current) => {
                const pains = { ...current.pains };
                if (pains[code] === undefined) {
                  pains[code] = 1;
                } else {
                  delete pains[code];
                }
                return { ...current, pains };
              })
            }
            pending={busy === 'decision-generation' || busy === 'regeneration'}
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

        {reasonOpen && decision !== null ? (
          <RecommendationReasonSheet
            decision={decision}
            onClose={() => setReasonOpen(false)}
            reasons={recommendationReasons}
          />
        ) : null}

        {exerciseGuide?.exerciseId && exerciseApi ? (
          <SheetFrame
            onClose={() => setExerciseGuide(null)}
            title={exerciseGuide.name}
            zIndex={25}
          >
            <ExerciseDetailSheet
              api={exerciseApi}
              exerciseId={exerciseGuide.exerciseId}
            />
          </SheetFrame>
        ) : null}

        {variantGuide ? (
          <SheetFrame
            onClose={() => setVariantGuide(null)}
            title={`${variantGuide.exerciseName} 장비 안내`}
            zIndex={25}
          >
            <ScrollView
              contentContainerStyle={styles.sheetScrollContent}
              showsVerticalScrollIndicator={false}
            >
              <ExerciseVariantsContent response={variantGuide.response} />
            </ScrollView>
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
          />
        ) : null}
      </View>
    </HomeStyleContext.Provider>
  );
}

function HomeHeader({
  currentDate,
  disabled,
  hasUnreadNotification,
  onNotifications,
  onProfile,
  profileImageUrl,
  useJua,
  userName,
}: {
  currentDate: string;
  disabled: boolean;
  hasUnreadNotification: boolean;
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
function WeeklyOverviewCard({
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

function CheckinButton({
  label = '오늘 루틴 체크인',
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
        testID="home-checkin"
        trailing={<CheckinChevronIcon />}
      />
    </View>
  );
}

function EmptyRoutineCard({
  baselineReady = false,
}: {
  baselineReady?: boolean;
}) {
  const styles = useHomeStyles();
  return (
    <View style={styles.messageCard} testID="home-empty-state">
      <Text style={styles.messageTitle}>
        {baselineReady
          ? '오늘 운동을 준비해볼까요?'
          : '아직 오늘의 운동이 없어요'}
      </Text>
      <Text style={styles.messageText}>
        {baselineReady
          ? '오늘 컨디션을 알려주면 나에게 맞게 운동을 조정해드려요.'
          : '오늘 체크인을 하면 컨디션에 맞는 추천 루틴을 받아볼 수 있어요.'}
      </Text>
    </View>
  );
}

function RoutineLookupCard({
  loading,
  onRetry,
}: {
  loading: boolean;
  onRetry?: () => void;
}) {
  const styles = useHomeStyles();
  return (
    <View style={styles.messageCard} testID="home-routine-lookup-state">
      {loading ? (
        <ActivityIndicator
          color="#5C9445"
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
          ? '운동 계획을 준비하고 있어요'
          : '운동 계획을 준비하지 못했어요'}
      </Text>
      <Text
        accessibilityRole={loading ? undefined : 'alert'}
        style={styles.messageText}
      >
        {loading
          ? '잠시만 기다려 주세요.\n준비가 끝나면 오늘 컨디션을 여쭤볼게요.'
          : '운동 계획을 준비하는 중 문제가 생겼어요.\n잠시 후 다시 시도해 주세요.'}
      </Text>
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

function GeneratingRoutineCard({
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

const ROUTINE_NOTES = [
  '오늘 컨디션과 운동 목표를 반영했어요.',
  '사용자 적합성과 안전 기준을 확인한 구성이에요.',
] as const;

function RoutineCard({
  actionCode,
  completedItemIds,
  currentPlanItemId,
  editDisabled,
  editing,
  editLabel,
  focus,
  items,
  minutes,
  notes = ROUTINE_NOTES,
  onEdit,
  onChangePrescription,
  onMove,
  onOpenExerciseGuide,
  onOpenExerciseVariants,
  onOpenReasons,
  onRest,
  onRequestAlternative,
  onStart,
  painPart,
  pending,
  phase,
  rerolling,
  rerolls,
  revisionNotice,
  startBlockedReason,
  title,
  variantApi,
}: {
  actionCode?: ActionCode;
  completedItemIds: readonly string[];
  currentPlanItemId: string | null;
  editDisabled: boolean;
  editing: boolean;
  editLabel: string;
  focus: string;
  items: readonly HomeRoutineItem[];
  minutes: string;
  notes?: readonly string[];
  onEdit?: () => void;
  onChangePrescription: (
    id: string,
    patch: Pick<Partial<HomeRoutineItem>, 'sets' | 'reps'>,
  ) => void;
  onMove?: (from: number, to: number) => void;
  onOpenExerciseGuide?: (item: HomeRoutineItem) => void;
  onOpenExerciseVariants: (
    item: HomeRoutineItem,
    response: ExerciseVariantsResponse,
  ) => void;
  onOpenReasons?: () => void;
  onRest?: () => void;
  onRequestAlternative?: () => void;
  onStart?: () => void;
  painPart: string | null;
  pending: boolean;
  phase: TodayRoutinePhase;
  rerolling: boolean;
  rerolls: number;
  revisionNotice?: string;
  startBlockedReason?: string | null;
  title: string;
  variantApi?: Partial<Pick<Api, 'getExerciseVariants'>>;
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
  const locked =
    phase === 'SESSION_ACTIVE' ||
    phase === 'STOPPED_RESUMABLE' ||
    phase === 'STOPPED_SAFETY' ||
    phase === 'COMPLETED';
  const interactionsDisabled = editing;
  const primaryActionLabel =
    phase === 'SESSION_ACTIVE' || phase === 'STOPPED_RESUMABLE'
      ? '이어하기'
      : '운동 시작하기';
  const statusCopy =
    phase === 'STOPPED_SAFETY'
      ? '안전 관련 중단으로 오늘은 이어서 진행할 수 없어요. 진행 기록은 그대로 보관됩니다.'
      : phase === 'COMPLETED'
        ? '오늘 운동 기록이에요. 완료한 운동과 진행 상태를 확인할 수 있어요.'
        : phase === 'SESSION_ACTIVE'
          ? '진행 중인 운동이에요. 완료한 항목부터 이어서 진행할 수 있어요.'
          : phase === 'STOPPED_RESUMABLE'
            ? '잠시 멈춘 운동이에요. 완료한 항목부터 이어서 진행할 수 있어요.'
            : null;
  return (
    <View style={styles.routineCard} testID="home-routine-state">
      <View style={styles.routineBadgeRow}>
        <View style={styles.routineBadge}>
          <Text style={styles.routineBadgeText}>
            {phase === 'STOPPED_SAFETY'
              ? '안전 중단'
              : phase === 'COMPLETED'
                ? '운동 기록'
                : locked
                  ? '운동 진행 중'
                  : '운동 준비 완료'}
          </Text>
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
      <Text style={styles.routineTitle}>
        오늘 컨디션에 맞춘 운동이 준비됐어요.
      </Text>
      <Text style={styles.routinePlanName}>{title}</Text>
      <Text style={styles.routineSummary}>
        {focus} · {minutes}분
      </Text>
      {statusCopy ? (
        <View style={styles.adjustmentNote}>
          <Text style={styles.adjustmentText}>{statusCopy}</Text>
        </View>
      ) : null}
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
          accessibilityState={{ disabled: interactionsDisabled }}
          disabled={interactionsDisabled}
          onPress={onOpenReasons}
          style={[
            styles.reasonLink,
            interactionsDisabled && styles.disabledControl,
          ]}
        >
          <Text
            style={[
              styles.reasonLinkText,
              interactionsDisabled && styles.disabledLabel,
            ]}
          >
            추천 이유 보기
          </Text>
        </Pressable>
      ) : null}
      <View style={styles.routineList}>
        {onMove ? (
          <Text style={styles.orderHint}>
            운동 순서는 자유롭게 바꿀 수 있어요.
          </Text>
        ) : null}
        {items.map((item, index) => {
          const completed = completedItemIds.includes(item.id);
          const current = currentPlanItemId === item.id && !completed;
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
                  completed && styles.routineRowCompleted,
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
                {onMove && !completed && !editing ? (
                  <DragHandle
                    disabled={interactionsDisabled}
                    index={index}
                    onEnd={drag.end}
                    onKeyboardMove={(direction) =>
                      drag.keyboardMove(index, direction, items.length)
                    }
                    onMove={drag.move}
                    onStart={drag.start}
                    style={[
                      styles.routineHandle,
                      interactionsDisabled && styles.disabledControl,
                    ]}
                    testID={`routine-drag-${item.id}`}
                  >
                    <RoutineDragIcon />
                  </DragHandle>
                ) : null}
                {editing ? (
                  <View
                    style={[
                      styles.inlinePrescriptionRow,
                      styles.inlinePrescriptionRowEditing,
                    ]}
                  >
                    <Text
                      adjustsFontSizeToFit
                      minimumFontScale={0.58}
                      numberOfLines={1}
                      style={[
                        styles.inlineExerciseName,
                        styles.inlineExerciseNameEditing,
                      ]}
                    >
                      {item.name}
                    </Text>
                    <Text
                      style={[
                        styles.inlinePrescriptionUnit,
                        styles.inlinePrescriptionUnitEditing,
                      ]}
                    >
                      ·
                    </Text>
                    <TextInput
                      accessibilityLabel={`${item.name} 세트 수`}
                      inputMode="numeric"
                      onChangeText={(sets) =>
                        onChangePrescription(item.id, {
                          sets: digitsOnly(sets),
                        })
                      }
                      style={[
                        styles.inlinePrescriptionInput,
                        styles.inlinePrescriptionInputEditing,
                      ]}
                      value={item.sets ?? ''}
                    />
                    <Text
                      style={[
                        styles.inlinePrescriptionUnit,
                        styles.inlinePrescriptionUnitEditing,
                      ]}
                    >
                      세트
                    </Text>
                    <Text
                      style={[
                        styles.inlinePrescriptionUnit,
                        styles.inlinePrescriptionUnitEditing,
                      ]}
                    >
                      ×
                    </Text>
                    <TextInput
                      accessibilityLabel={`${item.name} 반복 횟수`}
                      inputMode="numeric"
                      onChangeText={(reps) =>
                        onChangePrescription(item.id, {
                          reps: digitsOnly(reps),
                        })
                      }
                      placeholder={item.workSeconds ? '시간' : '0'}
                      placeholderTextColor="#B8AA9E"
                      style={[
                        styles.inlinePrescriptionInput,
                        styles.inlinePrescriptionInputEditing,
                      ]}
                      value={item.reps ?? ''}
                    />
                    <Text
                      style={[
                        styles.inlinePrescriptionUnit,
                        styles.inlinePrescriptionUnitEditing,
                      ]}
                    >
                      회
                    </Text>
                  </View>
                ) : (
                  <Text
                    accessibilityLabel={
                      completed
                        ? `완료: ${formatRoutineItem(item)}`
                        : current
                          ? `다음 운동: ${formatRoutineItem(item)}`
                          : undefined
                    }
                    style={[
                      styles.routineItemText,
                      completed && styles.routineItemCompleted,
                    ]}
                  >
                    {completed ? '✓ ' : ''}
                    {formatRoutineItem(item)}
                  </Text>
                )}
                {item.exerciseId &&
                (onOpenExerciseGuide || variantApi?.getExerciseVariants) ? (
                  <View
                    style={[
                      styles.routineGuideActions,
                      interactionsDisabled && styles.routineGuideActionsEditing,
                    ]}
                    testID={`routine-guide-actions-${item.id}`}
                  >
                    <View
                      style={[
                        styles.routineGuideSlot,
                        interactionsDisabled && styles.routineGuideSlotEditing,
                      ]}
                      testID={`routine-posture-slot-${item.id}`}
                    >
                      {onOpenExerciseGuide ? (
                        <Pressable
                          accessibilityLabel={`${item.name} 자세 보기`}
                          accessibilityRole="button"
                          accessibilityState={{
                            disabled: interactionsDisabled,
                          }}
                          disabled={interactionsDisabled}
                          onPress={() => onOpenExerciseGuide(item)}
                          style={[
                            styles.routineGuideButton,
                            interactionsDisabled &&
                              styles.routineGuideButtonEditing,
                            interactionsDisabled &&
                              styles.routineGuideButtonDisabled,
                          ]}
                        >
                          <Text
                            style={[
                              styles.routineGuideButtonText,
                              interactionsDisabled &&
                                styles.routineGuideButtonTextEditing,
                              interactionsDisabled && styles.disabledLabel,
                            ]}
                            numberOfLines={1}
                          >
                            자세 보기
                          </Text>
                        </Pressable>
                      ) : null}
                    </View>
                    <View
                      style={[
                        styles.routineGuideSlot,
                        interactionsDisabled && styles.routineGuideSlotEditing,
                      ]}
                      testID={`routine-equipment-slot-${item.id}`}
                    >
                      {variantApi ? (
                        <ExerciseVariantsAction
                          actionStyle={[
                            styles.routineGuideButton,
                            styles.routineEquipmentButton,
                            interactionsDisabled &&
                              styles.routineGuideButtonEditing,
                            interactionsDisabled &&
                              styles.routineGuideButtonDisabled,
                          ]}
                          actionTextStyle={[
                            styles.routineEquipmentButtonText,
                            interactionsDisabled &&
                              styles.routineGuideButtonTextEditing,
                            interactionsDisabled && styles.disabledLabel,
                          ]}
                          api={variantApi}
                          disabled={interactionsDisabled}
                          exerciseId={item.exerciseId}
                          exerciseName={item.name}
                          onOpen={(response) =>
                            onOpenExerciseVariants(item, response)
                          }
                        />
                      ) : null}
                    </View>
                  </View>
                ) : null}
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

      {phase === 'STOPPED_SAFETY' || phase === 'COMPLETED' ? null : (
        <Pressable
          accessibilityLabel={primaryActionLabel}
          accessibilityRole="button"
          accessibilityState={{
            disabled: interactionsDisabled || pending || !onStart,
          }}
          disabled={interactionsDisabled || pending || !onStart}
          onPress={onStart}
          style={[
            styles.startButton,
            (interactionsDisabled || pending || !onStart) &&
              styles.startButtonDisabled,
          ]}
        >
          <LinearGradient
            colors={
              interactionsDisabled || pending || !onStart
                ? ['#E7E5E2', '#E7E5E2']
                : ['#FFFDF8', '#FFF2D1', '#FFE2A3']
            }
            end={{ x: 0.5, y: 1 }}
            locations={
              interactionsDisabled || pending || !onStart
                ? [0, 1]
                : [0, 0.55, 1]
            }
            pointerEvents="none"
            start={{ x: 0.5, y: 0 }}
            style={styles.startButtonGradient}
            testID="home-start-gradient"
          />
          <Text
            style={[
              styles.startLabel,
              interactionsDisabled && styles.startLabelDisabled,
            ]}
          >
            {primaryActionLabel}
          </Text>
        </Pressable>
      )}
      {locked ? null : (
        <View style={styles.routineActions}>
          {onEdit ? (
            <Pressable
              accessibilityLabel={editLabel}
              accessibilityRole="button"
              accessibilityState={{ disabled: editDisabled }}
              disabled={editDisabled}
              onPress={onEdit}
              style={[
                styles.routineAction,
                editDisabled && styles.routineActionDisabled,
              ]}
            >
              <EditIcon />
              <Text style={styles.editActionLabel}>{editLabel}</Text>
            </Pressable>
          ) : null}
          {onRequestAlternative ? (
            <Pressable
              accessibilityLabel="다른 루틴 추천 받기"
              accessibilityRole="button"
              accessibilityState={{
                disabled:
                  interactionsDisabled || pending || rerolling || rerolls >= 2,
              }}
              disabled={
                interactionsDisabled || pending || rerolling || rerolls >= 2
              }
              onPress={onRequestAlternative}
              style={[
                styles.routineAction,
                (interactionsDisabled || rerolls >= 2) &&
                  styles.routineActionDisabled,
                interactionsDisabled && styles.disabledAction,
              ]}
            >
              <RerollIcon
                color={
                  interactionsDisabled || rerolls >= 2 ? '#A8A49E' : '#A45F00'
                }
              />
              <Text
                numberOfLines={1}
                style={[
                  styles.rerollActionLabel,
                  (interactionsDisabled || rerolls >= 2) &&
                    styles.rerollActionLabelDisabled,
                ]}
              >
                {rerollLabel}
              </Text>
            </Pressable>
          ) : null}
        </View>
      )}
      {!locked && onRest ? (
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: interactionsDisabled || pending }}
          disabled={interactionsDisabled || pending}
          onPress={onRest}
          style={[
            styles.routineAction,
            styles.restAction,
            interactionsDisabled && styles.disabledAction,
          ]}
        >
          <Text
            style={[
              styles.restActionLabel,
              interactionsDisabled && styles.disabledLabel,
            ]}
          >
            오늘은 쉬기
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function HomeBottomNavigation({
  activeTab,
  compact = false,
  onNavigate,
}: {
  activeTab: HomeTab;
  compact?: boolean;
  onNavigate?: (tab: HomeTab) => void;
}) {
  const insets = useSafeAreaInsets();
  const { height, width } = useScale();
  const controlScale = compact ? getContainedInterfaceScale(width, height) : 1;
  const scaled = (value: number) => value * controlScale;
  const homeColor = activeTab === 'home' ? '#A45F00' : '#B0ACA4';
  const logColor = activeTab === 'house' ? '#A45F00' : '#B0ACA4';
  const reportColor = activeTab === 'report' ? '#A45F00' : '#B0ACA4';
  const myColor = activeTab === 'my' ? '#A45F00' : '#B0ACA4';
  return (
    <View
      style={[
        bottomNavigationStyles.bottomBarOuter,
        {
          paddingTop: scaled(8),
          paddingHorizontal: scaled(HOME_LAYOUT.bottomBarHorizontalPadding),
          paddingBottom: bottomNavigationBottomPadding(
            insets.bottom,
            controlScale,
          ),
        },
      ]}
      testID="bottom-navigation"
    >
      <View
        accessibilityRole="tablist"
        style={[
          bottomNavigationStyles.bottomBar,
          {
            borderRadius: scaled(22),
            paddingVertical: scaled(10),
            paddingHorizontal: scaled(6),
          },
        ]}
        testID="bottom-navigation-tabs"
      >
        <TabButton
          active={activeTab === 'home'}
          controlScale={controlScale}
          icon={<HomeTabIcon color={homeColor} size={scaled(22)} />}
          label="홈"
          onPress={() => onNavigate?.('home')}
        />
        <TabButton
          active={activeTab === 'house'}
          controlScale={controlScale}
          icon={<LogTabIcon color={logColor} size={scaled(22)} />}
          label="끼끼의 집"
          onPress={() => onNavigate?.('house')}
        />
        <TabButton
          active={activeTab === 'report'}
          controlScale={controlScale}
          icon={<ReportTabIcon color={reportColor} size={scaled(22)} />}
          label="리포트"
          onPress={() => onNavigate?.('report')}
        />
        <TabButton
          active={activeTab === 'my'}
          controlScale={controlScale}
          icon={<MyTabIcon color={myColor} size={scaled(22)} />}
          label="마이페이지"
          onPress={() => onNavigate?.('my')}
        />
      </View>
    </View>
  );
}

export function bottomNavigationBottomPadding(
  safeAreaBottom: number,
  controlScale = 1,
) {
  return Math.max(
    HOME_LAYOUT.bottomBarBottomPadding * controlScale,
    safeAreaBottom,
  );
}

function TabButton({
  active,
  controlScale,
  icon,
  label,
  onPress,
}: {
  active: boolean;
  controlScale: number;
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
      style={[
        bottomNavigationStyles.tab,
        {
          minHeight: Math.max(44, 48 * controlScale),
          gap: 4 * controlScale,
          paddingVertical: 6 * controlScale,
          paddingHorizontal: 2 * controlScale,
        },
      ]}
    >
      {icon}
      <Text
        style={[
          bottomNavigationStyles.tabLabel,
          { fontSize: 11.5 * controlScale },
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
  const perspectiveSummaries = agentSummaries.filter(
    (summary) => summary.agent_type_code !== 'COORDINATOR',
  );
  const coordinatorSummary = agentSummaries.find(
    (summary) => summary.agent_type_code === 'COORDINATOR',
  );
  const [criteriaExpanded, setCriteriaExpanded] = useState(false);
  return (
    <SheetFrame onClose={onClose} title="추천 이유" zIndex={24}>
      <Text style={styles.sheetIntro}>
        저장된 체크인과 안전 기준을 바탕으로 서버가 결정한 내용이에요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.reasonSheetContent}
        showsVerticalScrollIndicator={false}
      >
        {perspectiveSummaries.length > 0 ? (
          <View style={styles.reasonSection}>
            <Text style={styles.checkinSectionTitle}>에이전트별 판단</Text>
            {perspectiveSummaries.map((summary) => (
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

        {coordinatorSummary ? (
          <View style={styles.reasonSection}>
            <Text style={styles.checkinSectionTitle}>최종 조정 이유</Text>
            <Text style={styles.reasonText}>{coordinatorSummary.summary}</Text>
          </View>
        ) : null}

        {reasons.length > 0 ? (
          <View style={styles.reasonSection}>
            <Pressable
              accessibilityLabel={`반영한 기준 ${criteriaExpanded ? '접기' : '펼치기'}`}
              accessibilityRole="button"
              accessibilityState={{ expanded: criteriaExpanded }}
              onPress={() => setCriteriaExpanded((current) => !current)}
              style={styles.reasonDisclosureHeader}
            >
              <Text style={styles.checkinSectionTitle}>반영한 기준</Text>
              <Text style={styles.reasonDisclosureAction}>
                {criteriaExpanded ? '접기' : '펼치기'}
              </Text>
            </Pressable>
            {criteriaExpanded
              ? reasons.map((reason) => (
                  <View key={reason} style={styles.reasonRow}>
                    <Text style={styles.reasonBullet}>•</Text>
                    <Text style={styles.reasonText}>{reason}</Text>
                  </View>
                ))
              : null}
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
  onChangePainIntensity,
  onChangeSleepHours,
  onChangeWorkoutMinutes,
  onClearPains,
  onClose,
  onOpenTimePicker,
  onSave,
  onRemoveAvailabilitySlot,
  onSetRedFlag,
  onToggleBodyArea,
  locationCodes,
  pending,
}: {
  draft: HomeCheckin;
  onAddAvailabilitySlot: () => void;
  onChangeFatigue: (value: string) => void;
  onChangeLocation: (code: string) => void;
  onChangePainIntensity: (bodyAreaCode: string, intensityScore: number) => void;
  onChangeSleepHours: (value: string) => void;
  onChangeWorkoutMinutes: (value: string) => void;
  onClearPains: () => void;
  onClose: () => void;
  onOpenTimePicker: (index: number, field: keyof HomeAvailabilitySlot) => void;
  onSave: () => void;
  onRemoveAvailabilitySlot: (index: number) => void;
  onSetRedFlag: (present: boolean) => void;
  onToggleBodyArea: (code: string) => void;
  locationCodes: readonly string[];
  pending: boolean;
}) {
  const styles = useHomeStyles();
  const { s } = useScale();
  const [showDiscomfortDetails, setShowDiscomfortDetails] = useState(
    Object.keys(draft.pains).length > 0,
  );
  const selectedDiscomfortCodes = Object.keys(draft.pains);
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
  const durationMissing = draft.workoutMinutes === '';
  const durationInvalid =
    !durationMissing &&
    (!/^\d+$/.test(draft.workoutMinutes) ||
      Number(draft.workoutMinutes) < CHECKIN_DURATION_MINUTES.min ||
      Number(draft.workoutMinutes) > CHECKIN_DURATION_MINUTES.max);
  const durationMinutes = Number(draft.workoutMinutes);
  const canDecreaseDuration =
    !pending &&
    !durationInvalid &&
    durationMinutes > CHECKIN_DURATION_MINUTES.min;
  const canIncreaseDuration =
    !pending &&
    (durationMissing ||
      (!durationInvalid && durationMinutes < CHECKIN_DURATION_MINUTES.max));
  const availabilityError = CHECKIN_AVAILABILITY_INPUT_ENABLED
    ? validateAvailabilitySlots(draft.availableSlots)
    : null;
  const availabilitySlots =
    draft.availableSlots && draft.availableSlots.length > 0
      ? draft.availableSlots
      : [EMPTY_AVAILABILITY_SLOT];
  const discomfortSelectionMissing =
    showDiscomfortDetails && Object.keys(draft.pains).length === 0;
  const redFlagSelectionMissing = draft.redFlagPresent === null;
  const saveDisabled =
    pending ||
    sleepInvalid ||
    durationMissing ||
    durationInvalid ||
    availabilityError !== null ||
    discomfortSelectionMissing ||
    redFlagSelectionMissing;
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
              accessibilityLabel={
                durationMissing
                  ? '원하는 운동 시간 미선택'
                  : `원하는 운동 시간 ${draft.workoutMinutes}분`
              }
              accessibilityLiveRegion="polite"
              style={styles.durationStepValue}
            >
              {durationMissing ? '선택' : `${draft.workoutMinutes}분`}
            </Text>
            <Pressable
              accessibilityLabel="운동 시간 10분 늘리기"
              accessibilityRole="button"
              accessibilityState={{ disabled: !canIncreaseDuration }}
              disabled={!canIncreaseDuration}
              onPress={() =>
                onChangeWorkoutMinutes(
                  String(
                    durationMissing
                      ? CHECKIN_DURATION_MINUTES.min
                      : Math.min(
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
        {durationMissing ? (
          <Text accessibilityRole="alert" style={styles.messageText}>
            오늘 가능한 운동 시간을 10~60분 중에서 선택해주세요.
          </Text>
        ) : null}
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
        {locationCodes.length > 0 ? (
          <ChoiceBlock label="오늘 어디에서 운동할까요?">
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
        <ChoiceBlock label="오늘 통증이 있는 부위가 있나요?">
          <ChoiceButton
            accessibilityLabel="통증 없어요"
            label="없어요"
            onPress={() => {
              setShowDiscomfortDetails(false);
              onClearPains();
            }}
            selected={!showDiscomfortDetails}
          />
          <ChoiceButton
            accessibilityLabel="통증 있어요"
            label="있어요"
            onPress={() => setShowDiscomfortDetails(true)}
            selected={showDiscomfortDetails}
          />
        </ChoiceBlock>
        {showDiscomfortDetails ? (
          <>
            <ChoiceBlock
              label="지금 불편하거나 통증이 있는 부위를 모두 선택해주세요."
              twoColumn
            >
              {DEFAULT_BODY_AREA_OPTIONS.map((option) => (
                <ChoiceButton
                  key={option.code}
                  label={option.label}
                  numberOfLines={2}
                  onPress={() => onToggleBodyArea(option.code)}
                  selected={draft.pains[option.code] !== undefined}
                  twoColumn
                />
              ))}
              {showExtendedAreas
                ? EXTENDED_BODY_AREA_OPTIONS.map((option) => (
                    <ChoiceButton
                      key={option.code}
                      label={option.label}
                      numberOfLines={2}
                      onPress={() => onToggleBodyArea(option.code)}
                      selected={draft.pains[option.code] !== undefined}
                      twoColumn
                    />
                  ))
                : null}
            </ChoiceBlock>
            <Pressable
              accessibilityLabel={
                showExtendedAreas ? '다른 부위 접기' : '다른 부위 보기'
              }
              accessibilityRole="button"
              accessibilityState={{ expanded: showExtendedAreas }}
              onPress={() => setShowExtendedAreas((visible) => !visible)}
              style={styles.extendedAreaToggle}
              testID="checkin-extended-area-toggle"
            >
              <Text style={styles.extendedAreaToggleLabel}>
                {showExtendedAreas ? '접기' : '다른 부위 보기'}
              </Text>
              <View style={styles.extendedAreaToggleIcon}>
                <View
                  style={
                    showExtendedAreas
                      ? styles.extendedAreaToggleCaretUp
                      : undefined
                  }
                  testID="checkin-extended-area-caret"
                >
                  <Svg
                    aria-hidden
                    fill="none"
                    height={s(14)}
                    viewBox="0 0 24 24"
                    width={s(14)}
                  >
                    <Path
                      d="M6 9l6 6 6-6"
                      stroke="#958476"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2.4}
                    />
                  </Svg>
                </View>
              </View>
            </Pressable>
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
          <View
            key={code}
            style={styles.painSliderCard}
            testID={`checkin-pain-slider-card-${bodyAreaLabel(code)}`}
          >
            <PainIntensitySlider
              bodyArea={bodyAreaLabel(code)}
              compact
              disabled={pending}
              onChange={(value) => onChangePainIntensity(code, value)}
              testIDPrefix="checkin"
              value={draft.pains[code] ?? 1}
            />
          </View>
        ))}
        <View style={styles.redFlagSection}>
          <Text style={styles.redFlagTitle}>오늘 위험 신호가 있나요?</Text>
          <Text style={styles.redFlagBody}>
            오늘 가슴 통증이나 압박감, 평소와 다른 심한 숨참, 심한 어지럼 또는
            실신할 것 같은 느낌, 심장이 매우 빠르거나 불규칙하게 뛰는 느낌 같은
            증상이 있나요?
          </Text>
        </View>
        <ChoiceBlock label="위 증상이 있나요?">
          <ChoiceButton
            accessibilityLabel="위험 신호 없어요"
            label="없어요"
            onPress={() => onSetRedFlag(false)}
            selected={draft.redFlagPresent === false}
          />
          <ChoiceButton
            accessibilityLabel="위험 신호 있어요"
            label="있어요"
            onPress={() => onSetRedFlag(true)}
            selected={draft.redFlagPresent === true}
          />
        </ChoiceBlock>
        {redFlagSelectionMissing ? (
          <Text accessibilityRole="alert" style={styles.messageText}>
            위험 신호 여부를 선택해주세요.
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
          <Text style={styles.sheetSaveLabel}>
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
  accessibilityLabel,
  label,
  numberOfLines = 1,
  onPress,
  selected,
  twoColumn = false,
}: {
  accessibilityLabel?: string;
  label: string;
  numberOfLines?: number;
  onPress: () => void;
  selected: boolean;
  twoColumn?: boolean;
}) {
  const styles = useHomeStyles();
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel ?? label}
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
                    disabled={false}
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
            <Text style={styles.sheetSaveLabel}>저장하기</Text>
          </Pressable>
        </View>
      </ScrollView>
    </SheetFrame>
  );
}

function DragHandle({
  children,
  disabled,
  index,
  onEnd,
  onKeyboardMove,
  onMove,
  onStart,
  style,
  testID,
}: {
  children: React.ReactNode;
  disabled: boolean;
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
        onStartShouldSetPanResponder: () => !disabled,
        onStartShouldSetPanResponderCapture: () => !disabled,
        onMoveShouldSetPanResponder: (
          _event: GestureResponderEvent,
          gesture: PanResponderGestureState,
        ) => !disabled && Math.abs(gesture.dy) > 2,
        onMoveShouldSetPanResponderCapture: (
          _event: GestureResponderEvent,
          gesture: PanResponderGestureState,
        ) => !disabled && Math.abs(gesture.dy) > 2,
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
    [disabled, index, onEnd, onMove, onStart],
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
      accessibilityState={{ disabled }}
      onAccessibilityAction={(event) => {
        if (disabled) {
          return;
        }
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

function HomeTabIcon({ color, size = 22 }: { color: string; size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M4 11.2 12 4.5l8 6.7V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1v-7.8Z"
        fill={color}
      />
    </Svg>
  );
}

function LogTabIcon({ color, size = 22 }: { color: string; size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M3.5 10v4M20.5 10v4M7 7.5v9M17 7.5v9M7 12h10"
        stroke={color}
        strokeWidth={2.2}
        strokeLinecap="round"
      />
    </Svg>
  );
}

function ReportTabIcon({ color, size = 22 }: { color: string; size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Rect x={4} y={12} width={3.6} height={7} rx={1.6} fill={color} />
      <Rect x={10.2} y={6} width={3.6} height={13} rx={1.6} fill={color} />
      <Rect x={16.4} y={9.5} width={3.6} height={9.5} rx={1.6} fill={color} />
    </Svg>
  );
}

function MyTabIcon({ color, size = 22 }: { color: string; size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
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
    greetingJua: { fontFamily: fontFamilies.slogan, fontWeight: '400' },
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
    disabledControl: {
      opacity: 0.42,
    },
    disabledAction: {
      borderColor: '#D8D5D1',
      backgroundColor: '#F2F1EF',
    },
    disabledLabel: {
      color: '#98948E',
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
    weekMascot: { width: '92%', height: '92%' },
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
    checkinWrapper: { marginBottom: s(16) },
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
    messageText: {
      marginTop: s(8),
      color: '#958476',
      fontSize: f(13),
      lineHeight: f(19.5),
      textAlign: 'center',
    },
    routineSetupLoadingTitle: { marginTop: s(12) },
    routineSetupAction: {
      alignSelf: 'stretch',
      marginTop: s(20),
    },
    routineSetupButtonLabel: {
      color: '#35512E',
      fontSize: f(18),
      fontWeight: '800',
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
    routinePlanName: {
      marginTop: s(8),
      color: '#5A4636',
      fontSize: f(15),
      fontWeight: '700',
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
    routineLoadingSlot: {
      minHeight: s(220),
      overflow: 'hidden',
      marginTop: s(14),
      marginBottom: s(4),
      borderTopWidth: s(1),
      borderTopColor: '#E8D8C2',
      borderStyle: 'dashed',
      borderRadius: s(16),
      backgroundColor: 'rgba(255, 248, 229, 0.62)',
      padding: s(10),
    },
    routineLoadingPreview: {
      width: '100%',
      opacity: 0.34,
    },
    routineLoadingRow: {
      minHeight: s(46),
      justifyContent: 'center',
      borderRadius: s(12),
      backgroundColor: '#F3ECE4',
      paddingHorizontal: s(12),
    },
    routineLoadingPlaceholderLine: {
      width: '68%',
      height: s(10),
      borderRadius: 999,
      backgroundColor: '#CDBEAF',
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
    routineItemText: {
      minWidth: 0,
      flex: 1,
      color: '#5A4636',
      fontSize: f(13.5),
      fontWeight: '700',
      lineHeight: f(19.575),
    },
    routineItemCompleted: {
      color: '#AAA49D',
    },
    routineRowCompleted: {
      backgroundColor: '#F4F2EF',
      opacity: 0.68,
    },
    inlinePrescriptionRow: {
      minWidth: 0,
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      gap: s(5),
    },
    inlinePrescriptionRowEditing: {
      gap: s(2),
    },
    inlineExerciseName: {
      minWidth: 0,
      flex: 1,
      color: '#5A4636',
      fontSize: f(13),
      fontWeight: '700',
    },
    inlineExerciseNameEditing: {
      minWidth: s(50),
    },
    inlinePrescriptionInput: {
      width: s(34),
      borderWidth: s(1),
      borderColor: '#E0A742',
      borderRadius: s(9),
      backgroundColor: '#FFFDF8',
      color: '#5A4636',
      fontSize: f(13),
      fontWeight: '700',
      paddingHorizontal: s(2),
      paddingVertical: s(7),
      textAlign: 'center',
    },
    inlinePrescriptionInputEditing: {
      width: s(28),
    },
    inlinePrescriptionUnit: {
      color: '#8B8178',
      fontSize: f(11),
      fontWeight: '700',
    },
    inlinePrescriptionUnitEditing: {
      fontSize: f(9.5),
    },
    routineGuideActions: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: s(4),
    },
    routineGuideActionsEditing: {
      gap: s(2),
    },
    routineGuideSlot: {
      width: s(64),
      height: s(32),
      alignItems: 'center',
      justifyContent: 'center',
    },
    routineGuideSlotEditing: {
      width: s(44),
    },
    routineGuideButton: {
      width: s(64),
      height: s(32),
      minHeight: s(32),
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(1),
      borderColor: '#C8D7AC',
      borderRadius: s(999),
      backgroundColor: '#EDF3DD',
      paddingHorizontal: 0,
      paddingVertical: 0,
    },
    routineGuideButtonText: {
      color: '#5F7048',
      fontSize: f(11.5),
      fontWeight: '700',
    },
    routineGuideButtonDisabled: {
      borderColor: '#D8D5D1',
      backgroundColor: '#F2F1EF',
    },
    routineGuideButtonEditing: {
      width: s(44),
    },
    routineGuideButtonTextEditing: {
      fontSize: f(9.5),
    },
    routineEquipmentButton: {
      borderColor: '#9CC5DF',
      backgroundColor: '#E7F3FA',
    },
    routineEquipmentButtonText: {
      color: '#356A85',
      fontSize: f(11.5),
      fontWeight: '700',
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
      minHeight: s(58),
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      position: 'relative',
      marginTop: s(16),
      marginBottom: s(10),
      borderWidth: s(1),
      borderColor: 'rgba(218, 150, 30, 0.2)',
      borderRadius: s(18),
      overflow: 'hidden',
      paddingVertical: s(16),
      paddingHorizontal: s(20),
      ...shadow(6, 12, 0.13),
    },
    startButtonDisabled: {
      borderColor: '#DDD4CA',
      shadowOpacity: 0,
      elevation: 0,
    },
    startButtonGradient: {
      position: 'absolute',
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
    },
    startLabel: {
      color: '#5A4636',
      fontSize: f(17),
      fontWeight: '800',
      letterSpacing: s(-0.1),
      textAlign: 'center',
    },
    startLabelDisabled: {
      color: '#9C9892',
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
    restAction: {
      alignSelf: 'center',
      flex: 0,
      minWidth: s(132),
      borderColor: '#D8D4CB',
      backgroundColor: 'transparent',
      paddingVertical: s(10),
    },
    restActionLabel: {
      color: '#7B695B',
      fontSize: f(13),
      fontWeight: '600',
    },
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
    reasonDisclosureHeader: {
      minHeight: s(32),
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: s(12),
    },
    reasonDisclosureAction: {
      color: '#A45F00',
      fontSize: f(12),
      fontWeight: '800',
    },
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
    extendedAreaToggle: {
      minHeight: s(36),
      alignSelf: 'center',
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: s(6),
      paddingHorizontal: s(8),
    },
    extendedAreaToggleLabel: {
      color: '#958476',
      fontSize: f(12),
      fontWeight: '600',
    },
    extendedAreaToggleIcon: {
      width: s(24),
      height: s(24),
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: s(1),
      borderColor: '#EEDFCB',
      borderRadius: s(12),
      backgroundColor: '#FFFFFF',
    },
    extendedAreaToggleCaretUp: {
      transform: [{ rotate: '180deg' }],
    },
    painSliderCard: {
      borderWidth: s(1),
      borderColor: '#E8C3B8',
      borderRadius: s(14),
      backgroundColor: '#FFFDFC',
      paddingVertical: s(12),
      paddingHorizontal: s(14),
    },
    redFlagSection: {
      gap: s(7),
      borderWidth: s(1),
      borderColor: '#E8C3B8',
      borderRadius: s(14),
      backgroundColor: '#FBECE8',
      padding: s(16),
    },
    redFlagTitle: {
      color: '#B04A2C',
      fontSize: f(15),
      fontWeight: '700',
    },
    redFlagBody: {
      color: '#B04A2C',
      fontSize: f(13),
      lineHeight: f(19),
    },
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
    sheetSaveLabel: { color: '#5A4636', fontSize: f(18), fontWeight: '800' },
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
