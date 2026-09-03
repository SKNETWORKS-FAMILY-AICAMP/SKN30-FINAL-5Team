/**
 * Renders an art slot, and the small glyphs the house needs.
 *
 * A slot with artwork renders as an image. A slot still waiting on artwork
 * renders as a labelled placeholder of the same footprint, so the layout does
 * not move when the real asset arrives.
 *
 * `fit` matters for the room: a full-bleed backdrop must cover its frame and
 * crop, never letterbox. Everything else defaults to `contain`.
 *
 * The glyphs are drawn from Views for the same reason `TabIcon` is: single
 * characters render inconsistently across platforms, and the house does not
 * justify an icon package.
 */

import {
  Image,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { imageAssets } from '../../assets';
import { colors, radii } from '../../components/theme';
import type { HouseArtSlot } from './houseArtSlots';

export function HouseArtView({
  slot,
  style,
  showPlaceholderLabel = true,
  showPlaceholderOutline = true,
}: {
  slot: HouseArtSlot;
  style?: StyleProp<ViewStyle>;
  /** Off for small tiles, where the caption sits outside the frame. */
  showPlaceholderLabel?: boolean;
  /** Off for placed decorations, which should look like objects, not slots. */
  showPlaceholderOutline?: boolean;
}) {
  if (slot.source !== null) {
    return (
      <View style={[styles.frame, style]} testID={`house-art-${slot.id}`}>
        <Image
          accessibilityLabel={slot.label}
          resizeMode={slot.fit ?? 'contain'}
          source={slot.source}
          style={styles.image}
        />
      </View>
    );
  }

  return (
    <View
      accessibilityLabel={`${slot.label} (준비 중)`}
      style={[
        styles.frame,
        styles.placeholder,
        !showPlaceholderOutline && styles.placeholderWithoutOutline,
        { backgroundColor: slot.fill, borderColor: slot.outline },
        style,
      ]}
      testID={`house-art-${slot.id}`}
    >
      {showPlaceholderLabel ? (
        <Text numberOfLines={2} style={styles.placeholderLabel}>
          {slot.label}
        </Text>
      ) : null}
    </View>
  );
}

/** The shared banana artwork used throughout the house and its mini-game. */
export function BananaGlyph({ size = 16 }: { size?: number }) {
  return (
    <Image
      accessible={false}
      accessibilityElementsHidden
      importantForAccessibility="no"
      resizeMode="contain"
      source={imageAssets.banana}
      style={{ width: size, height: size }}
      testID="house-banana-asset"
    />
  );
}

/** A gift box: a lid, a body and a ribbon down the middle. */
export function GiftGlyph({ size = 18 }: { size?: number }) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no"
      style={[styles.gift, { width: size, height: size }]}
    >
      <View style={styles.giftLid} />
      <View style={styles.giftBody} />
      <View style={styles.giftRibbon} />
    </View>
  );
}

/** A six-point star, drawn as two triangles. */
export function StarGlyph({ size = 16 }: { size?: number }) {
  const half = size / 2;
  const triangle = {
    borderLeftWidth: half,
    borderRightWidth: half,
    borderBottomWidth: size * 0.72,
  };
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no"
      style={[styles.star, { width: size, height: size }]}
    >
      <View style={[styles.starTriangle, triangle, styles.starUp]} />
      <View style={[styles.starTriangle, triangle, styles.starDown]} />
    </View>
  );
}

/** Two lobes over a rotated square. Fills for a level reached, pales for one not. */
export function HeartGlyph({
  size = 14,
  filled = true,
}: {
  size?: number;
  filled?: boolean;
}) {
  const color = filled ? colors.danger : colors.disabledFill;
  const lobe = {
    position: 'absolute' as const,
    width: size * 0.52,
    height: size * 0.52,
    borderRadius: size * 0.26,
    backgroundColor: color,
    top: size * 0.12,
  };
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no"
      style={{ width: size, height: size }}
    >
      <View style={[lobe, { left: size * 0.08 }]} />
      <View style={[lobe, { left: size * 0.4 }]} />
      <View
        style={{
          position: 'absolute',
          width: size * 0.64,
          height: size * 0.64,
          left: size * 0.18,
          top: size * 0.2,
          backgroundColor: color,
          transform: [{ rotate: '45deg' }],
        }}
      />
    </View>
  );
}

/** A teardrop with one sharp corner pointing up. Marks the visit streak. */
export function FlameGlyph({ size = 16 }: { size?: number }) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no"
      style={[styles.centered, { width: size, height: size }]}
    >
      <View
        style={{
          width: size * 0.66,
          height: size * 0.66,
          borderRadius: size * 0.33,
          borderTopLeftRadius: 0,
          backgroundColor: colors.warningText,
          transform: [{ rotate: '45deg' }],
        }}
      />
    </View>
  );
}

