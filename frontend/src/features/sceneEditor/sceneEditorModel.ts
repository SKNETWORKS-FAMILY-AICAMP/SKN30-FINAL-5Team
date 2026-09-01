export const SCENE_WIDTH = 1672;
export const SCENE_HEIGHT = 941;
export const DEFAULT_PREVIEW_SCALE = 0.4;
export const SCENE_EDITOR_STORAGE_KEY = 'campsite-scene-editor-layout-v1';

export const ASSET_CATEGORIES = [
  'cloud',
  'leaf',
  'bulb',
  'lantern',
  'flower',
  'grass',
  'custom',
] as const;

export type AssetCategory = (typeof ASSET_CATEGORIES)[number];

export type SceneAssetDefinition = {
  name: string;
  source: string;
  category: AssetCategory;
  group?: string;
  uri: string;
  width: number;
  height: number;
};

export type SceneBackgroundDefinition = {
  name: string;
  source: string;
  uri: string;
  width: number;
  height: number;
};

export type PlacedSceneAsset = {
  id: string;
  source: string;
  category: AssetCategory;
  uri: string;
  x: number;
  y: number;
  width: number;
  height: number;
  anchorX: number;
  anchorY: number;
  zIndex: number;
  motionType: string;
  duration: number;
  delay: number;
  amplitude: number;
};

export type ExportedSceneAsset = Omit<PlacedSceneAsset, 'uri'> & {
  nx: number;
  ny: number;
  nw: number;
  nh: number;
};

export type SceneLayout = {
  scene: {
    width: typeof SCENE_WIDTH;
    height: typeof SCENE_HEIGHT;
  };
  background?: {
    source: string;
  };
  assets: ExportedSceneAsset[];
};

type AssetDefaults = Pick<
  PlacedSceneAsset,
  | 'anchorX'
  | 'anchorY'
  | 'zIndex'
  | 'motionType'
  | 'duration'
  | 'delay'
  | 'amplitude'
>;

const CATEGORY_SET = new Set<string>(ASSET_CATEGORIES);

function roundNormalized(value: number): number {
  return Number(value.toFixed(4));
}

function defaultsFor(definition: SceneAssetDefinition): AssetDefaults {
  switch (definition.category) {
    case 'cloud':
      return {
        anchorX: 0.5,
        anchorY: 0.5,
        zIndex: 10,
        motionType: 'cloud',
        duration: 55,
        delay: 0,
        amplitude: 40,
      };
    case 'leaf':
      return {
        anchorX: definition.name === 'canopy_right' ? 0.9 : 0.1,
        anchorY: 0.15,
        zIndex: 20,
        motionType: 'leaf',
        duration: 6,
        delay: 0,
        amplitude: 0.6,
      };
    case 'bulb':
      if (definition.name === 'string_light_cable') {
        return {
          anchorX: 0.5,
          anchorY: 0,
          zIndex: 30,
          motionType: 'cable',
          duration: 6,
          delay: 0,
          amplitude: 0.5,
        };
      }
      return {
        anchorX: 0.5,
        anchorY: 0,
        zIndex: 31,
        motionType: 'bulb',
        duration: 3.2,
        delay: 0,
        amplitude: 1.1,
      };
    case 'lantern':
      return {
        anchorX: 0.5,
        anchorY: definition.name.includes('hanging') ? 0 : 0.5,
        zIndex: 40,
        motionType: definition.name.includes('hanging') ? 'lantern' : 'glow',
        duration: 4.8,
        delay: 0,
        amplitude: definition.name.includes('hanging') ? 1.5 : 1.03,
      };
    case 'flower':
      return {
        anchorX: 0.5,
        anchorY: 1,
        zIndex: 50,
        motionType: 'flower',
        duration: 3.7,
        delay: 0,
        amplitude: 1.2,
      };
    case 'grass':
      return {
        anchorX: 0.5,
        anchorY: 1,
        zIndex: 60,
        motionType: 'grass',
        duration: 2.6,
        delay: 0,
        amplitude: 0.8,
      };
    case 'custom':
      return {
        anchorX: 0.5,
        anchorY: 0.5,
        zIndex: 70,
        motionType: 'none',
        duration: 1,
        delay: 0,
        amplitude: 0,
      };
  }
}

export function createUniqueAssetId(
  assetName: string,
  placedAssets: readonly Pick<PlacedSceneAsset, 'id'>[],
): string {
  const escapedName = assetName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const matchingId = new RegExp(`^${escapedName}_(\\d{3,})$`);
  const usedNumbers = new Set(
    placedAssets.flatMap(({ id }) => {
      const match = matchingId.exec(id);
      return match ? [Number(match[1])] : [];
    }),
  );

  let next = 1;
  while (usedNumbers.has(next)) {
    next += 1;
  }
  return `${assetName}_${String(next).padStart(3, '0')}`;
}

export function createPlacedAsset(
  definition: SceneAssetDefinition,
  placedAssets: readonly PlacedSceneAsset[],
): PlacedSceneAsset {
  const offset = (placedAssets.length % 8) * 12;
  const defaults = defaultsFor(definition);
  return {
    id: createUniqueAssetId(definition.name, placedAssets),
    source: definition.source,
    category: definition.category,
    uri: definition.uri,
    x: Math.round((SCENE_WIDTH - definition.width) / 2 + offset),
    y: Math.round((SCENE_HEIGHT - definition.height) / 2 + offset),
    width: definition.width,
    height: definition.height,
    ...defaults,
  };
}

