/**
 * The home screen: the product's entry point.
 *
 * Today's state, the server's final routine, and the way into the workout sit
 * on one surface, so the user never leaves home to check in or to see what was
 * decided. This file is presentation only — it receives stored server values
 * and callbacks, and re-derives no safety, duration or coordinator decision.
 *
 * Invariants it renders rather than reproduces:
 *
 * - one final routine, plus the server's optional REST opt-out; no "lighter"
 *   or "original" plan alternatives are ever offered
 * - a safety veto (`BLOCKED`) has no plan and cannot be dismissed here
 * - `STOP_AND_SEEK_HELP` drops every playful element and shows a serious notice
 * - once the user chose rest, nothing on this screen prompts them to train
 */

import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  actionDescription,
  actionLabel,
  ADVERSE_REACTION_OPTIONS,
  agentTypeLabel,
  bodyAreaLabel,
  DEFAULT_BODY_AREA_OPTIONS,
  EXTENDED_BODY_AREA_OPTIONS,
  FATIGUE_OPTIONS,
  SEVERITY_OPTIONS,
} from '../../api/labels';
import type {
  DailyContextResponse,
  DecisionResponse,
  DiscomfortSeverityCode,
  RoutineResponse,
  WeeklyPlanRevisionResponse,
  WeekResponse,
} from '../../api/types';
import { fontFamilies, useBrandFonts } from '../../app/fonts';
import type { TabId } from '../../components/brand/BrandChrome';
import { Button, Card } from '../../components/primitives';
import {
  ErrorState,
  LoadingState,
  SafetyNotice,
} from '../../components/states/ScreenState';
import { colors, spacing } from '../../components/theme';
import {
  checkinDraftFromContext,
  emptyCheckinDraft,
  formatHomeDate,
  formatWeekRange,
  HOME_DURATION_CHOICES,
  HOME_WEEK_DAY_LABELS,
  planSummary,
  planTitle,
  routineItemsFromDay,
  routineItemsFromPlan,
  type HomeCheckinDraft,
  type HomePreviewState,
  type HomeRoutineItem,
} from './previousHomeModel';

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

/**
 * The contract's fixed cap on Coordinator-authored revisions per week, shown
 * as a remaining count. The server stays the authority: a third request is
 * refused with `AI_REVISION_LIMIT_REACHED` whatever this screen displays.
 */
export const AI_REVISION_LIMIT = 2;

/** Which server call is in flight, so only that control shows progress. */
export type HomeBusyKind = 'checkin' | 'revision' | 'starting';

type SheetName = 'none' | 'checkin' | 'editing';

export type HomeUserEdits = {
  routineId: string;
  locationCode: string;
};

export type PreviousHomeScreenProps = {
  nickname: string;
  /** The user's own `YYYY-MM-DD`; every daily resource is keyed by it. */
  localDate: string;

  status?: 'loading' | 'error' | 'ready';
  errorMessage?: string;
  permissionDenied?: boolean;
  onRetry?: () => void;

  routine?: RoutineResponse | null;
  context?: DailyContextResponse | null;
  decision?: DecisionResponse | null;
  week?: WeekResponse | null;
  planRevision?: WeeklyPlanRevisionResponse | null;

  /** Set once the user chose REST today; suppresses every workout prompt. */
  restToday?: boolean;

  /** Profile default, used for the first check-in of the day. */
  defaultDurationMinutes?: number;
  /** Locations from the profile, for a USER plan revision. */
  locationCodes?: readonly string[];

  busy?: HomeBusyKind | null;
  actionError?: string | null;
  /** The stored check-in moved on; the retry re-reads its version first. */
  staleContext?: boolean;
  onRetryCheckin?: () => void;

  onSubmitCheckin?: (draft: HomeCheckinDraft) => void;
  onStartWorkout?: () => void;
  onChooseRest?: () => void;
  onRequestAiRevision?: () => void;
  onSubmitUserEdits?: (edits: HomeUserEdits) => void;
  onNavigateTab?: (tab: TabId) => void;
  onOpenCalendar?: () => void;

  /** Development preview only: opens a sheet on mount. */
  previewState?: HomePreviewState;
};

export function PreviousHomeScreen({
  previewState,
  ...props
}: PreviousHomeScreenProps) {
  // Remounting on a preview change resets the sheet state, which is what the
  // gallery wants when it jumps between fixed states.
  return (
    <HomeScreenContent
      key={previewState ?? 'live'}
      {...props}
      previewState={previewState}
    />
  );
}

