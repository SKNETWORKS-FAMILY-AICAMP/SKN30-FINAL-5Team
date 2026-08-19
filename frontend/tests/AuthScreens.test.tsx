import { describe, expect, it, jest } from '@jest/globals';
import { useFonts } from 'expo-font';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import { fontFamilies } from '../src/app/fonts';
import { LoginScreen } from '../src/features/auth/LoginScreen';
import { SignUpScreen } from '../src/features/auth/SignUpScreen';

const useFontsMock = jest.mocked(useFonts);

describe('auth visual prototypes', () => {
  it('renders Login validation and keeps field interaction local', async () => {
    const onSubmit = jest.fn();
    await render(<LoginScreen onSubmit={onSubmit} previewState="validation" />);

    expect(screen.getByText('아이디를 입력해주세요.')).toBeOnTheScreen();
    expect(screen.getByText('비밀번호는 8자 이상이에요.')).toBeOnTheScreen();
    expect(
      StyleSheet.flatten(
        screen.getByRole('header', {
          name: '오늘도 자신과의 싸움에서\n승리하러 왔군요',
        }).props.style,
      ).fontFamily,
    ).toBe(fontFamilies.loginHeading);

    const saveId = screen.getByRole('checkbox', { name: /아이디 저장/ });
    expect(saveId).not.toBeChecked();
    fireEvent.press(saveId);
    expect(saveId).toBeChecked();

    fireEvent.press(screen.getByRole('button', { name: '로그인' }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('keeps a readable Login heading fallback when the local font fails', async () => {
    useFontsMock.mockReturnValueOnce([false, new Error('font unavailable')]);

    await render(<LoginScreen />);

    expect(
      StyleSheet.flatten(
        screen.getByRole('header', {
          name: '오늘도 자신과의 싸움에서\n승리하러 왔군요',
        }).props.style,
      ).fontFamily,
    ).toBeUndefined();
  });

  it('renders Login network retry and social loading mock states', async () => {
    const onRetry = jest.fn();
    const view = await render(
      <LoginScreen onRetry={onRetry} previewState="network-error" />,
    );

    fireEvent.press(screen.getByRole('button', { name: '다시 시도' }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    view.rerender(<LoginScreen previewState="social-loading" />);
    expect(screen.getByRole('alert')).toBeOnTheScreen();
    expect(screen.getByText('Google 인증 중...')).toBeOnTheScreen();
  });

  it('renders SignUp contract-reference states without completing signup', async () => {
    const onSubmit = jest.fn();
    const view = await render(
      <SignUpScreen onSubmit={onSubmit} previewState="password-mismatch" />,
    );

    expect(screen.getByText('비밀번호가 서로 달라요.')).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '필수 항목을 채워주세요' }),
    ).toBeDisabled();

    view.rerender(<SignUpScreen onSubmit={onSubmit} previewState="ready" />);
    fireEvent.press(
      screen.getByRole('button', { name: '가입하고 프로필 등록하기' }),
    );
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('renders SignUp failed feedback and exposes retry as a mock callback', async () => {
    const onSubmit = jest.fn();
    await render(<SignUpScreen onSubmit={onSubmit} previewState="failed" />);

    expect(
      screen.getByText('회원가입에 실패했어요. 잠시 후 다시 시도해주세요.'),
    ).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('button', { name: '다시 시도' }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});
