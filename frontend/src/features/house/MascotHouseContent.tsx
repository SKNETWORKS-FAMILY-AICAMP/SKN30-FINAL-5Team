/**
 * 끼끼의 집 — the scene itself.
 *
 * The backdrop is full-bleed: it fills the whole screen, runs under the status
 * bar and behind the tab bar, and is never boxed into a card. Everything else
 * floats on top of it — the top bar, the side chips, the mascot, the feed
 * button, the mini-game panel. A soft fade at the bottom carries the illustration
 * into the canvas colour so the artwork is not cut off by a hard edge.
 *
 * The artwork is a top-aligned, half-scale version of its former cover size.
 * Its horizontal centre stays fixed while the continuation gradient carries a
 * short illustration into the canvas. Controls remain in a centred phone-width
 * column rather than stretching with a desktop viewport.
 *
 * Presentation only. Every value arrives as a built `HouseView`, and every
 * press is handed straight back out, so the rules stay in `houseModel` and
 * this file can be re-skinned as the artwork lands.
 *
 * Tone rules that constrain what may be written here: a shortfall is never
 * framed as a loss, the mascot has no disappointed state, and nothing on this
 * screen pushes the user to train today.
 */

import { Asset } from 'expo-asset';
import { LinearGradient } from 'expo-linear-gradient';
import { Children, type ReactNode } from 'react';
import { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type GestureResponderEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Svg, {
  Defs,
  FeGaussianBlur,
  Filter,
  Image as SvgImage,
  LinearGradient as SvgLinearGradient,
  Mask,
  Rect,
  Stop,
} from 'react-native-svg';

import { imageAssets } from '../../assets';
import {
  BASE_H,
  getContainedInterfaceScale,
  useScale,
} from '../../components/scale';
import { colors, radii, shadows, spacing } from '../../components/theme';
import {
  BananaGlyph,
  BulbGlyph,
  ChevronGlyph,
  ClipboardGlyph,
  FlameGlyph,
  HeartGlyph,
  HouseArtView,
  HouseMarkGlyph,
  InfoGlyph,
  PlusGlyph,
  StarGlyph,
} from './HouseArt';
import {
  HOUSE_BACKDROP_FALLBACK,
  houseBackgroundArt,
  houseBackgroundLabels,
  houseBackgroundThumbnailArt,
  houseItemArt,
  housePoseArt,
  type HouseArtSlot,
} from './houseArtSlots';
import {
  HOUSE_ACTION_COST,
  HOUSE_BACKGROUND_IDS,
  HOUSE_DAILY_QUESTS,
  HOUSE_GAME_DAILY_PLAYS,
  INTIMACY_DAILY_EARN_LIMIT,
  INTIMACY_MAX_LEVEL,
  houseSpeech,
  type HouseBackgroundId,
  type HouseQuest,
  type HouseItemId,
  type HouseItemPlacement,
  type HousePose,
  type HouseView,
} from './houseModel';
/** Matches the Large phone preview's inset without fixing the layout to its pixels. */
const HOUSE_HORIZONTAL_INSET = '4%' as const;

/**
 * The requested scene zoom relative to the former full-screen `cover` size.
 * At 0.5 the objects in the illustration are half as large and roughly twice
 * as much of the source image is visible on the narrow reference viewport.
 */
export const HOUSE_BACKDROP_ZOOM = 0.5;

/** The selected mascot is displayed at 75% of the former 148px frame. */
export const HOUSE_MASCOT_SIZE = 148 * 0.75;

/** Grows the mascot gently on tall screens without letting it dominate. */
const HOUSE_MASCOT_TALL_SCREEN_GROWTH_RATIO = 0.04;
const HOUSE_MASCOT_MAX_SIZE = 126;

export function houseMascotSize(viewportHeight: number): number {
  const extraHeight = Math.max(0, viewportHeight - BASE_H);
  return Math.min(
    HOUSE_MASCOT_MAX_SIZE,
    HOUSE_MASCOT_SIZE + extraHeight * HOUSE_MASCOT_TALL_SCREEN_GROWTH_RATIO,
  );
}

/**
 * Tall screens enlarge the room toward the bottom controls faster than the
 * former 45% mascot anchor moves. Let the mascot follow a small part of that
 * extra height so it does not appear to climb up through the illustration.
 */
const HOUSE_MASCOT_TALL_SCREEN_FOLLOW_RATIO = 0.1;
const HOUSE_MASCOT_TALL_SCREEN_MAX_OFFSET = 50;

export function houseMascotTallScreenOffset(viewportHeight: number): number {
  const extraHeight = Math.max(0, viewportHeight - BASE_H);
  return Math.min(
    HOUSE_MASCOT_TALL_SCREEN_MAX_OFFSET,
    extraHeight * HOUSE_MASCOT_TALL_SCREEN_FOLLOW_RATIO,
  );
}

/** The anchor the scene was tuned to, as a fraction of the viewport height. */
export const HOUSE_MASCOT_ANCHOR_RATIO = 0.45;

/** Kept clear between the mascot's copy and the first control under it. */
export const HOUSE_MASCOT_CONTROL_CLEARANCE = 12;

/** Reserved for the touch hint until it has been measured. */
export const HOUSE_TOUCH_HINT_RESERVED_HEIGHT = 34;

/**
 * Screen y of the first control, or `null` before the controls are measured.
 *
 * The action area is bottom-anchored inside the column, so its top is the
 * column's bottom less its own height. This is the line the scene may not
 * cross.
 */
export function houseControlsTop(
  columnTop: number | null,
  columnHeight: number | null,
  actionAreaHeight: number | null,
): number | null {
  if (
    columnTop === null ||
    columnHeight === null ||
    actionAreaHeight === null ||
    !Number.isFinite(columnTop) ||
    !Number.isFinite(columnHeight) ||
    !Number.isFinite(actionAreaHeight) ||
    columnHeight <= 0 ||
    actionAreaHeight <= 0
  ) {
    return null;
  }
  return Math.max(0, columnTop + columnHeight - actionAreaHeight);
}

/**
 * Where the top of the mascot slot sits, in screen pixels.
 *
 * The 45% anchor is what the artwork was tuned to and is kept whenever there
 * is room for it. What must never happen is the mascot — or the touch hint
 * under it — sliding behind the controls, so the anchor is clamped to the
 * space actually measured above them.
 *
 * Everything here comes from measured layout rather than a device assumption,
 * so it holds on any aspect ratio and on the web, where the window can be any
 * shape at all. The controls are bottom-anchored and their height changes with
 * the design; the scene is what gives way.
 *
 * `sceneTop` is the floor: on a viewport too short to hold both, the mascot
 * stops under the top chips instead of climbing behind them.
 */
export function houseMascotTop({
  belowMascotHeight,
  controlsTop,
  mascotSize,
  sceneTop,
  viewportHeight,
}: {
  /** The touch hint under the mascot, its gap included. */
  belowMascotHeight: number;
  controlsTop: number | null;
  mascotSize: number;
  sceneTop: number;
  viewportHeight: number;
}): number {
  const floor = Math.max(0, sceneTop);
  const anchored =
    viewportHeight * HOUSE_MASCOT_ANCHOR_RATIO -
    mascotSize / 2 +
    houseMascotTallScreenOffset(viewportHeight);

  if (
    controlsTop === null ||
    !Number.isFinite(controlsTop) ||
    controlsTop <= 0
  ) {
    return Math.max(floor, anchored);
  }

  const highestAllowed =
    controlsTop -
    HOUSE_MASCOT_CONTROL_CLEARANCE -
    Math.max(0, belowMascotHeight) -
    mascotSize;

  return Math.max(floor, Math.min(anchored, highestAllowed));
}

/** Fallback dimensions used only when a platform cannot resolve a local asset. */
const HOUSE_BACKDROP_SOURCE_SIZE = { width: 1600, height: 976 } as const;

/** Source pixels sampled from the artwork's bottom edge for the soft extension. */
const HOUSE_BACKDROP_BLEND_BAND_PX = 160;

/** Display pixels where the blurred extension overlaps the original artwork. */
const HOUSE_BACKDROP_BLEND_OVERLAP = 48;

/** Places the blend boundary halfway across the gap above the bottom panel. */
const HOUSE_BACKDROP_BOTTOM_PANEL_GAP_OFFSET = spacing.sm / 2;

/** The bottom panel keeps this outer gap between its bottom and the column. */
const HOUSE_BOTTOM_PANEL_BOTTOM_MARGIN = spacing.xs;

/** Vertical geometry shared by the flex column and its boundary calculation. */
const HOUSE_COLUMN_TOP_PADDING = spacing.sm;
const HOUSE_COLUMN_GAP = spacing.sm;
const HOUSE_STAGE_MIN_HEIGHT = 210;

const PLACED_ITEM_SIZE = 44;
const DECORATE_GRID_GAP = spacing.sm;

export const HOUSE_MINI_GAMES = [
  {
    id: 'banana_catch',
    title: '바나나 받기',
    /** Shown under the title on the tile, in place of the old description. */
    limitLabel: '하루 1회 플레이 가능',
    imageSource: imageAssets.houseMascotCollectingBananasEmpty,
  },
] as const;

export type HouseMiniGameId = (typeof HOUSE_MINI_GAMES)[number]['id'];

/**
 * The bottom panel's inner height.
 *
 * `houseBottomPanelTop` is derived from this panel's own measured height, and
 * that boundary sets both the backdrop's minimum scale and where its blurred
 * continuation starts. The value below reproduces what the panel measured when
 * it held the `끼끼와 놀기` header above one 122px card
 * (16 + 20 + 8 + 122 + 16 = 182), so the room behind the mascot is unchanged.
 * Do not let it drift: anything that needs more room goes above the panel, not
 * inside it.
 */
const HOUSE_PANEL_CONTENT_HEIGHT = 150;

export const HOUSE_ACTION_EFFECT_MS = 900;

type HouseActionEffect = {
  id: number;
  amount: number;
  mascotEffect?: 'banana' | 'sparkle';
};

function houseControlStyles(controlScale: number) {
  const scaled = (value: number) => value * controlScale;
  return {
    column: {
      gap: scaled(HOUSE_COLUMN_GAP),
      paddingTop: scaled(HOUSE_COLUMN_TOP_PADDING),
    },
    stage: { minHeight: scaled(HOUSE_STAGE_MIN_HEIGHT) },
    rail: { gap: scaled(spacing.sm) },
    chip: {
      minWidth: scaled(84),
      gap: scaled(3),
      borderRadius: scaled(14),
      paddingHorizontal: scaled(10),
      paddingVertical: scaled(9),
    },
    chipValue: { fontSize: scaled(13) },
    streakChip: {
      gap: scaled(5),
      paddingHorizontal: scaled(10),
      paddingVertical: scaled(5),
    },
    streakLabel: { fontSize: scaled(11) },
    bubble: {
      maxWidth: scaled(250),
      borderRadius: scaled(18),
      paddingHorizontal: scaled(16),
      paddingVertical: scaled(11),
    },
    bubbleText: {
      fontSize: scaled(13.5),
      lineHeight: scaled(20),
    },
    primaryActionRow: { gap: scaled(spacing.sm) },
    primaryActionButton: {
      minHeight: 44,
      gap: scaled(spacing.sm),
      paddingVertical: scaled(15),
    },
    primaryActionLabel: { fontSize: scaled(14) },
    actionArea: { gap: scaled(spacing.sm) },
    actionStack: { gap: scaled(spacing.sm) },
    panel: {
      gap: scaled(spacing.sm),
      borderRadius: scaled(20),
      padding: scaled(spacing.lg),
      marginBottom: scaled(spacing.xs),
    },
    tileRow: {
      height: scaled(HOUSE_PANEL_CONTENT_HEIGHT),
      gap: scaled(spacing.sm),
    },
    tile: {
      gap: scaled(spacing.xs),
      borderRadius: scaled(radii.card),
      padding: scaled(spacing.md),
    },
    tileIcon: {
      width: scaled(52),
      height: scaled(52),
      borderRadius: scaled(16),
    },
    tileMascot: { width: scaled(46), height: scaled(46) },
    tileTitle: { fontSize: scaled(15) },
    tileCaption: { fontSize: scaled(11), lineHeight: scaled(15) },
    tileBadge: {
      paddingHorizontal: scaled(8),
      paddingVertical: scaled(3),
    },
    tileBadgeLabel: { fontSize: scaled(10) },
    tileCountBadge: {
      width: scaled(22),
      height: scaled(22),
      borderRadius: scaled(11),
    },
    tileCountLabel: { fontSize: scaled(12) },
    bonusRow: {
      gap: scaled(spacing.md),
      borderRadius: scaled(16),
      paddingHorizontal: scaled(spacing.md),
      paddingVertical: scaled(10),
    },
    bonusTitle: { fontSize: scaled(13) },
    bonusBody: { fontSize: scaled(11), lineHeight: scaled(15) },
    touchHint: { gap: scaled(2) },
    touchHintTitle: { fontSize: scaled(13) },
    touchHintBody: { fontSize: scaled(11) },
    intimacyChip: {
      gap: scaled(spacing.xs),
      paddingHorizontal: scaled(10),
      paddingVertical: scaled(6),
    },
    intimacyLabel: { fontSize: scaled(13) },
  };
}

/**
 * Returns half of the size the artwork would have occupied with `cover`, then
 * grows it proportionally when the control boundary requires a taller image.
 * `Backdrop` fixes the resulting frame to the top and centres it horizontally,
 * so any remaining horizontal crop is removed equally from the outer edges.
 */
export function houseBackdropSize(
  viewportWidth: number,
  viewportHeight: number,
  sourceWidth: number = HOUSE_BACKDROP_SOURCE_SIZE.width,
  sourceHeight: number = HOUSE_BACKDROP_SOURCE_SIZE.height,
  minimumHeight: number = 0,
): { width: number; height: number } {
  const width = Math.max(0, viewportWidth);
  const height = Math.max(0, viewportHeight);
  const safeSourceWidth = Math.max(1, sourceWidth);
  const safeSourceHeight = Math.max(1, sourceHeight);
  const coverScale = Math.max(
    width / safeSourceWidth,
    height / safeSourceHeight,
  );
  const requestedMinimumHeight = Math.min(Math.max(0, minimumHeight), height);
  const displayScale = Math.max(
    coverScale * HOUSE_BACKDROP_ZOOM,
    requestedMinimumHeight / safeSourceHeight,
  );

  return {
    width: safeSourceWidth * displayScale,
    height: safeSourceHeight * displayScale,
  };
}

function houseBackdropControlBoundary(
  viewportHeight: number,
  bottomPanelTop: number | null,
): number | null {
  if (
    bottomPanelTop === null ||
    !Number.isFinite(bottomPanelTop) ||
    bottomPanelTop <= 0
  ) {
    return null;
  }
  return Math.min(
    Math.max(0, bottomPanelTop - HOUSE_BACKDROP_BOTTOM_PANEL_GAP_OFFSET),
    Math.max(0, viewportHeight),
  );
}

export function houseBackdropMinimumHeight(
  viewportHeight: number,
  bottomPanelTop: number | null,
): number {
  const safeViewportHeight = Math.max(0, viewportHeight);
  const controlBoundary = houseBackdropControlBoundary(
    safeViewportHeight,
    bottomPanelTop,
  );
  if (controlBoundary === null) return 0;
  return Math.min(
    controlBoundary + HOUSE_BACKDROP_BLEND_OVERLAP,
    safeViewportHeight,
  );
}

export function houseBackdropContinuationTop(
  artHeight: number,
  viewportHeight: number,
  bottomPanelTop: number | null,
): number {
  const safeViewportHeight = Math.max(0, viewportHeight);
  const imageEnd = Math.min(Math.max(0, artHeight), safeViewportHeight);
  const imageBlendStart = Math.max(0, imageEnd - HOUSE_BACKDROP_BLEND_OVERLAP);
  const controlBoundary = houseBackdropControlBoundary(
    safeViewportHeight,
    bottomPanelTop,
  );
  if (controlBoundary === null) return imageBlendStart;
  return Math.min(imageBlendStart, controlBoundary);
}

/**
 * Derives the bottom panel's screen-relative top from bottom-anchored sizes.
 *
 * React Native Web does not guarantee a new `onLayout` event when an element
 * only changes position inside a flex parent. The column height does change
 * with the viewport, though, and the play panel is the last item in the
 * bottom action stack. Using their heights therefore keeps the boundary in
 * sync on both native and web without retaining a stale absolute y-coordinate.
 */
export function houseBottomPanelTop(
  columnTop: number | null,
  columnHeight: number | null,
  actionAreaHeight: number | null,
  bottomPanelHeight: number | null,
): number | null {
  if (
    columnTop === null ||
    columnHeight === null ||
    actionAreaHeight === null ||
    bottomPanelHeight === null ||
    !Number.isFinite(columnTop) ||
    !Number.isFinite(columnHeight) ||
    !Number.isFinite(actionAreaHeight) ||
    !Number.isFinite(bottomPanelHeight) ||
    columnHeight <= 0 ||
    actionAreaHeight <= 0 ||
    bottomPanelHeight <= 0
  ) {
    return null;
  }

  const contentBottom =
    columnTop +
    Math.max(
      columnHeight,
      HOUSE_COLUMN_TOP_PADDING +
        HOUSE_STAGE_MIN_HEIGHT +
        HOUSE_COLUMN_GAP +
        actionAreaHeight,
    );

  return Math.max(
    0,
    contentBottom - bottomPanelHeight - HOUSE_BOTTOM_PANEL_BOTTOM_MARGIN,
  );
}

/** @deprecated Use `houseBottomPanelTop`; retained for existing callers. */
export const houseWeekPanelTop = houseBottomPanelTop;

export function MascotHouseContent({
  footer,
  onBuyItem,
  onFeed,
  onPet,
  onPlayGame,
  onPlaceItem,
  onSelectBackground,
  mascotArt,
  pose,
  view,
}: {
  /** The tab bar, rendered inside the backdrop so the scene runs behind it. */
  footer?: ReactNode;
  onBuyItem: (itemId: HouseItemId) => boolean;
  onFeed: () => boolean;
  onPet: () => boolean;
  onPlayGame: (gameId: HouseMiniGameId) => void;
  onPlaceItem: (itemId: HouseItemId, placement: HouseItemPlacement) => void;
  onSelectBackground: (backgroundId: HouseBackgroundId) => void;
  mascotArt?: HouseArtSlot;
  pose: HousePose;
  view: HouseView;
}) {
  const scaleViewport = useScale();
  const [decorating, setDecorating] = useState(false);
  /**
   * 오늘의 퀘스트, opened as an overlay over the same action stack the
   * decorate panel covers. Every affordance that asks "how do I earn more?" —
   * the banana chip's `+`, the intimacy chip, the bonus row, the quest tile —
   * opens it, because the quest list is the one answer to all four. It is a
   * panel and not a screen so the backdrop, the mascot and the tab bar all
   * stay exactly where they are.
   */
  const [questing, setQuesting] = useState(false);
  const openQuests = () => setQuesting(true);
  const overlayOpen = decorating || questing;
  const [measuredViewport, setMeasuredViewport] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [columnLayout, setColumnLayout] = useState<{
    y: number;
    height: number;
  } | null>(null);
  const [actionAreaHeight, setActionAreaHeight] = useState<number | null>(null);
  /** Measured so the mascot's floor sits under the title and the top chips. */
  const [stageTop, setStageTop] = useState<number | null>(null);
  const [topRailHeight, setTopRailHeight] = useState<number | null>(null);
  /** Measured so the hint under the mascot is counted in its clearance. */
  const [touchHintHeight, setTouchHintHeight] = useState<number | null>(null);
  const [bottomPanelHeight, setBottomPanelHeight] = useState<number | null>(
    null,
  );
  const [decorationCanvas, setDecorationCanvas] = useState({
    width: 0,
    height: 0,
  });
  const [actionEffect, setActionEffect] = useState<HouseActionEffect | null>(
    null,
  );
  const actionEffectId = useRef(0);
  const actionEffectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (actionEffectTimer.current !== null) {
        clearTimeout(actionEffectTimer.current);
      }
    },
    [],
  );

  const showActionEffect = (effect: {
    amount: number;
    mascotEffect?: 'banana' | 'sparkle';
  }) => {
    actionEffectId.current += 1;
    setActionEffect({ ...effect, id: actionEffectId.current });
    if (actionEffectTimer.current !== null) {
      clearTimeout(actionEffectTimer.current);
    }
    actionEffectTimer.current = setTimeout(() => {
      setActionEffect(null);
      actionEffectTimer.current = null;
    }, HOUSE_ACTION_EFFECT_MS);
  };
  const viewport = measuredViewport ?? scaleViewport;
  const controlScale = getContainedInterfaceScale(
    viewport.width,
    viewport.height,
  );
  const compactStyles = houseControlStyles(controlScale);
  const mascotSize = houseMascotSize(viewport.height);
  const bottomPanelTop = houseBottomPanelTop(
    columnLayout?.y ?? null,
    columnLayout?.height ?? null,
    actionAreaHeight,
    bottomPanelHeight,
  );
  const controlsTop = houseControlsTop(
    columnLayout?.y ?? null,
    columnLayout?.height ?? null,
    actionAreaHeight,
  );
  // The hint's measured height is kept even while it is hidden mid-reaction, so
  // the mascot holds its place instead of hopping down and back.
  const belowMascotHeight =
    (touchHintHeight ?? HOUSE_TOUCH_HINT_RESERVED_HEIGHT * controlScale) +
    spacing.sm * controlScale;
  const mascotTop = houseMascotTop({
    belowMascotHeight,
    controlsTop,
    mascotSize,
    sceneTop: (columnLayout?.y ?? 0) + (stageTop ?? 0) + (topRailHeight ?? 0),
    viewportHeight: viewport.height,
  });

  return (
    <View
      onLayout={(event) => {
        const { height, width } = event.nativeEvent.layout;
        setMeasuredViewport((current) =>
          current?.height === height && current.width === width
            ? current
            : { height, width },
        );
      }}
      style={styles.screen}
      testID="mascot-house-content"
    >
      <Backdrop
        backgroundId={view.selectedBackgroundId}
        viewport={viewport}
        bottomPanelTop={bottomPanelTop}
      />

      {/* The slot keeps the tuned 45% anchor while there is room for it, and
          `houseMascotTop` lifts it only far enough that neither the mascot nor
          the hint under it ends up behind the controls. Every input is measured
          layout, so it holds on any aspect ratio and on the web. The bubble and
          the hint are absolutely positioned inside the slot: an ordinary child
          would stack in the column and push the mascot off its anchor. */}
      <View
        pointerEvents="box-none"
        style={[styles.mascotSlot, { height: mascotSize, top: mascotTop }]}
        testID="house-mascot-slot"
      >
        <SpeechBubble
          controlScale={controlScale}
          mascotSize={mascotSize}
          text={houseSpeech(view, pose)}
        />
        <Pressable
          accessibilityLabel="끼끼 쓰다듬기"
          accessibilityRole="button"
          onPress={() => {
            if (onPet())
              showActionEffect({ amount: 0, mascotEffect: 'sparkle' });
          }}
          style={{ width: mascotSize, height: mascotSize }}
          testID="house-pet-action"
        >
          <PersistentMascotArt
            size={mascotSize}
            slot={mascotArt ?? housePoseArt[pose]}
          />
        </Pressable>
        <TouchHint
          controlScale={controlScale}
          mascotSize={mascotSize}
          onMeasure={setTouchHintHeight}
          visible={pose !== 'petted' && pose !== 'eating'}
        />
        <MascotActionEffectOverlay effect={actionEffect} />
      </View>

      <View
        onLayout={(event) => setDecorationCanvas(event.nativeEvent.layout)}
        pointerEvents={decorating ? 'box-none' : 'none'}
        style={styles.decorationCanvas}
        testID="house-decoration-canvas"
      >
        {view.ownedItems.map((item) => (
          <DraggablePlacedItem
            canvasHeight={decorationCanvas.height}
            canvasWidth={decorationCanvas.width}
            editable={decorating}
            itemId={item.id}
            key={item.id}
            label={item.label}
            onPlace={onPlaceItem}
            placement={view.itemPlacements[item.id]}
          />
        ))}
      </View>

      <SafeAreaView
        edges={['top']}
        pointerEvents="box-none"
        style={styles.safeArea}
        testID="house-safe-area"
      >
        <View
          onLayout={(event) => {
            const { height, y } = event.nativeEvent.layout;
            setColumnLayout((current) =>
              current?.height === height && current.y === y
                ? current
                : { height, y },
            );
          }}
          pointerEvents="box-none"
          style={[styles.column, compactStyles.column]}
          testID="house-content-column"
        >
          <View
            pointerEvents="box-none"
            onLayout={(event) => setStageTop(event.nativeEvent.layout.y)}
            style={[styles.stage, compactStyles.stage]}
            testID="house-scene"
          >
            <View
              onLayout={(event) =>
                setTopRailHeight(event.nativeEvent.layout.height)
              }
              style={[styles.railLeft, compactStyles.rail]}
            >
              <View
                accessible
                accessibilityLabel={`바나나 ${view.bananas}개 보유`}
                style={[styles.chip, compactStyles.chip]}
                testID="house-banana-count"
              >
                <BananaGlyph size={40 * controlScale} />
                <Text style={[styles.chipValue, compactStyles.chipValue]}>
                  {view.bananas}개
                </Text>
                <Pressable
                  accessibilityLabel="바나나 얻는 방법 보기"
                  accessibilityRole="button"
                  onPress={openQuests}
                  style={[styles.chipPlus, { marginLeft: spacing.xs }]}
                  testID="house-banana-earn-action"
                >
                  <PlusGlyph size={12 * controlScale} />
                </Pressable>
                <SpendActionEffectOverlay effect={actionEffect} />
              </View>

              <Pressable
                accessibilityLabel="집 꾸미기"
                accessibilityRole="button"
                onPress={() => setDecorating(true)}
                style={[styles.chip, compactStyles.chip]}
                testID="house-decorate-action"
              >
                <HouseMarkGlyph
                  size={22 * controlScale}
                  color={colors.brandOutline}
                />
                <Text style={[styles.chipValue, compactStyles.chipValue]}>
                  집 꾸미기
                </Text>
              </Pressable>
            </View>

            <View style={styles.railCenter} pointerEvents="box-none">
              <Pressable
                accessibilityLabel={`친밀도 레벨 ${view.intimacyLevel}, 자세히 보기`}
                accessibilityRole="button"
                onPress={openQuests}
                style={[
                  styles.chip,
                  compactStyles.chip,
                  styles.intimacyChip,
                  compactStyles.intimacyChip,
                ]}
                testID="house-intimacy-chip"
              >
                <HeartGlyph size={22 * controlScale} />
                <View style={styles.intimacyCopy}>
                  <Text
                    style={[styles.intimacyLabel, compactStyles.intimacyLabel]}
                  >
                    친밀도 Lv.{view.intimacyLevel}
                  </Text>
                  <View style={styles.heartRow} testID="house-intimacy-hearts">
                    {Array.from({ length: INTIMACY_MAX_LEVEL }, (_, index) => (
                      <HeartGlyph
                        filled={index < view.intimacyLevel}
                        key={index}
                        size={11 * controlScale}
                      />
                    ))}
                  </View>
                </View>
                <ChevronGlyph size={13 * controlScale} />
              </Pressable>
            </View>

            <View style={[styles.railRight, compactStyles.rail]}>
              {view.visitStreakDays > 1 ? (
                <View
                  style={[styles.streakChip, compactStyles.streakChip]}
                  testID="house-visit-streak"
                >
                  <FlameGlyph size={14 * controlScale} />
                  <Text style={[styles.streakLabel, compactStyles.streakLabel]}>
                    {view.visitStreakDays}일 연속
                  </Text>
                </View>
              ) : null}
            </View>
          </View>

          {/* The stack stays mounted while the decorate panel is open, and the
              panel covers it as an overlay. Swapping them would change the
              column's height, which would move the scene and the mascot. */}
          <View
            onLayout={(event) =>
              setActionAreaHeight(event.nativeEvent.layout.height)
            }
            style={[styles.actionArea, compactStyles.actionArea]}
            testID="house-action-area"
          >
            <View
              accessibilityElementsHidden={overlayOpen}
              importantForAccessibility={
                overlayOpen ? 'no-hide-descendants' : 'auto'
              }
              pointerEvents={overlayOpen ? 'none' : 'auto'}
              style={[styles.actionStack, compactStyles.actionStack]}
            >
              <View
                style={[
                  styles.primaryActionRow,
                  compactStyles.primaryActionRow,
                ]}
                testID="house-primary-actions"
              >
                <FeedButton
                  controlScale={controlScale}
                  enabled={view.canFeed}
                  onPress={() => {
                    if (onFeed()) {
                      showActionEffect({
                        amount: HOUSE_ACTION_COST.feed,
                        mascotEffect: 'banana',
                      });
                    }
                  }}
                />
              </View>

              {/* Above the panel on purpose. The panel's own height fixes the
                  backdrop boundary, so anything that grows the controls has to
                  grow upward into the scene instead of downward into it. */}
              <IntimacyBonusRow
                controlScale={controlScale}
                onPress={openQuests}
                view={view}
              />

              <HouseTilePanel
                controlScale={controlScale}
                onHeightChange={setBottomPanelHeight}
                onOpenQuests={openQuests}
                onPlayGame={onPlayGame}
                view={view}
              />
            </View>

            {decorating ? (
              <DecoratePanel
                controlScale={controlScale}
                onBuyItem={onBuyItem}
                onClose={() => setDecorating(false)}
                onSelectBackground={onSelectBackground}
                onSpend={(amount) => showActionEffect({ amount })}
                view={view}
              />
            ) : null}

            {questing ? (
              <QuestPanel
                controlScale={controlScale}
                onClose={() => setQuesting(false)}
                view={view}
              />
            ) : null}
          </View>
        </View>

        {footer}
      </SafeAreaView>
    </View>
  );
}

