export type PreviewMode =
  | 'calendar-report'
  | 'gallery'
  | 'home'
  | 'home-map'
  | 'login'
  | 'my-page'
  | 'profile'
  | 'signup'
  | 'splash'
  | 'today'
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
    requestedPreview === 'calendar-report' ||
    requestedPreview === 'gallery' ||
    requestedPreview === 'home' ||
    requestedPreview === 'home-map' ||
    requestedPreview === 'login' ||
    requestedPreview === 'my-page' ||
    requestedPreview === 'profile' ||
    requestedPreview === 'signup' ||
    requestedPreview === 'splash' ||
    requestedPreview === 'today' ||
    requestedPreview === 'workout'
  ) {
    return requestedPreview;
  }

  return null;
}
