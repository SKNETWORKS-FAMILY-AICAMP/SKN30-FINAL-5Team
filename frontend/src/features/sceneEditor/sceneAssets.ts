import type {
  SceneAssetDefinition,
  SceneBackgroundDefinition,
} from './sceneEditorModel';

// The editor is web-only. Native exports stay asset-free so Android and iOS
// production bundles do not need to evaluate Metro's require.context registry.
export const SCENE_EDITOR_ASSETS: SceneAssetDefinition[] = [];
export const SCENE_EDITOR_REFERENCE_URI = '';
export const SCENE_EDITOR_BACKGROUND_URI = '';
export const SCENE_EDITOR_DEFAULT_BACKGROUND: SceneBackgroundDefinition = {
  name: '',
  source: '',
  uri: '',
  width: 1672,
  height: 941,
};
