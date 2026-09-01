import { describe, expect, it } from '@jest/globals';

import {
  createPlacedAsset,
  duplicatePlacedAsset,
  exportSceneLayout,
  parseSceneBackground,
  parseSceneLayout,
  SCENE_HEIGHT,
  SCENE_WIDTH,
  type SceneAssetDefinition,
  type SceneBackgroundDefinition,
} from '../src/features/sceneEditor/sceneEditorModel';

const flower: SceneAssetDefinition = {
  name: 'flower_pink_01',
  source: 'flowers/flower_pink_01.png',
  category: 'flower',
  uri: 'test-flower-uri',
  width: 48,
  height: 72,
};

const bulb: SceneAssetDefinition = {
  name: 'bulb_generic',
  source: 'bulbs/bulb_generic.png',
  category: 'bulb',
  uri: 'test-bulb-uri',
  width: 32,
  height: 44,
};

const background: SceneBackgroundDefinition = {
  name: 'night',
  source: 'local/backgrounds/night.png',
  uri: 'night-uri',
  width: 1672,
  height: 941,
};

describe('scene editor model', () => {
  it('creates category defaults in unscaled scene coordinates', () => {
    const placed = createPlacedAsset(flower, []);

    expect(placed).toMatchObject({
      id: 'flower_pink_01_001',
      x: Math.round((SCENE_WIDTH - flower.width) / 2),
      y: Math.round((SCENE_HEIGHT - flower.height) / 2),
      width: 48,
      height: 72,
      anchorX: 0.5,
      anchorY: 1,
      zIndex: 50,
      motionType: 'flower',
    });
  });

  it('duplicates reusable assets with independent sequential ids', () => {
    const first = createPlacedAsset(bulb, []);
    const second = duplicatePlacedAsset(first, [first]);
    const third = duplicatePlacedAsset(second, [first, second]);

    expect([first.id, second.id, third.id]).toEqual([
      'bulb_generic_001',
      'bulb_generic_002',
      'bulb_generic_003',
    ]);
    expect(second).toMatchObject({ x: first.x + 16, y: first.y + 16 });
  });

  it('exports normalized values without the runtime URI', () => {
    const placed = {
      ...createPlacedAsset(flower, []),
      x: 1214,
      y: 576,
    };

    const layout = exportSceneLayout([placed]);

    expect(layout.scene).toEqual({ width: 1672, height: 941 });
    expect(layout.assets[0]).toMatchObject({
      source: 'flowers/flower_pink_01.png',
      nx: 0.7261,
      ny: 0.6121,
      nw: 0.0287,
      nh: 0.0765,
    });
    expect(layout.assets[0]).not.toHaveProperty('uri');
  });

  it('exports and resolves a selected background', () => {
    const layout = exportSceneLayout([], background.source);

    expect(layout.background).toEqual({ source: background.source });
    expect(parseSceneBackground(layout, [background], background)).toEqual(
      background,
    );
  });

  it('keeps old layouts compatible by falling back to the default background', () => {
    const layout = exportSceneLayout([]);

    expect(parseSceneBackground(layout, [background], background)).toEqual(
      background,
    );
  });

  it('imports a valid export and resolves its bundled URI', () => {
    const placed = createPlacedAsset(flower, []);
    const imported = parseSceneLayout(exportSceneLayout([placed]), [flower]);

    expect(imported).toEqual([placed]);
  });

  it('rejects layouts with a wrong scene or unknown source', () => {
    const placed = createPlacedAsset(flower, []);
    const wrongScene = exportSceneLayout([placed]);
    const unknownSource = exportSceneLayout([placed]);
    wrongScene.scene.width = 1 as typeof SCENE_WIDTH;
    unknownSource.assets[0]!.source = 'flowers/missing.png';

    expect(() => parseSceneLayout(wrongScene, [flower])).toThrow('1672 × 941');
    expect(() => parseSceneLayout(unknownSource, [flower])).toThrow(
      'Unknown asset source',
    );
  });
});
