export function isSceneEditorRoute(): boolean {
  if (!__DEV__ || typeof window === 'undefined') {
    return false;
  }
  return window.location.pathname.replace(/\/+$/, '') === '/scene-editor';
}
