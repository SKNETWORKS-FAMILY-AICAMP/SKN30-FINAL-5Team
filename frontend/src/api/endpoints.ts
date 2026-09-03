/**
 * One function per implemented `/api/v1` endpoint.
 *
 * Profile-image methods are the frontend side of a proposed multipart contract;
 * the backend must review and implement that contract before production use.
 * Calendar and wearable routes remain absent while there is nothing to call.
 */

import type { ApiClient } from './client';
import type {
  ConsentResponse,
  ConsentValues,
  DailyContextRequest,
  DailyContextResponse,
  DecisionRegenerationRequest,
  DecisionResponse,
  DecisionSelectionResponse,
  ExerciseDetailResponse,
  ExerciseListResponse,
  ExerciseVariantsResponse,
  MeResponse,
  NotCompletedReasonCode,
  OnboardingRequest,
  OnboardingResponse,
  ProfileImageMutationResponse,
  ProfileImageUpload,
  ProfileSettingsUpdateRequest,
  ProfileSettingsUpdateResponse,
  RoutineResponse,
  SafetyEventResponse,
  SessionFinishResponse,
  SessionItemUpdateResponse,
  SessionNotCompletedResponse,
  SessionStartResponse,
  WeeklyPlanRevisionRequest,
  WeeklyPlanRevisionResponse,
  WeeklyReportResponse,
  WeekResponse,
  WorkoutAdditionalActivityResponse,
  WorkoutFeedbackResponse,
  WorkoutSessionDetailResponse,
  WorkoutSessionListResponse,
} from './types';

