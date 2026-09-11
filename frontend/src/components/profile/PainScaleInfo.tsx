import { useRef, useState } from 'react';
import {
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
  type StyleProp,
  type TextStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { InfoGlyph } from '../InfoGlyph';
import {
  type OverlayViewportBounds,
  useOverlayViewportMeasure,
} from '../OverlayViewport';
import { colors, radii, shadows, spacing } from '../theme';

/**
 * What the pain numbers stand for, shown only when the user asks for it.
 *
 * The scale and its owner are cited separately on purpose: the 0~10 numeric
 * rating scale is the NRS, while the three bands are this service's own
 * grouping of it. This is an explanation of an input, not a diagnosis.
 */
const PAIN_SCALE_INFO_COPY = {
  scale:
    'HELKKI는 통증 정도를 0~10의 숫자로 표현하는 숫자통증등급(NRS)을 사용합니다.',
  bands:
    '본 서비스에서는 통증 정도를 "1–3 경도 / 4–6 중등도 / 7–10 심한 통증"으로 구분합니다.',
  source: '출처: 국제통증연구학회 (IASP)',
} as const;

const PAIN_SCALE_INFO_LABEL = '통증 정도 기준 안내';

const BUTTON_SIZE = 22;
const GLYPH_SIZE = 16;
const POINTER_SIZE = 10;
const BUBBLE_MAX_WIDTH = 320;
/** Keeps the bubble off the screen edges and its pointer off the corners. */
const SCREEN_GUTTER = 16;

const clamp = (value: number, low: number, high: number) =>
  Math.min(Math.max(value, low), Math.max(low, high));

type Anchor = { height: number; width: number; x: number; y: number };

type BubblePlacement = {
  maxHeight: number;
  side: 'above' | 'below';
  top: number;
};

/** Keeps the entire bubble inside the usable vertical screen area. */
export function placePainScaleBubble({
  anchor,
  bubbleHeight,
  viewportBottom,
  viewportTop = 0,
}: {
  anchor: Anchor | null;
  bubbleHeight: number | null;
  viewportBottom: number;
  viewportTop?: number;
}): BubblePlacement {
  const safeTop = viewportTop + SCREEN_GUTTER;
  const safeBottom = Math.max(safeTop, viewportBottom - SCREEN_GUTTER);
  const maxHeight = Math.max(0, safeBottom - safeTop);
  const measuredHeight = Math.min(bubbleHeight ?? 0, maxHeight);
  const belowTop = anchor
    ? anchor.y + anchor.height + spacing.xs
    : viewportTop + Math.round((viewportBottom - viewportTop) / 3);
  const fitsBelow =
    anchor === null ||
    bubbleHeight === null ||
    belowTop + measuredHeight <= safeBottom;
  const side = fitsBelow ? 'below' : 'above';
  const requestedTop =
    side === 'above' && anchor
      ? anchor.y - spacing.xs - measuredHeight
      : belowTop;

  return {
    maxHeight,
    side,
    top: clamp(requestedTop, safeTop, safeBottom - measuredHeight),
  };
}

export function placePainScaleBubbleHorizontally({
  anchor,
  viewportLeft = 0,
  viewportRight,
}: {
  anchor: Anchor | null;
  viewportLeft?: number;
  viewportRight: number;
}) {
  const safeLeft = viewportLeft + SCREEN_GUTTER;
  const safeRight = Math.max(safeLeft, viewportRight - SCREEN_GUTTER);
  const width = Math.min(BUBBLE_MAX_WIDTH, Math.max(0, safeRight - safeLeft));
  const anchorCenterX = anchor
    ? anchor.x + anchor.width / 2
    : viewportLeft + (viewportRight - viewportLeft) / 2;
  const left = clamp(anchorCenterX - width / 2, safeLeft, safeRight - width);
  const pointerLeft = clamp(
    anchorCenterX - left - POINTER_SIZE / 2,
    radii.control,
    width - radii.control - POINTER_SIZE,
  );

  return { left, pointerLeft, width };
}

/**
 * A pain section heading with the circled `i` beside it.
 *
 * The bubble lives in a transparent modal, placed against the button's measured
 * window position, for two reasons: a tap anywhere on the screen has to dismiss
 * it (the screen-level `onPointerDown` the notification popover relies on is a
 * web-only event), and inside the check-in sheet it has to draw over the safety
 * copy below rather than compete with it for a stacking order. Opening it never
 * moves the inputs underneath.
 *
 * The bubble sits in the modal beside the backdrop, not in the page behind it,
 * so a screen reader -- whose focus the modal captures -- still reaches the copy.
 */
export function PainScaleInfoHeading({
  testIDPrefix,
  title,
  titleStyle,
}: {
  testIDPrefix: string;
  title: string;
  titleStyle?: StyleProp<TextStyle>;
}) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const [bubbleHeight, setBubbleHeight] = useState<number | null>(null);
  const [overlayBounds, setOverlayBounds] =
    useState<OverlayViewportBounds | null>(null);
  const buttonRef = useRef<View | null>(null);
  const insets = useSafeAreaInsets();
  const measureOverlayViewport = useOverlayViewportMeasure();
  const { height: windowHeight, width: windowWidth } = useWindowDimensions();

  const close = () => {
    setOpen(false);
    setBubbleHeight(null);
  };
  const toggle = () => {
    if (open) {
      close();
      return;
    }
    measureOverlayViewport?.(setOverlayBounds);
    // Measured on open rather than on layout: only the window position still
    // places the bubble under the button once the modal leaves the scroll view.
    buttonRef.current?.measureInWindow((x, y, width, height) => {
      if (typeof x !== 'number' || typeof y !== 'number') return;
      setAnchor({ height, width, x, y });
    });
    setBubbleHeight(null);
    setOpen(true);
  };

  const viewport = overlayBounds ?? {
    bottom: windowHeight - insets.bottom,
    left: 0,
    right: windowWidth,
    top: insets.top,
  };
  const horizontalPlacement = placePainScaleBubbleHorizontally({
    anchor,
    viewportLeft: viewport.left,
    viewportRight: viewport.right,
  });
  const placement = placePainScaleBubble({
    anchor,
    bubbleHeight,
    viewportBottom: viewport.bottom,
    viewportTop: viewport.top,
  });

  return (
    <View style={styles.wrapper}>
      <View style={styles.row}>
        <Text style={[styles.title, titleStyle]}>{title}</Text>
        <Pressable
          accessibilityLabel={PAIN_SCALE_INFO_LABEL}
          accessibilityRole="button"
          accessibilityState={{ expanded: open }}
          hitSlop={10}
          onPress={toggle}
          ref={buttonRef}
          style={({ pressed }) => [styles.button, pressed && styles.pressed]}
          testID={`${testIDPrefix}-pain-scale-info-button`}
        >
          <InfoGlyph size={GLYPH_SIZE} />
        </Pressable>
      </View>
      {open ? (
        <Modal
          animationType="none"
          onRequestClose={close}
          statusBarTranslucent
          transparent
          visible
        >
          <View style={styles.modalRoot}>
            <Pressable
              accessibilityLabel="통증 정도 기준 안내 닫기"
              accessibilityRole="button"
              onPress={close}
              style={styles.backdrop}
              testID={`${testIDPrefix}-pain-scale-info-backdrop`}
            />
            <View
              accessibilityLiveRegion="polite"
              onLayout={(event) => {
                const nextHeight = event.nativeEvent.layout.height;
                setBubbleHeight((current) =>
                  current === nextHeight ? current : nextHeight,
                );
              }}
              style={[
                styles.bubble,
                {
                  left: horizontalPlacement.left,
                  maxHeight: placement.maxHeight,
                  top: placement.top,
                  width: horizontalPlacement.width,
                },
              ]}
              testID={`${testIDPrefix}-pain-scale-info-bubble`}
            >
              {anchor ? (
                <View
                  pointerEvents="none"
                  style={[
                    styles.pointer,
                    placement.side === 'above'
                      ? styles.pointerBelow
                      : styles.pointerAbove,
                    { left: horizontalPlacement.pointerLeft },
                  ]}
                  testID={`${testIDPrefix}-pain-scale-info-pointer`}
                />
              ) : null}
              <ScrollView
                contentContainerStyle={styles.bubbleContent}
                nestedScrollEnabled
                showsVerticalScrollIndicator
              >
                <Text style={styles.bubbleBody}>
                  {PAIN_SCALE_INFO_COPY.scale}
                </Text>
                <Text style={styles.bubbleBody}>
                  {PAIN_SCALE_INFO_COPY.bands}
                </Text>
                <Text style={styles.bubbleSource}>
                  {PAIN_SCALE_INFO_COPY.source}
                </Text>
              </ScrollView>
            </View>
          </View>
        </Modal>
      ) : null}
    </View>
  );
}

