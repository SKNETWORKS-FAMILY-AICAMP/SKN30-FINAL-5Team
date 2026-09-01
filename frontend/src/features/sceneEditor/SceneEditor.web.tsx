import {
  type ChangeEvent,
  type CSSProperties,
  type InputHTMLAttributes,
  type PointerEvent as ReactPointerEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  SCENE_EDITOR_ASSETS,
  SCENE_EDITOR_DEFAULT_BACKGROUND,
  SCENE_EDITOR_REFERENCE_URI,
} from './sceneAssets';
import {
  createPlacedAsset,
  DEFAULT_PREVIEW_SCALE,
  duplicatePlacedAsset,
  exportSceneLayout,
  parseSceneBackground,
  parseSceneLayout,
  SCENE_EDITOR_STORAGE_KEY,
  SCENE_HEIGHT,
  SCENE_WIDTH,
  type AssetCategory,
  type PlacedSceneAsset,
  type SceneAssetDefinition,
  type SceneBackgroundDefinition,
} from './sceneEditorModel';

const CATEGORY_LABELS: Record<AssetCategory, string> = {
  cloud: 'Clouds',
  leaf: 'Leaves',
  bulb: 'Bulbs',
  lantern: 'Lanterns',
  flower: 'Flowers',
  grass: 'Grass',
  custom: 'Custom',
};

const CATEGORY_BY_FOLDER: Record<string, AssetCategory> = {
  bulb: 'bulb',
  bulbs: 'bulb',
  cloud: 'cloud',
  clouds: 'cloud',
  flower: 'flower',
  flowers: 'flower',
  grass: 'grass',
  lantern: 'lantern',
  lanterns: 'lantern',
  leaf: 'leaf',
  leaves: 'leaf',
};

const MOTION_TYPES = [
  'none',
  'cloud',
  'leaf',
  'cable',
  'bulb',
  'lantern',
  'glow',
  'flower',
  'grass',
];