export function createApi(client: ApiClient) {
  return {
    getMe(signal?: AbortSignal) {
      return client.request<MeResponse>({ path: '/me', signal });
    },

    submitOnboarding(body: OnboardingRequest) {
      return client.request<OnboardingResponse>({
        method: 'PUT',
        path: '/me/onboarding',
        body,
        idempotent: true,
      });
    },

    updateProfileSettings(
      body: ProfileSettingsUpdateRequest,
      expectedProfileVersion: number,
    ) {
      return client.request<ProfileSettingsUpdateResponse>({
        method: 'PATCH',
        path: '/me/profile',
        body,
        idempotent: true,
        ifMatch: expectedProfileVersion,
      });
    },

    uploadProfileImage(
      image: ProfileImageUpload,
      expectedProfileVersion: number,
    ) {
      const formData = new FormData();
      const filePart =
        image.webFile ??
        ({
          uri: image.uri,
          name: image.fileName,
          type: image.mimeType,
        } as unknown as Blob);
      formData.append('file', filePart, image.fileName);

      return client.request<ProfileImageMutationResponse>({
        method: 'POST',
        path: '/me/profile-image',
        formData,
        idempotent: true,
        ifMatch: expectedProfileVersion,
      });
    },

    deleteProfileImage(expectedProfileVersion: number) {
      return client.request<ProfileImageMutationResponse>({
        method: 'DELETE',
        path: '/me/profile-image',
        idempotent: true,
        ifMatch: expectedProfileVersion,
      });
    },

    /**
     * `requested_duration_minutes` is optional. Omitting it keeps the profile
     * default; sending it makes this routine a USER_OVERRIDE without changing
     * the stored profile default.
     */
    createRoutine(
      body: {
        effective_from: string;
        goal_code: string;
        requested_duration_minutes?: number;
      },
      idempotencyKey?: string,
    ) {
      return client.request<RoutineResponse>({
        method: 'POST',
        path: '/routines',
        body,
        idempotent: true,
        idempotencyKey,
      });
    },

    getCurrentRoutine(localDate: string, signal?: AbortSignal) {
      return client.request<RoutineResponse>({
        path: '/routines/current',
        query: { local_date: localDate },
        signal,
      });
    },

    /**
     * Reviewed catalog exercises only; the server never lists unapproved
     * content. Filters combine with AND and paging follows `next_cursor`.
     */
    listExercises(
      query: {
        bodyAreaCode?: string;
        equipmentCode?: string;
        trainingTypeCode?: string;
        difficultyCode?: string;
        cursor?: string;
        limit?: number;
      } = {},
      signal?: AbortSignal,
    ) {
      return client.request<ExerciseListResponse>({
        path: '/exercises',
        query: {
          body_area_code: query.bodyAreaCode,
          equipment_code: query.equipmentCode,
          training_type_code: query.trainingTypeCode,
          difficulty_code: query.difficultyCode,
          cursor: query.cursor,
          limit: query.limit === undefined ? undefined : String(query.limit),
        },
        signal,
      });
    },

    getExercise(exerciseId: string, signal?: AbortSignal) {
      return client.request<ExerciseDetailResponse>({
        path: `/exercises/${exerciseId}`,
        signal,
      });
    },

    /**
     * Reviewed EQUIPMENT variants for display only. An empty `items` array
     * means this exercise must not expose a variant action.
     */
    getExerciseVariants(exerciseId: string, signal?: AbortSignal) {
      return client.request<ExerciseVariantsResponse>({
        path: `/exercises/${exerciseId}/variants`,
        signal,
      });
    },

    getDailyContext(localDate: string, signal?: AbortSignal) {
      return client.request<DailyContextResponse>({
        path: `/daily-contexts/${localDate}`,
        signal,
      });
    },

    /**
     * `expectedVersion` must come from a previous read. Omitting it on an
     * existing check-in is what the server answers with `409 STALE_CONTEXT`.
     */
    replaceDailyContext(
      localDate: string,
      body: DailyContextRequest,
      expectedVersion?: number,
    ) {
      return client.request<DailyContextResponse>({
        method: 'PUT',
        path: `/daily-contexts/${localDate}`,
        body,
        idempotent: true,
        ifMatch: expectedVersion,
      });
    },

    createDecision(
      body: {
        local_date: string;
        daily_context_id: string;
        expected_context_version: number;
      },
      idempotencyKey?: string,
    ) {
      return client.request<DecisionResponse>({
        method: 'POST',
        path: '/decisions',
        body,
        idempotent: true,
        idempotencyKey,
      });
    },

    getDecision(decisionId: string, signal?: AbortSignal) {
      return client.request<DecisionResponse>({
        path: `/decisions/${decisionId}`,
        signal,
      });
    },

    /**
     * The day's stored decision, so a restarted client can resume it instead
     * of forcing the user through the check-in again. 404 means the day has
     * no completed decision yet.
     */
    getDecisionForDate(localDate: string, signal?: AbortSignal) {
      return client.request<DecisionResponse>({
        path: '/decisions',
        query: { local_date: localDate },
        signal,
      });
    },

    regenerateDecision(decisionId: string, body: DecisionRegenerationRequest) {
      return client.request<DecisionResponse>({
        method: 'POST',
        path: `/decisions/${decisionId}/regenerations`,
        body,
        idempotent: true,
      });
    },

    selectOption(decisionId: string, optionId: string) {
      return client.request<DecisionSelectionResponse>({
        method: 'POST',
        path: `/decisions/${decisionId}/selection`,
        body: { option_id: optionId },
        idempotent: true,
      });
    },

    listWorkoutSessions(
      query: {
        fromLocalDate?: string;
        toLocalDate?: string;
        statusCode?: string;
        cursor?: string;
        limit?: number;
      } = {},
      signal?: AbortSignal,
    ) {
      return client.request<WorkoutSessionListResponse>({
        path: '/workout-sessions',
        query: {
          from_local_date: query.fromLocalDate,
          to_local_date: query.toLocalDate,
          status_code: query.statusCode,
          cursor: query.cursor,
          limit: query.limit === undefined ? undefined : String(query.limit),
        },
        signal,
      });
    },

    getWorkoutSession(sessionId: string, signal?: AbortSignal) {
      return client.request<WorkoutSessionDetailResponse>({
        path: `/workout-sessions/${sessionId}`,
        signal,
      });
    },

    startSession(sessionId: string, startedAt: string) {
      return client.request<SessionStartResponse>({
        method: 'PATCH',
        path: `/workout-sessions/${sessionId}/start`,
        body: { started_at: startedAt },
        idempotent: true,
      });
    },

    /**
     * The only source of official completion. Elapsed time never calls this.
     */
    updateSessionItem(
      sessionId: string,
      planItemId: string,
      statusCode: 'PENDING' | 'COMPLETED',
      clientRecordedAt: string,
    ) {
      return client.request<SessionItemUpdateResponse>({
        method: 'PATCH',
        path: `/workout-sessions/${sessionId}/items/${planItemId}`,
        body: { status_code: statusCode, client_recorded_at: clientRecordedAt },
        idempotent: true,
      });
    },

    recordTimerEvent(
      sessionId: string,
      eventCode: 'START' | 'PAUSE' | 'RESUME' | 'END',
      occurredAt: string,
    ) {
      return client.request<{ event_id: string }>({
        method: 'POST',
        path: `/workout-sessions/${sessionId}/timer-events`,
        body: {
          event_code: eventCode,
          occurred_at: occurredAt,
          client_recorded_at: occurredAt,
        },
        idempotent: true,
      });
    },

    recordAdditionalActivity(
      sessionId: string,
      body: {
        activity_type_code: string;
        duration_seconds: number;
        intensity_code?: string | null;
        note?: string | null;
      },
    ) {
      return client.request<WorkoutAdditionalActivityResponse>({
        method: 'POST',
        path: `/workout-sessions/${sessionId}/additional-activities`,
        body,
        idempotent: true,
      });
    },

    reportSafetyEvent(
      sessionId: string,
      body: {
        occurred_at: string;
        discomforts: { body_area_code: string; severity_code: string }[];
        adverse_reaction_codes: string[];
      },
    ) {
      return client.request<SafetyEventResponse>({
        method: 'POST',
        path: `/workout-sessions/${sessionId}/safety-events`,
        body,
        idempotent: true,
      });
    },

    finishSession(
      sessionId: string,
      finishedAt: string,
      actualElapsedSeconds: number,
    ) {
      return client.request<SessionFinishResponse>({
        method: 'PATCH',
        path: `/workout-sessions/${sessionId}/finish`,
        body: {
          finished_at: finishedAt,
          actual_elapsed_seconds: actualElapsedSeconds,
        },
        idempotent: true,
      });
    },

    markNotCompleted(
      sessionId: string,
      endedAt: string,
      reasonCode: NotCompletedReasonCode,
    ) {
      return client.request<SessionNotCompletedResponse>({
        method: 'PATCH',
        path: `/workout-sessions/${sessionId}/not-completed`,
        body: { ended_at: endedAt, reason_code: reasonCode },
        idempotent: true,
      });
    },

    submitFeedback(
      sessionId: string,
      body: {
        difficulty_code: 'EASY' | 'APPROPRIATE' | 'HARD';
        fatigue_code?: string | null;
        satisfaction_code?: string | null;
        pain_occurred: boolean;
        discomforts: { body_area_code: string; severity_code: string }[];
        adverse_reaction_codes: string[];
      },
    ) {
      return client.request<WorkoutFeedbackResponse>({
        method: 'POST',
        path: `/workout-sessions/${sessionId}/feedback`,
        body,
        idempotent: true,
      });
    },

    getWeek(weekStart: string, signal?: AbortSignal) {
      return client.request<WeekResponse>({
        path: `/weeks/${weekStart}`,
        signal,
      });
    },

    /**
     * Creates the week's `INITIAL` plan revision. The response carries the
     * `revision_sequence` and `ai_revision_count` that a later revision needs;
     * there is no read endpoint for them, so the caller must keep what it gets.
     */
    createInitialWeeklyPlan(weekStart: string) {
      return client.request<WeeklyPlanRevisionResponse>({
        method: 'POST',
        path: `/weeks/${weekStart}/plan`,
        body: {},
        idempotent: true,
      });
    },

    /**
     * `AI` asks the Coordinator for a revised routine (at most twice a week);
     * `USER` submits a stored routine version and a location for the server to
     * re-validate. Neither lets the client author exercises or safety state.
     */
    createPlanRevision(weekStart: string, body: WeeklyPlanRevisionRequest) {
      return client.request<WeeklyPlanRevisionResponse>({
        method: 'POST',
        path: `/weeks/${weekStart}/plan-revisions`,
        body,
        idempotent: true,
      });
    },

    createWeeklyReport(weekStart: string) {
      return client.request<WeeklyReportResponse>({
        method: 'POST',
        path: `/weeks/${weekStart}/report`,
        body: { expected_week_status_code: 'CLOSED' },
        idempotent: true,
      });
    },

    getWeeklyReport(reportId: string, signal?: AbortSignal) {
      return client.request<WeeklyReportResponse>({
        path: `/weekly-reports/${reportId}`,
        signal,
      });
    },

    acknowledgeWeeklyReport(reportId: string, acknowledgedAt: string) {
      return client.request<WeeklyReportResponse>({
        method: 'POST',
        path: `/weekly-reports/${reportId}/acknowledgement`,
        body: { acknowledged_at: acknowledgedAt },
        idempotent: true,
      });
    },

    getConsents(signal?: AbortSignal) {
      return client.request<ConsentResponse>({ path: '/me/consents', signal });
    },

    /**
     * Replaces the full consent set. The required pair stays true from
     * onboarding; this call exists so the optional consents can be changed
     * and withdrawn after the fact.
     */
    replaceConsents(body: ConsentValues) {
      return client.request<ConsentResponse>({
        method: 'PUT',
        path: '/me/consents',
        body,
        idempotent: true,
      });
    },

    requestAccountDeletion() {
      return client.request<{
        deletion_request_id: string;
        status_code: string;
        operational_data_delete_by: string;
        backup_expiry_days: number;
      }>({
        method: 'DELETE',
        path: '/me',
        idempotent: true,
      });
    },
  };
}

/**
 * Forward-compatible read boundary for restoring the server-owned weekly plan
 * revision after an app restart. The backend route is not available yet, so
 * this capability stays optional and `createApi` does not issue a speculative
 * request. Once the route is implemented, adding this method to `createApi`
 * automatically enables MainFlow restoration.
 */
export type WeeklyPlanRevisionReadCapability = {
  getLatestWeeklyPlanRevision(
    weekStart: string,
    signal?: AbortSignal,
  ): Promise<WeeklyPlanRevisionResponse>;
};

export type Api = ReturnType<typeof createApi> &
  Partial<WeeklyPlanRevisionReadCapability>;
