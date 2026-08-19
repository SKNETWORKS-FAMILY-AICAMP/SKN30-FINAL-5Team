import { describe, expect, it, jest } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react-native';

import { App } from '../src/app/App';

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });

  return { promise, reject, resolve };
}

describe('App boot navigation', () => {
  it('opens the development gallery without starting app boot', async () => {
    const bootResolver = jest.fn(async () => 'Auth' as const);

    await render(<App bootResolver={bootResolver} previewMode="gallery" />);

    expect(
      screen.getByRole('header', { name: 'Preview Gallery' }),
    ).toBeOnTheScreen();
    expect(screen.getByTestId('preview-app-canvas')).toBeOnTheScreen();
    expect(bootResolver).not.toHaveBeenCalled();
  });

  it('keeps the splash visible in explicit local preview mode', async () => {
    const bootResolver = jest.fn(async () => 'Auth' as const);

    await render(<App bootResolver={bootResolver} splashPreview />);

    expect(screen.getByRole('header', { name: '헬끼' })).toBeOnTheScreen();
    expect(screen.getByTestId('splash-island')).toBeOnTheScreen();
    expect(screen.queryByTestId('question-mark')).toBeNull();
    expect(bootResolver).not.toHaveBeenCalled();
  });

  it('opens the API-backed home preview without starting app boot', async () => {
    const bootResolver = jest.fn(async () => 'Auth' as const);

    await render(<App bootResolver={bootResolver} previewMode="today" />);

    expect(
      screen.getByRole('header', { name: 'Preview Gallery' }),
    ).toBeOnTheScreen();
    expect(
      await screen.findByRole('button', { name: '오늘 루틴 체크인' }),
    ).toBeOnTheScreen();
    expect(bootResolver).not.toHaveBeenCalled();
  });

  it.each([
    {
      mode: 'account' as const,
      label: 'Account (API)',
      readyText: '내 프로필',
    },
    {
      mode: 'mascot-house' as const,
      label: 'Mascot house (API)',
      readyText: '지금 내 루틴',
    },
    {
      mode: 'session' as const,
      label: 'Workout session (API)',
      readyText: '0 / 3 블록 완료',
    },
    {
      mode: 'session-result' as const,
      label: 'Workout result (API)',
      readyText: '오늘 운동을 마쳤어요',
    },
    {
      mode: 'weekly-report' as const,
      label: 'Weekly report (API)',
      readyText: '마감된 주',
    },
  ])(
    'opens the $mode API preview through the gallery',
    async ({ label, mode, readyText }) => {
      const bootResolver = jest.fn(async () => 'Auth' as const);

      await render(<App bootResolver={bootResolver} previewMode={mode} />);

      expect(screen.getByRole('radio', { name: label })).toBeChecked();
      expect(await screen.findByText(readyText)).toBeOnTheScreen();
      expect(screen.getByText(`단독 진입: ?preview=${mode}`)).toBeOnTheScreen();
      expect(bootResolver).not.toHaveBeenCalled();
    },
  );

  it.each([
    {
      mode: 'login' as const,
      heading: '오늘도 자신과의 싸움에서\n승리하러 왔군요',
    },
    { mode: 'profile' as const, heading: '프로필 등록' },
    { mode: 'signup' as const, heading: '회원가입' },
    { mode: 'home' as const, heading: '안녕하세요, 헬끼님!' },
    {
      mode: 'home-map' as const,
      heading: '오늘의 운동 섬이에요. 표시를 눌러 루틴을 확인해보세요.',
    },
    { mode: 'calendar-report' as const, heading: '운동 캘린더' },
    { mode: 'my-page' as const, heading: '마이페이지' },
    {
      mode: 'onboarding' as const,
      heading: '온보딩',
    },
    { mode: 'workout' as const, heading: '전신 기본 루틴' },
  ])(
    'opens the $mode direct preview without starting app boot',
    async ({ heading, mode }) => {
      const bootResolver = jest.fn(async () => 'Auth' as const);

      await render(<App bootResolver={bootResolver} previewMode={mode} />);

      expect(screen.getByRole('header', { name: heading })).toBeOnTheScreen();
      expect(bootResolver).not.toHaveBeenCalled();
    },
  );

  it('moves from splash to the resolved destination exactly once', async () => {
    const boot = createDeferred<'Auth'>();
    const bootResolver = jest.fn(() => boot.promise);
    const onNavigationTransition = jest.fn();

    await render(
      <App
        bootResolver={bootResolver}
        onNavigationTransition={onNavigationTransition}
      />,
    );

    const destinationScreen = screen.findByRole('header', {
      name: '로그인 준비 중',
    });
    boot.resolve('Auth');

    expect(await destinationScreen).toBeOnTheScreen();

    expect(bootResolver).toHaveBeenCalledTimes(1);
    expect(onNavigationTransition).toHaveBeenCalledTimes(1);
    expect(onNavigationTransition).toHaveBeenCalledWith('Auth');
  });

  it('leaves the splash recoverable when initialization fails', async () => {
    const failedBoot = createDeferred<'Auth'>();
    const successfulBoot = createDeferred<'Auth'>();
    const bootResolver = jest
      .fn<() => Promise<'Auth'>>()
      .mockImplementationOnce(() => failedBoot.promise)
      .mockImplementationOnce(() => successfulBoot.promise);

    await render(<App bootResolver={bootResolver} />);

    const retryAction = screen.findByRole('button', { name: '다시 시도' });
    failedBoot.reject(new Error('bootstrap failed'));
    const retry = await retryAction;
    fireEvent.press(retry);

    const destinationScreen = screen.findByRole('header', {
      name: '로그인 준비 중',
    });
    successfulBoot.resolve('Auth');

    expect(await destinationScreen).toBeOnTheScreen();
    expect(bootResolver).toHaveBeenCalledTimes(2);
  });
});