function PersistentMascotArt({
  size,
  slot,
}: {
  size: number;
  slot: HouseArtSlot;
}) {
  const [displayedSlot, setDisplayedSlot] = useState(slot);
  const pendingSlot =
    displayedSlot.id === slot.id && displayedSlot.source === slot.source
      ? null
      : slot;

  return (
    <View
      pointerEvents="none"
      style={{ height: size, width: size }}
      testID="house-mascot-art-stack"
    >
      <HouseArtView
        showPlaceholderLabel={false}
        slot={displayedSlot}
        style={[styles.mascot, { height: size, width: size }]}
      />
      {pendingSlot !== null && pendingSlot.source !== null ? (
        <Image
          accessible={false}
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          onLoad={() => {
            setDisplayedSlot(pendingSlot);
          }}
          resizeMode={pendingSlot.fit ?? 'contain'}
          source={pendingSlot.source}
          style={[
            styles.mascot,
            styles.mascotPreload,
            { height: size, width: size },
          ]}
          testID="house-mascot-art-preload"
        />
      ) : null}
    </View>
  );
}

/**
 * The scene behind everything.
 *
 * Until the illustration lands this is a sky-to-path gradient rather than a
 * dashed placeholder box: a full-bleed backdrop with a visible frame would
 * read as a bug, not as unfinished art.
 */
