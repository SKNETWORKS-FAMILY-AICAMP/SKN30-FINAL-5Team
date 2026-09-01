/**
 * 끼끼의 집 — the scene itself.
 *
 * The backdrop is full-bleed: it fills the whole screen, runs under the status
 * bar and behind the tab bar, and is never boxed into a card. Everything else
 * floats on top of it — the top bar, the side chips, the mascot, the feed
 * button, the weekly card. A soft fade at the bottom carries the illustration
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
import type { ReactNode } from 'react';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
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

import { InlineFeedback } from '../../components/primitives';
import { useScale } from '../../components/scale';
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
  houseItemArt,
  housePoseArt,
  houseRoomArt,
} from './houseArtSlots';
import {
  CHEAPEST_ITEM_COST,
  HOUSE_ACTION_COST,
  houseSpeech,
  type HouseItemId,
  type HousePose,
  type HouseView,
} from './houseModel';
import {
  MovingHouseBackdrop,
  movingHouseBackgroundSource,
} from './MovingHouseBackdrop';

export type BackgroundTestFeedback = {
  tone: 'success' | 'warning';
  message: string;
  /** Present when the message is about something the user can try again. */
  onRetry?: () => void;
};

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

/** Moves the mascot and its speech bubble down from the original fixed anchor. */
export const HOUSE_MASCOT_Y_OFFSET = 24;

/** Fallback dimensions used only when a platform cannot resolve a local asset. */
const HOUSE_BACKDROP_SOURCE_SIZE = { width: 1600, height: 976 } as const;

/** Source pixels sampled from the artwork's bottom edge for the soft extension. */
const HOUSE_BACKDROP_BLEND_BAND_PX = 160;

/** Display pixels where the blurred extension overlaps the original artwork. */
const HOUSE_BACKDROP_BLEND_OVERLAP = 48;

/**
 * Returns half of the size the artwork would have occupied with `cover`.
 * `Backdrop` fixes the resulting frame to the top and centres it horizontally,
 * so any remaining horizontal crop is removed equally from the outer edges.
 */
export function houseBackdropSize(
  viewportWidth: number,
  viewportHeight: number,
  sourceWidth: number = HOUSE_BACKDROP_SOURCE_SIZE.width,
  sourceHeight: number = HOUSE_BACKDROP_SOURCE_SIZE.height,
): { width: number; height: number } {
  const width = Math.max(0, viewportWidth);
  const height = Math.max(0, viewportHeight);
  const safeSourceWidth = Math.max(1, sourceWidth);
  const safeSourceHeight = Math.max(1, sourceHeight);
  const coverScale = Math.max(
    width / safeSourceWidth,
    height / safeSourceHeight,
  );

  return {
    width: safeSourceWidth * coverScale * HOUSE_BACKDROP_ZOOM,
    height: safeSourceHeight * coverScale * HOUSE_BACKDROP_ZOOM,
  };
}

