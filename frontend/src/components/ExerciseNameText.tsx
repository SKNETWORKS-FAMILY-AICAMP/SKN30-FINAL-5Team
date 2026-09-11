import type { ComponentProps } from 'react';
import { Platform, Text, type TextStyle } from 'react-native';

const WORD_JOINER = '\u2060';

type ExerciseNameTextProps = Omit<ComponentProps<typeof Text>, 'children'> & {
  children: string;
};

/**
 * Keep each whitespace-delimited part of an exercise name together.
 *
 * Android does not expose the Hangul word-break strategy that iOS provides,
 * so invisible Unicode word joiners supply the missing break boundary there.
 * Normal spaces and explicit newlines remain valid wrapping points.
 */
export function keepExerciseNameWordsTogether(value: string): string {
  return value
    .split(/(\s+)/u)
    .map((part) =>
      /^\s+$/u.test(part) ? part : Array.from(part).join(WORD_JOINER),
    )
    .join('');
}

export function ExerciseNameText({
  accessibilityLabel,
  android_hyphenationFrequency = 'none',
  children,
  lineBreakStrategyIOS = 'hangul-word',
  style,
  textBreakStrategy = 'highQuality',
  ...props
}: ExerciseNameTextProps) {
  const visibleText =
    Platform.OS === 'android'
      ? keepExerciseNameWordsTogether(children)
      : children;

  return (
    <Text
      {...props}
      accessibilityLabel={accessibilityLabel ?? children}
      android_hyphenationFrequency={android_hyphenationFrequency}
      lineBreakStrategyIOS={lineBreakStrategyIOS}
      style={[webKeepAllStyle, style]}
      textBreakStrategy={textBreakStrategy}
    >
      {visibleText}
    </Text>
  );
}

// `wordBreak` is supported by react-native-web but is not part of React
// Native's cross-platform TextStyle type.
const webKeepAllStyle =
  Platform.OS === 'web'
    ? ({ wordBreak: 'keep-all' } as unknown as TextStyle)
    : undefined;