function Backdrop({
  backgroundId,
  bottomPanelTop,
  viewport,
}: {
  backgroundId: HouseBackgroundId;
  bottomPanelTop: number | null;
  viewport: { width: number; height: number };
}) {
  const roomArt = houseBackgroundArt[backgroundId];
  const roomSource = roomArt.source;
  const sourceModule = Array.isArray(roomSource) ? roomSource[0] : roomSource;
  const resolvedSource =
    sourceModule == null
      ? null
      : Asset.fromModule(
          sourceModule as Parameters<typeof Asset.fromModule>[0],
        );
  const sourceWidth =
    resolvedSource?.width != null && resolvedSource.width > 1
      ? resolvedSource.width
      : HOUSE_BACKDROP_SOURCE_SIZE.width;
  const sourceHeight =
    resolvedSource?.height != null && resolvedSource.height > 1
      ? resolvedSource.height
      : HOUSE_BACKDROP_SOURCE_SIZE.height;
  const minimumArtHeight = houseBackdropMinimumHeight(
    viewport.height,
    bottomPanelTop,
  );
  const artSize = houseBackdropSize(
    viewport.width,
    viewport.height,
    sourceWidth,
    sourceHeight,
    minimumArtHeight,
  );
  const blendBandHeight = Math.min(sourceHeight, HOUSE_BACKDROP_BLEND_BAND_PX);
  const continuationTop = houseBackdropContinuationTop(
    artSize.height,
    viewport.height,
    bottomPanelTop,
  );
  const continuationHeight = Math.max(1, viewport.height - continuationTop);
  const continuationWidth = Math.max(artSize.width, viewport.width);
  const overlapRatio = Math.min(
    0.3,
    HOUSE_BACKDROP_BLEND_OVERLAP / continuationHeight,
  );

  return (
    <View
      pointerEvents="none"
      style={[StyleSheet.absoluteFill, styles.backdrop]}
      testID="house-backdrop"
    >
      {roomSource === null ? (
        <LinearGradient
          colors={[...HOUSE_BACKDROP_FALLBACK]}
          locations={[0, 0.34, 0.6, 1]}
          style={StyleSheet.absoluteFill}
          testID="house-backdrop-fallback"
        />
      ) : (
        <>
          <View
            style={[StyleSheet.absoluteFill, styles.backdropSurround]}
            testID="house-backdrop-surround"
          />
          <View style={[styles.backdropArtFrame, artSize]}>
            <HouseArtView
              showPlaceholderLabel={false}
              slot={roomArt}
              style={StyleSheet.absoluteFill}
            />
          </View>
          <View
            style={[styles.backdropContinuation, { top: continuationTop }]}
            testID="house-backdrop-continuation"
          >
            <Svg
              height="100%"
              preserveAspectRatio="none"
              style={styles.backdropContinuationStrip}
              testID="house-backdrop-blurred-band"
              viewBox={`0 0 ${sourceWidth} ${blendBandHeight}`}
              width={continuationWidth}
            >
              <Defs>
                <Filter
                  height="160%"
                  id="house-backdrop-blur"
                  width="120%"
                  x="-10%"
                  y="-30%"
                >
                  <FeGaussianBlur edgeMode="duplicate" stdDeviation={32} />
                </Filter>
                <SvgLinearGradient
                  gradientUnits="objectBoundingBox"
                  id="house-backdrop-overlap-gradient"
                  x1="0%"
                  x2="0%"
                  y1="0%"
                  y2="100%"
                >
                  <Stop offset={0} stopColor="white" stopOpacity={0} />
                  <Stop
                    offset={overlapRatio}
                    stopColor="white"
                    stopOpacity={1}
                  />
                </SvgLinearGradient>
                <Mask id="house-backdrop-overlap-mask">
                  <Rect
                    fill="url(#house-backdrop-overlap-gradient)"
                    height={blendBandHeight}
                    width={sourceWidth}
                    x={0}
                    y={0}
                  />
                </Mask>
              </Defs>
              <SvgImage
                height={sourceHeight}
                href={roomSource}
                filter="url(#house-backdrop-blur)"
                mask="url(#house-backdrop-overlap-mask)"
                preserveAspectRatio="none"
                testID="house-backdrop-blurred-source"
                width={sourceWidth}
                x={0}
                y={blendBandHeight - sourceHeight}
              />
            </Svg>
            <LinearGradient
              colors={[
                fadeFrom(colors.canvas, 0),
                fadeFrom(colors.canvas, 0.28),
                fadeFrom(colors.canvas, 0.82),
                colors.canvas,
              ]}
              locations={[0, 0.18, 0.58, 1]}
              style={StyleSheet.absoluteFill}
              testID="house-backdrop-continuation-fade"
            />
          </View>
        </>
      )}

      <LinearGradient
        colors={[
          fadeFrom(colors.canvas, 0),
          fadeFrom(colors.canvas, 0.82),
          colors.canvas,
        ]}
        locations={[0, 0.62, 1]}
        style={[styles.bottomFade, { top: continuationTop }]}
        testID="house-bottom-fade"
      />
    </View>
  );
}

