/**
 * Regression coverage for the demo sign-up/sign-in gate.
 *
 * Two failures made a valid demo account impossible to create: the screen
 * gated on a hardcoded 6-character rule while the Firebase project enforced
 * its own policy, and every mapped Korean auth message was replaced by the
 * generic API fallback before it reached the screen.
 */

import { jest } from '@jest/globals';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';

import { messageForError } from '../src/api/errors';
import { AuthFailure, type AuthAdapter } from '../src/auth/firebase';
import { SignInScreen } from '../src/features/auth/SignInScreen';

function adapter(overrides: Partial<AuthAdapter> = {}): AuthAdapter {
  return {
    observe: () => () => undefined,
    signIn: jest.fn(async () => undefined),
    signUp: jest.fn(async () => undefined),
    signOutUser: jest.fn(async () => undefined),
    getIdToken: jest.fn(async () => null),
    describePasswordPolicy: jest.fn(async () => null),
    checkPassword: jest.fn(async () => ({ ok: true }) as const),
    ...overrides,
  };
}

async function fillCredentials(password: string) {
  fireEvent.changeText(
    screen.getByPlaceholderText('demo@example.com'),
    'a@b.com',
  );
  fireEvent.changeText(screen.getByPlaceholderText('비밀번호'), password);
}

describe('sign-in password policy', () => {
  it('states the project policy instead of a hardcoded minimum', async () => {
    const auth = adapter({
      describePasswordPolicy: jest.fn(async () => '8자 이상 · 숫자 포함'),
    });

    await render(<SignInScreen auth={auth} />);
    fireEvent.press(
      screen.getByRole('button', { name: '계정이 없어요. 회원가입하기' }),
    );
    // The policy resolves in an effect after the first paint; flush it so the
    // hint is asserted on settled output.
    await act(async () => undefined);

    expect(
      screen.getByText('비밀번호 조건: 8자 이상 · 숫자 포함'),
    ).toBeOnTheScreen();
  });

  it('shows which requirement failed rather than a generic error', async () => {
    const signUp = jest.fn(async () => undefined);
    const auth = adapter({
      signUp,
      checkPassword: jest.fn(async () => ({
        ok: false as const,
        code: 'auth/password-does-not-meet-requirements',
        message: '비밀번호가 조건을 충족하지 않습니다: 숫자 포함',
      })),
    });

    await render(<SignInScreen auth={auth} />);
    fireEvent.press(
      screen.getByRole('button', { name: '계정이 없어요. 회원가입하기' }),
    );
    await fillCredentials('password');
    fireEvent.press(screen.getByRole('button', { name: '회원가입하고 시작' }));

    await waitFor(() =>
      expect(
        screen.getByText('비밀번호가 조건을 충족하지 않습니다: 숫자 포함'),
      ).toBeOnTheScreen(),
    );
    expect(signUp).not.toHaveBeenCalled();
  });

  it('accepts a password the project policy allows even below six characters', async () => {
    const signUp = jest.fn(async () => undefined);
    const auth = adapter({ signUp });

    await render(<SignInScreen auth={auth} />);
    fireEvent.press(
      screen.getByRole('button', { name: '계정이 없어요. 회원가입하기' }),
    );
    await fillCredentials('ab1X');
    fireEvent.press(screen.getByRole('button', { name: '회원가입하고 시작' }));

    await waitFor(() => expect(signUp).toHaveBeenCalledWith('a@b.com', 'ab1X'));
  });

  it('does not gate sign-in on the policy, so an older password still works', async () => {
    const signIn = jest.fn(async () => undefined);
    const checkPassword = jest.fn(async () => ({
      ok: false as const,
      code: 'auth/password-does-not-meet-requirements',
      message: '비밀번호가 조건을 충족하지 않습니다: 특수문자 포함',
    }));
    const auth = adapter({ signIn, checkPassword });

    await render(<SignInScreen auth={auth} />);
    await fillCredentials('legacy-password');
    fireEvent.press(screen.getByRole('button', { name: '로그인' }));

    await waitFor(() =>
      expect(signIn).toHaveBeenCalledWith('a@b.com', 'legacy-password'),
    );
    expect(checkPassword).not.toHaveBeenCalled();
  });

  it('explains why a rejected session sent the user back here', async () => {
    await render(
      <SignInScreen auth={adapter()} notice="유효하지 않은 인증 토큰입니다." />,
    );

    expect(
      screen.getByText('유효하지 않은 인증 토큰입니다.'),
    ).toBeOnTheScreen();
  });

  it('surfaces the mapped Firebase reason for a failed sign-up', async () => {
    const auth = adapter({
      signUp: jest.fn(async () => {
        throw new AuthFailure(
          'auth/email-already-in-use',
          '이미 가입된 이메일입니다.',
        );
      }),
    });

    await render(<SignInScreen auth={auth} />);
    fireEvent.press(
      screen.getByRole('button', { name: '계정이 없어요. 회원가입하기' }),
    );
    await fillCredentials('password1');
    fireEvent.press(screen.getByRole('button', { name: '회원가입하고 시작' }));

    await waitFor(() =>
      expect(screen.getByText('이미 가입된 이메일입니다.')).toBeOnTheScreen(),
    );
  });
});

describe('messageForError', () => {
  it('keeps the localized auth message instead of the API fallback', () => {
    expect(
      messageForError(
        new AuthFailure(
          'auth/invalid-credential',
          '이메일 또는 비밀번호를 확인해주세요.',
        ),
      ),
    ).toBe('이메일 또는 비밀번호를 확인해주세요.');
  });

  it('still falls back for errors with no user-safe copy', () => {
    expect(messageForError(new Error('Firebase: internal error'))).toBe(
      '요청을 처리하지 못했습니다.',
    );
  });
});