export function duplicatePlacedAsset(
  sourceAsset: PlacedSceneAsset,
  placedAssets: readonly PlacedSceneAsset[],
): PlacedSceneAsset {
  const name =
    sourceAsset.source
      .split('/')
      .at(-1)
      ?.replace(/\.png$/i, '') ?? 'asset';
  return {
    ...sourceAsset,
    id: createUniqueAssetId(name, placedAssets),
    x: sourceAsset.x + 16,
    y: sourceAsset.y + 16,
  };
}

export function exportSceneLayout(
  placedAssets: readonly PlacedSceneAsset[],
  backgroundSource?: string,
): SceneLayout {
  return {
    scene: { width: SCENE_WIDTH, height: SCENE_HEIGHT },
    ...(backgroundSource ? { background: { source: backgroundSource } } : {}),
    assets: placedAssets.map(({ uri: _uri, ...asset }) => ({
      ...asset,
      nx: roundNormalized(asset.x / SCENE_WIDTH),
      ny: roundNormalized(asset.y / SCENE_HEIGHT),
      nw: roundNormalized(asset.width / SCENE_WIDTH),
      nh: roundNormalized(asset.height / SCENE_HEIGHT),
    })),
  };
}

export function parseSceneBackground(
  raw: unknown,
  backgroundDefinitions: readonly SceneBackgroundDefinition[],
  fallback: SceneBackgroundDefinition,
): SceneBackgroundDefinition {
  if (typeof raw !== 'object' || raw === null) {
    throw new Error('Layout must be a JSON object.');
  }
  const background = (raw as { background?: unknown }).background;
  if (background === undefined) return fallback;
  if (typeof background !== 'object' || background === null) {
    throw new Error('Layout background must be an object.');
  }
  const source = (background as { source?: unknown }).source;
  if (typeof source !== 'string' || source.trim() === '') {
    throw new Error('Layout background.source must be a non-empty string.');
  }
  const definition = backgroundDefinitions.find(
    (candidate) => candidate.source === source,
  );
  if (!definition) {
    throw new Error(`Unknown background source: ${source}`);
  }
  return definition;
}

function requireString(
  value: unknown,
  field: string,
  assetIndex: number,
): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(
      `assets[${assetIndex}].${field} must be a non-empty string.`,
    );
  }
  return value;
}

function requireNumber(
  value: unknown,
  field: string,
  assetIndex: number,
): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`assets[${assetIndex}].${field} must be a finite number.`);
  }
  return value;
}

export function parseSceneLayout(
  raw: unknown,
  assetDefinitions: readonly SceneAssetDefinition[],
): PlacedSceneAsset[] {
  if (typeof raw !== 'object' || raw === null) {
    throw new Error('Layout must be a JSON object.');
  }

  const candidate = raw as { scene?: unknown; assets?: unknown };
  const scene = candidate.scene as
    { width?: unknown; height?: unknown } | undefined;
  if (scene?.width !== SCENE_WIDTH || scene.height !== SCENE_HEIGHT) {
    throw new Error(
      `Scene must use the ${SCENE_WIDTH} × ${SCENE_HEIGHT} coordinate system.`,
    );
  }
  if (!Array.isArray(candidate.assets)) {
    throw new Error('Layout assets must be an array.');
  }

  const definitionsBySource = new Map(
    assetDefinitions.map((definition) => [definition.source, definition]),
  );
  const ids = new Set<string>();

  return candidate.assets.map((rawAsset, index) => {
    if (typeof rawAsset !== 'object' || rawAsset === null) {
      throw new Error(`assets[${index}] must be an object.`);
    }
    const asset = rawAsset as Record<string, unknown>;
    const id = requireString(asset.id, 'id', index);
    if (ids.has(id)) {
      throw new Error(`Duplicate asset id: ${id}`);
    }
    ids.add(id);

    const source = requireString(asset.source, 'source', index);
    const definition = definitionsBySource.get(source);
    if (!definition) {
      throw new Error(`Unknown asset source: ${source}`);
    }
    const category = requireString(asset.category, 'category', index);
    if (!CATEGORY_SET.has(category) || category !== definition.category) {
      throw new Error(`Invalid category for ${source}: ${category}`);
    }

    const width = requireNumber(asset.width, 'width', index);
    const height = requireNumber(asset.height, 'height', index);
    if (width <= 0 || height <= 0) {
      throw new Error(
        `assets[${index}] width and height must be greater than zero.`,
      );
    }

    const anchorX = requireNumber(asset.anchorX, 'anchorX', index);
    const anchorY = requireNumber(asset.anchorY, 'anchorY', index);
    if (anchorX < 0 || anchorX > 1 || anchorY < 0 || anchorY > 1) {
      throw new Error(`assets[${index}] anchors must be between 0 and 1.`);
    }

    const duration = requireNumber(asset.duration, 'duration', index);
    if (duration <= 0) {
      throw new Error(`assets[${index}].duration must be greater than zero.`);
    }

    return {
      id,
      source,
      category: definition.category,
      uri: definition.uri,
      x: requireNumber(asset.x, 'x', index),
      y: requireNumber(asset.y, 'y', index),
      width,
      height,
      anchorX,
      anchorY,
      zIndex: requireNumber(asset.zIndex, 'zIndex', index),
      motionType: requireString(asset.motionType, 'motionType', index),
      duration,
      delay: requireNumber(asset.delay, 'delay', index),
      amplitude: requireNumber(asset.amplitude, 'amplitude', index),
    };
  });
}
