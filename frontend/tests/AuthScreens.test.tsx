import { describe, expect, it, jest } from '@jest/globals';
import { useFonts } from 'expo-font';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import { fontFamilies } from '../src/app/fonts';
import type { AuthAdapter } from '../src/auth/firebase';
import { AuthFlow } from '../src/features/auth/AuthFlow';
import { LoginScreen } from '../src/features/auth/LoginScreen';
import { SignUpScreen } from '../src/features/auth/SignUpScreen';

const useFontsMock = jest.mocked(useFonts);

function authAdapter(overrides: Partial<AuthAdapter> = {}): AuthAdapter {
  return {
    observe: () => () => undefined,
    signIn: jest.fn(async () => undefined),
    signUp: jest.fn(async () => undefined),
    signOutUser: jest.fn(async () => undefined),
    getIdToken: jest.fn(async () => null),
    describePasswordPolicy: jest.fn(async () => '6자 이상'),
    checkPassword: jest.fn(async () => ({ ok: true }) as const),
    ...overrides,
  };
}

describe('auth visual prototypes', () => {
  it('renders Login validation and keeps field interaction local', async () => {
    const onSubmit = jest.fn();
    await render(<LoginScreen onSubmit={onSubmit} previewState="validation" />);

    expect(screen.getByText('이메일을 입력해주세요.')).toBeOnTheScreen();
    expect(screen.getByText('비밀번호는 8자 이상이에요.')).toBeOnTheScreen();
    expect(
      StyleSheet.flatten(
        screen.getByRole('header', {
          name: '오늘도 자신과의 싸움에서\n승리하러 왔군요',
        }).props.style,
      ).fontFamily,
    ).toBe(fontFamilies.loginHeading);

    const saveId = screen.getByRole('checkbox', { name: /이메일 저장/ });
    expect(saveId).not.toBeChecked();
    expect(
      screen.queryByText('다음 방문 시 이메일만 자동 입력돼요'),
    ).toBeNull();
    expect(
      screen.queryByText('로그인 상태를 유지해요 (비밀번호는 저장하지 않아요)'),
    ).toBeNull();
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

  it('updates the SignUp preview button from the edited required fields', () => {
    const onSubmit = jest.fn();
    render(<SignUpScreen onSubmit={onSubmit} />);

    expect(screen.queryByText('6자 이상 입력해주세요.')).toBeNull();
    expect(
      screen.getByText('가입 후 맞춤 루틴을 위한 기본 정보를 입력해주세요.'),
    ).toBeOnTheScreen();
    expect(
      screen.queryByText(/로그인에 사용할 계정 정보만 입력해요/),
    ).toBeNull();
    expect(
      screen.getByRole('button', { name: '필수 항목을 채워주세요' }),
    ).toBeDisabled();

    fireEvent.changeText(
      screen.getByLabelText('회원가입 이메일'),
      'new@example.com',
    );
    fireEvent.changeText(screen.getByLabelText('회원가입 비밀번호'), 'short');
    expect(
      screen.getByText('6자 이상 입력해주세요.').props.accessibilityRole,
    ).toBe('alert');
    fireEvent.changeText(
      screen.getByLabelText('회원가입 비밀번호 확인'),
      'short',
    );
    expect(
      screen.getByRole('button', { name: '필수 항목을 채워주세요' }),
    ).toBeDisabled();
    fireEvent.changeText(screen.getByLabelText('회원가입 비밀번호'), 'secret');
    expect(screen.queryByText('6자 이상 입력해주세요.')).toBeNull();
    fireEvent.changeText(
      screen.getByLabelText('회원가입 비밀번호 확인'),
      'secret',
    );

    const submitButton = screen.getByRole('button', {
      name: '가입하고 프로필 등록하기',
    });
    expect(submitButton).toBeEnabled();
    fireEvent.press(submitButton);
    expect(onSubmit).toHaveBeenCalledWith('new@example.com', 'secret');
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

  it('connects Login to Firebase and opens the separate SignUp page', async () => {
    const signIn = jest.fn(async () => undefined);
    const auth = authAdapter({ signIn });
    render(<AuthFlow auth={auth} />);

    expect(
      screen.getByRole('header', {
        name: '오늘도 자신과의 싸움에서\n승리하러 왔군요',
      }),
    ).toBeOnTheScreen();
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(
      screen.queryByRole('button', { name: 'Google로 계속하기' }),
    ).toBeNull();

    fireEvent.changeText(screen.getByLabelText('이메일'), 'user@example.com');
    fireEvent.changeText(screen.getByLabelText('비밀번호'), 'password1');
    fireEvent.press(screen.getByRole('button', { name: '로그인' }));

    await waitFor(() =>
      expect(signIn).toHaveBeenCalledWith('user@example.com', 'password1'),
    );

    fireEvent.press(screen.getByRole('button', { name: '회원가입' }));
    expect(screen.getByRole('header', { name: '회원가입' })).toBeOnTheScreen();
    expect(
      await screen.findByText('비밀번호 조건: 6자 이상'),
    ).toBeOnTheScreen();
  });

  it('connects SignUp to the Firebase password policy and account creation', async () => {
    const signUp = jest.fn(async () => undefined);
    const checkPassword = jest.fn(async () => ({ ok: true }) as const);
    const auth = authAdapter({
      checkPassword,
      describePasswordPolicy: jest.fn(
        async () => '6자 이상 · 4096자 이하 · 숫자 포함',
      ),
      signUp,
    });
    render(<SignUpScreen auth={auth} />);

    expect(
      await screen.findByText('비밀번호 조건: 6자 이상 · 숫자 포함'),
    ).toBeOnTheScreen();
    expect(screen.queryByText(/4096자 이하/)).not.toBeOnTheScreen();
    fireEvent.changeText(
      screen.getByLabelText('회원가입 이메일'),
      'new@example.com',
    );
    fireEvent.changeText(
      screen.getByLabelText('회원가입 비밀번호'),
      'password1',
    );
    fireEvent.changeText(
      screen.getByLabelText('회원가입 비밀번호 확인'),
      'password1',
    );
    fireEvent.press(
      screen.getByRole('button', { name: '가입하고 프로필 등록하기' }),
    );

    await waitFor(() =>
      expect(checkPassword).toHaveBeenCalledWith('password1'),
    );
    await waitFor(() =>
      expect(signUp).toHaveBeenCalledWith('new@example.com', 'password1'),
    );
  });
});
