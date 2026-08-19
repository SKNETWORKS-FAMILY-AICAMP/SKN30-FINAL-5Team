import type { Api } from '../../api/endpoints';

/**
 * Network-free API surface for `?preview=onboarding`.
 *
 * The preview accepts the form so validation and success handling can be
 * inspected without creating or changing a real user profile.
 */
export const onboardingPreviewApi: Pick<Api, 'submitOnboarding'> = {
  async submitOnboarding() {
    return {
      user_id: 'preview-user',
      onboarding_completed: true,
      profile_version: 1,
      coaching_style_code: 'SUPPORTIVE',
      ai_trial_started_at: '2026-08-18T00:00:00+09:00',
      ai_trial_ends_at: '2026-09-17T00:00:00+09:00',
      premium_status_code: 'TRIAL',
      created_at: '2026-08-18T00:00:00+09:00',
      updated_at: '2026-08-18T00:00:00+09:00',
    };
  },
};