const styles: Record<string, CSSProperties> = {
  page: {
    background: '#111827',
    color: '#e5e7eb',
    display: 'flex',
    flexDirection: 'column',
    fontFamily:
      'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    height: '100vh',
    minWidth: 1180,
    overflow: 'hidden',
  },
  toolbar: {
    alignItems: 'center',
    background: '#1f2937',
    borderBottom: '1px solid #374151',
    display: 'flex',
    flexWrap: 'wrap',
    gap: 8,
    padding: '10px 14px',
  },
  title: { fontSize: 16, fontWeight: 800, marginRight: 12 },
  spacer: { flex: 1 },
  button: {
    background: '#374151',
    border: '1px solid #4b5563',
    borderRadius: 5,
    color: '#f9fafb',
    cursor: 'pointer',
    font: 'inherit',
    padding: '7px 10px',
  },
  primaryButton: {
    background: '#2563eb',
    border: '1px solid #3b82f6',
    borderRadius: 5,
    color: '#fff',
    cursor: 'pointer',
    font: 'inherit',
    padding: '7px 10px',
  },
  dangerButton: {
    background: '#7f1d1d',
    border: '1px solid #991b1b',
    borderRadius: 5,
    color: '#fff',
    cursor: 'pointer',
    font: 'inherit',
    padding: '7px 10px',
  },
  body: {
    display: 'grid',
    flex: 1,
    gridTemplateColumns: '270px 1fr 310px',
    minHeight: 0,
  },
  panel: { background: '#18202d', minHeight: 0, overflow: 'auto', padding: 12 },
  leftPanel: { borderRight: '1px solid #374151' },
  rightPanel: { borderLeft: '1px solid #374151' },
  center: {
    alignItems: 'center',
    background: '#0b1120',
    display: 'flex',
    justifyContent: 'center',
    minHeight: 0,
    overflow: 'auto',
    padding: 24,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: 800,
    letterSpacing: 0.6,
    margin: '14px 0 7px',
  },
  search: {
    background: '#0f172a',
    border: '1px solid #475569',
    borderRadius: 5,
    boxSizing: 'border-box',
    color: '#f8fafc',
    font: 'inherit',
    padding: 8,
    width: '100%',
  },
  assetButton: {
    alignItems: 'center',
    background: '#263244',
    border: '1px solid #3f4b5d',
    borderRadius: 5,
    color: '#f8fafc',
    cursor: 'pointer',
    display: 'grid',
    font: 'inherit',
    gap: 8,
    gridTemplateColumns: '42px minmax(0, 1fr)',
    padding: 5,
    textAlign: 'left',
    width: '100%',
  },
  assetRow: {
    display: 'grid',
    gap: 5,
    gridTemplateColumns: 'minmax(0, 1fr) 44px',
    marginBottom: 5,
  },
  backgroundButton: {
    background: '#164e63',
    border: '1px solid #0891b2',
    borderRadius: 5,
    color: '#ecfeff',
    cursor: 'pointer',
    font: 'inherit',
    fontSize: 10,
    padding: 4,
  },
  thumbnail: { height: 36, objectFit: 'contain', width: 42 },
  assetName: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  sceneViewport: {
    background: '#030712',
    border: '1px solid #64748b',
    boxShadow: '0 12px 36px rgba(0,0,0,.45)',
    flex: '0 0 auto',
    overflow: 'hidden',
    position: 'relative',
  },
  sceneScaleWrapper: {
    height: SCENE_HEIGHT,
    position: 'relative',
    transformOrigin: 'top left',
    width: SCENE_WIDTH,
  },
  sceneWorld: {
    height: SCENE_HEIGHT,
    overflow: 'hidden',
    position: 'relative',
    width: SCENE_WIDTH,
  },
  fullSceneImage: {
    height: '100%',
    left: 0,
    objectFit: 'fill',
    position: 'absolute',
    top: 0,
    width: '100%',
  },
  assetPosition: {
    boxSizing: 'border-box',
    cursor: 'move',
    position: 'absolute',
  },
  assetMotion: {
    display: 'block',
    height: '100%',
    pointerEvents: 'none',
    userSelect: 'none',
    width: '100%',
  },
  resizeHandle: {
    background: '#fff',
    border: '2px solid #2563eb',
    bottom: -8,
    cursor: 'nwse-resize',
    height: 14,
    position: 'absolute',
    right: -8,
    width: 14,
  },
  field: {
    display: 'grid',
    gap: 5,
    gridTemplateColumns: '104px 1fr',
    marginBottom: 7,
  },
  fieldLabel: { alignSelf: 'center', color: '#9ca3af', fontSize: 11 },
  input: {
    background: '#0f172a',
    border: '1px solid #475569',
    borderRadius: 4,
    boxSizing: 'border-box',
    color: '#f8fafc',
    font: 'inherit',
    minWidth: 0,
    padding: '5px 6px',
    width: '100%',
  },
  readout: {
    background: '#111827',
    border: '1px solid #374151',
    borderRadius: 4,
    color: '#d1d5db',
    overflow: 'hidden',
    padding: '5px 6px',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  help: { color: '#94a3b8', fontSize: 11, lineHeight: 1.5, marginTop: 12 },
  status: { color: '#bfdbfe', fontSize: 11, marginLeft: 8 },
  checkboxLabel: {
    alignItems: 'center',
    display: 'flex',
    fontSize: 12,
    gap: 5,
  },
};

const animationCss = `
@keyframes editor-cloud { 0%,100% { transform: translateX(calc(var(--amplitude) * -0.5px)); } 50% { transform: translateX(calc(var(--amplitude) * 0.5px)); } }
@keyframes editor-sway { 0%,100% { transform: rotate(calc(var(--amplitude) * -1deg)); } 50% { transform: rotate(calc(var(--amplitude) * 1deg)); } }
@keyframes editor-grass { 0%,100% { transform: rotate(calc(var(--amplitude) * -1deg)) skewX(calc(var(--amplitude) * -0.6deg)); } 50% { transform: rotate(calc(var(--amplitude) * 1deg)) skewX(calc(var(--amplitude) * 0.6deg)); } }
@keyframes editor-glow { 0%,100% { filter: brightness(1); } 50% { filter: brightness(var(--amplitude)); } }
`;

type InitialLayout = {
  assets: PlacedSceneAsset[];
  background: SceneBackgroundDefinition;
  error: string | null;
  pendingRaw: unknown | null;
};

type DirectoryInputProps = InputHTMLAttributes<HTMLInputElement> & {
  directory?: string;
  webkitdirectory?: string;
};

const directoryInputProps: DirectoryInputProps = {
  directory: '',
  webkitdirectory: '',
};

function normalizedFilePath(file: File): string {
  const path =
    (file as File & { webkitRelativePath?: string }).webkitRelativePath ||
    file.name;
  return path.replace(/\\/g, '/').replace(/^\/+/, '');
}

function inferCategory(path: string): AssetCategory {
  for (const segment of path.toLowerCase().split('/')) {
    const category = CATEGORY_BY_FOLDER[segment];
    if (category) return category;
  }
  return 'custom';
}

function fileGroup(path: string): string {
  const directory = path.split('/').slice(0, -1).join('/');
  return directory || 'Selected files';
}

function imageSize(uri: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const image = new window.Image();
    image.onload = () =>
      resolve({ width: image.naturalWidth, height: image.naturalHeight });
    image.onerror = () => reject(new Error(`Could not read PNG: ${uri}`));
    image.src = uri;
  });
}