export function BackgroundTestContent({
  feedback,
  footer,
  nickname,
  onBuyItem,
  onClaimGift,
  onDismissFeedback,
  onFeed,
  onPet,
  pose,
  view,
}: {
  feedback: BackgroundTestFeedback | null;
  /** The tab bar, rendered inside the backdrop so the scene runs behind it. */
  footer?: ReactNode;
  nickname: string;
  onBuyItem: (itemId: HouseItemId) => void;
  onClaimGift: () => void;
  onDismissFeedback: () => void;
  onFeed: () => void;
  onPet: () => void;
  pose: HousePose;
  view: HouseView;
}) {
  const [decorating, setDecorating] = useState(false);

  return (
    <View style={styles.screen} testID="background-test-content">
      <Backdrop />

      <SafeAreaView
        edges={['top']}
        style={styles.safeArea}
        testID="house-safe-area"
      >
        <View style={styles.column} testID="house-content-column">
          {/* Title only. 홈 and 마이페이지 already sit in the tab bar below,
              and a second copy of both in the corners was two ways to reach the
              same two screens. */}
          <View style={styles.topBar}>
            <Text accessibilityRole="header" style={styles.title}>
              끼끼의 집
            </Text>
          </View>

          <View style={styles.stage} testID="house-scene">
            <View style={styles.railLeft}>
              <View style={styles.chip} testID="house-banana-count">
                <BananaGlyph size={20} />
                <Text style={styles.chipCaption}>보유 바나나</Text>
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

            <View
              pointerEvents="none"
              style={styles.mascotSlot}
              testID="house-mascot-slot"
            >
              <SpeechBubble text={houseSpeech(view, pose)} />
              <HouseArtView
                showPlaceholderLabel={false}
                slot={housePoseArt[pose]}
                style={styles.mascot}
              />
              <View style={styles.placedRow}>
                {view.ownedItems.map((item) => (
                  <HouseArtView
                    key={item.id}
                    showPlaceholderLabel={false}
                    slot={houseItemArt[item.id]}
                    style={styles.placedItem}
                  />
                ))}
              </View>
            </View>
          </View>

          <View style={styles.feedbackSlot} testID="house-feedback-slot">
            {feedback === null ? null : (
              <InlineFeedback
                action={
                  <View style={styles.feedbackActions}>
                    {feedback.onRetry === undefined ? null : (
                      <Pressable
                        accessibilityLabel="다시 시도"
                        accessibilityRole="button"
                        onPress={feedback.onRetry}
                        style={styles.retryButton}
                      >
                        <Text style={styles.retryLabel}>다시 시도</Text>
                      </Pressable>
                    )}
                    <Pressable
                      accessibilityLabel="알림 닫기"
                      accessibilityRole="button"
                      onPress={onDismissFeedback}
                      style={styles.dismissButton}
                      testID="house-feedback-dismiss"
                    >
                      <Text style={styles.dismissLabel}>닫기</Text>
                    </Pressable>
                  </View>
                }
                message={feedback.message}
                style={styles.feedback}
                testID="house-feedback"
                tone={feedback.tone}
              />
            )}
          </View>

          {/* The stack stays mounted while the decorate panel is open, and the
              panel covers it as an overlay. Swapping them would change the
              column's height, which would move the scene and the mascot. */}
          <View style={styles.actionArea}>
            <View
              accessibilityElementsHidden={decorating}
              importantForAccessibility={
                decorating ? 'no-hide-descendants' : 'auto'
              }
              pointerEvents={decorating ? 'none' : 'auto'}
              style={styles.actionStack}
            >
              <FeedButton enabled={view.canFeed} onPress={onFeed} />
              <Pressable
                accessibilityLabel={`쓰다듬기, 바나나 ${HOUSE_ACTION_COST.pet}개`}
                accessibilityRole="button"
                accessibilityState={{ disabled: !view.canPet }}
                disabled={!view.canPet}
                onPress={onPet}
                style={[styles.petButton, !view.canPet && styles.spent]}
                testID="house-pet-action"
              >
                <Text style={styles.petLabel}>
                  쓰다듬기 · 바나나 {HOUSE_ACTION_COST.pet}개
                </Text>
              </Pressable>

              <WeekPanel nickname={nickname} view={view} />
            </View>

            {decorating ? (
              <DecoratePanel
                onBuyItem={onBuyItem}
                onClose={() => setDecorating(false)}
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
function Backdrop() {
  const viewport = useScale();
  const roomSource = movingHouseBackgroundSource;
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
  // The motion package has different pixel dimensions from the approved room
  // artwork. Keep both pages on the approved room's coordinate frame so the
  // mountains, path and buildings occupy the same screen position. The motion
  // scene and every sprite are stretched together inside that shared frame.
  const layoutSource = houseRoomArt.source ?? roomSource;
  const layoutModule = Array.isArray(layoutSource)
    ? layoutSource[0]
    : layoutSource;
  const resolvedLayoutSource =
    layoutModule == null
      ? null
      : Asset.fromModule(
          layoutModule as Parameters<typeof Asset.fromModule>[0],
        );
  const layoutSourceWidth =
    resolvedLayoutSource?.width != null && resolvedLayoutSource.width > 1
      ? resolvedLayoutSource.width
      : HOUSE_BACKDROP_SOURCE_SIZE.width;
  const layoutSourceHeight =
    resolvedLayoutSource?.height != null && resolvedLayoutSource.height > 1
      ? resolvedLayoutSource.height
      : HOUSE_BACKDROP_SOURCE_SIZE.height;
  const artSize = houseBackdropSize(
    viewport.width,
    viewport.height,
    layoutSourceWidth,
    layoutSourceHeight,
  );
  const blendBandHeight = Math.min(sourceHeight, HOUSE_BACKDROP_BLEND_BAND_PX);
  const continuationTop = Math.max(
    0,
    artSize.height - HOUSE_BACKDROP_BLEND_OVERLAP,
  );
  const continuationHeight = Math.max(1, viewport.height - continuationTop);
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
            <MovingHouseBackdrop size={artSize} />
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
              width={artSize.width}
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
        style={styles.bottomFade}
        testID="house-bottom-fade"
      />
    </View>
  );
}

function SpeechBubble({ text }: { text: string }) {
  return (
    <View style={styles.bubble}>
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
      <Text style={styles.feedLabel}>바나나 주기</Text>
      <BananaGlyph size={18} />
    </Pressable>
  );
}

function WeekPanel({ nickname, view }: { nickname: string; view: HouseView }) {
  const ratio = view.weekProgress ?? 0;
  const known = view.weekTargetCount !== null;

  return (
    <View style={styles.weekPanel} testID="house-week-panel">
      <Text style={styles.weekEyebrow}>{nickname}님의 이번 주 목표</Text>

      <View style={styles.weekRow}>
        <StarGlyph size={20} />
        <Text style={styles.weekTitle}>
          {known
            ? `주 ${view.weekTargetCount}회 운동하기`
            : '목표를 불러오지 못했어요'}
        </Text>
        {known ? (
          <Text style={styles.weekCount}>
            {view.weekCompletedCount} / {view.weekTargetCount} 회
          </Text>
        ) : null}
      </View>

      <View
        accessibilityLabel={
          known
            ? `이번 주 ${view.weekCompletedCount}회 완료, 목표 ${view.weekTargetCount}회`
            : '이번 주 진행도를 알 수 없어요'
        }
        accessibilityRole="progressbar"
        style={styles.progressTrack}
      >
        <View
          style={[
            styles.progressFill,
            { width: `${Math.round(ratio * 100)}%` },
          ]}
          testID="house-week-progress"
        />
      </View>

      <Text style={styles.weekNote}>
        {view.weekClosed
          ? '마감된 주예요. 리포트 탭에서 돌아볼 수 있어요.'
          : '진행 중인 주예요. 편한 날에 하나씩 채워요.'}
      </Text>
    </View>
  );
}

function DecoratePanel({
  onBuyItem,
  onClose,
  view,
}: {
  onBuyItem: (itemId: HouseItemId) => void;
  onClose: () => void;
  view: HouseView;
}) {
  return (
    <View
      style={[styles.weekPanel, styles.decoratePanel]}
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

      <ScrollView
        contentContainerStyle={styles.itemGrid}
        showsVerticalScrollIndicator={false}
        style={styles.decorateGrid}
      >
        {view.ownedItems.map((item) => (
          <View key={item.id} style={[styles.itemTile, styles.itemOwned]}>
            <HouseArtView
              showPlaceholderLabel={false}
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
      </ScrollView>

      <Text style={styles.weekNote}>
        가장 싼 물건은 바나나 {CHEAPEST_ITEM_COST}개예요.
      </Text>
    </View>
  );
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
    height: '34%',
  },
  safeArea: {
    flex: 1,
    backgroundColor: 'transparent',
  },
  column: {
    flex: 1,
    width: '100%',
    alignSelf: 'center',
    gap: spacing.sm,
    paddingHorizontal: HOUSE_HORIZONTAL_INSET,
    paddingTop: spacing.sm,
  },
  topBar: {
    alignItems: 'center',
    paddingVertical: spacing.xs,
  },
  title: {
    color: colors.brandOutline,
    fontSize: 19,
    fontWeight: '800',
  },
  stage: {
    flex: 1,
    minHeight: 210,
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
  chipCaption: {
    color: colors.textSub,
    fontSize: 10,
    fontWeight: '600',
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
    position: 'relative',
    height: 210,
    alignItems: 'center',
  },
  bubble: {
    position: 'absolute',
    bottom:
      34 + spacing.sm + HOUSE_MASCOT_SIZE + spacing.sm - HOUSE_MASCOT_Y_OFFSET,
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
    bottom: 34 + spacing.sm - HOUSE_MASCOT_Y_OFFSET,
    width: HOUSE_MASCOT_SIZE,
    height: HOUSE_MASCOT_SIZE,
  },
  placedRow: {
    position: 'absolute',
    right: 0,
    bottom: 0,
    left: 0,
    height: 34,
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'center',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  placedItem: {
    width: 34,
    height: 34,
    borderRadius: radii.control,
  },
  feedbackSlot: {
    height: 104,
    justifyContent: 'center',
  },
  feedback: {
    backgroundColor: colors.surface,
  },
  feedbackActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  retryButton: {
    alignSelf: 'flex-start',
    borderRadius: radii.control,
    borderWidth: 1,
    borderColor: colors.warningBorder,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  retryLabel: {
    color: colors.warningText,
    fontSize: 12,
    fontWeight: '700',
  },
  dismissButton: {
    alignSelf: 'flex-start',
    borderRadius: radii.control,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    backgroundColor: 'rgba(255, 255, 255, 0.62)',
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  dismissLabel: {
    color: colors.textSub,
    fontSize: 12,
    fontWeight: '700',
  },
  feedButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    overflow: 'hidden',
    borderRadius: 999,
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
    alignItems: 'center',
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    backgroundColor: 'rgba(255, 255, 255, 0.86)',
    paddingVertical: 10,
  },
  petLabel: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '700',
  },
  spent: {
    opacity: 0.45,
  },
  actionArea: {
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
  weekPanel: {
    gap: spacing.sm,
    borderRadius: 20,
    backgroundColor: colors.surface,
    padding: spacing.lg,
    marginBottom: spacing.xs,
    ...shadows.card,
  },
  weekEyebrow: {
    color: colors.textSub,
    fontSize: 12,
    fontWeight: '600',
  },
  weekRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  weekTitle: {
    flex: 1,
    minWidth: 0,
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
  },
  weekCount: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  progressTrack: {
    height: 11,
    borderRadius: 999,
    backgroundColor: colors.divider,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 999,
    backgroundColor: colors.yellowDeep,
  },
  weekNote: {
    color: colors.textSub,
    fontSize: 12,
    lineHeight: 18,
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
  itemGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  itemTile: {
    width: 78,
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
