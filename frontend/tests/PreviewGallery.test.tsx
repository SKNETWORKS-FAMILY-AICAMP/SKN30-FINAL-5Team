import { describe, expect, it } from '@jest/globals';
import { StyleSheet } from 'react-native';
import {
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react-native';

import { localDateString, weekStartString } from '../src/api/useAsync';
import { formatHomeDate } from '../src/features/home/homeModel';
import { PreviewGallery } from '../src/features/preview/PreviewGallery';
import { homePreviewProps } from '../src/features/preview/homePreview';

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

  it('marks SignUp as a contract-reference screen and changes its mock state', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'SignUp (API)' }));
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
        '시각 참고 전용입니다. 실제 백엔드 필드에 연결되는 가입 후 입력은 Onboarding (API) 화면에서 확인할 수 있습니다.',
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

  it('shows the API-shaped onboarding flow and lets the gallery select a step', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Onboarding (API)' }));
    expect(
      screen.getByText(
        '개발 확인 전용 API를 사용합니다. 입력 내용은 저장되거나 네트워크로 전송되지 않지만, 실제 화면과 동일한 요청 필드로 구성됩니다.',
      ),
    ).toBeOnTheScreen();
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText('1 / 13'),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: '3. body' }));
    expect(
      within(screen.getByTestId('preview-app-canvas')).getByText('3 / 13'),
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

    fireEvent.press(canvas.getByRole('button', { name: '오늘 루틴 체크인' }));
    expect(canvas.queryByText('컨디션')).toBeNull();
    expect(canvas.queryByLabelText('오늘 걸음 수')).toBeNull();
    expect(canvas.getByRole('button', { name: '어깨' })).toBeOnTheScreen();
    expect(canvas.getByRole('button', { name: '무릎' })).toBeOnTheScreen();
    expect(canvas.queryByRole('button', { name: '허리' })).toBeNull();
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
    fireEvent.press(
      canvas.getByRole('button', { name: '푸시업 운동 설명 보기' }),
    );
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
    expect(screen.getByRole('radio', { name: 'Account (API)' })).toBeChecked();
  });

  it('navigates from the Home API preview into the workout session', async () => {
    await render(<PreviewGallery />);

    fireEvent.press(screen.getByRole('radio', { name: 'Home (API)' }));
    fireEvent.press(screen.getByRole('radio', { name: '최종 추천' }));
    const canvas = within(screen.getByTestId('preview-app-canvas'));
    fireEvent.press(canvas.getByRole('button', { name: '운동 시작하기' }));

    expect(
      screen.getByRole('radio', { name: 'Workout session (API)' }),
    ).toBeChecked();
    expect((await canvas.findAllByText('의자 스쿼트')).length).toBeGreaterThan(
      0,
    );
  });

  it('previews the API-backed home states without authentication', async () => {
    await render(<PreviewGallery initialScreenId="today" />);

    const canvas = within(screen.getByTestId('preview-app-canvas'));
    expect(
      screen.getByRole('radio', { name: 'Home previous (API)' }),
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
      screen.getByRole('radio', { name: 'Workout session (API)' }),
    );
    expect((await canvas.findAllByText('의자 스쿼트')).length).toBeGreaterThan(
      0,
    );
    expect(canvas.getByRole('button', { name: '운동 마치기' })).toBeDisabled();

    fireEvent.press(
      screen.getByRole('radio', { name: 'Workout result (API)' }),
    );
    expect(
      canvas.getByRole('header', { name: '오늘 운동을 마쳤어요' }),
    ).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('radio', { name: '안전 중단' }));
    expect(
      canvas.getByRole('header', { name: '운동을 중단했어요' }),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Mascot house (API)' }));
    expect(await canvas.findByText('지금 내 루틴')).toBeOnTheScreen();
    expect(canvas.getByText('목표 4회')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Weekly report (API)' }));
    expect(
      await canvas.findByRole('header', { name: '주간 리포트' }),
    ).toBeOnTheScreen();
    expect(
      canvas.getByRole('button', { name: '리포트 생성하기' }),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Account (API)' }));
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
    fireEvent.press(canvas.getByRole('button', { name: '리포트 확인' }));
    expect(await canvas.findByText('리포트를 확인했어요')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('radio', { name: 'Account (API)' }));
    fireEvent.press(canvas.getByRole('button', { name: '계정 삭제 요청' }));
    fireEvent.press(canvas.getByRole('button', { name: '삭제를 요청할게요' }));
    expect(await canvas.findByText('계정 삭제를 접수했어요')).toBeOnTheScreen();
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

    fireEvent.press(
      screen.getByRole('radio', { name: 'Calendar/report(API)' }),
    );
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

    fireEvent.press(screen.getByRole('radio', { name: 'Workout(API)' }));
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
