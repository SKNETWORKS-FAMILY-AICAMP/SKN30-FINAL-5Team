import { useState } from 'react';

import type { Api } from '../../api/endpoints';
import { isApiError } from '../../api/errors';
import type {
  ConsentValues,
  MeResponse,
  ProfileSettingsUpdateRequest,
} from '../../api/types';
import {
  localDateString,
  useAsyncAction,
  useAsyncData,
} from '../../api/useAsync';
import type { TabId } from '../../components/brand/BrandChrome';
import type { MyPagePreviewState } from './homeSecondaryModel';
import { MyPageScreen } from './MyPageScreen';
import type { ProfileImageChange } from './MyPageProfileEditor';
import { daysTogether } from './myPageModel';

type MyPageContainerProps = {
  api: Api;
  me: MeResponse;
  onNavigateTab: (tab: TabId) => void;
  onOpenExerciseCatalog?: () => void;
  onRefreshMe: () => Promise<void>;
  onSignOut: () => void;
  now?: Date;
  previewState?: MyPagePreviewState;
};

const DEFAULT_CONSENTS: ConsentValues = {
  general_personal_data: true,
  sensitive_data: true,
  wearable_integration: false,
  calendar_integration: false,
  marketing: false,
};

export function MyPageContainer({
  api,
  me,
  onNavigateTab,
  onOpenExerciseCatalog,
  onRefreshMe,
  onSignOut,
  now,
  previewState,
}: MyPageContainerProps) {
  const referenceNow = now ?? new Date();
  const profile = me.profile;
  const timeZone = profile?.timezone;
  const today = localDateString(referenceNow, timeZone);
  const [deletionDeadline, setDeletionDeadline] = useState<string | null>(null);

  const updateProfile = useAsyncAction(
    async (body: ProfileSettingsUpdateRequest) => {
      if (profile === null) return;
      try {
        await api.updateProfileSettings(body, profile.profile_version);
      } catch (error) {
        if (isApiError(error) && error.code === 'STALE_PROFILE') {
          await onRefreshMe().catch(() => undefined);
        }
        throw error;
      }
      await onRefreshMe();
    },
  );

  const updateBasicProfile = useAsyncAction(
    async ({
      body,
      imageChange,
    }: {
      body: ProfileSettingsUpdateRequest;
      imageChange: ProfileImageChange | undefined;
    }) => {
      if (profile === null) return;
      let expectedVersion = profile.profile_version;
      let profileWasUpdated = false;
      try {
        if (Object.keys(body).length > 0) {
          const response = await api.updateProfileSettings(
            body,
            expectedVersion,
          );
          expectedVersion = response.profile_version;
          profileWasUpdated = true;
        }
        if (imageChange !== undefined) {
          if (imageChange === null) {
            await api.deleteProfileImage(expectedVersion);
          } else {
            await api.uploadProfileImage(imageChange, expectedVersion);
          }
        }
      } catch (error) {
        if (
          profileWasUpdated ||
          (isApiError(error) && error.code === 'STALE_PROFILE')
        ) {
          await onRefreshMe().catch(() => undefined);
        }
        throw error;
      }
      await onRefreshMe();
    },
  );

  const updateCoach = (coachingStyleCode: string) => {
    if (profile === null) return;
    void updateProfile.run({ coaching_style_code: coachingStyleCode });
  };

  const consents = useAsyncData((signal) => api.getConsents(signal), [api]);
  const storedConsents =
    consents.state.status === 'ready'
      ? consents.state.data.consents.reduce<ConsentValues>(
          (values, consent) => ({
            ...values,
            [consent.consent_type_code.toLowerCase()]: consent.granted,
          }),
          DEFAULT_CONSENTS,
        )
      : null;
  const updateConsents = useAsyncAction(async (next: ConsentValues) => {
    const response = await api.replaceConsents(next);
    consents.setData(response);
  });

  const requestDeletion = useAsyncAction(async () => {
    const response = await api.requestAccountDeletion();
    setDeletionDeadline(response.operational_data_delete_by);
  });

  const joinedDays =
    profile === null
      ? null
      : daysTogether(
          localDateString(new Date(profile.created_at), profile.timezone),
          today,
        );

  return (
    <MyPageScreen
      me={me}
      joinedDays={joinedDays}
      coachingStylePending={updateProfile.pending}
      coachingStyleError={updateProfile.error}
      onCoachingStyleChange={updateCoach}
      profileUpdatePending={updateProfile.pending || updateBasicProfile.pending}
      profileUpdateError={profileUpdateErrorMessage(
        updateBasicProfile.error ?? updateProfile.error,
        updateBasicProfile.lastError ?? updateProfile.lastError,
      )}
      onBasicProfileChange={(body, imageChange) =>
        void updateBasicProfile.run({ body, imageChange })
      }
      onProfileFieldChange={(body) => void updateProfile.run(body)}
      onRetryProfile={() => void onRefreshMe()}
      consentValues={storedConsents}
      consentPending={
        consents.state.status === 'loading' || updateConsents.pending
      }
      consentError={
        updateConsents.error ??
        (consents.state.status === 'error' ? consents.state.message : null)
      }
      onConsentChange={(key, enabled) => {
        if (storedConsents === null) return;
        void updateConsents.run({ ...storedConsents, [key]: enabled });
      }}
      onRetryConsents={consents.reload}
      deletionDeadline={deletionDeadline}
      withdrawalPending={requestDeletion.pending}
      withdrawalError={requestDeletion.error}
      onConfirmWithdraw={() => void requestDeletion.run()}
      onConfirmLogout={onSignOut}
      onNavigateTab={onNavigateTab}
      onOpenExerciseCatalog={onOpenExerciseCatalog}
      persistedSettingsAvailable={false}
      previewState={previewState}
    />
  );
}

const PROFILE_FIELD_LABELS: Record<string, string> = {
  primary_goal_code: '운동 목표',
  desired_weekly_workout_count: '주간 목표',
  default_requested_duration_minutes: '희망 시간',
  preferred_location_code: '선호 장소',
  available_location_codes: '운동 장소',
  attention_area_codes: '통증 부위',
  preferred_exercise_type_codes: '선호 운동',
  coaching_style_code: '코칭 스타일',
  experience_level_code: '운동 경험',
  nickname: '닉네임',
  height_cm: '키',
  weight_kg: '체중',
  sex_code: '성별',
  date_of_birth: '생년월일',
};

function profileUpdateErrorMessage(
  message: string | null,
  error: unknown,
): string | null {
  if (message === null || !isApiError(error)) return message;
  const fields = [
    ...new Set(
      error.details
        .map((detail) => detail.field?.split('.').at(-1))
        .filter((field): field is string => Boolean(field)),
    ),
  ];
  const labels = fields
    .map((field) => PROFILE_FIELD_LABELS[field])
    .filter((label): label is string => Boolean(label));
  return labels.length > 0
    ? `${labels.join('·')} 값을 확인해주세요. ${message}`
    : message;
}
