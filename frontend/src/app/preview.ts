export type PreviewMode =
  | 'account'
  | 'calendar-report'
  | 'gallery'
  | 'home'
  | 'home-map'
  | 'login'
  | 'mascot-house'
  | 'my-page'
  | 'onboarding'
  | 'profile'
  | 'signup'
  | 'splash'
  | 'session'
  | 'session-result'
  | 'today'
  | 'weekly-report'
  | 'workout'
  | null;

export function getPreviewMode(): PreviewMode {
  return null;
}
