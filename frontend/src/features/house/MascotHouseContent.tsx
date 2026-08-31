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
import { useRef, useState } from 'react';
import {
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

import { BASE_H, useScale } from '../../components/scale';
import { colors, radii, shadows, spacing } from '../../components/theme';
import {
  BananaGlyph,
  GiftGlyph,
  HouseArtView,
  HouseMarkGlyph,
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
  houseSpeech,
  type HouseBackgroundId,
  type HouseItemId,
  type HouseItemPlacement,
  type HousePose,
  type HouseView,
} from './houseModel';
/**
 * The controls stay phone-width however wide the window gets. Past this the
 * extra room goes to the scene, not to stretched buttons.
 */
const CONTENT_MAX_WIDTH = 430;

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
    description: '떨어지는 바나나를 받아요',
    durationLabel: '30초',
  },
] as const;

export type HouseMiniGameId = (typeof HOUSE_MINI_GAMES)[number]['id'];

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
  onClaimGift,
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
  onBuyItem: (itemId: HouseItemId) => void;
  onClaimGift: () => void;
  onFeed: () => void;
  onPet: () => void;
  onPlayGame: (gameId: HouseMiniGameId) => void;
  onPlaceItem: (itemId: HouseItemId, placement: HouseItemPlacement) => void;
  onSelectBackground: (backgroundId: HouseBackgroundId) => void;
  mascotArt?: HouseArtSlot;
  pose: HousePose;
  view: HouseView;
}) {
  const scaleViewport = useScale();
  const [decorating, setDecorating] = useState(false);
  const [measuredViewport, setMeasuredViewport] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [columnLayout, setColumnLayout] = useState<{
    y: number;
    height: number;
  } | null>(null);
  const [actionAreaHeight, setActionAreaHeight] = useState<number | null>(null);
  const [bottomPanelHeight, setBottomPanelHeight] = useState<number | null>(
    null,
  );
  const [decorationCanvas, setDecorationCanvas] = useState({
    width: 0,
    height: 0,
  });
  const viewport = measuredViewport ?? scaleViewport;
  const mascotSize = houseMascotSize(viewport.height);
  const bottomPanelTop = houseBottomPanelTop(
    columnLayout?.y ?? null,
    columnLayout?.height ?? null,
    actionAreaHeight,
    bottomPanelHeight,
  );

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

      <View
        pointerEvents="none"
        style={[
          styles.mascotSlot,
          {
            height: mascotSize,
            transform: [
              {
                translateY:
                  -mascotSize / 2 +
                  houseMascotTallScreenOffset(viewport.height),
              },
            ],
          },
        ]}
        testID="house-mascot-slot"
      >
        <SpeechBubble mascotSize={mascotSize} text={houseSpeech(view, pose)} />
        <HouseArtView
          showPlaceholderLabel={false}
          slot={mascotArt ?? housePoseArt[pose]}
          style={[styles.mascot, { height: mascotSize, width: mascotSize }]}
        />
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
          style={styles.column}
          testID="house-content-column"
        >
          <View
            pointerEvents="box-none"
            style={styles.stage}
            testID="house-scene"
          >
            <View style={styles.railLeft}>
              <View
                accessible
                accessibilityLabel={`바나나 ${view.bananas}개 보유`}
                style={styles.chip}
                testID="house-banana-count"
              >
                <BananaGlyph size={40} />
                <Text style={styles.chipValue}>{view.bananas}개</Text>
              </View>

              <Pressable
                accessibilityLabel="집 꾸미기"
                accessibilityRole="button"
                onPress={() => setDecorating(true)}
                style={styles.chip}
                testID="house-decorate-action"
              >
                <HouseMarkGlyph size={22} color={colors.brandOutline} />
                <Text style={styles.chipValue}>집 꾸미기</Text>
              </Pressable>
            </View>

            <View style={styles.railRight}>
              <Pressable
                accessibilityLabel={
                  view.giftAvailable
                    ? '오늘의 선물 받기'
                    : '오늘의 선물, 이미 받았어요'
                }
                accessibilityRole="button"
                accessibilityState={{ disabled: !view.giftAvailable }}
                disabled={!view.giftAvailable}
                onPress={onClaimGift}
                style={[styles.chip, !view.giftAvailable && styles.spent]}
                testID="house-gift-button"
              >
                <GiftGlyph size={22} />
                <Text style={styles.chipValue}>
                  {view.giftAvailable ? '오늘의 선물' : '받았어요'}
                </Text>
              </Pressable>

              {view.visitStreakDays > 1 ? (
                <View style={styles.streakChip} testID="house-visit-streak">
                  <StarGlyph size={14} />
                  <Text style={styles.streakLabel}>
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
            style={styles.actionArea}
            testID="house-action-area"
          >
            <View
              accessibilityElementsHidden={decorating}
              importantForAccessibility={
                decorating ? 'no-hide-descendants' : 'auto'
              }
              pointerEvents={decorating ? 'none' : 'auto'}
              style={styles.actionStack}
            >
              <View
                style={styles.primaryActionRow}
                testID="house-primary-actions"
              >
                <FeedButton enabled={view.canFeed} onPress={onFeed} />
                <Pressable
                  accessibilityLabel={`쓰다듬기, 바나나 ${HOUSE_ACTION_COST.pet}개`}
                  accessibilityRole="button"
                  accessibilityState={{ disabled: !view.canPet }}
                  disabled={!view.canPet}
                  onPress={onPet}
                  style={[
                    styles.primaryActionButton,
                    styles.petButton,
                    !view.canPet && styles.spent,
                  ]}
                  testID="house-pet-action"
                >
                  <Text style={styles.petLabel}>
                    쓰다듬기 · {HOUSE_ACTION_COST.pet}개
                  </Text>
                  <BananaGlyph size={18} />
                </Pressable>
              </View>

              <MiniGamePanel
                onHeightChange={setBottomPanelHeight}
                onPlayGame={onPlayGame}
              />
            </View>

            {decorating ? (
              <DecoratePanel
                onBuyItem={onBuyItem}
                onClose={() => setDecorating(false)}
                onSelectBackground={onSelectBackground}
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
  mascotSize,
  text,
}: {
  mascotSize: number;
  text: string;
}) {
  return (
    <View
      style={[styles.bubble, { bottom: mascotSize + spacing.sm }]}
      testID="house-speech-bubble"
    >
      <Text style={styles.bubbleText}>{text}</Text>
      <View style={styles.bubbleTail} />
    </View>
  );
}

function FeedButton({
  enabled,
  onPress,
}: {
  enabled: boolean;
  onPress: () => void;
}) {
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
      <Text style={styles.feedLabel}>
        바나나 주기 · {HOUSE_ACTION_COST.feed}개
      </Text>
      <BananaGlyph size={18} />
    </Pressable>
  );
}

function MiniGamePanel({
  onHeightChange,
  onPlayGame,
}: {
  onHeightChange: (height: number) => void;
  onPlayGame: (gameId: HouseMiniGameId) => void;
}) {
  return (
    <View
      onLayout={(event) => onHeightChange(event.nativeEvent.layout.height)}
      style={styles.panel}
      testID="house-play-panel"
    >
      <View style={styles.playPanelHeader}>
        <Text style={styles.playPanelTitle}>끼끼와 놀기</Text>
        <Text style={styles.playPanelCaption}>함께 할 미니게임을 골라요</Text>
      </View>

      <ScrollView
        contentContainerStyle={styles.miniGameListContent}
        horizontal
        showsHorizontalScrollIndicator={false}
        testID="house-mini-game-list"
      >
        {HOUSE_MINI_GAMES.map((game) => (
          <Pressable
            accessibilityLabel={`${game.title} 게임하기`}
            accessibilityRole="button"
            key={game.id}
            onPress={() => onPlayGame(game.id)}
            style={({ pressed }) => [
              styles.miniGameCard,
              pressed && styles.miniGameCardPressed,
            ]}
            testID={`house-mini-game-${game.id}`}
          >
            <View style={styles.miniGameIcon}>
              <BananaGlyph size={26} />
            </View>
            <View style={styles.miniGameCopy}>
              <Text style={styles.miniGameTitle}>{game.title}</Text>
              <Text style={styles.miniGameDescription}>{game.description}</Text>
            </View>
            <View style={styles.miniGameDuration}>
              <Text style={styles.miniGameDurationLabel}>
                {game.durationLabel}
              </Text>
            </View>
            <Text accessibilityElementsHidden style={styles.miniGameArrow}>
              ›
            </Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

function DecoratePanel({
  onBuyItem,
  onClose,
  onSelectBackground,
  view,
}: {
  onBuyItem: (itemId: HouseItemId) => void;
  onClose: () => void;
  onSelectBackground: (backgroundId: HouseBackgroundId) => void;
  view: HouseView;
}) {
  const [category, setCategory] = useState<'background' | 'items'>(
    'background',
  );

  return (
    <View
      style={[styles.panel, styles.decoratePanel]}
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
                  onPress={() => onBuyItem(item.id)}
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
    maxWidth: CONTENT_MAX_WIDTH,
    alignSelf: 'center',
    gap: HOUSE_COLUMN_GAP,
    paddingHorizontal: spacing.lg,
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
    top: '45%',
    right: 0,
    left: 0,
    alignItems: 'center',
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
    color: colors.brandOutline,
    fontSize: 17,
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
    fontSize: 17,
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
  playPanelCaption: {
    color: colors.textSub,
    fontSize: 12,
    lineHeight: 18,
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
