import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { bodyAreaLabel, decisionReasonLabel } from '../../api/labels';
import type {
  ExerciseVariantsResponse,
  SessionStatusCode,
  WorkoutPlan,
} from '../../api/types';
import { moveArrayItem, routineTitleFromPlan } from '../../api/workoutPlan';
import { useBrandFonts } from '../../app/fonts';
import type { TabId } from '../../components/brand/BrandChrome';
import { useScale } from '../../components/scale';
import { ExerciseDetailSheet } from '../workout/ExerciseDetailSheet';
import { ExerciseVariantsContent } from '../workout/ExerciseVariants';
import {
  HOME_ROUTINE_VARIANTS,
  HOME_WEEK_DAYS,
  apiCheckinDraft,
  applyRoutineItemOverrides,
  checkinFromContext,
  copyRoutineItems,
  formatHomeDate,
  formatWeekRange,
  formatWeekRangeForLocalDate,
  getHomeRoutineVariant,
  homeCheckinDraftsEqual,
  deriveTodayRoutineViewState,
  routineItemOverrides,
  routineFocusFromPlan,
  routineItemsFromPlan,
  weekDaysFromSessions,
  weeklyCompletionPercentage,
  weekStartForLocalDate,
  type HomeCheckin,
  type HomePreviewState,
  type HomeRoutineItem,
  type RoutineItemDraftOverride,
} from './homeModel';

import {
  CHECKIN_AVAILABILITY_INPUT_ENABLED,
  CHECKIN_DURATION_MINUTES,
  EMPTY_AVAILABILITY_SLOT,
  HOME_BACKGROUND_COLOR,
} from './homeConstants';
import {
  HomeBottomNavigation,
  RecommendationReasonSheet,
  SheetFrame,
} from './HomeChrome';
import { CheckinSheet, TimePickerSheet } from './HomeCheckinSheet';
import { EditRoutineSheet } from './HomeEditRoutineSheet';
import {
  CheckinButton,
  EmptyRoutineCard,
  GeneratingRoutineCard,
  HomeHeader,
  HomeStateCard,
  RoutineLookupCard,
  WeeklyOverviewCard,
} from './HomeOverview';
import { RoutineCard } from './HomeRoutineCard';
import {
  clampNumericString,
  cleanRoutineItems,
  digitsOnly,
  hasInvalidRoutinePrescription,
  patchRoutinePrescription,
} from './HomeSupport';
import { createHomeStyles, HomeStyleContext } from './homeStyles';

import type { HomeScreenProps } from './HomeScreen';
import {
  buildInitialCheckin,
  EMPTY_ITEM_OVERRIDES,
  EMPTY_PERSISTENT_PAINS,
  recommendationReasonsFromDecision,
  shouldShowGuidanceCard,
  routineNotesFromDecision,
  type TimePickerTarget,
} from './homeContentModel';
import { revisionNotice } from './homeRevisionNotice';

export function HomeScreenContent({
  actionError = null,
  alternativeUsedCount = 0,
  busy = null,
  context = null,
  currentDate = '2026.08.11 (화)',
  decision = null,
  exerciseApi,
  hasTodayRoutine = true,
  hasUnreadNotification = false,
  notificationPanel,
  onDismissNotificationPanel,
  notificationToastVisible = false,
  initialState,
  localDate,
  locationCodes = [],
  recommendedDurationMinutes = null,
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
  onRetryPlanEdit,
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
  const variantsAvailableInContext =
    context?.location_code === undefined || context.location_code === 'HOME';
  const [showTip, setShowTip] = useState(false);
  const [rerolling, setRerolling] = useState(initialState === 'generating');
  const [previewRerolls, setPreviewRerolls] = useState(0);
  const [variantIndex, setVariantIndex] = useState(0);
  const [adjustedRoutine, setAdjustedRoutine] = useState(
    initialState === 'adjusted',
  );
  const initialCheckin = useMemo<HomeCheckin>(
    () =>
      buildInitialCheckin(
        apiMode,
        context,
        persistentPains,
        locationCodes,
        initialState,
      ),
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
    () => checkinFromContext(context, persistentPains, locationCodes),
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
  const routineNotes = apiMode ? routineNotesFromDecision(decision) : undefined;
  const currentRevisionNotice = revisionNotice(planRevision);
  const recommendationReasons = useMemo(
    () => recommendationReasonsFromDecision(decision),
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

  const inlineEditInvalid = hasInvalidRoutinePrescription(editDraft);

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
  ) => setEditDraft((current) => patchRoutinePrescription(current, id, patch));

  const navigateFromHome = (tab: TabId) => {
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
    const [source, target] = [items[from], items[to]];
    if (
      source === undefined ||
      target === undefined ||
      completedPlanItemIds.includes(source.id) ||
      completedPlanItemIds.includes(target.id) ||
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
  const showGuidanceCard = shouldShowGuidanceCard({
    actionError: Boolean(actionError),
    apiMode,
    blockingRevisionNotice,
    contentReady,
    noRoutine,
    restRecommended,
    restToday,
    routineExists: routine !== null,
    seriousDecision,
  });
  const checkinLabel = recheckMode ? '다시 체크인하기' : undefined;
  return (
    <HomeStyleContext.Provider value={styles}>
      <View
        onPointerDown={onDismissNotificationPanel}
        style={styles.screen}
        testID="home-screen"
      >
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
              notificationPanel={notificationPanel}
              onNotifications={onNotifications}
              onProfile={onProfile}
              profileImageUrl={profileImageUrl}
              useJua={useJua}
              userName={nickname ?? userName}
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
            {showCheckin && !showGuidanceCard ? (
              <CheckinButton
                label={checkinLabel}
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
                    : onRetryPlanEdit
                      ? '수정 저장 다시 시도'
                      : onRetryDecision
                        ? '루틴 생성 다시 시도'
                        : undefined
                }
                onAction={
                  staleContext
                    ? onRetryCheckin
                    : (onRetryPlanEdit ?? onRetryDecision)
                }
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
            {showGuidanceCard ? (
              <EmptyRoutineCard
                baselineReady={apiMode && routine !== null}
                checkinLabel={checkinLabel}
                onCheckin={
                  showCheckin ? () => openCheckin('INITIAL') : undefined
                }
              />
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
                locationCode={context?.location_code}
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

        {notificationToastVisible ? (
          <View
            accessibilityLiveRegion="polite"
            accessibilityRole="alert"
            pointerEvents="none"
            style={styles.notificationToast}
          >
            <Text style={styles.notificationToastText}>
              끼끼가 소식을 가져왔어요!
            </Text>
          </View>
        ) : null}

        {checkinOpen ? (
          <CheckinSheet
            draft={checkinDraft}
            locationCodes={apiMode ? locationCodes : []}
            locationRequired={apiMode}
            recommendedDurationMinutes={recommendedDurationMinutes}
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
              guideContext={{ locationCode: displayedCheckin.locationCode }}
            />
          </SheetFrame>
        ) : null}

        {variantGuide && variantsAvailableInContext ? (
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