function SpeechBubble({
  controlScale,
  mascotSize,
  text,
}: {
  controlScale: number;
  mascotSize: number;
  text: string;
}) {
  const compactStyles = houseControlStyles(controlScale);
  return (
    <View
      style={[
        styles.bubble,
        compactStyles.bubble,
        { bottom: mascotSize + spacing.sm * controlScale },
      ]}
      testID="house-speech-bubble"
    >
      <Text style={[styles.bubbleText, compactStyles.bubbleText]}>{text}</Text>
      <View style={styles.bubbleTail} />
    </View>
  );
}

function FeedButton({
  controlScale,
  enabled,
  onPress,
}: {
  controlScale: number;
  enabled: boolean;
  onPress: () => void;
}) {
  const compactStyles = houseControlStyles(controlScale);
  return (
    <Pressable
      accessibilityLabel={`바나나 주기, 바나나 ${HOUSE_ACTION_COST.feed}개`}
      accessibilityRole="button"
      accessibilityState={{ disabled: !enabled }}
      disabled={!enabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.primaryActionButton,
        styles.feedButton,
        compactStyles.primaryActionButton,
        !enabled && styles.spent,
        pressed && enabled && styles.feedButtonPressed,
      ]}
      testID="house-feed-action"
    >
      <LinearGradient
        colors={['#FFE79A', '#FBD24E', '#F4C438']}
        end={{ x: 0.5, y: 1 }}
        locations={[0, 0.55, 1]}
        pointerEvents="none"
        start={{ x: 0.5, y: 0 }}
        style={styles.feedGradient}
      />
      <BananaGlyph size={18 * controlScale} />
      <Text style={[styles.feedLabel, compactStyles.primaryActionLabel]}>
        바나나 주기
      </Text>
      <BananaGlyph size={18 * controlScale} />
      <Text style={[styles.feedLabel, compactStyles.primaryActionLabel]}>
        -{HOUSE_ACTION_COST.feed}
      </Text>
    </Pressable>
  );
}