async function definitionsFromFile(file: File): Promise<{
  asset: SceneAssetDefinition;
  background: SceneBackgroundDefinition;
}> {
  const path = normalizedFilePath(file);
  const uri = URL.createObjectURL(file);
  let size: { width: number; height: number };
  try {
    size = await imageSize(uri);
  } catch (error) {
    URL.revokeObjectURL(uri);
    throw error;
  }
  const name =
    path
      .split('/')
      .at(-1)
      ?.replace(/\.png$/i, '') ?? path;
  const source = `local/${path}`;
  return {
    asset: {
      name,
      source,
      category: inferCategory(path),
      group: fileGroup(path),
      uri,
      ...size,
    },
    background: { name, source, uri, ...size },
  };
}

function mergeBySource<T extends { source: string }>(
  current: readonly T[],
  additions: readonly T[],
): T[] {
  const merged = new Map(current.map((item) => [item.source, item]));
  additions.forEach((item) => merged.set(item.source, item));
  return [...merged.values()];
}

function backgroundFromAsset(
  asset: SceneAssetDefinition,
): SceneBackgroundDefinition {
  const { name, source, uri, width, height } = asset;
  return { name, source, uri, width, height };
}

function readStoredLayout(): InitialLayout {
  try {
    const stored = window.localStorage.getItem(SCENE_EDITOR_STORAGE_KEY);
    if (!stored) {
      return {
        assets: [],
        background: SCENE_EDITOR_DEFAULT_BACKGROUND,
        error: null,
        pendingRaw: null,
      };
    }
    const raw = JSON.parse(stored) as unknown;
    return {
      assets: parseSceneLayout(raw, SCENE_EDITOR_ASSETS),
      background: parseSceneBackground(
        raw,
        [SCENE_EDITOR_DEFAULT_BACKGROUND],
        SCENE_EDITOR_DEFAULT_BACKGROUND,
      ),
      error: null,
      pendingRaw: null,
    };
  } catch (error) {
    let pendingRaw: unknown = null;
    try {
      const stored = window.localStorage.getItem(SCENE_EDITOR_STORAGE_KEY);
      pendingRaw = stored ? (JSON.parse(stored) as unknown) : null;
    } catch {
      // The original error below is more useful than a second parse error.
    }
    return {
      assets: [],
      background: SCENE_EDITOR_DEFAULT_BACKGROUND,
      error: `Stored layout was not loaded: ${error instanceof Error ? error.message : 'unknown error'}`,
      pendingRaw,
    };
  }
}

function animationName(motionType: string): string {
  if (motionType === 'cloud') return 'editor-cloud';
  if (motionType === 'grass') return 'editor-grass';
  if (motionType === 'glow') return 'editor-glow';
  if (motionType === 'none') return 'none';
  return 'editor-sway';
}

function isFormControl(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLSelectElement ||
    target instanceof HTMLTextAreaElement
  );
}

