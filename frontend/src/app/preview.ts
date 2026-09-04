export type PreviewMode =
  | 'account'
  | 'app-status'
  | 'auth'
  | 'background_test'
  | 'banana-catch'
  | 'calendar-report'
  | 'exercise-catalog'
  | 'gallery'
  | 'home'
  | 'home-map'
  | 'login'
  | 'loading'
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

export type PreviewViewportMode = 'device' | null;

export function getPreviewMode(): PreviewMode {
  return null;
}

export function getPreviewViewportMode(): PreviewViewportMode {
  return null;
}
