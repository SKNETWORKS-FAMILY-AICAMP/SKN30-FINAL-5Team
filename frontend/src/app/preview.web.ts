export type PreviewMode =
  | 'account'
  | 'auth'
  | 'background_test'
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

export function getPreviewMode(): PreviewMode {
  if (!__DEV__ || typeof window === 'undefined') {
    return null;
  }

  const requestedPreview = new URLSearchParams(window.location.search).get(
    'preview',
  );

  if (
    requestedPreview === 'account' ||
    requestedPreview === 'auth' ||
    requestedPreview === 'background_test' ||
    requestedPreview === 'calendar-report' ||
    requestedPreview === 'exercise-catalog' ||
    requestedPreview === 'gallery' ||
    requestedPreview === 'home' ||
    requestedPreview === 'home-map' ||
    requestedPreview === 'login' ||
    requestedPreview === 'loading' ||
    requestedPreview === 'mascot-house' ||
    requestedPreview === 'my-page' ||
    requestedPreview === 'onboarding' ||
    requestedPreview === 'profile' ||
    requestedPreview === 'signup' ||
    requestedPreview === 'splash' ||
    requestedPreview === 'session' ||
    requestedPreview === 'session-result' ||
    requestedPreview === 'today' ||
    requestedPreview === 'weekly-report' ||
    requestedPreview === 'workout'
  ) {
    return requestedPreview;
  }

  return null;
}
