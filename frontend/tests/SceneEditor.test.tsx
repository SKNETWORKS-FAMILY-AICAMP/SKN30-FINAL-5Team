import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { act, render, waitFor } from '@testing-library/react-native';

import { SceneEditor } from '../src/features/sceneEditor/SceneEditor.web';
import { SCENE_EDITOR_STORAGE_KEY } from '../src/features/sceneEditor/sceneEditorModel';

jest.mock('../src/features/sceneEditor/sceneAssets', () => ({
  SCENE_EDITOR_ASSETS: [
    {
      name: 'flower_pink_01',
      source: 'flowers/flower_pink_01.png',
      category: 'flower',
      uri: 'flower-uri',
      width: 48,
      height: 72,
    },
  ],
  SCENE_EDITOR_BACKGROUND_URI: 'background-uri',
  SCENE_EDITOR_DEFAULT_BACKGROUND: {
    name: 'background_static',
    source: 'background/background_static.png',
    uri: 'background-uri',
    width: 1672,
    height: 941,
  },
  SCENE_EDITOR_REFERENCE_URI: 'reference-uri',
}));

const storage = new Map<string, string>();
const localStorage = {
  getItem: jest.fn((key: string) => storage.get(key) ?? null),
  removeItem: jest.fn((key: string) => storage.delete(key)),
  setItem: jest.fn((key: string, value: string) => storage.set(key, value)),
};

class MockImage {
  naturalHeight = 180;
  naturalWidth = 320;
  onerror: (() => void) | null = null;
  onload: (() => void) | null = null;

  set src(_value: string) {
    this.onload?.();
  }
}

beforeEach(() => {
  storage.clear();
  jest.clearAllMocks();
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      addEventListener: jest.fn(),
      confirm: jest.fn(() => true),
      Image: MockImage,
      localStorage,
      removeEventListener: jest.fn(),
      setTimeout,
    },
  });
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    value: jest.fn(() => 'blob:local-png'),
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    value: jest.fn(),
  });
});

describe('SceneEditor', () => {
  it('starts at 40% scale, adds an asset, and auto-saves scene coordinates', async () => {
    const view = render(<SceneEditor />);

    expect(JSON.stringify(view.toJSON())).toContain(
      'Campsite Scene Asset Editor',
    );
    expect(
      view.UNSAFE_root.findByProps({ 'aria-label': 'Preview scale' }).props
        .value,
    ).toBe(0.4);
    expect(JSON.stringify(view.toJSON())).toContain('Motion Preview ');
    expect(JSON.stringify(view.toJSON())).toContain('OFF');

    await act(() => {
      view.UNSAFE_root.findByProps({
        title: 'Add flowers/flower_pink_01.png',
      }).props.onClick();
    });

    expect(JSON.stringify(view.toJSON())).toContain('flower_pink_01_001');
    await act(() => {
      view.UNSAFE_root.findByProps({ 'aria-label': 'x' }).props.onChange({
        target: { value: '1200' },
      });
    });

    await waitFor(() => {
      const stored = localStorage.setItem.mock.calls.at(-1)?.[1];
      expect(stored).toBeDefined();
      expect(JSON.parse(stored ?? '{}')).toMatchObject({
        scene: { width: 1672, height: 941 },
        background: { source: 'background/background_static.png' },
        assets: [{ id: 'flower_pink_01_001', x: 1200 }],
      });
    });
    expect(localStorage.setItem).toHaveBeenCalledWith(
      SCENE_EDITOR_STORAGE_KEY,
      expect.any(String),
    );
  });

  it('can use a listed PNG as the scene background', async () => {
    const view = render(<SceneEditor />);

    await act(() => {
      view.UNSAFE_root.findByProps({
        'aria-label': 'Use flowers/flower_pink_01.png as background',
      }).props.onClick();
    });

    expect(JSON.stringify(view.toJSON())).toContain(
      'flowers/flower_pink_01.png',
    );
    await waitFor(() => {
      const stored = localStorage.setItem.mock.calls.at(-1)?.[1];
      expect(JSON.parse(stored ?? '{}')).toMatchObject({
        background: { source: 'flowers/flower_pink_01.png' },
      });
    });
  });

  it('loads PNGs recursively from a selected folder as custom assets', async () => {
    const view = render(<SceneEditor />);
    const png = {
      name: 'sparkle.png',
      type: 'image/png',
      webkitRelativePath: 'theme/decor/sparkle.png',
    } as File;

    await act(async () => {
      await view.UNSAFE_root.findByProps({
        'aria-label': 'Open PNG folder',
      }).props.onChange({
        target: { files: [png], value: 'folder' },
      });
    });

    expect(JSON.stringify(view.toJSON())).toContain('theme/decor');
    await act(() => {
      view.UNSAFE_root.findByProps({
        title: 'Add local/theme/decor/sparkle.png',
      }).props.onClick();
    });
    expect(JSON.stringify(view.toJSON())).toContain('custom');
  });
});