/**
 * The invitation to touch the mascot.
 *
 * Absolutely positioned below the mascot rather than stacked under it: the
 * slot's height is the mascot's, and an ordinary sibling would move the
 * anchor. It steps aside while the mascot is mid-reaction so the bubble and
 * the hint never talk over each other.
 */
function TouchHint({
  controlScale,
  mascotSize,
  onMeasure,
  visible,
}: {
  controlScale: number;
  mascotSize: number;
  /** Reports the hint's height so the mascot's clearance can account for it. */
  onMeasure: (height: number) => void;
  visible: boolean;
}) {
  const compactStyles = houseControlStyles(controlScale);
  if (!visible) return null;
  return (
    <View
      onLayout={(event) => onMeasure(event.nativeEvent.layout.height)}
      pointerEvents="none"
      style={[
        styles.touchHint,
        compactStyles.touchHint,
        { top: mascotSize + spacing.sm * controlScale },
      ]}
      testID="house-touch-hint"
    >
      <Text style={[styles.touchHintTitle, compactStyles.touchHintTitle]}>
        끼끼를 터치해보세요!
      </Text>
      <View style={styles.touchHintBodyRow}>
        <Text style={[styles.touchHintBody, compactStyles.touchHintBody]}>
          쓰다듬으면 친밀도가 올라가요
        </Text>
        <HeartGlyph filled={false} size={11 * controlScale} />
        <InfoGlyph size={12 * controlScale} />
      </View>
    </View>
  );
}

/** Says what intimacy is still available today, and where the rest comes from. */
function IntimacyBonusRow({
  controlScale,
  onPress,
  view,
}: {
  controlScale: number;
  onPress: () => void;
  view: HouseView;
}) {
  const compactStyles = houseControlStyles(controlScale);
  return (
    <Pressable
      accessibilityLabel={`친밀도 보너스, 오늘 남은 획득 가능 ${view.intimacyRemainingToday}회`}
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [
        styles.bonusRow,
        compactStyles.bonusRow,
        pressed && styles.tilePressed,
      ]}
      testID="house-intimacy-bonus"
    >
      <BulbGlyph size={20 * controlScale} />
      <View style={styles.bonusCopy}>
        <Text style={[styles.bonusTitle, compactStyles.bonusTitle]}>
          친밀도 보너스{' '}
          <Text style={styles.bonusTitleWeak}>
            (오늘 남은 획득 가능: {view.intimacyRemainingToday}/
            {INTIMACY_DAILY_EARN_LIMIT})
          </Text>
        </Text>
        <Text style={[styles.bonusBody, compactStyles.bonusBody]}>
          쓰다듬기, 바나나 주기, 운동 완료 등으로 친밀도를 올려보세요!
        </Text>
      </View>
      <ChevronGlyph size={14 * controlScale} />
    </Pressable>
  );
}

/**
 * The two square tiles at the foot of the screen.
 *
 * Its height is pinned to `HOUSE_PANEL_CONTENT_HEIGHT` because
 * `houseBottomPanelTop` reads this panel to place the backdrop's blur
 * boundary. New tiles go into the same row, never into a taller panel.
 */
function HouseTilePanel({
  controlScale,
  onHeightChange,
  onOpenQuests,
  onPlayGame,
  view,
}: {
  controlScale: number;
  onHeightChange: (height: number) => void;
  onOpenQuests: () => void;
  onPlayGame: (gameId: HouseMiniGameId) => void;
  view: HouseView;
}) {
  const compactStyles = houseControlStyles(controlScale);
  return (
    <View
      onLayout={(event) => onHeightChange(event.nativeEvent.layout.height)}
      style={[styles.panel, compactStyles.panel]}
      testID="house-play-panel"
    >
      <View style={[styles.tileRow, compactStyles.tileRow]}>
        {HOUSE_MINI_GAMES.map((game) => (
          <HouseTile
            badge={
              view.gamePlayedToday
                ? `오늘 ${HOUSE_GAME_DAILY_PLAYS}/${HOUSE_GAME_DAILY_PLAYS} 완료`
                : null
            }
            caption={game.limitLabel}
            controlScale={controlScale}
            disabled={!view.canPlayGame}
            key={game.id}
            label={`${game.title} 게임하기`}
            onPress={() => onPlayGame(game.id)}
            testID={`house-mini-game-${game.id}`}
            title={game.title}
            tone="banana"
          >
            <Image
              accessible={false}
              accessibilityElementsHidden
              importantForAccessibility="no"
              resizeMode="contain"
              source={game.imageSource}
              style={[styles.tileMascot, compactStyles.tileMascot]}
              testID={`house-mini-game-mascot-${game.id}`}
            />
          </HouseTile>
        ))}

        <HouseTile
          caption={`${view.questsCompletedCount} / ${view.questCount} 완료`}
          controlScale={controlScale}
          count={view.questsCompletedCount}
          label={`퀘스트, ${view.questCount}개 중 ${view.questsCompletedCount}개 완료`}
          onPress={onOpenQuests}
          testID="house-quest-tile"
          title="퀘스트"
          tone="quest"
        >
          <ClipboardGlyph size={40 * controlScale} />
        </HouseTile>
      </View>
    </View>
  );
}

function HouseTile({
  badge = null,
  caption,
  children,
  controlScale,
  count,
  disabled = false,
  label,
  onPress,
  testID,
  title,
  tone,
}: {
  badge?: string | null;
  caption: string;
  children: ReactNode;
  controlScale: number;
  count?: number;
  disabled?: boolean;
  label: string;
  onPress: () => void;
  testID: string;
  title: string;
  tone: 'banana' | 'quest';
}) {
  const compactStyles = houseControlStyles(controlScale);
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.tile,
        compactStyles.tile,
        tone === 'quest' ? styles.tileQuest : styles.tileBanana,
        disabled && styles.spent,
        pressed && !disabled && styles.tilePressed,
      ]}
      testID={testID}
    >
      {badge !== null ? (
        <View
          style={[styles.tileBadge, compactStyles.tileBadge]}
          testID={`${testID}-badge`}
        >
          <Text style={[styles.tileBadgeLabel, compactStyles.tileBadgeLabel]}>
            {badge}
          </Text>
        </View>
      ) : null}

      {count !== undefined && count > 0 ? (
        <View
          style={[styles.tileCountBadge, compactStyles.tileCountBadge]}
          testID={`${testID}-count`}
        >
          <Text style={[styles.tileCountLabel, compactStyles.tileCountLabel]}>
            {count}
          </Text>
        </View>
      ) : null}

      <View style={[styles.tileIcon, compactStyles.tileIcon]}>{children}</View>
      <Text style={[styles.tileTitle, compactStyles.tileTitle]}>{title}</Text>
      <Text style={[styles.tileCaption, compactStyles.tileCaption]}>
        {caption}
      </Text>
    </Pressable>
  );
}

/**
 * 오늘의 퀘스트.
 *
 * An overlay over the action stack, exactly like 집 꾸미기: the backdrop, the
 * mascot and the tab bar all stay put, and the content scrolls inside the
 * panel rather than making the panel taller.
 *
 * An unmet quest shows its count and nothing else — no warning colour, no
 * "아직", no red mark. A rest day simply leaves a row at `0 / 1`, which is
 * what a learning signal looks like when it is not a penalty.
 */