const keepAll = Platform.OS === 'web' ? { wordBreak: 'keep-all' as const } : {};

const styles = StyleSheet.create({
  wrapper: { alignSelf: 'stretch' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  title: { color: colors.text, fontSize: 14, fontWeight: '700' },
  button: {
    width: BUTTON_SIZE,
    height: BUTTON_SIZE,
    flexShrink: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: { opacity: 0.6 },
  modalRoot: { flex: 1 },
  /** Transparent on purpose: it only has to catch the dismissing tap. */
  backdrop: StyleSheet.absoluteFill,
  bubble: {
    position: 'absolute',
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderRadius: radii.control,
    backgroundColor: colors.surface,
    ...shadows.card,
  },
  bubbleContent: {
    gap: 3,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  pointer: {
    position: 'absolute',
    zIndex: 1,
    width: POINTER_SIZE,
    height: POINTER_SIZE,
    borderColor: colors.borderSoft,
    backgroundColor: colors.surface,
    transform: [{ rotate: '45deg' }],
  },
  pointerAbove: {
    top: -POINTER_SIZE / 2,
    borderTopWidth: 1,
    borderLeftWidth: 1,
  },
  pointerBelow: {
    bottom: -POINTER_SIZE / 2,
    borderRightWidth: 1,
    borderBottomWidth: 1,
  },
  bubbleBody: {
    color: colors.textSub,
    fontSize: 12,
    fontWeight: '500',
    lineHeight: 17,
    ...keepAll,
  },
  bubbleSource: {
    color: colors.textFaint,
    fontSize: 11,
    fontWeight: '400',
    lineHeight: 16,
    ...keepAll,
  },
});
