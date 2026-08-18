import { describe, expect, it, jest } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import { ProfileScreen } from '../src/features/profile/ProfileScreen';

describe('ProfileScreen visual prototype', () => {
  it('moves between the 14 local visual steps without saving', async () => {
    const onStepChange = jest.fn();
    await render(<ProfileScreen onStepChange={onStepChange} />);

    expect(screen.getByText('1 / 14')).toBeOnTheScreen();
    expect(screen.getByText('앱에서 어떻게 불러드릴까요?')).toBeOnTheScreen();
    expect(
      StyleSheet.flatten(screen.getByTestId('profile-progress').props.style)
        .width,
    ).toBe('7%');

    fireEvent.press(screen.getByRole('button', { name: '다음' }));
    expect(screen.getByText('2 / 14')).toBeOnTheScreen();
    expect(screen.getByText('생년월일을 알려주세요')).toBeOnTheScreen();
    expect(onStepChange).toHaveBeenCalledWith(2);
  });

  it('shows body validation without pretending to save profile data', async () => {
    await render(
      <ProfileScreen initialStep={4} previewState="validation-error" />,
    );

    expect(
      screen.getByText('키와 체중을 입력해야 등록을 완료할 수 있어요.'),
    ).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '입력이 필요해요' }),
    ).toBeDisabled();
  });

  it('opens summary rows for editing and exposes save retry as a callback', async () => {
    const onFinish = jest.fn();
    const view = await render(
      <ProfileScreen initialStep={14} onFinish={onFinish} />,
    );

    fireEvent.press(
      screen.getByRole('button', { name: '키 · 체중 (필수) 수정' }),
    );
    expect(screen.getByText('4 / 14')).toBeOnTheScreen();

    view.rerender(
      <ProfileScreen onFinish={onFinish} previewState="save-error" />,
    );
    expect(
      screen.getByText(
        '프로필 저장에 실패했어요. 저장이 완료되지 않으면 홈을 이용할 수 없어요.',
      ),
    ).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('button', { name: '다시 시도' }));
    expect(onFinish).toHaveBeenCalledTimes(1);
  });

  it('renders exit and completion overlays as mock-only states', async () => {
    const view = await render(<ProfileScreen previewState="exit" />);
    expect(screen.getByText('등록을 중단할까요?')).toBeOnTheScreen();

    view.rerender(<ProfileScreen previewState="done" />);
    expect(screen.getByText('프로필 등록 완료')).toBeOnTheScreen();
    expect(screen.getByText('로그인 화면으로')).toBeOnTheScreen();
  });
});