function QuestPanel({
  controlScale,
  onClose,
  view,
}: {
  controlScale: number;
  onClose: () => void;
  view: HouseView;
}) {
  const compactStyles = houseControlStyles(controlScale);
  const [tab, setTab] = useState<'daily' | 'weekly'>('daily');

  return (
    <View
      style={[styles.panel, compactStyles.panel, styles.decoratePanel]}
      testID="house-quest-panel"
    >
      <View style={styles.decorateHeader}>
        <View style={styles.decorateHeading}>
          <Text style={styles.weekTitle}>오늘의 퀘스트</Text>
        </View>
        <Pressable
          accessibilityLabel="오늘의 퀘스트 닫기"
          accessibilityRole="button"
          onPress={onClose}
          style={styles.closeButton}
          testID="house-quest-close"
        >
          <Text style={styles.closeLabel}>닫기</Text>
        </Pressable>
      </View>

      <View style={styles.decorateTabs}>
        <Pressable
          accessibilityRole="tab"
          accessibilityState={{ selected: tab === 'daily' }}
          onPress={() => setTab('daily')}
          style={[
            styles.decorateTab,
            tab === 'daily' && styles.decorateTabSelected,
          ]}
          testID="house-quest-tab-daily"
        >
          <Text
            style={[
              styles.decorateTabLabel,
              tab === 'daily' && styles.decorateTabLabelSelected,
            ]}
          >
            일일
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="tab"
          accessibilityState={{ selected: tab === 'weekly' }}
          onPress={() => setTab('weekly')}
          style={[
            styles.decorateTab,
            tab === 'weekly' && styles.decorateTabSelected,
          ]}
          testID="house-quest-tab-weekly"
        >
          <Text
            style={[
              styles.decorateTabLabel,
              tab === 'weekly' && styles.decorateTabLabelSelected,
            ]}
          >
            주간
          </Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.questListContent}
        showsVerticalScrollIndicator={false}
        style={styles.questList}
        testID="house-quest-list"
      >
        {tab === 'daily' ? (
          <>
            {HOUSE_DAILY_QUESTS.map((quest) => (
              <QuestRow
                key={quest.id}
                progress={view.questProgress[quest.id]}
                quest={quest}
              />
            ))}
            <Text style={styles.questFootnote}>
              일일 퀘스트는 매일 00시에 초기화돼요.
            </Text>
          </>
        ) : (
          <View style={styles.questWeekly}>
            <Text style={styles.questWeeklyTitle}>
              {view.weekTargetCount === null
                ? '이번 주 정보를 불러오지 못했어요.'
                : `이번 주 ${view.weekTargetCount}회 중 ${view.weekCompletedCount}회 함께했어요.`}
            </Text>
            <Text style={styles.questWeeklyBody}>
              쉬는 날은 그냥 쉬어도 괜찮아요. 주간 목표만 채우면 돼요.
            </Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

function QuestRow({
  progress,
  quest,
}: {
  progress: number;
  quest: HouseQuest;
}) {
  const done = progress >= quest.target;
  // A one-step quest already reads as finished from its mark, so the count is
  // only spelled out where it actually carries information.
  const counted = quest.target > 1 || !done;

  return (
    <View
      accessible
      accessibilityLabel={`${quest.label}, ${progress} / ${quest.target}${
        done ? ', 완료' : ''
      }, 바나나 ${quest.reward}개`}
      style={styles.questRow}
      testID={`house-quest-row-${quest.id}`}
    >
      <View style={[styles.questMark, done && styles.questMarkDone]}>
        {done ? (
          <View style={styles.questCheck} />
        ) : (
          <ClipboardGlyph size={15} />
        )}
      </View>
      <Text style={styles.questLabel}>
        {quest.label}
        {counted ? (
          <Text style={styles.questCount}>
            {' '}
            ({progress}/{quest.target})
          </Text>
        ) : null}
      </Text>
      <View style={styles.questReward}>
        <Text style={styles.questRewardLabel}>+{quest.reward}</Text>
        <BananaGlyph size={16} />
      </View>
    </View>
  );
}

function DecoratePanel({
  controlScale,
  onBuyItem,
  onClose,
  onSelectBackground,
  onSpend,
  view,
}: {
  controlScale: number;
  onBuyItem: (itemId: HouseItemId) => boolean;
  onClose: () => void;
  onSelectBackground: (backgroundId: HouseBackgroundId) => void;
  onSpend: (amount: number) => void;
  view: HouseView;
}) {
  const compactStyles = houseControlStyles(controlScale);
  const [category, setCategory] = useState<'background' | 'items'>(
    'background',
  );

  return (
    <View
      style={[styles.panel, compactStyles.panel, styles.decoratePanel]}
      testID="house-decorate-panel"
    >
      <View style={styles.decorateHeader}>
        <View style={styles.decorateHeading}>
          <Text style={styles.weekTitle}>집 꾸미기</Text>
        </View>
        <Pressable
          accessibilityLabel="집 꾸미기 닫기"
          accessibilityRole="button"
          onPress={onClose}
          style={styles.closeButton}
        >
          <Text style={styles.closeLabel}>닫기</Text>
        </Pressable>
      </View>

      <View style={styles.decorateTabs}>
        <Pressable
          accessibilityRole="tab"
          accessibilityState={{ selected: category === 'background' }}
          onPress={() => setCategory('background')}
          style={[
            styles.decorateTab,
            category === 'background' && styles.decorateTabSelected,
          ]}
        >
          <Text
            style={[
              styles.decorateTabLabel,
              category === 'background' && styles.decorateTabLabelSelected,
            ]}
          >
            배경
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="tab"
          accessibilityState={{ selected: category === 'items' }}
          onPress={() => setCategory('items')}
          style={[
            styles.decorateTab,
            category === 'items' && styles.decorateTabSelected,
          ]}
        >
          <Text
            style={[
              styles.decorateTabLabel,
              category === 'items' && styles.decorateTabLabelSelected,
            ]}
          >
            소품
          </Text>
        </Pressable>
      </View>

      {category === 'background' ? (
        <ScrollView
          contentContainerStyle={styles.decorateGridContent}
          showsVerticalScrollIndicator={false}
          style={styles.decorateGrid}
          testID="house-background-list"
        >
          <FixedGrid columns={2} testID="house-background-grid">
            {HOUSE_BACKGROUND_IDS.map((backgroundId) => {
              const selected = view.selectedBackgroundId === backgroundId;
              const label = houseBackgroundLabels[backgroundId];
              return (
                <Pressable
                  accessibilityLabel={
                    selected
                      ? `${label} 배경, 사용 중`
                      : `${label} 배경으로 변경`
                  }
                  accessibilityRole="button"
                  accessibilityState={{ disabled: selected, selected }}
                  disabled={selected}
                  key={backgroundId}
                  onPress={() => onSelectBackground(backgroundId)}
                  style={[
                    styles.backgroundTile,
                    selected && styles.backgroundTileSelected,
                  ]}
                  testID={`house-background-${backgroundId}`}
                >
                  <HouseArtView
                    showPlaceholderLabel={false}
                    slot={houseBackgroundThumbnailArt[backgroundId]}
                    style={styles.backgroundArt}
                  />
                  <Text style={styles.itemLabel}>{label}</Text>
                  <Text style={styles.itemOwnedLabel}>
                    {selected ? '사용 중' : '바꾸기'}
                  </Text>
                </Pressable>
              );
            })}
          </FixedGrid>
        </ScrollView>
      ) : (
        <ScrollView
          contentContainerStyle={styles.decorateGridContent}
          showsVerticalScrollIndicator={false}
          style={styles.decorateGrid}
          testID="house-item-list"
        >
          <FixedGrid columns={3} testID="house-item-grid">
            {view.ownedItems.map((item) => (
              <View key={item.id} style={[styles.itemTile, styles.itemOwned]}>
                <HouseArtView
                  showPlaceholderLabel={false}
                  showPlaceholderOutline={false}
                  slot={houseItemArt[item.id]}
                  style={styles.itemArt}
                />
                <Text style={styles.itemLabel}>{item.label}</Text>
                <Text style={styles.itemOwnedLabel}>배치됨</Text>
              </View>
            ))}

            {view.lockedItems.map((item) => {
              const affordable = view.bananas >= item.cost;
              return (
                <Pressable
                  accessibilityLabel={`${item.label}, 바나나 ${item.cost}개`}
                  accessibilityRole="button"
                  accessibilityState={{ disabled: !affordable }}
                  disabled={!affordable}
                  key={item.id}
                  onPress={() => {
                    if (onBuyItem(item.id)) onSpend(item.cost);
                  }}
                  style={[styles.itemTile, !affordable && styles.spent]}
                  testID={`house-item-${item.id}`}
                >
                  <HouseArtView
                    showPlaceholderLabel={false}
                    showPlaceholderOutline={false}
                    slot={houseItemArt[item.id]}
                    style={styles.itemArt}
                  />
                  <Text style={styles.itemLabel}>{item.label}</Text>
                  <View style={styles.itemCost}>
                    <BananaGlyph size={12} />
                    <Text style={styles.itemCostLabel}>{item.cost}</Text>
                  </View>
                </Pressable>
              );
            })}
          </FixedGrid>
        </ScrollView>
      )}
    </View>
  );
}

function FloatingActionEffect({
  children,
  effectId,
  style,
  testID,
}: {
  children: ReactNode;
  effectId: number;
  style: object;
  testID: string;
}) {
  const [progress] = useState(() => new Animated.Value(0));

  useEffect(() => {
    progress.setValue(0);
    const animation = Animated.timing(progress, {
      duration: HOUSE_ACTION_EFFECT_MS,
      toValue: 1,
      useNativeDriver: true,
    });
    animation.start();
    return () => animation.stop();
  }, [effectId, progress]);

  return (
    <Animated.View
      accessible={false}
      pointerEvents="none"
      style={[
        style,
        {
          opacity: progress.interpolate({
            inputRange: [0, 0.12, 0.72, 1],
            outputRange: [0, 1, 1, 0],
          }),
          transform: [
            {
              translateY: progress.interpolate({
                inputRange: [0, 1],
                outputRange: [8, -24],
              }),
            },
            {
              scale: progress.interpolate({
                inputRange: [0, 0.18, 1],
                outputRange: [0.82, 1.08, 1],
              }),
            },
          ],
        },
      ]}
      testID={testID}
    >
      {children}
    </Animated.View>
  );
}

function SpendActionEffectOverlay({
  effect,
}: {
  effect: HouseActionEffect | null;
}) {
  // Petting spends nothing, so it gets the sparkle on the mascot and no
  // deduction chip on the banana count.
  if (effect === null || effect.amount <= 0) return null;

  return (
    <FloatingActionEffect
      effectId={effect.id}
      style={styles.spendActionEffect}
      testID="house-action-effect-spend"
    >
      <View style={styles.spendEffect}>
        <BananaGlyph size={18} />
        <Text
          style={styles.spendEffectLabel}
          testID="house-action-effect-amount"
        >
          -{effect.amount}
        </Text>
      </View>
    </FloatingActionEffect>
  );
}

function MascotActionEffectOverlay({
  effect,
}: {
  effect: HouseActionEffect | null;
}) {
  if (effect?.mascotEffect === undefined) return null;

  return (
    <FloatingActionEffect
      effectId={effect.id}
      style={styles.mascotActionEffect}
      testID={`house-mascot-effect-${effect.mascotEffect}`}
    >
      {effect.mascotEffect === 'banana' ? (
        <View style={styles.sparkleEffect} testID="house-mascot-effect-bananas">
          <BananaGlyph size={10} />
          <BananaGlyph size={18} />
          <BananaGlyph size={12} />
        </View>
      ) : (
        <View style={styles.sparkleEffect} testID="house-mascot-effect-stars">
          <StarGlyph size={10} />
          <StarGlyph size={18} />
          <StarGlyph size={12} />
        </View>
      )}
    </FloatingActionEffect>
  );
}

function FixedGrid({
  children,
  columns,
  testID,
}: {
  children: ReactNode;
  columns: number;
  testID: string;
}) {
  const items = Children.toArray(children);
  const rows: (typeof items)[] = [];
  for (let index = 0; index < items.length; index += columns) {
    rows.push(items.slice(index, index + columns));
  }

  return (
    <View style={styles.fixedGrid} testID={testID}>
      {rows.map((row, rowIndex) => (
        <View
          key={`${testID}-row-${rowIndex}`}
          style={styles.fixedGridRow}
          testID={`${testID}-row-${rowIndex}`}
        >
          {Array.from({ length: columns }, (_, columnIndex) => {
            const child = row[columnIndex];
            return (
              <View
                key={`${testID}-cell-${rowIndex}-${columnIndex}`}
                pointerEvents={child === undefined ? 'none' : 'auto'}
                style={styles.fixedGridCell}
                testID={`${testID}-cell-${rowIndex}-${columnIndex}`}
              >
                {child}
              </View>
            );
          })}
        </View>
      ))}
    </View>
  );
}

function DraggablePlacedItem({
  canvasHeight,
  canvasWidth,
  editable,
  itemId,
  label,
  onPlace,
  placement,
}: {
  canvasHeight: number;
  canvasWidth: number;
  editable: boolean;
  itemId: HouseItemId;
  label: string;
  onPlace: (itemId: HouseItemId, placement: HouseItemPlacement) => void;
  placement: HouseItemPlacement;
}) {
  const [dragPlacement, setDragPlacement] = useState<HouseItemPlacement | null>(
    null,
  );
  const livePlacementRef = useRef(placement);
  const dragOrigin = useRef<{
    pageX: number;
    pageY: number;
    placement: HouseItemPlacement;
  } | null>(null);
  const usableWidth = Math.max(0, canvasWidth - PLACED_ITEM_SIZE);
  const usableHeight = Math.max(0, canvasHeight - PLACED_ITEM_SIZE);

  const startDragging = (event: GestureResponderEvent) => {
    livePlacementRef.current = placement;
    dragOrigin.current = {
      pageX: event.nativeEvent.pageX,
      pageY: event.nativeEvent.pageY,
      placement,
    };
  };
  const continueDragging = (event: GestureResponderEvent) => {
    const origin = dragOrigin.current;
    if (origin === null || usableWidth <= 0 || usableHeight <= 0) return;
    const next = {
      x: clampUnit(
        origin.placement.x +
          (event.nativeEvent.pageX - origin.pageX) / usableWidth,
      ),
      y: clampUnit(
        origin.placement.y +
          (event.nativeEvent.pageY - origin.pageY) / usableHeight,
      ),
    };
    livePlacementRef.current = next;
    setDragPlacement(next);
  };
  const finishDragging = () => {
    if (dragOrigin.current === null) return;
    dragOrigin.current = null;
    const next = livePlacementRef.current;
    setDragPlacement(null);
    onPlace(itemId, next);
  };
  const renderedPlacement = dragPlacement ?? placement;

  return (
    <View
      accessibilityLabel={editable ? `${label}, 끌어서 위치 조정` : undefined}
      accessibilityRole={editable ? 'adjustable' : undefined}
      onMoveShouldSetResponder={() => editable}
      onResponderGrant={startDragging}
      onResponderMove={continueDragging}
      onResponderRelease={finishDragging}
      onResponderTerminate={finishDragging}
      onResponderTerminationRequest={() => false}
      onStartShouldSetResponder={() => editable}
      onStartShouldSetResponderCapture={() => editable}
      style={[
        styles.placedItem,
        editable && styles.placedItemEditable,
        {
          left: renderedPlacement.x * usableWidth,
          top: renderedPlacement.y * usableHeight,
        },
      ]}
      testID={`house-placed-item-${itemId}`}
    >
      <HouseArtView
        showPlaceholderLabel={false}
        showPlaceholderOutline={false}
        slot={houseItemArt[itemId]}
        style={styles.placedItemArt}
      />
    </View>
  );
}

function clampUnit(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/**
 * `#RRGGBB` with an alpha, so the bottom fade always starts from the canvas
 * colour itself. Fading from the literal `transparent` goes through black on
 * some platforms, and hard-coding the rgba would drift when the token changes.
 */
function fadeFrom(hex: string, alpha: number): string {
  const value = hex.replace('#', '');
  const red = parseInt(value.slice(0, 2), 16);
  const green = parseInt(value.slice(2, 4), 16);
  const blue = parseInt(value.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.canvas,
  },
  backdrop: {
    alignItems: 'center',
    justifyContent: 'flex-start',
    overflow: 'hidden',
  },
  backdropArtFrame: {
    flexShrink: 0,
    overflow: 'hidden',
  },
  backdropSurround: {
    backgroundColor: colors.canvas,
  },
  backdropContinuation: {
    position: 'absolute',
    right: 0,
    bottom: 0,
    left: 0,
    alignItems: 'center',
    overflow: 'hidden',
  },
  backdropContinuationStrip: {
    flexShrink: 0,
  },
  bottomFade: {
    position: 'absolute',
    right: 0,
    bottom: 0,
    left: 0,
  },
  safeArea: {
    flex: 1,
    backgroundColor: 'transparent',
  },
  column: {
    flex: 1,
    width: '100%',
    alignSelf: 'center',
    gap: HOUSE_COLUMN_GAP,
    paddingHorizontal: HOUSE_HORIZONTAL_INSET,
    paddingTop: HOUSE_COLUMN_TOP_PADDING,
  },
  stage: {
    flex: 1,
    minHeight: HOUSE_STAGE_MIN_HEIGHT,
    justifyContent: 'flex-end',
  },
  railLeft: {
    position: 'absolute',
    top: 0,
    left: 0,
    gap: spacing.sm,
    zIndex: 2,
  },
  railRight: {
    position: 'absolute',
    top: 0,
    right: 0,
    alignItems: 'flex-end',
    gap: spacing.sm,
    zIndex: 2,
  },
  chip: {
    minWidth: 84,
    alignItems: 'center',
    gap: 3,
    borderRadius: 14,
    backgroundColor: 'rgba(255, 255, 255, 0.76)',
    paddingHorizontal: 10,
    paddingVertical: 9,
    ...shadows.card,
  },
  chipValue: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '800',
  },
  streakChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: 'rgba(225, 158, 36, 0.72)',
    backgroundColor: 'rgba(255, 231, 154, 0.76)',
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  streakLabel: {
    color: colors.warningText,
    fontSize: 11,
    fontWeight: '700',
  },
  mascotSlot: {
    position: 'absolute',
    right: 0,
    left: 0,
    alignItems: 'center',
  },
  touchHint: {
    position: 'absolute',
    alignItems: 'center',
  },
  touchHintTitle: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '900',
  },
  touchHintBodyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  touchHintBody: {
    color: colors.textSub,
    fontSize: 11,
    fontWeight: '600',
  },
  railCenter: {
    position: 'absolute',
    top: 0,
    right: 0,
    left: 0,
    alignItems: 'center',
    zIndex: 2,
  },
  intimacyChip: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  intimacyCopy: {
    alignItems: 'center',
    gap: 2,
  },
  intimacyLabel: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '900',
  },
  heartRow: {
    flexDirection: 'row',
    gap: 2,
  },
  chipPlus: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    backgroundColor: colors.surface,
  },
  bonusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    backgroundColor: 'rgba(255, 255, 255, 0.88)',
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
  },
  bonusCopy: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  bonusTitle: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '900',
  },
  bonusTitleWeak: {
    color: colors.textSub,
    fontWeight: '600',
  },
  bonusBody: {
    color: colors.textSub,
    fontSize: 11,
    lineHeight: 15,
  },
  tileRow: {
    flexDirection: 'row',
    height: HOUSE_PANEL_CONTENT_HEIGHT,
    gap: spacing.sm,
  },
  tile: {
    flex: 1,
    flexBasis: 0,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    borderRadius: radii.card,
    borderWidth: 1,
    padding: spacing.md,
  },
  tileBanana: {
    borderColor: colors.successBorder,
    backgroundColor: colors.successSurface,
  },
  tileQuest: {
    borderColor: colors.greenBorder,
    backgroundColor: colors.greenTint,
  },
  tilePressed: {
    opacity: 0.72,
  },
  tileIcon: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 52,
    height: 52,
    borderRadius: 16,
    backgroundColor: 'rgba(255, 231, 154, 0.7)',
  },
  tileMascot: {
    width: 46,
    height: 46,
  },
  tileTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '900',
  },
  tileCaption: {
    color: colors.textSub,
    fontSize: 11,
    lineHeight: 15,
    textAlign: 'center',
  },
  tileBadge: {
    position: 'absolute',
    top: spacing.sm,
    borderRadius: 999,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  tileBadgeLabel: {
    color: colors.textSub,
    fontSize: 10,
    fontWeight: '800',
  },
  tileCountBadge: {
    position: 'absolute',
    top: -8,
    right: -6,
    alignItems: 'center',
    justifyContent: 'center',
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.danger,
    zIndex: 2,
  },
  tileCountLabel: {
    color: colors.surface,
    fontSize: 12,
    fontWeight: '900',
  },
  questList: {
    flexGrow: 0,
    flexShrink: 1,
  },
  questListContent: {
    gap: spacing.md,
    paddingBottom: spacing.xs,
  },
  questRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  questMark: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.surfaceAlt,
  },
  questMarkDone: {
    backgroundColor: colors.greenBand,
  },
  questCheck: {
    width: 11,
    height: 6,
    marginTop: -3,
    borderLeftWidth: 2.5,
    borderBottomWidth: 2.5,
    borderColor: colors.greenText,
    transform: [{ rotate: '-45deg' }],
  },
  questLabel: {
    flex: 1,
    minWidth: 0,
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  questCount: {
    color: colors.textSub,
    fontWeight: '600',
  },
  questReward: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  questRewardLabel: {
    color: colors.greenText,
    fontSize: 14,
    fontWeight: '900',
  },
  questFootnote: {
    color: colors.textMuted,
    fontSize: 11,
    textAlign: 'center',
  },
  questWeekly: {
    gap: spacing.sm,
  },
  questWeeklyTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
  },
  questWeeklyBody: {
    color: colors.textSub,
    fontSize: 12,
    lineHeight: 18,
  },
  bubble: {
    position: 'absolute',
    maxWidth: 250,
    borderRadius: 18,
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 11,
    ...shadows.card,
  },
  bubbleText: {
    color: colors.text,
    fontSize: 13.5,
    lineHeight: 20,
    textAlign: 'center',
  },
  bubbleTail: {
    position: 'absolute',
    bottom: -7,
    alignSelf: 'center',
    width: 0,
    height: 0,
    borderLeftWidth: 8,
    borderRightWidth: 8,
    borderTopWidth: 8,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    borderTopColor: colors.surface,
  },
  mascot: {
    position: 'absolute',
    top: 0,
  },
  mascotPreload: {
    opacity: 0,
  },
  decorationCanvas: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  placedItem: {
    position: 'absolute',
    width: PLACED_ITEM_SIZE,
    height: PLACED_ITEM_SIZE,
    borderWidth: 0,
    borderRadius: radii.control,
  },
  placedItemEditable: {
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: colors.brandOutline,
  },
  placedItemArt: {
    width: '100%',
    height: '100%',
    borderRadius: radii.control,
  },
  primaryActionRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  primaryActionButton: {
    flex: 1,
    flexBasis: 0,
    minWidth: 0,
  },
  feedButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    overflow: 'hidden',
    borderRadius: 999,
    borderWidth: 1,
    borderColor: 'transparent',
    paddingVertical: 15,
    ...shadows.card,
  },
  feedButtonPressed: {
    opacity: 0.9,
  },
  feedGradient: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  feedLabel: {
    color: colors.textSub,
    fontSize: 14,
    fontWeight: '800',
  },
  petButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    backgroundColor: 'rgba(255, 255, 255, 0.86)',
    paddingVertical: 15,
  },
  petLabel: {
    color: colors.textSub,
    fontSize: 14,
    fontWeight: '800',
  },
  spent: {
    opacity: 0.45,
  },
  actionArea: {
    position: 'relative',
    gap: spacing.sm,
  },
  actionStack: {
    gap: spacing.sm,
  },
  decoratePanel: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  decorateGrid: {
    flex: 1,
  },
  panel: {
    gap: spacing.sm,
    borderRadius: 20,
    backgroundColor: colors.surface,
    padding: spacing.lg,
    marginBottom: spacing.xs,
    ...shadows.card,
  },
  playPanelHeader: {
    gap: 2,
  },
  playPanelTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '900',
  },
  spendActionEffect: {
    position: 'absolute',
    top: 18,
    right: -46,
    zIndex: 4,
  },
  mascotActionEffect: {
    position: 'absolute',
    top: '18%',
    zIndex: 4,
    alignSelf: 'center',
  },
  spendEffect: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: 999,
    backgroundColor: 'rgba(255, 255, 255, 0.92)',
    paddingHorizontal: 12,
    paddingVertical: 7,
    ...shadows.card,
  },
  spendEffectLabel: {
    color: colors.warningText,
    fontSize: 17,
    fontWeight: '900',
  },
  sparkleEffect: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  miniGameListContent: {
    gap: spacing.sm,
  },
  miniGameCard: {
    width: 286,
    minHeight: 122,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceAlt,
    padding: spacing.md,
  },
  miniGameCardPressed: {
    opacity: 0.72,
  },
  miniGameIcon: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 14,
    backgroundColor: 'rgba(255, 231, 154, 0.86)',
  },
  miniGameMascot: {
    width: 42,
    height: 42,
  },
  miniGameCopy: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  miniGameTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '900',
  },
  miniGameDescription: {
    color: colors.textSub,
    fontSize: 11,
    lineHeight: 16,
  },
  miniGameDuration: {
    borderRadius: 999,
    backgroundColor: colors.surface,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  miniGameDurationLabel: {
    color: colors.greenText,
    fontSize: 11,
    fontWeight: '800',
  },
  miniGameArrow: {
    marginTop: -2,
    color: colors.textSub,
    fontSize: 22,
    lineHeight: 24,
  },
  weekTitle: {
    flex: 1,
    minWidth: 0,
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
  },
  decorateHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  decorateHeading: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
  decorateTabs: {
    flexDirection: 'row',
    gap: spacing.xs,
    borderRadius: radii.control,
    backgroundColor: colors.surfaceAlt,
    padding: spacing.xs,
  },
  decorateTab: {
    flex: 1,
    alignItems: 'center',
    borderRadius: radii.control,
    paddingVertical: 6,
  },
  decorateTabSelected: {
    backgroundColor: colors.surface,
    ...shadows.card,
  },
  decorateTabLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  decorateTabLabelSelected: {
    color: colors.brandOutline,
  },
  closeButton: {
    borderRadius: radii.control,
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  closeLabel: {
    color: colors.textSub,
    fontSize: 12,
    fontWeight: '600',
  },
  decorateGridContent: {
    width: '100%',
  },
  fixedGrid: {
    width: '100%',
    gap: DECORATE_GRID_GAP,
  },
  fixedGridRow: {
    width: '100%',
    flexDirection: 'row',
    gap: DECORATE_GRID_GAP,
  },
  fixedGridCell: {
    flex: 1,
    minWidth: 0,
  },
  backgroundTile: {
    width: '100%',
    gap: 3,
    borderRadius: radii.control,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceAlt,
    padding: spacing.xs,
  },
  backgroundTileSelected: {
    borderColor: colors.greenBorder,
    backgroundColor: colors.greenTint,
  },
  backgroundArt: {
    width: '100%',
    height: 62,
    borderRadius: 9,
  },
  itemTile: {
    width: '100%',
    alignItems: 'center',
    gap: 4,
    borderRadius: radii.control,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceAlt,
    paddingVertical: spacing.sm,
  },
  itemOwned: {
    borderColor: colors.greenBorder,
    backgroundColor: colors.greenTint,
  },
  itemArt: {
    width: 34,
    height: 34,
    borderRadius: radii.control,
  },
  itemLabel: {
    color: colors.text,
    fontSize: 11,
    fontWeight: '600',
  },
  itemOwnedLabel: {
    color: colors.greenText,
    fontSize: 10,
    fontWeight: '700',
  },
  itemCost: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  itemCostLabel: {
    color: colors.textMuted,
    fontSize: 11,
  },
});
