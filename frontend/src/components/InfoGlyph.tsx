import { StyleSheet, View } from 'react-native';

import { colors } from './theme';

/**
 * A circled `i`, marking copy that explains a rule.
 *
 * Drawn from Views rather than a character: single glyphs render
 * inconsistently across platforms. The house drew it first; the pain sections
 * need the same mark, so it lives here instead of inside either feature.
 */
export function InfoGlyph({
  color = colors.textMuted,
  size = 14,
}: {
  color?: string;
  size?: number;
}) {
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
          borderColor: color,
          gap: size * 0.09,
        },
      ]}
    >
      <View
        style={{
          width: Math.max(1.5, size * 0.12),
          height: Math.max(1.5, size * 0.12),
          borderRadius: size * 0.06,
          backgroundColor: color,
        }}
      />
      <View
        style={{
          width: Math.max(1.5, size * 0.12),
          height: size * 0.32,
          borderRadius: size * 0.06,
          backgroundColor: color,
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  centered: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
