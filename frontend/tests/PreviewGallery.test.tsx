import { describe, expect, it, jest } from '@jest/globals';
import { processColor, StyleSheet } from 'react-native';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react-native';

import { localDateString, weekStartString } from '../src/api/useAsync';
import { formatHomeDate } from '../src/features/home/homeModel';
import { PreviewGallery } from '../src/features/preview/PreviewGallery';
import { homePreviewProps } from '../src/features/preview/homePreview';
import { getWorkoutResponsiveLayout } from '../src/features/workout/workoutModel';

jest.mock('expo-asset', () => ({
  Asset: {
    fromModule: () => ({
      uri: 'http://localhost/assets/preview/barbell-deadlift.gif',
    }),
  },
}));

describe('PreviewGallery', () => {
  it('keeps development controls outside the 390 x 844 app canvas', async () => {
    await render(<PreviewGallery />);

    expect(screen.getByText('DEVELOPMENT ONLY')).toBeOnTheScreen();
    expect(screen.getByRole('radio', { name: 'Splash (API)' })).toBeChecked();
    expect(screen.getByRole('header', { name: '헬끼' })).toBeOnTheScreen();

    const canvasStyle = StyleSheet.flatten(
      screen.getByTestId('preview-app-canvas').props.style,
    );
    expect(canvasStyle.width).toBe(390);
    expect(canvasStyle.height).toBe(844);
    expect(
      within(screen.getByTestId('preview-app-canvas')).queryByText(
        'DEVELOPMENT ONLY',
      ),
    ).toBeNull();
  });

  it('groups real app UI separately from mock-only alternatives', async () => {
    await render(<PreviewGallery />);

    expect(screen.getByText('Auth')).toBeOnTheScreen();
    expect(screen.getByText('Workout')).toBeOnTheScreen();
    expect(screen.getByText('Calendar / report')).toBeOnTheScreen();
    expect(
      screen.getByRole('radio', { name: 'Auth (mock)' }),
    ).toBeOnTheScreen();
    expect(
      screen.getByRole('radio', { name: 'Login (API)' }),
    ).toBeOnTheScreen();
    expect(
      screen.getByRole('radio', { name: 'SignUp (API)' }),
    ).toBeOnTheScreen();
    expect(
      screen.getByRole('radio', { name: 'Workout session (mock)' }),
    ).toBeOnTheScreen();
    expect(
      screen.getByRole('radio', { name: 'Exercise catalog (API)' }),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Login (API)' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByRole('header', {
        name: '오늘도 자신과의 싸움에서\n승리하러 왔군요',
      }),
    ).toBeOnTheScreen();
    fireEvent.press(
      within(screen.getByTestId('preview-app-canvas')).getByRole('button', {
        name: '회원가입',
      }),
    );
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByRole('header', {
        name: '회원가입',
      }),
    ).toBeOnTheScreen();
  });

  it('switches Splash between pending and error mock states', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'error' }));
    expect(screen.getByText('앱을 시작하지 못했어요')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: '다시 시도' }));
    expect(screen.queryByText('앱을 시작하지 못했어요')).not.toBeOnTheScreen();
    expect(screen.getByRole('radio', { name: 'pending' })).toBeChecked();
  });

  it('compares the production loading UI used by each main tab', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Page loading (API)' }));
    const canvas = within(screen.getByTestId('preview-app-canvas'));

    expect(canvas.getByText('오늘 상태를 불러오는 중이에요')).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=loading')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '끼끼의 집' }));
    expect(canvas.getByText('불러오는 중이에요')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '운동 캘린더' }));
    expect(
      canvas.getByRole('header', { name: '운동 캘린더' }),
    ).toBeOnTheScreen();
    expect(canvas.getByText('운동 기록을 불러오고 있어요')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '마이페이지' }));
    expect(
      canvas.getByRole('header', { name: '마이페이지' }),
    ).toBeOnTheScreen();
    expect(canvas.getByText('프로필 정보를 불러오고 있어요')).toBeOnTheScreen();
  });

  it('applies the selected real phone viewport to Splash and the other screens', async () => {
    await render(<PreviewGallery />);

    expect(
      screen.getByRole('radio', { name: '원본 기준 · 390 × 844' }),
    ).toBeChecked();

    fireEvent.press(
      screen.getByRole('radio', { name: 'Android compact · 360 × 800' }),
    );
    expect(
      StyleSheet.flatten(screen.getByTestId('preview-app-canvas').props.style),
    ).toEqual(expect.objectContaining({ width: 360, height: 800 }));
    fireEvent.press(screen.getByRole('radio', { name: 'Home (API)' }));
    expect(
      StyleSheet.flatten(screen.getByTestId('preview-app-canvas').props.style),
    ).toEqual(expect.objectContaining({ width: 360, height: 800 }));

    fireEvent.press(
      screen.getByRole('radio', { name: 'Large phone · 430 × 932' }),
    );
    expect(
      StyleSheet.flatten(screen.getByTestId('preview-app-canvas').props.style),
    ).toEqual(expect.objectContaining({ width: 430, height: 932 }));

    fireEvent.press(screen.getByRole('radio', { name: 'Login (API)' }));
    expect(
      StyleSheet.flatten(screen.getByTestId('preview-app-canvas').props.style),
    ).toEqual(expect.objectContaining({ width: 430, height: 932 }));
  });

  it('renders a web-sized viewport and fits its frame inside the gallery', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(
      screen.getByRole('radio', { name: 'Web desktop · 1440 × 900' }),
    );

    expect(
      StyleSheet.flatten(screen.getByTestId('preview-app-canvas').props.style),
    ).toEqual(
      expect.objectContaining({
        width: 1440,
        height: 900,
        transform: [{ scale: expect.any(Number) }],
      }),
    );

    const frameStyle = StyleSheet.flatten(
      screen.getByTestId('preview-canvas-frame').props.style,
    );
    expect(frameStyle.width / frameStyle.height).toBeCloseTo(1440 / 900);
    expect(frameStyle.width).toBeLessThanOrEqual(1440);
    expect(
      StyleSheet.flatten(screen.getByTestId('preview-app-content').props.style),
    ).toMatchObject({ maxWidth: 640, width: '100%' });
    expect(screen.getByText('App max 640px')).toBeOnTheScreen();
    expect(screen.getByText('1440 × 900')).toBeOnTheScreen();
  });

  it('lets the user adjust the canvas width and height in pixels', async () => {
    await render(<PreviewGallery />);

    const widthSlider = screen.getByRole('adjustable', {
      name: '가로 픽셀',
    });
    const heightSlider = screen.getByRole('adjustable', {
      name: '세로 픽셀',
    });

    expect(widthSlider).toHaveAccessibilityValue({
      max: 1920,
      min: 320,
      now: 390,
      text: '390 픽셀',
    });
    expect(heightSlider).toHaveAccessibilityValue({
      max: 1440,
      min: 568,
      now: 844,
      text: '844 픽셀',
    });

    fireEvent(widthSlider, 'accessibilityAction', {
      nativeEvent: { actionName: 'increment' },
    });
    fireEvent(heightSlider, 'accessibilityAction', {
      nativeEvent: { actionName: 'decrement' },
    });

    expect(
      StyleSheet.flatten(screen.getByTestId('preview-app-canvas').props.style),
    ).toEqual(expect.objectContaining({ width: 400, height: 834 }));
    expect(screen.getByText('400 × 834')).toBeOnTheScreen();
    expect(
      screen.getByRole('radio', { name: '원본 기준 · 390 × 844' }),
    ).not.toBeChecked();
  });

  it('accepts exact canvas dimensions from numeric inputs', async () => {
    await render(<PreviewGallery />);

    const widthInput = screen.getByLabelText('가로 픽셀 직접 입력');
    const heightInput = screen.getByLabelText('세로 픽셀 직접 입력');

    fireEvent.changeText(widthInput, '768');
    fireEvent(widthInput, 'submitEditing');
    fireEvent.changeText(heightInput, '1024');
    fireEvent(heightInput, 'blur');

    expect(
      StyleSheet.flatten(screen.getByTestId('preview-app-canvas').props.style),
    ).toEqual(expect.objectContaining({ width: 768, height: 1024 }));
    expect(screen.getByText('768 × 1024')).toBeOnTheScreen();
    expect(widthInput.props.value).toBe('768');
    expect(heightInput.props.value).toBe('1024');
  });

  it('toggles reduced motion for the selected screen', async () => {
    await render(<PreviewGallery />);

    const reducedMotion = screen.getByRole('switch', {
      name: 'Reduced motion',
    });
    expect(reducedMotion).not.toBeChecked();

    fireEvent(reducedMotion, 'valueChange', true);
    expect(reducedMotion).toBeChecked();
  });

  it('switches Login API preview states inside the fixed app canvas', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Login (API)' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByRole('header', {
        name: '오늘도 자신과의 싸움에서\n승리하러 왔군요',
      }),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '네트워크 오류' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText(
        '네트워크에 연결할 수 없어요. 연결 상태를 확인한 뒤 다시 시도해주세요.',
      ),
    ).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=login')).toBeOnTheScreen();
  });

  it('shows the SignUp API contract and changes its preview state', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'SignUp (API)' }));
    const canvas = within(screen.getByTestId('preview-app-canvas'));
    expect(
      screen.getByText(
        '실제 앱의 Firebase 이메일·비밀번호 회원가입 UI입니다. 갤러리 상태는 계정과 네트워크를 변경하지 않는 fixture입니다.',
      ),
    ).toBeOnTheScreen();
    expect(canvas.queryByText('6자 이상 입력해주세요.')).toBeNull();
    expect(
      canvas.queryByText(/로그인에 사용할 계정 정보만 입력해요/),
    ).toBeNull();

    fireEvent.press(screen.getByRole('radio', { name: '비밀번호 규칙 오류' }));
    expect(
      canvas.getByText('6자 이상 입력해주세요.').props.accessibilityRole,
    ).toBe('alert');

    fireEvent.press(screen.getByRole('radio', { name: '입력 전' }));

    fireEvent.changeText(
      canvas.getByLabelText('회원가입 이메일'),
      'preview@example.com',
    );
    fireEvent.changeText(canvas.getByLabelText('회원가입 비밀번호'), 'secret');
    fireEvent.changeText(
      canvas.getByLabelText('회원가입 비밀번호 확인'),
      'secret',
    );
    expect(
      canvas.getByRole('button', { name: '가입하고 프로필 등록하기' }),
    ).toBeEnabled();

    fireEvent.press(screen.getByRole('radio', { name: '가입 실패' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText(
        '회원가입에 실패했어요. 잠시 후 다시 시도해주세요.',
      ),
    ).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=signup')).toBeOnTheScreen();
  });

  it('switches all Profile steps and mock save states inside the app canvas', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Profile (mock)' }));
    expect(
      screen.getByText(
        '시각 참고 전용입니다. 실제 백엔드 필드에 연결되는 가입 후 입력은 Onboarding (API) 화면에서 확인할 수 있습니다.',
      ),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '13. summary' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText('13 / 13'),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '저장 실패' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText(
        '프로필 저장에 실패했어요. 저장이 완료되지 않으면 홈을 이용할 수 없어요.',
      ),
    ).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=profile')).toBeOnTheScreen();
  });

  it('shows the API-shaped onboarding flow and lets the gallery select a step', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Onboarding (API)' }));
    expect(
      screen.getByText(
        '개발 확인 전용 API를 사용합니다. 입력 내용은 저장되거나 네트워크로 전송되지 않지만, 실제 화면과 동일한 요청 필드로 구성됩니다.',
      ),
    ).toBeOnTheScreen();
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText('1 / 11'),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '3. body' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText('3 / 11'),
    ).toBeOnTheScreen();
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText(
        '키와 체중을 입력해주세요',
      ),
    ).toBeOnTheScreen();
    expect(
      screen.getByText('단독 진입: ?preview=onboarding'),
    ).toBeOnTheScreen();
  });

  it('runs the Home API preview interactions with persisted check-in fields', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Home (API)' }));
    const canvas = within(screen.getByTestId('preview-app-canvas'));
    const now = new Date();
    const localDate = localDateString(now, 'Asia/Seoul');
    const preview = homePreviewProps('pre-checkin');
    expect(preview.localDate).toBe(localDate);
    expect(preview.week?.week_start).toBe(weekStartString(now, 'Asia/Seoul'));
    expect(canvas.getByText(formatHomeDate(localDate))).toBeOnTheScreen();
    expect(
      screen.getByText(
        '시각 참고 전용: 체크인·루틴 생성·조정 결과는 fixture이며 최종 추천 1개만 표시합니다.',
      ),
    ).toBeOnTheScreen();
    expect(canvas.getByText('아직 오늘의 운동이 없어요')).toBeOnTheScreen();
    expect(canvas.getByTestId('home-checkin-gradient').props.colors).toEqual(
      ['#FEE8B1', '#FEDA99', '#FFD790'].map(processColor),
    );

    fireEvent.press(canvas.getByRole('button', { name: '오늘 루틴 체크인' }));
    expect(
      canvas.getByTestId('home-checkin-submit-gradient').props.colors,
    ).toEqual(['#FEE8B1', '#FEDA99', '#FFD790'].map(processColor));
    expect(canvas.queryByText('컨디션')).toBeNull();
    expect(canvas.queryByLabelText('오늘 걸음 수')).toBeNull();
    expect(canvas.queryByRole('button', { name: '어깨' })).toBeNull();
    fireEvent.press(canvas.getByRole('button', { name: '있음' }));
    expect(canvas.getByRole('button', { name: '어깨' })).toBeOnTheScreen();
    expect(canvas.getByRole('button', { name: '무릎' })).toBeOnTheScreen();
    expect(canvas.getByRole('button', { name: '허리' })).toBeOnTheScreen();
    expect(canvas.queryByRole('button', { name: '전신' })).toBeNull();
    expect(canvas.getByRole('button', { name: '집' })).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '헬스장' }));
    fireEvent.press(canvas.getByRole('button', { name: '어깨' }));
    fireEvent.press(canvas.getByRole('button', { name: '무릎' }));
    expect(canvas.getByText('어깨 통증 정도')).toBeOnTheScreen();
    expect(canvas.getByText('무릎 통증 정도')).toBeOnTheScreen();
    expect(canvas.queryByText('가슴 압박감 또는 통증')).toBeNull();
    fireEvent.press(canvas.getByRole('button', { name: '있어요' }));
    expect(canvas.getByText('이런 증상이 있나요?')).toBeOnTheScreen();
    expect(
      canvas.getByRole('button', { name: '가슴 압박감 또는 통증' }),
    ).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '없어요' }));

    fireEvent.press(canvas.getByRole('button', { name: '체크인 !' }));
    expect(await canvas.findByText('상체 근력 루틴')).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '추천 이유 보기' }));
    expect(canvas.getByRole('header', { name: '추천 이유' })).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '닫기' }));
    fireEvent.press(canvas.getByRole('button', { name: '푸시업 자세 보기' }));
    expect(
      await canvas.findByText('통증이 없는 범위에서 천천히 움직여주세요.'),
    ).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '닫기' }));

    fireEvent.press(
      canvas.getByRole('button', { name: '다른 루틴 추천 받기' }),
    );
    expect(
      await canvas.findByText('오늘 컨디션에 맞춰 부담을 낮췄어요.'),
    ).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '오늘은 쉬기' }));
    expect(
      await canvas.findByText('오늘은 휴식하기로 했어요'),
    ).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=home')).toBeOnTheScreen();

    fireEvent.press(canvas.getByRole('button', { name: '프로필 열기' }));
    expect(screen.getByRole('radio', { name: 'My page (API)' })).toBeChecked();
  });

  it('navigates from the Home API preview into the current workout screen', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Home (API)' }));
    fireEvent.press(screen.getByRole('radio', { name: '최종 추천' }));
    const canvas = within(screen.getByTestId('preview-app-canvas'));
    fireEvent.press(canvas.getByRole('button', { name: '운동 시작하기' }));

    expect(screen.getByRole('radio', { name: 'Workout (API)' })).toBeChecked();
    expect(
      canvas.queryByRole('header', { name: '오늘 운동을 마쳤어요' }),
    ).toBeNull();
    expect((await canvas.findAllByText('의자 스쿼트')).length).toBeGreaterThan(
      0,
    );
  });

  it('shows working reorder handles in the Home API preview', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Home (API)' }));
    fireEvent.press(screen.getByRole('radio', { name: '최종 추천' }));
    const canvas = within(screen.getByTestId('preview-app-canvas'));

    const handles = canvas.getAllByLabelText('순서 변경 핸들');
    expect(handles.map((handle) => handle.props.testID)).toEqual([
      'routine-drag-plan-item-1',
      'routine-drag-plan-item-2',
      'routine-drag-plan-item-3',
    ]);

    fireEvent(handles[0]!, 'accessibilityAction', {
      nativeEvent: { actionName: 'increment' },
    });

    expect(
      canvas
        .getAllByLabelText('순서 변경 핸들')
        .map((handle) => handle.props.testID),
    ).toEqual([
      'routine-drag-plan-item-2',
      'routine-drag-plan-item-1',
      'routine-drag-plan-item-3',
    ]);
  });

  it('shows API-backed Workout controls without mock-only symptom states', async () => {
    await render(<PreviewGallery initialScreenId="workout" />);
    const canvas = within(screen.getByTestId('preview-app-canvas'));

    expect(screen.getByRole('radio', { name: 'API 실제 흐름' })).toBeChecked();
    expect(
      screen.getByRole('radio', { name: '미수행 이유' }),
    ).toBeOnTheScreen();
    expect(
      screen.getByRole('radio', { name: '안전 중단 확인' }),
    ).toBeOnTheScreen();
    expect(screen.queryByRole('radio', { name: '경미한 불편' })).toBeNull();
    expect(
      screen.queryByRole('radio', { name: '중대한 이상 반응' }),
    ).toBeNull();
    await waitFor(() =>
      expect(canvas.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );
    expect(
      StyleSheet.flatten(canvas.getByTestId('workout-stop-action').props.style),
    ).toMatchObject({
      backgroundColor: '#FFFFFF',
      borderColor: '#EEDFCB',
    });
    for (const testId of [
      'workout-smash-action',
      'workout-rest-action',
      'workout-pain-action',
    ]) {
      expect(
        StyleSheet.flatten(canvas.getByTestId(testId).props.style),
      ).toMatchObject({ flex: 1, flexBasis: 0, height: 58 });
    }
  });

  it('opens the equipment and variant guide from the Workout preview', async () => {
    await render(<PreviewGallery initialScreenId="workout" />);
    const canvas = within(screen.getByTestId('preview-app-canvas'));

    fireEvent.press(screen.getByRole('radio', { name: '장비가 없을 때 안내' }));

    expect(
      await canvas.findByRole('header', { name: '의자 스쿼트 장비 안내' }),
    ).toBeOnTheScreen();
    expect(canvas.getByText('원래 운동의 필요 장비')).toBeOnTheScreen();
    expect(canvas.getByText('맨몸 스쿼트')).toBeOnTheScreen();
    expect(
      screen.getByText(
        '의자 스쿼트의 장비 안내판을 바로 엽니다. 필요 장비와 장비가 없을 때 가능한 검토된 변형운동을 함께 확인할 수 있으며, 운동을 자동 교체하지 않습니다.',
      ),
    ).toBeOnTheScreen();
  });

  it('scales the Workout composition proportionally on the large-phone preset', async () => {
    await render(<PreviewGallery initialScreenId="workout" />);
    const layout = getWorkoutResponsiveLayout({ width: 430, height: 932 });

    fireEvent.press(screen.getByRole('radio', { name: '일반 진행' }));
    fireEvent.press(
      screen.getByRole('radio', { name: 'Large phone · 430 × 932' }),
    );
    const largeCanvas = within(screen.getByTestId('preview-app-canvas'));

    expect(
      StyleSheet.flatten(largeCanvas.getByTestId('workout-card-0').props.style),
    ).toMatchObject({
      height: layout.cardHeight,
      width: layout.cardWidth,
    });
    expect(
      StyleSheet.flatten(
        largeCanvas.getByTestId('workout-smash-action').props.style,
      ).height,
    ).toBeCloseTo(58 * layout.scale);
  });

  it('starts a fresh workout after leaving a completed result through the gallery', async () => {
    await render(<PreviewGallery initialScreenId="workout" />);
    const canvas = within(screen.getByTestId('preview-app-canvas'));
    await waitFor(() =>
      expect(canvas.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );

    for (const [index, exerciseName] of [
      '의자 스쿼트',
      '벽 푸시업',
      '제자리 걷기',
    ].entries()) {
      await waitFor(() =>
        expect(
          canvas.getByRole('button', {
            name: `${exerciseName} 블록 격파`,
          }),
        ).toBeEnabled(),
      );
      fireEvent.press(
        canvas.getByRole('button', {
          name: `${exerciseName} 블록 격파`,
        }),
      );
      if (index < 2) {
        await waitFor(() =>
          expect(canvas.getByText(`완료 ${index + 1} / 3`)).toBeOnTheScreen(),
        );
      }
    }
    expect(
      await canvas.findByRole('header', { name: '오늘 운동을 마쳤어요' }),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Home (API)' }));
    fireEvent.press(screen.getByRole('radio', { name: '최종 추천' }));
    fireEvent.press(canvas.getByRole('button', { name: '운동 시작하기' }));

    expect(screen.getByRole('radio', { name: 'Workout (API)' })).toBeChecked();
    expect(
      canvas.queryByRole('header', { name: '오늘 운동을 마쳤어요' }),
    ).toBeNull();
    await waitFor(() =>
      expect(canvas.getByText('완료 0 / 3')).toBeOnTheScreen(),
    );
  });

  it('previews the API-backed home states without authentication', async () => {
    await render(<PreviewGallery initialScreenId="today" />);

    const canvas = within(screen.getByTestId('preview-app-canvas'));
    expect(
      screen.getByRole('radio', { name: 'Home previous (mock)' }),
    ).toBeChecked();
    expect(
      await canvas.findByRole('button', { name: '오늘 루틴 체크인' }),
    ).toBeOnTheScreen();
    expect(canvas.getByText('아직 오늘의 운동이 없어요')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '체크인 후' }));
    expect(screen.getByRole('radio', { name: '체크인 후' })).toBeChecked();
    expect(
      await canvas.findByRole('button', { name: '오늘 루틴 체크인' }),
    ).toBeOnTheScreen();
    expect(canvas.getByText('전신 근력 루틴')).toBeOnTheScreen();
    expect(canvas.getByText('오늘은 계획대로 진행해요.')).toBeOnTheScreen();
    expect(
      canvas.getByRole('button', { name: '오늘은 쉬기' }),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '권한 없음' }));
    expect(screen.getByRole('radio', { name: '권한 없음' })).toBeChecked();
    expect(screen.getByText('단독 진입: ?preview=today')).toBeOnTheScreen();
  });

  it('shows every remaining API-backed signed-in screen in the gallery', async () => {
    await render(<PreviewGallery />);
    const canvas = within(screen.getByTestId('preview-app-canvas'));

    fireEvent.press(
      screen.getByRole('radio', { name: 'Workout session (mock)' }),
    );
    expect((await canvas.findAllByText('의자 스쿼트')).length).toBeGreaterThan(
      0,
    );
    expect(canvas.getByRole('button', { name: '운동 마치기' })).toBeDisabled();

    expect(
      screen.queryByRole('radio', { name: 'Workout result (API)' }),
    ).toBeNull();
    fireEvent.press(screen.getByRole('radio', { name: 'Workout (API)' }));
    expect(screen.queryByRole('radio', { name: '완료 결과' })).toBeNull();
    expect(screen.queryByRole('radio', { name: '안전 중단 결과' })).toBeNull();
    expect(
      screen.getByRole('radio', { name: '결과 · 일부 완료' }),
    ).toBeOnTheScreen();
    expect(
      screen.getByRole('radio', { name: '결과 · 미수행' }),
    ).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('radio', { name: '결과 · 완료' }));
    expect(
      canvas.getByRole('header', { name: '오늘 운동을 마쳤어요' }),
    ).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('radio', { name: '결과 · 안전 중단' }));
    expect(
      canvas.getByRole('header', { name: '운동을 중단했어요' }),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Mascot house (API)' }));
    expect(await canvas.findByTestId('house-scene')).toBeOnTheScreen();
    expect(canvas.getByTestId('mascot-house-content')).toBeOnTheScreen();
    expect(canvas.queryByTestId('background-test-content')).toBeNull();
    expect(canvas.queryByTestId('moving-house-backdrop')).toBeNull();
    expect(canvas.getByText('끼끼와 놀기')).toBeOnTheScreen();
    expect(canvas.getByText('바나나 받기')).toBeOnTheScreen();
    expect(canvas.queryByText('주 4회 운동하기')).toBeNull();
    expect(canvas.queryByText('2 / 4 회')).toBeNull();

    fireEvent.press(
      screen.getByRole('radio', { name: 'background_test (mock)' }),
    );
    expect(
      await canvas.findByTestId('moving-house-backdrop'),
    ).toBeOnTheScreen();
    expect(canvas.getByTestId('background-test-content')).toBeOnTheScreen();
    expect(canvas.queryByTestId('mascot-house-content')).toBeNull();
    expect(canvas.getByTestId('moving-house-background')).toBeOnTheScreen();
    expect(canvas.getByTestId('moving-house-cloud-1')).toBeOnTheScreen();
    expect(canvas.getByTestId('moving-house-canopy-left')).toBeOnTheScreen();
    const movingBackdropStyle = StyleSheet.flatten(
      canvas.getByTestId('moving-house-backdrop').props.style,
    );
    expect(movingBackdropStyle.width).toBeCloseTo(691.8, 1);
    expect(movingBackdropStyle.height).toBe(422);
    expect(canvas.getByText('주 4회 운동하기')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Weekly report (API)' }));
    expect(
      await canvas.findByRole('header', { name: '주간 리포트' }),
    ).toBeOnTheScreen();
    expect(
      canvas.getByRole('button', { name: '리포트 생성하기' }),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Account (mock)' }));
    expect(canvas.getByRole('header', { name: '내 프로필' })).toBeOnTheScreen();
    expect(
      canvas.getByRole('button', { name: '계정 삭제 요청' }),
    ).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=account')).toBeOnTheScreen();
  });

  it('keeps backend preview mutations local to the gallery fixtures', async () => {
    await render(<PreviewGallery initialScreenId="weekly-report" />);
    const canvas = within(screen.getByTestId('preview-app-canvas'));

    fireEvent.press(
      await canvas.findByRole('button', { name: '리포트 생성하기' }),
    );
    expect(
      await canvas.findByText('이번 주 목표에 맞춰 차근차근 운동했어요.'),
    ).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '리포트 확인했어요' }));
    expect(await canvas.findByText('리포트를 확인했어요')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Account (mock)' }));
    fireEvent.press(canvas.getByRole('button', { name: '계정 삭제 요청' }));
    fireEvent.press(canvas.getByRole('button', { name: '삭제를 요청할게요' }));
    expect(await canvas.findByText('계정 삭제를 접수했어요')).toBeOnTheScreen();
  });

  it('switches the three Home secondary screens and their mock states', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Home map (mock)' }));
    expect(
      screen.getByText(
        '제품 경계: 원본의 lighter/original 공개 선택지는 이관하지 않고 최종 추천 1개와 휴식 동작만 표시합니다.',
      ),
    ).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('radio', { name: '최종 루틴' }));
    const mapCanvas = within(screen.getByTestId('preview-app-canvas'));
    expect(mapCanvas.getByText('목표 4회')).toBeOnTheScreen();
    expect(mapCanvas.getByText('지금 내 루틴')).toBeOnTheScreen();
    expect(mapCanvas.getByText('의자 스쿼트')).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=home-map')).toBeOnTheScreen();

    fireEvent.press(
      screen.getByRole('radio', { name: 'Calendar/report (API)' }),
    );
    fireEvent.press(screen.getByRole('radio', { name: '주차 상세' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText(
        '한 주가 끝났어요. 리포트를 만들면 이번 주 운동 패턴을 정리해드려요.',
      ),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'My page (API)' }));
    fireEvent.press(screen.getByRole('radio', { name: '회원 탈퇴 확인' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByRole('header', {
        name: '회원 탈퇴할까요?',
      }),
    ).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=my-page')).toBeOnTheScreen();
  });

  it('opens a calendar workout-history mock for visual review', async () => {
    await render(<PreviewGallery initialScreenId="calendar-report" />);
    const canvas = within(screen.getByTestId('preview-app-canvas'));

    fireEvent.press(screen.getByRole('radio', { name: '주차 상세' }));
    fireEvent.press(
      canvas.getByRole('button', { name: '2026-08-04 운동 기록 보기' }),
    );

    expect(
      await screen.findByRole('header', { name: '2026-08-04 운동 기록' }),
    ).toBeOnTheScreen();
    expect(screen.getByText(/의자 스쿼트/)).toBeOnTheScreen();
    expect(screen.getByText(/벽 푸시업/)).toBeOnTheScreen();
    expect(screen.getByText(/데드 버그/)).toBeOnTheScreen();
    expect(screen.getByText(/3.*3.*블록/)).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: '운동 기록 닫기' }));
    expect(screen.queryByText('2026-08-04 운동 기록')).not.toBeOnTheScreen();
  });

  it('connects all four Home tabs to their matching gallery screens', async () => {
    await render(<PreviewGallery initialScreenId="home" />);
    const canvas = within(screen.getByTestId('preview-app-canvas'));

    fireEvent.press(canvas.getByRole('tab', { name: '끼끼의 집' }));
    expect(
      screen.getByRole('radio', { name: 'Mascot house (API)' }),
    ).toBeChecked();

    fireEvent.press(canvas.getByRole('tab', { name: '리포트' }));
    expect(
      screen.getByRole('radio', { name: 'Calendar/report (API)' }),
    ).toBeChecked();

    fireEvent.press(canvas.getByRole('tab', { name: '마이페이지' }));
    expect(screen.getByRole('radio', { name: 'My page (API)' })).toBeChecked();

    fireEvent.press(canvas.getByRole('tab', { name: '홈' }));
    expect(screen.getByRole('radio', { name: 'Home (API)' })).toBeChecked();
  });

  it('opens the exercise catalog from My page with the same route as the real app', async () => {
    await render(<PreviewGallery initialScreenId="my-page" />);
    const canvas = within(screen.getByTestId('preview-app-canvas'));

    expect(await canvas.findByText('운동 도구')).toBeOnTheScreen();
    fireEvent.press(canvas.getByText('운동 카탈로그'));

    expect(
      screen.getByRole('radio', { name: 'Exercise catalog (API)' }),
    ).toBeChecked();
    expect(
      await canvas.findByRole('header', { name: '운동 카탈로그' }),
    ).toBeOnTheScreen();
    expect(canvas.getByText('바벨 데드리프트')).toBeOnTheScreen();
    expect(
      screen.getByText('단독 진입: ?preview=exercise-catalog'),
    ).toBeOnTheScreen();

    fireEvent.press(
      canvas.getByRole('button', { name: '바벨 데드리프트 설명 열기' }),
    );
    expect(
      await canvas.findByRole('header', { name: '바벨 데드리프트' }),
    ).toBeOnTheScreen();
    expect(await canvas.findByTestId('exercise-media-image')).toBeOnTheScreen();
    expect(
      canvas.getByText(
        '데드리프트 운동은 엉덩이를 뒤로 보내며 엉덩이를 사용하는 운동입니다.',
      ),
    ).toBeOnTheScreen();

    fireEvent.press(canvas.getByRole('button', { name: '목록으로' }));
    expect(
      await canvas.findByRole('header', { name: '운동 카탈로그' }),
    ).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '돌아가기' }));
    expect(screen.getByRole('radio', { name: 'My page (API)' })).toBeChecked();
    expect(await canvas.findByText('운동 도구')).toBeOnTheScreen();
  });

  it('shows empty and error fixtures for the exercise catalog', async () => {
    await render(<PreviewGallery initialScreenId="exercise-catalog" />);
    const canvas = within(screen.getByTestId('preview-app-canvas'));

    expect(await canvas.findByText('의자 스쿼트')).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('radio', { name: '목록 없음' }));
    expect(
      await canvas.findByText('조건에 맞는 운동이 아직 없어요.'),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '오류' }));
    expect(
      await canvas.findByText('운동 카탈로그를 불러오지 못했어요.'),
    ).toBeOnTheScreen();
    expect(canvas.getByRole('button', { name: '다시 시도' })).toBeOnTheScreen();
  });

  it('runs the Workout API preview through missed, feedback, home, and partial outcomes', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Workout (API)' }));
    expect(
      screen.getByText(
        '개발 확인 전용 API를 사용합니다. 시작·타이머·블록·중단·안전 보고·피드백은 실제 프론트엔드 API 계약으로 연결되며, 데이터는 네트워크로 전송되지 않습니다.',
      ),
    ).toBeOnTheScreen();
    const canvas = within(screen.getByTestId('preview-app-canvas'));
    await waitFor(() =>
      expect(canvas.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );

    fireEvent.press(canvas.getByRole('button', { name: '일시정지' }));
    expect(canvas.getByText('일시정지됨 · 기록용')).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '재개' }));
    fireEvent.press(canvas.getByRole('button', { name: '선택 휴식 타이머' }));
    expect(canvas.getByText('선택 휴식')).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '휴식 끝' }));
    expect(canvas.queryByTestId('workout-additional-action')).toBeNull();
    expect(
      canvas.queryByRole('button', { name: '계획 외 활동 기록' }),
    ).toBeNull();

    fireEvent.press(canvas.getByRole('button', { name: '운동 중단' }));
    fireEvent.press(canvas.getByRole('button', { name: '중단하기' }));
    expect(
      canvas.getByRole('header', { name: '오늘 운동을 마치지 못한 이유' }),
    ).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '시간이 부족했어요' }));

    expect(
      await canvas.findByRole('header', { name: '오늘 기록을 저장했어요' }),
    ).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('radio', { name: '적당했어요' }));
    fireEvent.press(canvas.getByRole('button', { name: '피드백 저장' }));
    expect(await canvas.findByText('피드백을 저장했어요.')).toBeOnTheScreen();
    fireEvent.press(canvas.getByRole('button', { name: '홈으로' }));
    expect(screen.getByRole('radio', { name: 'Home (API)' })).toBeChecked();

    fireEvent.press(screen.getByRole('radio', { name: 'Workout (API)' }));
    await waitFor(() =>
      expect(canvas.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );
    fireEvent.press(
      canvas.getByRole('button', { name: '의자 스쿼트 블록 격파' }),
    );
    await waitFor(() =>
      expect(canvas.getByText('완료 1 / 3')).toBeOnTheScreen(),
    );
    fireEvent.press(
      canvas.getByRole('button', { name: '의자 스쿼트 완료 취소' }),
    );
    await waitFor(() =>
      expect(canvas.getByText('완료 0 / 3')).toBeOnTheScreen(),
    );
    fireEvent.press(
      canvas.getByRole('button', { name: '의자 스쿼트 블록 격파' }),
    );
    await waitFor(() =>
      expect(canvas.getByText('완료 1 / 3')).toBeOnTheScreen(),
    );
    fireEvent.press(canvas.getByRole('button', { name: '운동 중단' }));
    fireEvent.press(canvas.getByRole('button', { name: '중단하기' }));
    expect(
      await canvas.findByRole('header', { name: '오늘 운동을 기록했어요' }),
    ).toBeOnTheScreen();
    expect(canvas.getAllByText('블록 1 / 3 완료')).toHaveLength(2);
    expect(screen.getByText('단독 진입: ?preview=workout')).toBeOnTheScreen();
  });

  it('connects the Workout API preview safety report to a serious stop result', async () => {
    await render(<PreviewGallery initialScreenId="workout" />);
    const canvas = within(screen.getByTestId('preview-app-canvas'));
    await waitFor(() =>
      expect(canvas.queryByText('운동 세션을 준비하고 있어요…')).toBeNull(),
    );

    fireEvent.press(
      canvas.getByRole('button', { name: '통증 및 이상 반응 보고' }),
    );
    fireEvent.press(
      canvas.getByRole('checkbox', { name: '가슴 압박감 또는 통증' }),
    );
    fireEvent.press(
      canvas.getByRole('button', { name: '보고하고 안전 안내 확인' }),
    );

    expect(
      await canvas.findByRole('header', { name: '운동을 중단했어요' }),
    ).toBeOnTheScreen();
    expect(
      canvas.getByText('오늘은 더 이상 운동을 권하지 않아요.'),
    ).toBeOnTheScreen();
  });
});
