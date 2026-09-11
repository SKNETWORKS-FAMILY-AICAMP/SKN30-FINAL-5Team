import { useRef, useState } from 'react';
import {
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
  type StyleProp,
  type TextStyle,
} from 'react-native';

import { InfoGlyph } from '../InfoGlyph';
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
  const buttonRef = useRef<View | null>(null);
  const { height: windowHeight, width: windowWidth } = useWindowDimensions();

  const close = () => setOpen(false);
  const toggle = () => {
    if (open) {
      close();
      return;
    }
    // Measured on open rather than on layout: only the window position still
    // places the bubble under the button once the modal leaves the scroll view.
    buttonRef.current?.measureInWindow((x, y, width, height) => {
      if (typeof x !== 'number' || typeof y !== 'number') return;
      setAnchor({ height, width, x, y });
    });
    setOpen(true);
  };

  const bubbleWidth = Math.min(
    BUBBLE_MAX_WIDTH,
    Math.max(0, windowWidth - SCREEN_GUTTER * 2),
  );
  const anchorCenterX = anchor ? anchor.x + anchor.width / 2 : windowWidth / 2;
  const bubbleLeft = clamp(
    anchorCenterX - bubbleWidth / 2,
    SCREEN_GUTTER,
    windowWidth - SCREEN_GUTTER - bubbleWidth,
  );
  // Without a measurement the copy still has to be readable, so it falls back to
  // the upper third of the screen and drops the pointer that would lie.
  const bubbleTop = anchor
    ? anchor.y + anchor.height + spacing.xs
    : Math.round(windowHeight / 3);
  const pointerLeft = clamp(
    anchorCenterX - bubbleLeft - POINTER_SIZE / 2,
    radii.control,
    bubbleWidth - radii.control - POINTER_SIZE,
  );

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
          <Pressable
            accessibilityLabel="통증 정도 기준 안내 닫기"
            accessibilityRole="button"
            onPress={close}
            style={styles.backdrop}
            testID={`${testIDPrefix}-pain-scale-info-backdrop`}
          >
            <View
              accessibilityLiveRegion="polite"
              style={[
                styles.bubble,
                { left: bubbleLeft, top: bubbleTop, width: bubbleWidth },
              ]}
              testID={`${testIDPrefix}-pain-scale-info-bubble`}
            >
              {anchor ? (
                <View
                  pointerEvents="none"
                  style={[styles.pointer, { left: pointerLeft }]}
                  testID={`${testIDPrefix}-pain-scale-info-pointer`}
                />
              ) : null}
              <Text style={styles.bubbleBody}>
                {PAIN_SCALE_INFO_COPY.scale}
              </Text>
              <Text style={styles.bubbleBody}>
                {PAIN_SCALE_INFO_COPY.bands}
              </Text>
              <Text style={styles.bubbleSource}>
                {PAIN_SCALE_INFO_COPY.source}
              </Text>
            </View>
          </Pressable>
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
  /** Transparent on purpose: it only has to catch the dismissing tap. */
  backdrop: { flex: 1 },
  bubble: {
    position: 'absolute',
    gap: 3,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    borderRadius: radii.control,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    ...shadows.card,
  },
  pointer: {
    position: 'absolute',
    top: -POINTER_SIZE / 2,
    width: POINTER_SIZE,
    height: POINTER_SIZE,
    borderTopWidth: 1,
    borderLeftWidth: 1,
    borderColor: colors.borderSoft,
    backgroundColor: colors.surface,
    transform: [{ rotate: '45deg' }],
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
