import { useState } from 'react';

import type { Api } from '../../api/endpoints';
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
      await api.updateProfileSettings(body, profile.profile_version);
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
      profileUpdatePending={updateProfile.pending}
      profileUpdateError={updateProfile.error}
      onProfileFieldChange={(body) => void updateProfile.run(body)}
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
