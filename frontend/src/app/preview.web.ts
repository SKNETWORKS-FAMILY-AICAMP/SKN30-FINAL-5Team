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
  if (!__DEV__ || typeof window === 'undefined') {
    return null;
  }

  const requestedPreview = new URLSearchParams(window.location.search).get(
    'preview',
  );

  if (
    requestedPreview === 'account' ||
    requestedPreview === 'calendar-report' ||
    requestedPreview === 'gallery' ||
    requestedPreview === 'home' ||
    requestedPreview === 'home-map' ||
    requestedPreview === 'login' ||
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