function HomeScreenContent({
  nickname,
  localDate,
  status = 'ready',
  errorMessage,
  permissionDenied = false,
  onRetry,
  routine = null,
  context = null,
  decision = null,
  week = null,
  planRevision = null,
  restToday = false,
  defaultDurationMinutes,
  locationCodes = [],
  busy = null,
  actionError = null,
  staleContext = false,
  onRetryCheckin,
  onSubmitCheckin,
  onStartWorkout,
  onChooseRest,
  onRequestAiRevision,
  onSubmitUserEdits,
  onNavigateTab,
  onOpenCalendar,
  previewState,
}: PreviousHomeScreenProps) {
  const brandFonts = useBrandFonts();
  const useJua = brandFonts.loaded && !brandFonts.failed;

  const [sheet, setSheet] = useState<SheetName>(
    previewState === 'checkin'
      ? 'checkin'
      : previewState === 'editing'
        ? 'editing'
        : 'none',
  );
  const [showWeeklyTip, setShowWeeklyTip] = useState(false);

  const plan = decision?.final_plan ?? null;
  const routineDay = routine?.days[0] ?? null;
  const isSerious = decision?.action_code === 'STOP_AND_SEEK_HELP';
  const isBlocked = decision?.safety_status_code === 'BLOCKED';
  const generating =
    busy === 'checkin' || busy === 'revision' || previewState === 'generating';

  const routineOption =
    decision?.options.find(
      (option) => option.option_code === 'FINAL_ROUTINE',
    ) ?? null;
  const restOption =
    decision?.options.find((option) => option.option_code === 'REST') ?? null;

  const startingDuration =
    context?.requested_duration_minutes ??
    defaultDurationMinutes ??
    routineDay?.requested_duration_minutes ??
    HOME_DURATION_CHOICES[1];

  return (
    <SafeAreaView edges={['left', 'right']} style={styles.screen}>
      <StatusBar style="light" />
      <View pointerEvents="none" style={styles.backgroundBands}>
        <View style={styles.backgroundGreen} />
        <View style={styles.backgroundMist} />
        <View style={styles.backgroundCanvas} />
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
      >
        <HomeHeader
          nickname={nickname}
          dateLabel={formatHomeDate(localDate)}
          onOpenProfile={onNavigateTab ? () => onNavigateTab('my') : undefined}
        />

        {status === 'loading' ? (
          <LoadingState label="오늘 상태를 불러오는 중이에요" />
        ) : status === 'error' ? (
          <ErrorState
            message={
              permissionDenied
                ? '오늘의 운동 정보에 접근할 권한이 없어요.'
                : (errorMessage ?? '오늘 상태를 불러오지 못했어요.')
            }
            onRetry={permissionDenied ? undefined : onRetry}
          />
        ) : (
          <>
            <WeeklyRoutineCard week={week} localDate={localDate} />
            <WeeklyProgressCard
              week={week}
              showTip={showWeeklyTip}
              onToggleTip={() => setShowWeeklyTip((current) => !current)}
              onOpenCalendar={onOpenCalendar}
            />

            {/* Rest wins over every other prompt, including routine setup. */}
            {restToday ? (
              <RestCard />
            ) : routine === null ? (
              <NoRoutineCard onRetry={onRetry} useJua={useJua} />
            ) : (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="오늘 루틴 체크인"
                onPress={() => setSheet('checkin')}
                style={({ pressed }) => [
                  styles.checkinButton,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={[styles.checkinLabel, useJua && styles.juaLabel]}>
                  {context === null
                    ? '오늘 루틴 체크인🍌'
                    : '체크인 다시 하기🍌'}
                </Text>
                <Text style={styles.checkinArrow}>›</Text>
              </Pressable>
            )}

            {actionError ? (
              <Card style={formStyles.alertCard}>
                <Text accessibilityRole="alert" style={formStyles.alertText}>
                  {actionError}
                </Text>
                {staleContext && onRetryCheckin ? (
                  <Button
                    label="최신 상태로 다시 시도"
                    tone="secondary"
                    onPress={onRetryCheckin}
                  />
                ) : null}
              </Card>
            ) : null}

            {isSerious && decision ? (
              <SafetyNotice
                title={decision.guidance?.title ?? '운동을 멈춰주세요'}
                message={
                  decision.guidance?.message ??
                  '안내를 확인하고 도움을 받아주세요. 오늘은 운동 계획을 제공하지 않아요.'
                }
              />
            ) : null}

            {!isSerious && isBlocked && plan === null ? (
              <BlockedCard summary={decision?.summary ?? null} />
            ) : null}

            {generating ? <GeneratingRoutineCard /> : null}

            {!generating &&
            !restToday &&
            routine !== null &&
            plan === null &&
            !isSerious &&
            !isBlocked ? (
              <EmptyRoutineCard hasContext={context !== null} />
            ) : null}

            {!generating && !restToday && plan !== null && decision !== null ? (
              <RoutineCard
                decision={decision}
                items={routineItemsFromPlan(plan)}
                startSelectable={routineOption?.selectable ?? false}
                startBlockedReason={routineOption?.blocked_reason_code ?? null}
                aiRevisionsLeft={
                  planRevision === null
                    ? null
                    : AI_REVISION_LIMIT - planRevision.ai_revision_count
                }
                starting={busy === 'starting'}
                onEdit={() => setSheet('editing')}
                onRequestAiRevision={onRequestAiRevision}
                onStart={onStartWorkout}
                useJua={useJua}
              />
            ) : null}

            {/*
              The REST opt-out lives outside the routine card because a safety
              veto leaves no plan to attach it to, and the user must still be
              able to take it.
            */}
            {!restToday && restOption !== null ? (
              <View style={formStyles.restOption}>
                <Button
                  label="오늘은 쉬기"
                  tone="secondary"
                  disabled={!restOption.selectable || busy === 'starting'}
                  onPress={onChooseRest}
                />
              </View>
            ) : null}
          </>
        )}
      </ScrollView>

      <HomeBottomNavigation activeTab="home" onNavigate={onNavigateTab} />

      {sheet === 'checkin' ? (
        <CheckinSheet
          initialDraft={
            context === null
              ? emptyCheckinDraft(startingDuration)
              : checkinDraftFromContext(context)
          }
          pending={busy === 'checkin'}
          onClose={() => setSheet('none')}
          onSave={(draft) => {
            setSheet('none');
            onSubmitCheckin?.(draft);
          }}
          useJua={useJua}
        />
      ) : null}

      {sheet === 'editing' ? (
        <EditRoutineSheet
          routine={planRevision?.routine ?? routine}
          locationCodes={locationCodes}
          selectedLocationCode={
            planRevision?.selected_location_code ??
            context?.location_code ??
            null
          }
          items={
            routineDay === null
              ? plan === null
                ? []
                : routineItemsFromPlan(plan)
              : routineItemsFromDay(routineDay)
          }
          pending={busy === 'revision'}
          onClose={() => setSheet('none')}
          onSave={(edits) => {
            setSheet('none');
            onSubmitUserEdits?.(edits);
          }}
          useJua={useJua}
        />
      ) : null}
    </SafeAreaView>
  );
}

function HomeHeader({
  dateLabel,
  nickname,
  onOpenProfile,
}: {
  dateLabel: string;
  nickname: string;
  onOpenProfile?: () => void;
}) {
  return (
    <View style={styles.header}>
      <View style={styles.headerCopy}>
        <Text accessibilityRole="header" style={styles.greeting}>
          안녕하세요, <Text style={styles.greetingName}>{nickname}님!</Text>
        </Text>
        <Text style={styles.date}>{dateLabel}</Text>
      </View>
      <View style={styles.headerActions}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="마이페이지 열기"
          onPress={onOpenProfile}
          style={styles.profileButton}
        >
          <Text style={styles.profileMark}>{nickname.slice(0, 1)}</Text>
        </Pressable>
      </View>
    </View>
  );
}

/**
 * The week strip. Per-day completion has no read endpoint while the week is
 * open, so the strip marks today and points at where the record lives instead
 * of showing checks the client cannot substantiate.
 */
function WeeklyRoutineCard({
  localDate,
  week,
}: {
  localDate: string;
  week: WeekResponse | null;
}) {
  const todayIndex = weekdayIndex(localDate);

  return (
    <Card style={styles.summaryCard}>
      <Text style={styles.cardTitle}>
        {week === null ? (
          '이번 주 목표를 불러오지 못했어요'
        ) : (
          <>
            이번 주 목표는{' '}
            <Text style={styles.greenText}>{week.target_workout_count}회</Text>
            예요
          </>
        )}
      </Text>
      <View style={styles.weekRow}>
        {HOME_WEEK_DAY_LABELS.map((label, index) => {
          const isToday = index === todayIndex;
          return (
            <View key={label} style={styles.weekDay}>
              <View
                style={[
                  styles.weekCircle,
                  isToday && styles.weekCircleCompleted,
                ]}
              >
                <Text
                  style={[
                    styles.weekCircleText,
                    isToday && styles.weekCircleTextCompleted,
                  ]}
                >
                  ·
                </Text>
              </View>
              <Text
                style={[styles.weekLabel, isToday && styles.weekLabelCompleted]}
              >
                {label}
              </Text>
            </View>
          );
        })}
      </View>
    </Card>
  );
}

function WeeklyProgressCard({
  onOpenCalendar,
  onToggleTip,
  showTip,
  week,
}: {
  onOpenCalendar?: () => void;
  onToggleTip: () => void;
  showTip: boolean;
  week: WeekResponse | null;
}) {
  const range = week === null ? null : formatWeekRange(week.week_start);

  return (
    <Card style={styles.progressCard}>
      <View style={styles.progressHeader}>
        <View style={styles.progressTitleRow}>
          <Text style={styles.cardTitle}>주간 진행 현황</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="주간 진행 현황 설명 보기"
            onPress={onToggleTip}
            style={styles.iconTouch}
          >
            <Text style={styles.infoIcon}>ⓘ</Text>
          </Pressable>
        </View>
        <View style={styles.progressTitleRow}>
          <Text style={styles.weekRange}>{range ?? '이번 주'}</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="캘린더 연동 상태 보기"
            onPress={onOpenCalendar}
            style={styles.iconTouch}
          >
            <Text style={styles.calendarIcon}>▦</Text>
          </Pressable>
        </View>
      </View>

      {showTip ? (
        <View accessibilityRole="summary" style={styles.tip}>
          <Text style={styles.tipText}>
            이번 주에 목표한 운동 횟수예요. 완료한 횟수는 주가 끝난 뒤 주간
            리포트에서 확인할 수 있어요.
          </Text>
        </View>
      ) : null}

      <View style={styles.countRow}>
        <Text style={styles.countLabel}>
          목표{' '}
          <Text style={styles.countValue}>
            {week === null ? '-' : week.target_workout_count}
          </Text>{' '}
          회
        </Text>
        <Text style={styles.countLabel}>
          {week === null
            ? '주 상태 확인 중'
            : week.status_code === 'CLOSED'
              ? '이번 주 종료'
              : '진행 중'}
        </Text>
      </View>
      <View style={styles.progressCells}>
        {Array.from({ length: week?.target_workout_count ?? 0 }, (_, index) => (
          <View key={`progress-${index}`} style={styles.progressCell}>
            <Text style={styles.progressCellMark}>•</Text>
          </View>
        ))}
      </View>
    </Card>
  );
}

function NoRoutineCard({
  onRetry,
  useJua,
}: {
  onRetry?: () => void;
  useJua: boolean;
}) {
  return (
    <Card style={styles.messageCard}>
      <Text style={styles.messageTitle}>기본 루틴을 불러오지 못했어요</Text>
      <Text style={styles.messageText}>
        서버에 저장된 기본 루틴을 다시 불러와 주세요.
      </Text>
      <Button
        label="다시 불러오기"
        labelStyle={useJua ? styles.juaLabel : undefined}
        onPress={onRetry}
      />
    </Card>
  );
}

function EmptyRoutineCard({ hasContext }: { hasContext: boolean }) {
  return (
    <Card style={styles.messageCard}>
      <Text style={styles.messageTitle}>아직 오늘의 운동이 없어요</Text>
      <Text style={styles.messageText}>
        {hasContext
          ? '체크인은 저장했어요. 다시 체크인하면 오늘의 최종 루틴을 받을 수 있어요.'
          : '오늘 체크인을 하면 컨디션에 맞는 추천 루틴을 받아볼 수 있어요.'}
      </Text>
    </Card>
  );
}

function GeneratingRoutineCard() {
  return (
    <Card style={styles.messageCard}>
      <ActivityIndicator color="#F6BA50" size="small" />
      <Text style={[styles.messageTitle, styles.loadingTitle]}>
        새로운 루틴을 받고 있어요
      </Text>
      <Text style={styles.messageText}>
        요청한 운동 시간에 맞춰 다시 구성하는 중이에요.
      </Text>
    </Card>
  );
}

/** The user chose rest. Nothing here asks them to train again today. */
function RestCard() {
  return (
    <Card style={styles.messageCard}>
      <Text style={styles.messageTitle}>오늘은 휴식하기로 했어요</Text>
      <Text style={styles.messageText}>
        푹 쉬고 내일 다시 만나요. 오늘은 더 이상 운동을 권하지 않을게요.
      </Text>
    </Card>
  );
}

/** A safety veto. The client offers no way to override or retry it. */
function BlockedCard({ summary }: { summary: string | null }) {
  return (
    <Card style={formStyles.blockedCard}>
      <Text style={formStyles.blockedTitle}>
        오늘은 운동 계획을 제공하지 않아요
      </Text>
      <Text style={formStyles.blockedBody}>
        {summary ??
          '안전 기준에 따라 오늘은 운동 대신 회복을 권해요. 이 판단은 앱에서 해제할 수 없어요.'}
      </Text>
    </Card>
  );
}

function RoutineCard({
  aiRevisionsLeft,
  decision,
  items,
  onEdit,
  onRequestAiRevision,
  onStart,
  starting,
  startBlockedReason,
  startSelectable,
  useJua,
}: {
  aiRevisionsLeft: number | null;
  decision: DecisionResponse;
  items: readonly HomeRoutineItem[];
  onEdit: () => void;
  onRequestAiRevision?: () => void;
  onStart?: () => void;
  starting: boolean;
  startBlockedReason: string | null;
  startSelectable: boolean;
  useJua: boolean;
}) {
  const plan = decision.final_plan;
  if (plan === null) {
    return null;
  }
  const adjusted = decision.action_code !== 'KEEP';
  const revisionExhausted = aiRevisionsLeft !== null && aiRevisionsLeft <= 0;

  return (
    <Card style={styles.routineCard}>
      <View style={styles.routineBadge}>
        <Text style={styles.routineBadgeText}>오늘의 운동</Text>
      </View>
      <Text style={styles.routineTitle}>{planTitle(plan)}</Text>
      <Text style={styles.routineSummary}>{planSummary(plan)}</Text>
      <View style={styles.routineNotes}>
        <Text style={styles.routineNote}>{decision.summary}</Text>
        <Text style={styles.routineNote}>
          {actionDescription(decision.action_code)}
        </Text>
      </View>

      <View style={styles.routineList}>
        {items.map((item) => (
          <View key={item.id} style={styles.routineRow}>
            <Text style={styles.routineItemText}>
              {item.name}
              {item.prescription ? ` · ${item.prescription}` : ''}
            </Text>
            <View style={styles.routineDot} />
          </View>
        ))}
      </View>

      {adjusted ? (
        <View style={styles.adjustmentNote}>
          <Text style={styles.adjustmentText}>
            {actionLabel(decision.action_code)} ·{' '}
            {decision.guidance?.message ??
              actionDescription(decision.action_code)}
          </Text>
        </View>
      ) : null}

      {/*
        The contract's meeting UI. The order of `public_agent_summaries` is
        fixed by the server and is not re-sorted here, and only the public
        summary is shown — never internal reasoning.
      */}
      {decision.public_agent_summaries &&
      decision.public_agent_summaries.length > 0 ? (
        <View style={formStyles.agentBlock}>
          <Text style={formStyles.agentHeading}>이렇게 결정했어요</Text>
          {decision.public_agent_summaries.map((summary) => (
            <View key={summary.agent_type_code} style={formStyles.agentRow}>
              <Text style={formStyles.agentName}>
                {agentTypeLabel(summary.agent_type_code)}
              </Text>
              <Text style={formStyles.agentSummary}>{summary.summary}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <Button
        label={starting ? '준비 중…' : '운동 시작하기  ›'}
        labelStyle={[styles.startLabel, useJua && styles.juaLabel]}
        disabled={!startSelectable || starting}
        onPress={onStart}
        style={styles.startButton}
      />
      {!startSelectable ? (
        <Text style={formStyles.disabledNote}>
          지금은 시작할 수 없는 루틴이에요
          {startBlockedReason ? ` (${startBlockedReason})` : ''}.
        </Text>
      ) : null}

      <View style={styles.routineActions}>
        <Button
          label="✎  운동 계획 수정"
          labelStyle={styles.routineActionLabel}
          onPress={onEdit}
          style={styles.routineAction}
          tone="secondary"
        />
        <Button
          label={
            aiRevisionsLeft === null
              ? '↻  다른 루틴'
              : `↻  다른 루틴 · ${aiRevisionsLeft}회 남음`
          }
          labelStyle={styles.routineActionLabel}
          disabled={revisionExhausted}
          onPress={onRequestAiRevision}
          style={styles.routineAction}
          tone="secondary"
        />
      </View>
      {revisionExhausted ? (
        <Text style={formStyles.disabledNote}>
          이번 주 계획 수정 요청을 모두 사용했어요.
        </Text>
      ) : null}
    </Card>
  );
}

export function HomeBottomNavigation({
  activeTab,
  onNavigate,
}: {
  activeTab: TabId;
  onNavigate?: (tab: TabId) => void;
}) {
  const tabs = [
    { id: 'home', icon: '⌂', label: '홈' },
    { id: 'house', icon: '⌁', label: '끼끼의 집' },
    { id: 'report', icon: '▥', label: '리포트' },
    { id: 'my', icon: '●', label: '마이페이지' },
  ] as const;

  return (
    <View style={styles.bottomBarOuter}>
      <View accessibilityRole="tablist" style={styles.bottomBar}>
        {tabs.map((tab) => {
          const active = tab.id === activeTab;
          return (
            <Pressable
              key={tab.id}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={tab.label}
              onPress={() => onNavigate?.(tab.id)}
              style={styles.tab}
            >
              <Text style={[styles.tabIcon, active && styles.tabActive]}>
                {tab.icon}
              </Text>
              <Text style={[styles.tabLabel, active && styles.tabActive]}>
                {tab.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function SheetFrame({
  children,
  onClose,
  title,
}: {
  children: React.ReactNode;
  onClose: () => void;
  title: string;
}) {
  return (
    <View accessibilityViewIsModal style={styles.sheetOverlay}>
      <View style={styles.sheet}>
        <View style={styles.sheetHeader}>
          <Text accessibilityRole="header" style={styles.sheetTitle}>
            {title}
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="닫기"
            onPress={onClose}
            style={styles.closeButton}
          >
            <Text style={styles.closeText}>×</Text>
          </Pressable>
        </View>
        {children}
      </View>
    </View>
  );
}

/**
 * The manual check-in, in the contract's own fields.
 *
 * This is the fallback that must always work: there is no wearable
 * integration, so a complete manual check-in has to be sufficient on its own.
 * Nothing optional is guessed at — an unset value is sent unset.
 */
function CheckinSheet({
  initialDraft,
  onClose,
  onSave,
  pending,
  useJua,
}: {
  initialDraft: HomeCheckinDraft;
  onClose: () => void;
  onSave: (draft: HomeCheckinDraft) => void;
  pending: boolean;
  useJua: boolean;
}) {
  const [draft, setDraft] = useState<HomeCheckinDraft>(initialDraft);
  const [openArea, setOpenArea] = useState<string | null>(null);
  const [showExtendedAreas, setShowExtendedAreas] = useState(() =>
    Object.keys(initialDraft.discomforts).some((code) =>
      EXTENDED_BODY_AREA_OPTIONS.some((option) => option.code === code),
    ),
  );

  const selectedAreas = Object.keys(draft.discomforts);
  const sleepInvalid = sleepHoursInvalid(draft.sleepHours);

  const setSeverity = (code: string, severity: DiscomfortSeverityCode) => {
    setDraft((current) => {
      const next = { ...current.discomforts };
      if (next[code] === severity) {
        delete next[code];
      } else {
        next[code] = severity;
      }
      return { ...current, discomforts: next };
    });
  };

  const toggleReaction = (code: string) => {
    setDraft((current) => ({
      ...current,
      adverseReactionCodes: current.adverseReactionCodes.includes(code)
        ? current.adverseReactionCodes.filter((entry) => entry !== code)
        : [...current.adverseReactionCodes, code],
    }));
  };

  return (
    <SheetFrame onClose={onClose} title="오늘 컨디션 체크">
      <Text style={styles.sheetIntro}>
        오늘 상태를 알려주면 루틴을 맞춰 조정해드려요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.sheetScrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.checkinSection}>
          <Text style={styles.checkinSectionTitle}>피로도</Text>
          <View style={styles.choiceRow}>
            {FATIGUE_OPTIONS.map((option) => (
              <Choice
                key={option.code}
                label={option.label}
                selected={draft.fatigueLevelCode === option.code}
                onPress={() =>
                  setDraft((current) => ({
                    ...current,
                    fatigueLevelCode: option.code,
                  }))
                }
              />
            ))}
          </View>
        </View>

        <View style={styles.checkinSection}>
          <Text style={styles.checkinSectionTitle}>통증 부위</Text>
          <View style={styles.choiceRow}>
            <Choice
              label="없음"
              selected={selectedAreas.length === 0}
              onPress={() => {
                setOpenArea(null);
                setDraft((current) => ({ ...current, discomforts: {} }));
              }}
            />
            {DEFAULT_BODY_AREA_OPTIONS.map((area) => (
              <Choice
                key={area.code}
                label={area.label}
                selected={draft.discomforts[area.code] !== undefined}
                onPress={() =>
                  setOpenArea((current) =>
                    current === area.code ? null : area.code,
                  )
                }
              />
            ))}
            <Choice
              label={showExtendedAreas ? '다른 부위 접기' : '다른 부위 더 보기'}
              selected={showExtendedAreas}
              onPress={() => setShowExtendedAreas((visible) => !visible)}
            />
            {showExtendedAreas
              ? EXTENDED_BODY_AREA_OPTIONS.map((area) => (
                  <Choice
                    key={area.code}
                    label={area.label}
                    selected={draft.discomforts[area.code] !== undefined}
                    onPress={() =>
                      setOpenArea((current) =>
                        current === area.code ? null : area.code,
                      )
                    }
                  />
                ))
              : null}
          </View>
          {openArea ? (
            <View style={formStyles.severityBlock}>
              <Text style={formStyles.severityLabel}>
                {bodyAreaLabel(openArea)} 정도
              </Text>
              <View style={styles.choiceRow}>
                {SEVERITY_OPTIONS.map((severity) => (
                  <Choice
                    key={severity.code}
                    label={severity.label}
                    selected={draft.discomforts[openArea] === severity.code}
                    onPress={() => setSeverity(openArea, severity.code)}
                  />
                ))}
              </View>
            </View>
          ) : null}
          {/*
            The server's SafetyAgent only has approved rules for SEVERE input.
            Per-body-area MILD and MODERATE rules have not been domain-reviewed,
            so it fails closed rather than guessing. Saying so here is more
            honest than letting the request fail without explanation.
          */}
          <Text style={formStyles.hint}>
            현재는 &apos;심함&apos;만 처리할 수 있어요. 부위별
            &apos;가벼움&apos;·&apos;보통&apos; 판단 규칙은 아직 도메인 검수
            전이라, 선택하면 추천을 만들지 않고 중단해요.
          </Text>
        </View>

        <View style={formStyles.seriousSection}>
          <Text style={formStyles.seriousTitle}>이런 증상이 있나요?</Text>
          <Text style={formStyles.seriousBody}>
            해당하는 항목이 있으면 선택해주세요. 안전을 위해 운동을 중단하도록
            안내할 수 있어요.
          </Text>
          <View style={styles.choiceRow}>
            {ADVERSE_REACTION_OPTIONS.map((option) => (
              <Choice
                key={option.code}
                label={option.label}
                selected={draft.adverseReactionCodes.includes(option.code)}
                onPress={() => toggleReaction(option.code)}
              />
            ))}
          </View>
        </View>

        <View style={styles.checkinSection}>
          <Text style={styles.checkinSectionTitle}>원하는 운동 시간</Text>
          <View style={styles.choiceRow}>
            {HOME_DURATION_CHOICES.map((minutes) => (
              <Choice
                key={minutes}
                label={`${minutes}분`}
                selected={draft.requestedDurationMinutes === minutes}
                onPress={() =>
                  setDraft((current) => ({
                    ...current,
                    requestedDurationMinutes: minutes,
                  }))
                }
              />
            ))}
          </View>
          <Text style={formStyles.hint}>
            시간은 그대로 두고 부담만 조절해요. 시간을 줄이려면 직접
            선택해주세요.
          </Text>
        </View>

        <View style={styles.numberRow}>
          <Text style={styles.numberLabel}>
            수면 시간 <Text style={styles.optionalText}>(선택)</Text>
          </Text>
          <View style={styles.numberInputGroup}>
            <TextInput
              accessibilityLabel="어젯밤 수면 시간 (시간)"
              inputMode="numeric"
              onChangeText={(value) =>
                setDraft((current) => ({ ...current, sleepHours: value }))
              }
              placeholder="0"
              placeholderTextColor={colors.placeholder}
              style={styles.numberInput}
              value={draft.sleepHours}
            />
            <Text style={styles.numberSuffix}>시간</Text>
          </View>
        </View>
        {sleepInvalid ? (
          <Text accessibilityRole="alert" style={formStyles.alertText}>
            수면 시간은 0~24 사이로 입력해주세요.
          </Text>
        ) : null}

        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: pending || sleepInvalid }}
          disabled={pending || sleepInvalid}
          onPress={() => onSave(draft)}
          style={({ pressed }) => [
            styles.sheetSaveButton,
            pressed && styles.pressed,
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

/**
 * A USER plan revision.
 *
 * The contract takes a stored routine version and a training location, not an
 * arbitrary exercise list, and the server re-checks duration, location,
 * equipment and the saved safety exclusions against it. So this sheet chooses
 * where to train and shows what the resulting plan holds; it never lets the
 * client author or reinstate an exercise the safety rules removed.
 */
function EditRoutineSheet({
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
  const [locationCode, setLocationCode] = useState<string | null>(
    selectedLocationCode ?? locationCodes[0] ?? null,
  );
  const canSave = routine !== null && locationCode !== null && !pending;

  return (
    <SheetFrame onClose={onClose} title="오늘의 운동 수정">
      <Text style={styles.sheetIntro}>
        운동할 장소를 고르면 서버가 시간·장소·안전 기준을 다시 확인해 계획을
        수정해요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.editList}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.checkinSection}>
          <Text style={styles.checkinSectionTitle}>운동 장소</Text>
          <View style={styles.choiceRow}>
            {locationCodes.map((code) => (
              <Choice
                key={code}
                label={code}
                selected={locationCode === code}
                onPress={() => setLocationCode(code)}
              />
            ))}
          </View>
          {locationCodes.length === 0 ? (
            <Text style={formStyles.hint}>
              프로필에 저장된 운동 장소가 없어요. 마이페이지에서 먼저
              설정해주세요.
            </Text>
          ) : null}
        </View>

        <View style={styles.checkinSection}>
          <Text style={styles.checkinSectionTitle}>
            현재 계획 {routine === null ? '' : `v${routine.version}`}
          </Text>
          {items.map((item) => (
            <View key={item.id} style={styles.editRow}>
              <Text style={styles.editNameInput}>{item.name}</Text>
              <Text style={styles.editPrescription}>
                {item.prescription ?? '시간 자유'}
              </Text>
            </View>
          ))}
          {/*
            Exercise names, order and prescriptions are the server's output. The
            contract refuses arbitrary exercise edits, and letting the client
            reinstate an excluded movement would step over a safety decision.
          */}
          <Text style={formStyles.hint}>
            운동 구성은 안전 기준에 따라 서버가 정해요. 직접 바꿀 수는 없지만,
            장소를 바꾸면 그에 맞게 다시 구성해요.
          </Text>
        </View>

        <View style={styles.editActions}>
          <Button
            label="닫기"
            labelStyle={styles.resetLabel}
            onPress={onClose}
            style={styles.resetButton}
            tone="secondary"
          />
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: !canSave }}
            disabled={!canSave}
            onPress={() =>
              routine !== null && locationCode !== null
                ? onSave({ routineId: routine.id, locationCode })
                : undefined
            }
            style={({ pressed }) => [
              styles.editSaveButton,
              pressed && styles.pressed,
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

function Choice({
  label,
  onPress,
  selected,
}: {
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.choiceButton, selected && styles.choiceButtonSelected]}
    >
      <Text
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

function sleepHoursInvalid(hours: string): boolean {
  const trimmed = hours.trim();
  if (trimmed === '') {
    return false;
  }
  const value = Number(trimmed);
  return !Number.isFinite(value) || value < 0 || value > 24;
}

/** Monday-first index of `YYYY-MM-DD`, matching the week strip's order. */
function weekdayIndex(localDate: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(localDate);
  if (!match) {
    return -1;
  }
  const [, year, month, day] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return (date.getDay() + 6) % 7;
}

const formStyles = StyleSheet.create({
  hint: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
  },
  severityBlock: {
    gap: spacing.sm,
  },
  severityLabel: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '700',
  },
  seriousSection: {
    gap: spacing.sm,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.dangerBorder,
    backgroundColor: colors.dangerSurface,
    padding: spacing.md,
  },
  seriousTitle: {
    color: colors.dangerText,
    fontSize: 15,
    fontWeight: '700',
  },
  seriousBody: {
    color: colors.dangerText,
    fontSize: 13,
    lineHeight: 19,
  },
  alertCard: {
    gap: spacing.sm,
  },
  alertText: {
    color: colors.dangerText,
    fontSize: 13,
    lineHeight: 19,
  },
  blockedCard: {
    gap: spacing.sm,
  },
  blockedTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
  },
  blockedBody: {
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 20,
  },
  disabledNote: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
  },
  restOption: {
    gap: spacing.sm,
  },
  agentBlock: {
    gap: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
    paddingTop: spacing.md,
  },
  agentHeading: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  agentRow: {
    gap: 3,
  },
  agentName: {
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '700',
  },
  agentSummary: {
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 19,
  },
});

const cardShadow = {
  shadowColor: '#5A4636',
  shadowOffset: { width: 0, height: 6 },
  shadowOpacity: 0.1,
  shadowRadius: 9,
  elevation: 3,
} as const;

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: colors.canvas,
  },
  backgroundBands: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  backgroundGreen: {
    height: 245,
    backgroundColor: '#F6BA50',
  },
  backgroundMist: {
    height: 250,
    backgroundColor: '#FFEBC2',
  },
  backgroundCanvas: {
    flex: 1,
    backgroundColor: colors.canvas,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    gap: HOME_LAYOUT.cardGap,
    paddingTop: HOME_LAYOUT.contentTopPadding,
    paddingHorizontal: HOME_LAYOUT.contentHorizontalPadding,
    paddingBottom: 118,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingHorizontal: HOME_LAYOUT.headerHorizontalPadding,
    paddingBottom: HOME_LAYOUT.headerBottomPadding - HOME_LAYOUT.cardGap,
  },
  headerCopy: {
    minWidth: 0,
    flex: 1,
  },
  greeting: {
    color: colors.text,
    fontSize: 22,
    fontWeight: '800',
    lineHeight: 28,
  },
  greetingName: {
    color: '#F6BA50',
  },
  date: {
    marginTop: 6,
    color: '#F3FBE4',
    fontSize: 13,
    fontWeight: '600',
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  notificationButton: {
    position: 'relative',
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 14,
    backgroundColor: '#FFF8E5',
  },
  notificationIcon: {
    color: colors.text,
    fontSize: 24,
    lineHeight: 26,
  },
  badge: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 8,
    height: 8,
    borderWidth: 1.5,
    borderColor: '#FFF8E5',
    borderRadius: 4,
    backgroundColor: '#EE875B',
  },
  profileButton: {
    width: 48,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: colors.surface,
    borderRadius: 24,
    backgroundColor: '#F6BA50',
  },
  profileMark: {
    color: '#3E512D',
    fontSize: 16,
    fontWeight: '900',
  },
  summaryCard: {
    ...cardShadow,
    borderRadius: 22,
    padding: 16,
  },
  cardTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
  },
  greenText: {
    color: '#A45F00',
  },
  weekRow: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 14,
  },
  weekDay: {
    minWidth: 0,
    flex: 1,
    alignItems: 'center',
    gap: 6,
  },
  weekCircle: {
    width: 30,
    height: 30,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 15,
    backgroundColor: '#F0EEE8',
  },
  weekCircleCompleted: {
    backgroundColor: '#F6BA50',
  },
  weekCircleText: {
    color: '#B7B1A7',
    fontSize: 16,
    fontWeight: '800',
  },
  weekCircleTextCompleted: {
    color: colors.text,
  },
  weekLabel: {
    color: '#9A968E',
    fontSize: 11,
    fontWeight: '600',
  },
  weekLabelCompleted: {
    color: '#A45F00',
    fontWeight: '800',
  },
  progressCard: {
    ...cardShadow,
    borderRadius: 22,
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 18,
  },
  progressHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 6,
  },
  progressTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconTouch: {
    width: 34,
    height: 34,
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: -10,
  },
  infoIcon: {
    color: '#9A968E',
    fontSize: 16,
  },
  weekRange: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '600',
  },
  calendarIcon: {
    color: '#F6BA50',
    fontSize: 18,
  },
  tip: {
    marginTop: 10,
    borderRadius: 12,
    backgroundColor: '#FFF8E5',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  tipText: {
    color: '#4A5B44',
    fontSize: 12.5,
    lineHeight: 19,
  },
  countRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
    marginTop: 14,
  },
  countLabel: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
  },
  countValue: {
    color: '#A45F00',
    fontSize: 22,
  },
  progressCells: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
  progressCell: {
    height: 58,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: '#F0EEE8',
  },
  progressCellCompleted: {
    backgroundColor: '#FFEBC2',
  },
  progressCellMark: {
    color: '#F6BA50',
    fontSize: 20,
    fontWeight: '800',
  },
  checkinButton: {
    minHeight: 58,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 18,
    backgroundColor: '#F6BA50',
    paddingHorizontal: 18,
    shadowColor: '#D98B16',
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 1,
    shadowRadius: 0,
    elevation: 4,
  },
  checkinLabel: {
    flex: 1,
    color: '#342E17',
    fontSize: 21,
    fontWeight: '800',
    letterSpacing: 0.5,
    textAlign: 'center',
    paddingLeft: 22,
  },
  juaLabel: {
    fontFamily: fontFamilies.slogan,
    fontWeight: '400',
  },
  checkinArrow: {
    color: colors.text,
    fontSize: 28,
    lineHeight: 30,
  },
  pressed: {
    opacity: 0.84,
  },
  messageCard: {
    ...cardShadow,
    alignItems: 'center',
    borderRadius: 24,
    paddingHorizontal: 20,
    paddingVertical: 28,
  },
  messageTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
    textAlign: 'center',
  },
  loadingTitle: {
    marginTop: 14,
  },
  messageText: {
    marginTop: 8,
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 20,
    textAlign: 'center',
  },
  routineCard: {
    ...cardShadow,
    borderRadius: 24,
    paddingHorizontal: 18,
    paddingTop: 18,
    paddingBottom: 8,
  },
  routineBadge: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#F6BA50',
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  routineBadgeText: {
    color: colors.text,
    fontSize: 12,
    fontWeight: '700',
  },
  routineTitle: {
    marginTop: 12,
    color: colors.text,
    fontSize: 26,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  routineSummary: {
    marginTop: 10,
    color: '#A45F00',
    fontSize: 14,
    fontWeight: '700',
  },
  routineNotes: {
    gap: 4,
    marginTop: 10,
  },
  routineNote: {
    color: '#6F6B63',
    fontSize: 13.5,
    fontWeight: '500',
    lineHeight: 21,
  },
  routineList: {
    gap: 8,
    marginTop: 14,
    borderTopWidth: 1,
    borderTopColor: '#E2DED4',
    borderStyle: 'dashed',
    paddingTop: 12,
  },
  orderHint: {
    color: '#A29B8E',
    fontSize: 11.5,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
  routineRow: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 12,
    backgroundColor: '#FAF7F1',
    paddingHorizontal: 10,
  },
  dragMark: {
    width: 24,
    color: '#B4AEA2',
    fontSize: 20,
    textAlign: 'center',
  },
  routineItemText: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 13.5,
    fontWeight: '700',
    lineHeight: 20,
  },
  routineDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#F6BA50',
  },
  adjustmentNote: {
    marginTop: 12,
    borderRadius: 12,
    backgroundColor: '#FFF8E5',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  adjustmentText: {
    color: '#4A5B44',
    fontSize: 12.5,
    lineHeight: 19,
  },
  startButton: {
    minHeight: 54,
    marginTop: 16,
    borderRadius: 16,
    backgroundColor: '#F6BA50',
  },
  startLabel: {
    color: colors.text,
    fontSize: 17,
  },
  routineActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
    marginBottom: 10,
  },
  routineAction: {
    minWidth: 0,
    minHeight: 48,
    flex: 1,
    borderColor: '#F1D39A',
    borderRadius: 16,
    paddingHorizontal: 6,
  },
  routineActionLabel: {
    color: '#A45F00',
    fontSize: 12.5,
  },
  bottomBarOuter: {
    flexShrink: 0,
    backgroundColor: colors.canvas,
    paddingTop: 8,
    paddingHorizontal: HOME_LAYOUT.bottomBarHorizontalPadding,
    paddingBottom: HOME_LAYOUT.bottomBarBottomPadding,
  },
  bottomBar: {
    minHeight: 68,
    flexDirection: 'row',
    borderRadius: 22,
    backgroundColor: colors.surface,
    paddingHorizontal: 6,
    paddingVertical: 10,
    shadowColor: '#5A4636',
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.07,
    shadowRadius: 7,
    elevation: 2,
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
  },
  tabIcon: {
    color: '#B0ACA4',
    fontSize: 22,
    fontWeight: '800',
  },
  tabLabel: {
    color: '#B0ACA4',
    fontSize: 10.5,
    fontWeight: '700',
    textAlign: 'center',
  },
  tabActive: {
    color: '#A45F00',
  },
  sheetOverlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 30,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(20, 32, 16, 0.42)',
  },
  sheet: {
    maxHeight: '88%',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: colors.canvas,
    paddingTop: 20,
    paddingHorizontal: HOME_LAYOUT.sheetHorizontalPadding,
    paddingBottom: HOME_LAYOUT.sheetBottomPadding,
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  sheetTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '800',
  },
  closeButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: -10,
    marginRight: -12,
    marginBottom: -10,
  },
  closeText: {
    color: colors.textMuted,
    fontSize: 22,
  },
  sheetIntro: {
    marginTop: 4,
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 20,
  },
  sheetScrollContent: {
    gap: 10,
    paddingTop: 14,
  },
  checkinSection: {
    borderRadius: 18,
    backgroundColor: colors.surface,
    padding: 16,
  },
  checkinSectionTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  choiceRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 10,
  },
  choiceButton: {
    minHeight: 40,
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: colors.canvas,
    paddingHorizontal: 10,
  },
  choiceButtonSelected: {
    borderColor: '#F6BA50',
    backgroundColor: '#F6BA50',
  },
  choiceButtonText: {
    color: colors.text,
    fontSize: 12.5,
    fontWeight: '700',
  },
  choiceButtonTextSelected: {
    color: colors.text,
  },
  numberRow: {
    minHeight: 68,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderRadius: 18,
    backgroundColor: colors.surface,
    padding: 16,
  },
  numberLabel: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  optionalText: {
    color: colors.textMuted,
    fontWeight: '500',
  },
  numberInputGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  numberInput: {
    width: 84,
    minHeight: 42,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: colors.canvas,
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
    paddingHorizontal: 12,
    textAlign: 'right',
  },
  stepsInput: {
    width: 110,
  },
  numberSuffix: {
    color: colors.textMuted,
    fontSize: 13,
  },
  sheetSaveButton: {
    minHeight: 56,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
    marginBottom: 5,
    borderRadius: 18,
    backgroundColor: '#F6BA50',
    shadowColor: '#D98B16',
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 1,
    shadowRadius: 0,
    elevation: 3,
  },
  sheetSaveLabel: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '800',
  },
  editList: {
    gap: 8,
    paddingTop: 14,
  },
  editRow: {
    minHeight: 58,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    backgroundColor: colors.surface,
    paddingHorizontal: 10,
  },
  editHandle: {
    color: '#B4AEA2',
    fontSize: 20,
  },
  editNameInput: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 13.5,
    fontWeight: '700',
    paddingVertical: 8,
  },
  editPrescription: {
    maxWidth: 96,
    color: colors.textMuted,
    fontSize: 11.5,
    textAlign: 'right',
  },
  editActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
    paddingBottom: 5,
  },
  resetButton: {
    width: 112,
    minHeight: 54,
    borderRadius: 18,
    paddingHorizontal: 8,
  },
  resetLabel: {
    color: colors.textMuted,
    fontSize: 12.5,
  },
  editSaveButton: {
    minHeight: 54,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 18,
    backgroundColor: '#F6BA50',
  },
});