/** A clipboard with a clip and two lines. Marks the quest tile. */
export function ClipboardGlyph({ size = 22 }: { size?: number }) {
  const line = {
    width: size * 0.42,
    height: Math.max(1.5, size * 0.09),
    borderRadius: size * 0.05,
    backgroundColor: colors.textSub,
  };
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no"
      style={[styles.centered, { width: size, height: size }]}
    >
      <View
        style={{
          position: 'absolute',
          top: 0,
          width: size * 0.36,
          height: size * 0.16,
          borderRadius: size * 0.06,
          backgroundColor: colors.textSub,
          zIndex: 1,
        }}
      />
      <View
        style={{
          width: size * 0.76,
          height: size * 0.88,
          marginTop: size * 0.08,
          borderRadius: size * 0.14,
          borderWidth: Math.max(1.5, size * 0.08),
          borderColor: colors.textSub,
          backgroundColor: colors.surface,
          alignItems: 'center',
          justifyContent: 'center',
          gap: size * 0.12,
        }}
      >
        <View style={line} />
        <View style={line} />
      </View>
    </View>
  );
}

/** A bulb over a base. Marks the intimacy bonus row. */
export function BulbGlyph({ size = 18 }: { size?: number }) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no"
      style={[styles.centered, { width: size, height: size }]}
    >
      <View
        style={{
          width: size * 0.62,
          height: size * 0.62,
          borderRadius: size * 0.31,
          backgroundColor: colors.primary,
        }}
      />
      <View
        style={{
          width: size * 0.34,
          height: size * 0.16,
          marginTop: size * 0.04,
          borderRadius: size * 0.06,
          backgroundColor: colors.primaryBusy,
        }}
      />
    </View>
  );
}

/** A plus sign. Opens the list of ways to earn bananas. */
export function PlusGlyph({
  size = 14,
  color = colors.textSub,
}: {
  size?: number;
  color?: string;
}) {
  const bar = {
    position: 'absolute' as const,
    borderRadius: size * 0.1,
    backgroundColor: color,
  };
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no"
      style={[styles.centered, { width: size, height: size }]}
    >
      <View
        style={[bar, { width: size, height: Math.max(1.5, size * 0.16) }]}
      />
      <View
        style={[bar, { width: Math.max(1.5, size * 0.16), height: size }]}
      />
    </View>
  );
}

/** A chevron pointing right, for a row that opens something. */
export function ChevronGlyph({
  size = 14,
  color = colors.textMuted,
}: {
  size?: number;
  color?: string;
}) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no"
      style={[styles.centered, { width: size, height: size }]}
    >
      <View
        style={{
          width: size * 0.46,
          height: size * 0.46,
          marginLeft: -size * 0.12,
          borderTopWidth: Math.max(1.5, size * 0.13),
          borderRightWidth: Math.max(1.5, size * 0.13),
          borderColor: color,
          transform: [{ rotate: '45deg' }],
        }}
      />
    </View>
  );
}

/** A circled `i`, marking copy that explains a rule. */
export function InfoGlyph({ size = 14 }: { size?: number }) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no"
      style={[
        styles.centered,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          borderWidth: Math.max(1, size * 0.09),
          borderColor: colors.textMuted,
          gap: size * 0.09,
        },
      ]}
    >
      <View
        style={{
          width: Math.max(1.5, size * 0.12),
          height: Math.max(1.5, size * 0.12),
          borderRadius: size * 0.06,
          backgroundColor: colors.textMuted,
        }}
      />
      <View
        style={{
          width: Math.max(1.5, size * 0.12),
          height: size * 0.32,
          borderRadius: size * 0.06,
          backgroundColor: colors.textMuted,
        }}
      />
    </View>
  );
}

/** A roof over a body. Used by the 집 꾸미기 chip. */
export function HouseMarkGlyph({
  size = 20,
  color = colors.brandOutline,
}: {
  size?: number;
  color?: string;
}) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no"
      style={[styles.centered, { width: size, height: size }]}
    >
      <View
        style={{
          width: 0,
          height: 0,
          borderLeftWidth: size * 0.5,
          borderRightWidth: size * 0.5,
          borderBottomWidth: size * 0.42,
          borderLeftColor: 'transparent',
          borderRightColor: 'transparent',
          borderBottomColor: color,
        }}
      />
      <View
        style={{
          width: size * 0.68,
          height: size * 0.44,
          borderWidth: Math.max(1.5, size * 0.1),
          borderTopWidth: 0,
          borderColor: color,
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  image: {
    width: '100%',
    height: '100%',
  },
  placeholder: {
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderRadius: radii.control,
    padding: 4,
  },
  placeholderLabel: {
    color: colors.textSub,
    fontSize: 10,
    lineHeight: 14,
    textAlign: 'center',
  },
  placeholderWithoutOutline: {
    borderWidth: 0,
  },
  gift: {
    alignItems: 'center',
    justifyContent: 'flex-end',
  },
  giftLid: {
    width: '100%',
    height: '26%',
    borderRadius: 2,
    backgroundColor: colors.yellowDeep,
  },
  giftBody: {
    width: '86%',
    height: '62%',
    marginTop: 1,
    borderRadius: 2,
    backgroundColor: colors.yellow,
  },
  giftRibbon: {
    position: 'absolute',
    width: '18%',
    height: '100%',
    backgroundColor: colors.warningText,
  },
  star: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  starTriangle: {
    position: 'absolute',
    width: 0,
    height: 0,
    backgroundColor: 'transparent',
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    borderBottomColor: colors.yellowDeep,
  },
  starUp: {
    top: 0,
  },
  starDown: {
    bottom: 0,
    transform: [{ rotate: '180deg' }],
  },
  centered: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
