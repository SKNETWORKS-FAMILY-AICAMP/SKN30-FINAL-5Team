import { describe, expect, it, jest } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { StyleSheet, Text } from 'react-native';

import {
  Button,
  Card,
  InlineFeedback,
  type InlineFeedbackTone,
  TextField,
} from '../src/components/primitives';
import { colors, radii } from '../src/components/theme';

const feedbackCases: {
  tone: InlineFeedbackTone;
  backgroundColor: string;
}[] = [
  { tone: 'success', backgroundColor: colors.successSurface },
  { tone: 'warning', backgroundColor: colors.warningSurface },
  { tone: 'error', backgroundColor: colors.dangerSurface },
];

describe('prototype primitives', () => {
  it('renders an interactive primary button and a non-interactive disabled button', async () => {
    const onPress = jest.fn();
    await render(
      <>
        <Button label="로그인" onPress={onPress} />
        <Button disabled label="다음" onPress={onPress} />
      </>,
    );

    fireEvent.press(screen.getByRole('button', { name: '로그인' }));

    expect(onPress).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: '다음' })).toBeDisabled();
  });

  it('keeps Card layout relative and allows a screen-local style override', async () => {
    await render(
      <Card testID="profile-card" style={{ padding: 22 }}>
        <Text>프로필</Text>
      </Card>,
    );

    const style = StyleSheet.flatten(
      screen.getByTestId('profile-card').props.style,
    );
    expect(style.position).toBeUndefined();
    expect(style.borderRadius).toBe(radii.card);
    expect(style.padding).toBe(22);
  });

  it('renders TextField labels, trailing content, and field errors', async () => {
    await render(
      <TextField
        accessibilityLabel="비밀번호"
        error="비밀번호를 입력해 주세요."
        label="비밀번호"
        placeholder="비밀번호"
        trailing={<Text>표시</Text>}
      />,
    );

    expect(screen.getByLabelText('비밀번호')).toBeOnTheScreen();
    expect(screen.getByText('표시')).toBeOnTheScreen();
    expect(screen.getByRole('alert')).toHaveTextContent(
      '비밀번호를 입력해 주세요.',
    );
  });

  it.each(feedbackCases)(
    'renders the $tone inline feedback tone',
    async ({ tone, backgroundColor }) => {
      const view = await render(
        <InlineFeedback
          message={`${tone} feedback`}
          testID={`${tone}-feedback`}
          tone={tone}
        />,
      );

      expect(
        StyleSheet.flatten(view.getByTestId(`${tone}-feedback`).props.style)
          .backgroundColor,
      ).toBe(backgroundColor);
    },
  );
});
