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
