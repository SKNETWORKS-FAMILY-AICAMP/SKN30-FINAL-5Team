import { Asset } from 'expo-asset';

import type {
  AssetCategory,
  SceneAssetDefinition,
  SceneBackgroundDefinition,
} from './sceneEditorModel';

type ResolvedAsset = {
  uri: string;
  width?: number;
  height?: number;
};

type MetroAssetModule =
  | number
  | string
  | ResolvedAsset
  | { default: number | string | ResolvedAsset };

type MetroRequireContext = {
  keys(): string[];
  (id: string): unknown;
};

declare global {
  namespace NodeJS {
    interface Require {
      context(
        path: string,
        recursive?: boolean,
        filter?: RegExp,
        mode?: 'sync' | 'eager' | 'weak' | 'lazy' | 'lazy-once',
      ): MetroRequireContext;
    }
  }
}

const assetContext = require.context(
  '../../assets/house/moving_temp/campsite_motion_assets_v3_work',
  true,
  /^\.\/(bulbs|clouds|flowers|grass|lanterns|leaves)\/.*\.png$/,
  'sync',
);

const CATEGORY_BY_DIRECTORY: Record<string, AssetCategory> = {
  bulbs: 'bulb',
  clouds: 'cloud',
  flowers: 'flower',
  grass: 'grass',
  lanterns: 'lantern',
  leaves: 'leaf',
};

function resolveStaticAsset(module: MetroAssetModule) {
  const value =
    typeof module === 'object' && 'default' in module ? module.default : module;
  const resolved =
    typeof value === 'number'
      ? Asset.fromModule(value)
      : typeof value === 'string'
        ? { uri: value }
        : value;
  if (!resolved?.uri) {
    throw new Error('Metro could not resolve a campsite editor asset.');
  }
  return resolved;
}

export const SCENE_EDITOR_ASSETS: SceneAssetDefinition[] = assetContext
  .keys()
  .map((key) => {
    const source = key.replace(/^\.\//, '').replace(/\\/g, '/');
    const directory = source.split('/')[0] ?? '';
    const category = CATEGORY_BY_DIRECTORY[directory];
    if (!category) {
      throw new Error(`Unsupported campsite asset directory: ${directory}`);
    }
    const name =
      source
        .split('/')
        .at(-1)
        ?.replace(/\.png$/i, '') ?? source;
    const resolved = resolveStaticAsset(assetContext(key) as MetroAssetModule);
    return {
      name,
      source,
      category,
      uri: resolved.uri,
      width: resolved.width || 1,
      height: resolved.height || 1,
    };
  })
  .sort((left, right) =>
    `${left.category}/${left.name}`.localeCompare(
      `${right.category}/${right.name}`,
      undefined,
      { numeric: true },
    ),
  );

export const SCENE_EDITOR_REFERENCE_URI = resolveStaticAsset(
  require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/reference.png') as MetroAssetModule,
).uri;

const defaultBackground = resolveStaticAsset(
  require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/background/background_static.png') as MetroAssetModule,
);

export const SCENE_EDITOR_DEFAULT_BACKGROUND: SceneBackgroundDefinition = {
  name: 'background_static',
  source: 'background/background_static.png',
  uri: defaultBackground.uri,
  width: defaultBackground.width || 1672,
  height: defaultBackground.height || 941,
};

export const SCENE_EDITOR_BACKGROUND_URI = SCENE_EDITOR_DEFAULT_BACKGROUND.uri;
