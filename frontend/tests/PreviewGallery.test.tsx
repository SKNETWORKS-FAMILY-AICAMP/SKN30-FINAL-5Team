import { describe, expect, it } from '@jest/globals';
import { StyleSheet } from 'react-native';
import {
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react-native';

import { PreviewGallery } from '../src/features/preview/PreviewGallery';

describe('PreviewGallery', () => {
  it('keeps development controls outside the 390 x 844 app canvas', async () => {
    await render(<PreviewGallery />);

    expect(screen.getByText('DEVELOPMENT ONLY')).toBeOnTheScreen();
    expect(screen.getByRole('radio', { name: 'Splash' })).toBeChecked();
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

  it('switches Splash between pending and error mock states', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'error' }));
    expect(screen.getByText('앱을 시작하지 못했어요')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: '다시 시도' }));
    expect(screen.queryByText('앱을 시작하지 못했어요')).not.toBeOnTheScreen();
    expect(screen.getByRole('radio', { name: 'pending' })).toBeChecked();
  });

  it('shows Splash at three real phone viewport sizes without changing other screens', async () => {
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
    expect(
      StyleSheet.flatten(screen.getByTestId('question-mark').props.style),
    ).toEqual(
      expect.objectContaining({
        left: (129 * 360) / 390,
        top: (345 * 800) / 844,
      }),
    );

    fireEvent.press(
      screen.getByRole('radio', { name: 'Large phone · 430 × 932' }),
    );
    expect(
      StyleSheet.flatten(screen.getByTestId('preview-app-canvas').props.style),
    ).toEqual(expect.objectContaining({ width: 430, height: 932 }));

    fireEvent.press(screen.getByRole('radio', { name: 'Login' }));
    expect(
      StyleSheet.flatten(screen.getByTestId('preview-app-canvas').props.style),
    ).toEqual(expect.objectContaining({ width: 390, height: 844 }));
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

  it('switches Login mock states inside the fixed app canvas', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Login' }));
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

  it('marks SignUp as a contract-reference screen and changes its mock state', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'SignUp' }));
    expect(
      screen.getByText(
        '시각 참고 전용: 로컬 계정 유지 여부와 Firebase 인증 계약은 미확정입니다.',
      ),
    ).toBeOnTheScreen();

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

    fireEvent.press(screen.getByRole('radio', { name: 'Profile' }));
    expect(
      screen.getByText(
        '시각 참고 전용: 생년월일·성별·키·체중 필수 시안은 현재 API/DB 계약과 충돌합니다.',
      ),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '14. summary' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText('14 / 14'),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '저장 실패' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText(
        '프로필 저장에 실패했어요. 저장이 완료되지 않으면 홈을 이용할 수 없어요.',
      ),
    ).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=profile')).toBeOnTheScreen();
  });

  it('switches Home core mock states without exposing extra plan options', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Home' }));
    expect(
      screen.getByText(
        '시각 참고 전용: 체크인·루틴 생성·조정 결과는 fixture이며 최종 추천 1개만 표시합니다.',
      ),
    ).toBeOnTheScreen();
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText(
        '아직 오늘의 운동이 없어요',
      ),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '최종 추천' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText(
        '상체 근력 루틴',
      ),
    ).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=home')).toBeOnTheScreen();
  });

  it('switches the three Home secondary screens and their mock states', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Home map' }));
    expect(
      screen.getByText(
        '제품 경계: 원본의 lighter/original 공개 선택지는 이관하지 않고 최종 추천 1개와 휴식 동작만 표시합니다.',
      ),
    ).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('radio', { name: '최종 루틴' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText(
        '오늘의 운동 계획을 준비했어요',
      ),
    ).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=home-map')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Calendar/report' }));
    fireEvent.press(screen.getByRole('radio', { name: '주차 상세' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText(
        '한 주가 끝났어요. 리포트를 만들면 이번 주 운동 패턴을 정리해드려요.',
      ),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'My page' }));
    fireEvent.press(screen.getByRole('radio', { name: '회원 탈퇴 확인' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByRole('header', {
        name: '회원 탈퇴할까요?',
      }),
    ).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=my-page')).toBeOnTheScreen();
  });

  it('switches Workout states while keeping severe safety guidance non-resumable', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Workout' }));
    expect(
      screen.getByText(
        '시각 참고 전용: 타이머와 블록 체크는 공식 완료를 결정하지 않으며, 안전 안내와 결과는 서버 응답 fixture로 분리했습니다.',
      ),
    ).toBeOnTheScreen();
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByRole('header', {
        name: '전신 기본 루틴',
      }),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '중대한 이상 반응' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByRole('button', {
        name: '보고하고 안전 중단',
      }),
    ).toBeOnTheScreen();
    expect(screen.getByText('단독 진입: ?preview=workout')).toBeOnTheScreen();
  });
});
