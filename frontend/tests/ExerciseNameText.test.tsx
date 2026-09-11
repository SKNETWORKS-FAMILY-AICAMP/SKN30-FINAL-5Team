import { describe, expect, it } from '@jest/globals';
import { render, screen } from '@testing-library/react-native';
import { Platform } from 'react-native';

import {
  ExerciseNameText,
  keepExerciseNameWordsTogether,
} from '../src/components/ExerciseNameText';

describe('ExerciseNameText', () => {
  it('keeps whitespace as wrapping boundaries and joins characters within words', () => {
    expect(keepExerciseNameWordsTogether('전신 근력 스트레칭')).toBe(
      '전\u2060신 근\u2060력 스\u2060트\u2060레\u2060칭',
    );
    expect(keepExerciseNameWordsTogether('워밍업\n가벼운 걷기')).toBe(
      '워\u2060밍\u2060업\n가\u2060벼\u2060운 걷\u2060기',
    );
  });

  it('uses the native Hangul word strategy and keeps the raw accessibility label', () => {
    render(
      <ExerciseNameText testID="exercise-name">
        전신 근력 스트레칭
      </ExerciseNameText>,
    );

    expect(screen.getByTestId('exercise-name').props).toMatchObject({
      accessibilityLabel: '전신 근력 스트레칭',
      android_hyphenationFrequency: 'none',
      lineBreakStrategyIOS: 'hangul-word',
      textBreakStrategy: 'highQuality',
    });
  });

  it('adds invisible word joiners only to Android display text', () => {
    const originalPlatform = Platform.OS;
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: 'android',
    });

    try {
      render(
        <ExerciseNameText testID="android-exercise-name">
          전신 스트레칭
        </ExerciseNameText>,
      );

      const text = screen.getByTestId('android-exercise-name');
      expect(text.props.children).toBe('전\u2060신 스\u2060트\u2060레\u2060칭');
      expect(text.props.accessibilityLabel).toBe('전신 스트레칭');
    } finally {
      Object.defineProperty(Platform, 'OS', {
        configurable: true,
        value: originalPlatform,
      });
    }
  });
});
