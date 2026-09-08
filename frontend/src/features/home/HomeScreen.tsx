import type { ReactNode } from 'react';

import type { Api } from '../../api/endpoints';
import type {
  DailyContextResponse,
  DecisionResponse,
  PainAreaInput,
  RoutineResponse,
  SessionStatusCode,
  WeekResponse,
  WeeklyPlanRevisionResponse,
  WorkoutSessionDetailResponse,
  WorkoutSessionLogSummary,
} from '../../api/types';
import type { TabId } from '../../components/brand/BrandChrome';
import type {
  HomeCheckinDraft,
  HomePreviewState,
  HomeRoutineItem,
  LocalWorkoutPresentationState,
  RoutineItemDraftOverride,
} from './homeModel';
import type { RoutineGenerationPhaseCode } from './RoutineGenerationLoading';
import { HomeScreenContent } from './HomeScreenContent';

export { HOME_BACKGROUND_COLOR, HOME_LAYOUT } from './homeConstants';
export {
  HomeBottomNavigation,
  bottomNavigationBottomPadding,
} from './HomeChrome';

type HomeTab = TabId;
export type WeekDay = {
  completed: boolean;
  label: string;
  statusCodes?: readonly SessionStatusCode[];
};

export type HomeBusyKind =
  | 'decision-generation'
  | 'plan-edit'
  | 'regeneration'
  | 'revision'
  | 'starting';

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
  notificationPanel?: ReactNode;
  onDismissNotificationPanel?: () => void;
  notificationToastVisible?: boolean;
  localDate?: string;
  locationCodes?: readonly string[];
  /** Server-provided guidance; never computed or enforced by the client. */
  recommendedDurationMinutes?: number | null;
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
  onRetryPlanEdit?: () => void;
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
  routineLoadingContent?: ReactNode;
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