export function SceneEditor() {
  const [initialLayout] = useState(readStoredLayout);
  const [assets, setAssets] = useState(initialLayout.assets);
  const [background, setBackground] = useState(initialLayout.background);
  const [localAssets, setLocalAssets] = useState<SceneAssetDefinition[]>([]);
  const [localBackgrounds, setLocalBackgrounds] = useState<
    SceneBackgroundDefinition[]
  >([]);
  const [pendingStoredLayout, setPendingStoredLayout] = useState(
    initialLayout.pendingRaw,
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previewScale, setPreviewScale] = useState(DEFAULT_PREVIEW_SCALE);
  const [referenceVisible, setReferenceVisible] = useState(true);
  const [referenceOpacity, setReferenceOpacity] = useState(0.4);
  const [referenceAbove, setReferenceAbove] = useState(true);
  const [motionPreview, setMotionPreview] = useState(false);
  const [filter, setFilter] = useState('');
  const [status, setStatus] = useState(initialLayout.error);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const backgroundInputRef = useRef<HTMLInputElement>(null);
  const localObjectUrls = useRef(new Set<string>());
  const skipNextAutoSave = useRef(initialLayout.error !== null);

  const selected = assets.find(({ id }) => id === selectedId) ?? null;
  const availableAssets = useMemo(
    () => mergeBySource(SCENE_EDITOR_ASSETS, localAssets),
    [localAssets],
  );
  const availableBackgrounds = useMemo(
    () =>
      mergeBySource(
        [SCENE_EDITOR_DEFAULT_BACKGROUND, ...localBackgrounds],
        availableAssets.map(backgroundFromAsset),
      ),
    [availableAssets, localBackgrounds],
  );
  const groupedAssets = useMemo(() => {
    const normalizedFilter = filter.trim().toLowerCase();
    const groups = new Map<string, SceneAssetDefinition[]>();
    availableAssets.forEach((asset) => {
      if (
        normalizedFilter &&
        !`${asset.name} ${asset.source}`
          .toLowerCase()
          .includes(normalizedFilter)
      ) {
        return;
      }
      const group =
        asset.group ?? `Bundled / ${CATEGORY_LABELS[asset.category]}`;
      groups.set(group, [...(groups.get(group) ?? []), asset]);
    });
    return [...groups].map(([label, groupAssets]) => ({
      label,
      assets: groupAssets,
    }));
  }, [availableAssets, filter]);

  useEffect(() => {
    if (skipNextAutoSave.current) {
      skipNextAutoSave.current = false;
      return;
    }
    try {
      window.localStorage.setItem(
        SCENE_EDITOR_STORAGE_KEY,
        JSON.stringify(exportSceneLayout(assets, background.source)),
      );
    } catch (error) {
      const message = `Auto-save failed: ${error instanceof Error ? error.message : 'unknown error'}`;
      window.setTimeout(() => setStatus(message), 0);
    }
  }, [assets, background.source]);

  useEffect(
    () => () => {
      localObjectUrls.current.forEach((uri) => URL.revokeObjectURL(uri));
    },
    [],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!selectedId || isFormControl(event.target)) return;
      const distance = event.shiftKey ? 10 : 1;
      const movement: Partial<PlacedSceneAsset> = {};
      if (event.key === 'ArrowLeft') movement.x = (selected?.x ?? 0) - distance;
      if (event.key === 'ArrowRight')
        movement.x = (selected?.x ?? 0) + distance;
      if (event.key === 'ArrowUp') movement.y = (selected?.y ?? 0) - distance;
      if (event.key === 'ArrowDown') movement.y = (selected?.y ?? 0) + distance;

      if (Object.keys(movement).length > 0) {
        event.preventDefault();
        setAssets((current) =>
          current.map((asset) =>
            asset.id === selectedId ? { ...asset, ...movement } : asset,
          ),
        );
      } else if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault();
        setAssets((current) => current.filter(({ id }) => id !== selectedId));
        setSelectedId(null);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selected, selectedId]);

  const updateAsset = (id: string, patch: Partial<PlacedSceneAsset>) => {
    setAssets((current) =>
      current.map((asset) =>
        asset.id === id ? { ...asset, ...patch } : asset,
      ),
    );
  };

  const registerPngFiles = async (
    files: readonly File[],
    options: { addToLibrary: boolean; selectFirstAsBackground: boolean },
  ) => {
    const pngFiles = files.filter(
      (file) =>
        file.type === 'image/png' || file.name.toLowerCase().endsWith('.png'),
    );
    if (pngFiles.length === 0) {
      setStatus('No PNG files were found in the selected folder.');
      return;
    }
    try {
      const loaded = await Promise.all(pngFiles.map(definitionsFromFile));
      loaded.forEach(({ asset }) => localObjectUrls.current.add(asset.uri));
      const loadedAssets = loaded.map(({ asset }) => asset);
      const loadedBackgrounds = loaded.map(({ background: item }) => item);
      const nextLocalAssets = options.addToLibrary
        ? mergeBySource(localAssets, loadedAssets)
        : localAssets;
      const nextLocalBackgrounds = mergeBySource(
        localBackgrounds,
        loadedBackgrounds,
      );
      if (options.addToLibrary) setLocalAssets(nextLocalAssets);
      setLocalBackgrounds(nextLocalBackgrounds);

      const nextAvailableAssets = mergeBySource(
        SCENE_EDITOR_ASSETS,
        nextLocalAssets,
      );
      const nextAvailableBackgrounds = mergeBySource(
        [SCENE_EDITOR_DEFAULT_BACKGROUND, ...nextLocalBackgrounds],
        nextAvailableAssets.map(backgroundFromAsset),
      );
      const definitionBySource = new Map(
        nextAvailableAssets.map((definition) => [
          definition.source,
          definition,
        ]),
      );
      setAssets((current) =>
        current.map((asset) => {
          const definition = definitionBySource.get(asset.source);
          return definition ? { ...asset, uri: definition.uri } : asset;
        }),
      );
      const refreshedBackground = nextAvailableBackgrounds.find(
        (candidate) => candidate.source === background.source,
      );
      if (refreshedBackground) setBackground(refreshedBackground);

      if (options.selectFirstAsBackground) {
        setBackground(loadedBackgrounds[0]!);
      }

      if (pendingStoredLayout) {
        try {
          const restoredAssets = parseSceneLayout(
            pendingStoredLayout,
            nextAvailableAssets,
          );
          const restoredBackground = parseSceneBackground(
            pendingStoredLayout,
            nextAvailableBackgrounds,
            SCENE_EDITOR_DEFAULT_BACKGROUND,
          );
          setAssets(restoredAssets);
          setBackground(restoredBackground);
          setPendingStoredLayout(null);
          setStatus(
            `Loaded ${pngFiles.length} PNG(s) and restored the saved layout.`,
          );
          return;
        } catch {
          // More than one local folder may be needed before restoration works.
        }
      }

      setStatus(
        `Loaded ${pngFiles.length} PNG(s)${options.selectFirstAsBackground ? ' and selected the background' : ''}.`,
      );
    } catch (error) {
      setStatus(
        `PNG folder load failed: ${error instanceof Error ? error.message : 'unknown error'}`,
      );
    }
  };

  const loadAssetFolder = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = [...(event.target.files ?? [])];
    event.target.value = '';
    await registerPngFiles(files, {
      addToLibrary: true,
      selectFirstAsBackground: false,
    });
  };

  const chooseBackgroundFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    await registerPngFiles([file], {
      addToLibrary: false,
      selectFirstAsBackground: true,
    });
  };

  const addAsset = (definition: SceneAssetDefinition) => {
    setAssets((current) => {
      const added = createPlacedAsset(definition, current);
      setSelectedId(added.id);
      return [...current, added];
    });
  };

  const duplicateSelected = () => {
    if (!selected) return;
    setAssets((current) => {
      const duplicate = duplicatePlacedAsset(selected, current);
      setSelectedId(duplicate.id);
      return [...current, duplicate];
    });
  };

  const deleteSelected = () => {
    if (!selectedId) return;
    setAssets((current) => current.filter(({ id }) => id !== selectedId));
    setSelectedId(null);
  };

  const beginPointerEdit = (
    event: ReactPointerEvent<HTMLDivElement>,
    asset: PlacedSceneAsset,
    mode: 'move' | 'resize',
  ) => {
    event.preventDefault();
    event.stopPropagation();
    setSelectedId(asset.id);
    const startClientX = event.clientX;
    const startClientY = event.clientY;
    const ratio = asset.width / asset.height;

    const onPointerMove = (moveEvent: PointerEvent) => {
      const deltaX = (moveEvent.clientX - startClientX) / previewScale;
      const deltaY = (moveEvent.clientY - startClientY) / previewScale;
      if (mode === 'move') {
        updateAsset(asset.id, {
          x: Math.round(asset.x + deltaX),
          y: Math.round(asset.y + deltaY),
        });
        return;
      }

      if (moveEvent.shiftKey) {
        updateAsset(asset.id, {
          width: Math.max(1, Math.round(asset.width + deltaX)),
          height: Math.max(1, Math.round(asset.height + deltaY)),
        });
        return;
      }

      const widthFromX = Math.max(1, asset.width + deltaX);
      const heightFromY = Math.max(1, asset.height + deltaY);
      const useHeight = Math.abs(deltaY * ratio) > Math.abs(deltaX);
      const nextWidth = useHeight ? heightFromY * ratio : widthFromX;
      updateAsset(asset.id, {
        width: Math.max(1, Math.round(nextWidth)),
        height: Math.max(1, Math.round(nextWidth / ratio)),
      });
    };
    const onPointerUp = () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
    };
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  };

  const exportLayout = () => {
    const json = JSON.stringify(
      exportSceneLayout(assets, background.source),
      null,
      2,
    );
    const url = URL.createObjectURL(
      new Blob([json], { type: 'application/json;charset=utf-8' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = 'scene-layout.json';
    link.click();
    URL.revokeObjectURL(url);
    setStatus(`Exported ${assets.length} asset instance(s).`);
  };

  const importLayout = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (
      (window.localStorage.getItem(SCENE_EDITOR_STORAGE_KEY) ||
        assets.length > 0) &&
      !window.confirm('기존 저장 배치를 불러온 JSON으로 덮어쓸까요?')
    ) {
      return;
    }
    try {
      const raw = JSON.parse(await file.text()) as unknown;
      const imported = parseSceneLayout(raw, availableAssets);
      const importedBackground = parseSceneBackground(
        raw,
        availableBackgrounds,
        SCENE_EDITOR_DEFAULT_BACKGROUND,
      );
      setAssets(imported);
      setBackground(importedBackground);
      setSelectedId(null);
      setStatus(
        `Imported ${imported.length} asset instance(s) from ${file.name}.`,
      );
    } catch (error) {
      setStatus(
        `Import failed: ${error instanceof Error ? error.message : 'invalid JSON'}`,
      );
    }
  };

  const resetLayout = () => {
    if (!window.confirm('모든 배치와 로컬 저장 데이터를 초기화할까요?')) return;
    window.localStorage.removeItem(SCENE_EDITOR_STORAGE_KEY);
    setAssets([]);
    setBackground(SCENE_EDITOR_DEFAULT_BACKGROUND);
    setPendingStoredLayout(null);
    setSelectedId(null);
    setStatus('Layout reset.');
  };

  const updateNumber = (field: keyof PlacedSceneAsset, value: string) => {
    if (!selected || value.trim() === '') return;
    let number = Number(value);
    if (!Number.isFinite(number)) return;
    if (field === 'width' || field === 'height' || field === 'duration') {
      number = Math.max(0.01, number);
    }
    if (field === 'anchorX' || field === 'anchorY') {
      number = Math.min(1, Math.max(0, number));
    }
    updateAsset(selected.id, { [field]: number });
  };

  const renderNumberField = (
    label: string,
    field: keyof PlacedSceneAsset,
    value: number,
    step = 1,
  ) => (
    <label style={styles.field}>
      <span style={styles.fieldLabel}>{label}</span>
      <input
        aria-label={label}
        onChange={(event) => updateNumber(field, event.target.value)}
        step={step}
        style={styles.input}
        type="number"
        value={value}
      />
    </label>
  );

  return (
    <main style={styles.page}>
      <style>{animationCss}</style>
      <header style={styles.toolbar}>
        <span style={styles.title}>Campsite Scene Asset Editor</span>
        <button
          onClick={exportLayout}
          style={styles.primaryButton}
          type="button"
        >
          Export scene-layout.json
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          style={styles.button}
          type="button"
        >
          Import Layout
        </button>
        <input
          accept="application/json,.json"
          aria-label="Import scene-layout.json"
          hidden
          onChange={(event) => void importLayout(event)}
          ref={fileInputRef}
          type="file"
        />
        <button
          onClick={() => folderInputRef.current?.click()}
          style={styles.button}
          type="button"
        >
          Open PNG Folder
        </button>
        <input
          {...directoryInputProps}
          accept="image/png,.png"
          aria-label="Open PNG folder"
          hidden
          multiple
          onChange={(event) => void loadAssetFolder(event)}
          ref={folderInputRef}
          type="file"
        />
        <button
          onClick={() => backgroundInputRef.current?.click()}
          style={styles.button}
          type="button"
        >
          Choose Background PNG
        </button>
        <input
          accept="image/png,.png"
          aria-label="Choose background PNG"
          hidden
          onChange={(event) => void chooseBackgroundFile(event)}
          ref={backgroundInputRef}
          type="file"
        />
        <button onClick={resetLayout} style={styles.dangerButton} type="button">
          Reset
        </button>
        <span style={styles.spacer} />
        <label style={styles.checkboxLabel}>
          Scale
          <select
            aria-label="Preview scale"
            onChange={(event) => setPreviewScale(Number(event.target.value))}
            style={styles.input}
            value={previewScale}
          >
            <option value={0.25}>25%</option>
            <option value={0.4}>40%</option>
            <option value={0.5}>50%</option>
            <option value={0.75}>75%</option>
          </select>
        </label>
        <label style={styles.checkboxLabel}>
          <input
            checked={motionPreview}
            onChange={(event) => setMotionPreview(event.target.checked)}
            type="checkbox"
          />
          Motion Preview {motionPreview ? 'ON' : 'OFF'}
        </label>
        {status ? <span style={styles.status}>{status}</span> : null}
      </header>

      <div style={styles.body}>
        <aside style={{ ...styles.panel, ...styles.leftPanel }}>
          <input
            aria-label="Filter assets"
            onChange={(event) => setFilter(event.target.value)}
            placeholder={`Filter ${availableAssets.length} assets`}
            style={styles.search}
            value={filter}
          />
          {groupedAssets.map((group) => (
            <section key={group.label}>
              <h2 style={styles.sectionTitle}>
                {group.label} ({group.assets.length})
              </h2>
              {group.assets.map((asset) => (
                <div key={asset.source} style={styles.assetRow}>
                  <button
                    onClick={() => addAsset(asset)}
                    style={styles.assetButton}
                    title={`Add ${asset.source}`}
                    type="button"
                  >
                    <img alt="" src={asset.uri} style={styles.thumbnail} />
                    <span style={styles.assetName}>{asset.name}</span>
                  </button>
                  <button
                    aria-label={`Use ${asset.source} as background`}
                    onClick={() => {
                      const candidate = availableBackgrounds.find(
                        ({ source }) => source === asset.source,
                      );
                      if (candidate) {
                        setBackground(candidate);
                        setStatus(`Background: ${candidate.source}`);
                      }
                    }}
                    style={styles.backgroundButton}
                    title={`Use ${asset.source} as background`}
                    type="button"
                  >
                    BG
                  </button>
                </div>
              ))}
            </section>
          ))}
        </aside>

        <section style={styles.center}>
          <div
            aria-label={`${SCENE_WIDTH} by ${SCENE_HEIGHT} scene viewport`}
            onPointerDown={() => setSelectedId(null)}
            style={{
              ...styles.sceneViewport,
              height: SCENE_HEIGHT * previewScale,
              width: SCENE_WIDTH * previewScale,
            }}
          >
            <div
              className="SceneScaleWrapper"
              style={{
                ...styles.sceneScaleWrapper,
                transform: `scale(${previewScale})`,
              }}
            >
              <div className="SceneWorld" style={styles.sceneWorld}>
                <img
                  alt=""
                  draggable={false}
                  src={background.uri}
                  style={{ ...styles.fullSceneImage, zIndex: 0 }}
                />
                {referenceVisible && !referenceAbove ? (
                  <img
                    alt="Reference overlay"
                    draggable={false}
                    src={SCENE_EDITOR_REFERENCE_URI}
                    style={{
                      ...styles.fullSceneImage,
                      opacity: referenceOpacity,
                      pointerEvents: 'none',
                      zIndex: 1,
                    }}
                  />
                ) : null}
                {assets.map((asset) => {
                  const isSelected = selectedId === asset.id;
                  const motionStyle = {
                    ...styles.assetMotion,
                    '--amplitude': asset.amplitude,
                    animationDelay: `${asset.delay}s`,
                    animationDuration: `${asset.duration}s`,
                    animationIterationCount: 'infinite',
                    animationName: motionPreview
                      ? animationName(asset.motionType)
                      : 'none',
                    animationTimingFunction: 'ease-in-out',
                    transformOrigin: `${asset.anchorX * 100}% ${asset.anchorY * 100}%`,
                  } as CSSProperties;
                  return (
                    <div
                      aria-label={asset.id}
                      key={asset.id}
                      onPointerDown={(event) =>
                        beginPointerEdit(event, asset, 'move')
                      }
                      style={{
                        ...styles.assetPosition,
                        border: isSelected ? '2px solid #2563eb' : undefined,
                        height: asset.height,
                        left: asset.x,
                        top: asset.y,
                        width: asset.width,
                        zIndex: asset.zIndex,
                      }}
                      title={asset.id}
                    >
                      <img
                        alt=""
                        draggable={false}
                        src={asset.uri}
                        style={motionStyle}
                      />
                      {isSelected ? (
                        <div
                          aria-label={`Resize ${asset.id}`}
                          onPointerDown={(event) =>
                            beginPointerEdit(event, asset, 'resize')
                          }
                          style={styles.resizeHandle}
                        />
                      ) : null}
                    </div>
                  );
                })}
                {referenceVisible && referenceAbove ? (
                  <img
                    alt="Reference overlay"
                    draggable={false}
                    src={SCENE_EDITOR_REFERENCE_URI}
                    style={{
                      ...styles.fullSceneImage,
                      opacity: referenceOpacity,
                      pointerEvents: 'none',
                      zIndex: 10000,
                    }}
                  />
                ) : null}
              </div>
            </div>
          </div>
        </section>

        <aside style={{ ...styles.panel, ...styles.rightPanel }}>
          <h2 style={{ ...styles.sectionTitle, marginTop: 0 }}>Background</h2>
          <div style={styles.field}>
            <span style={styles.fieldLabel}>source</span>
            <code style={styles.readout} title={background.source}>
              {background.source}
            </code>
          </div>
          <button
            onClick={() => setBackground(SCENE_EDITOR_DEFAULT_BACKGROUND)}
            style={styles.button}
            type="button"
          >
            Use bundled background
          </button>
          <p style={styles.help}>
            Open a folder, then click BG beside any PNG, or choose one PNG
            directly. Backgrounds are stretched to {SCENE_WIDTH} ×{' '}
            {SCENE_HEIGHT}.
          </p>

          <h2 style={styles.sectionTitle}>Reference</h2>
          <label style={styles.checkboxLabel}>
            <input
              checked={referenceVisible}
              onChange={(event) => setReferenceVisible(event.target.checked)}
              type="checkbox"
            />
            Show reference
          </label>
          <label style={{ ...styles.field, marginTop: 8 }}>
            <span style={styles.fieldLabel}>opacity</span>
            <input
              aria-label="Reference opacity"
              max={1}
              min={0}
              onChange={(event) =>
                setReferenceOpacity(Number(event.target.value))
              }
              step={0.01}
              type="range"
              value={referenceOpacity}
            />
          </label>
          <label style={styles.checkboxLabel}>
            <input
              checked={referenceAbove}
              onChange={(event) => setReferenceAbove(event.target.checked)}
              type="checkbox"
            />
            Reference above assets
          </label>

          <h2 style={styles.sectionTitle}>Inspector</h2>
          {selected ? (
            <>
              <div style={styles.field}>
                <span style={styles.fieldLabel}>id</span>
                <code style={styles.readout}>{selected.id}</code>
              </div>
              <div style={styles.field}>
                <span style={styles.fieldLabel}>src</span>
                <code style={styles.readout} title={selected.source}>
                  {selected.source}
                </code>
              </div>
              <div style={styles.field}>
                <span style={styles.fieldLabel}>category</span>
                <code style={styles.readout}>{selected.category}</code>
              </div>
              {renderNumberField('x', 'x', selected.x)}
              {renderNumberField('y', 'y', selected.y)}
              {renderNumberField('width', 'width', selected.width)}
              {renderNumberField('height', 'height', selected.height)}
              <div style={styles.field}>
                <span style={styles.fieldLabel}>normalizedX</span>
                <code style={styles.readout}>
                  {(selected.x / SCENE_WIDTH).toFixed(4)}
                </code>
              </div>
              <div style={styles.field}>
                <span style={styles.fieldLabel}>normalizedY</span>
                <code style={styles.readout}>
                  {(selected.y / SCENE_HEIGHT).toFixed(4)}
                </code>
              </div>
              <div style={styles.field}>
                <span style={styles.fieldLabel}>normalizedWidth</span>
                <code style={styles.readout}>
                  {(selected.width / SCENE_WIDTH).toFixed(4)}
                </code>
              </div>
              <div style={styles.field}>
                <span style={styles.fieldLabel}>normalizedHeight</span>
                <code style={styles.readout}>
                  {(selected.height / SCENE_HEIGHT).toFixed(4)}
                </code>
              </div>
              {renderNumberField('anchorX', 'anchorX', selected.anchorX, 0.01)}
              {renderNumberField('anchorY', 'anchorY', selected.anchorY, 0.01)}
              {renderNumberField('zIndex', 'zIndex', selected.zIndex)}
              <label style={styles.field}>
                <span style={styles.fieldLabel}>motionType</span>
                <select
                  aria-label="motionType"
                  onChange={(event) =>
                    updateAsset(selected.id, { motionType: event.target.value })
                  }
                  style={styles.input}
                  value={selected.motionType}
                >
                  {MOTION_TYPES.map((motionType) => (
                    <option key={motionType} value={motionType}>
                      {motionType}
                    </option>
                  ))}
                </select>
              </label>
              {renderNumberField(
                'duration',
                'duration',
                selected.duration,
                0.1,
              )}
              {renderNumberField('delay', 'delay', selected.delay, 0.1)}
              {renderNumberField(
                'amplitude',
                'amplitude',
                selected.amplitude,
                0.1,
              )}
              <div style={{ display: 'flex', gap: 7, marginTop: 12 }}>
                <button
                  onClick={duplicateSelected}
                  style={styles.button}
                  type="button"
                >
                  Duplicate
                </button>
                <button
                  onClick={deleteSelected}
                  style={styles.dangerButton}
                  type="button"
                >
                  Delete
                </button>
              </div>
            </>
          ) : (
            <p style={styles.help}>Scene에서 asset을 선택하세요.</p>
          )}
          <p style={styles.help}>
            Drag: move · Handle: proportional resize · Shift+resize: free resize
            <br />
            Arrow: 1 scene px · Shift+Arrow: 10 scene px · Delete: remove
            <br />
            Scene coordinates stay {SCENE_WIDTH} × {SCENE_HEIGHT} at every
            preview scale.
          </p>
        </aside>
      </div>
    </main>
  );
}
