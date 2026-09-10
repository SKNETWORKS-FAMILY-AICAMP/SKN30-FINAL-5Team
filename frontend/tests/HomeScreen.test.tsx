import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  act,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react-native';
import { Animated, processColor, StyleSheet } from 'react-native';

import { fontFamilies } from '../src/app/fonts';
import { imageAssets } from '../src/assets';
import { ScaleViewportProvider } from '../src/components/scale';
import { colors } from '../src/components/theme';
import {
  HOME_BACKGROUND_COLOR,
  HomeBottomNavigation,
  HomeScreen,
  bottomNavigationBottomPadding,
} from '../src/features/home/HomeScreen';
import {
  HOME_CHECKIN_OPTIONS,
  formatRoutineItem,
  getHomeRerollLabel,
  parseRoutineItem,
  type HomeRoutineItem,
} from '../src/features/home/homeModel';
import { homePreviewProps } from '../src/features/preview/homePreview';

describe('HomeScreen Home v1 transcription', () => {
  it('renders exactly one of the empty, loading, and routine branches', () => {
    const view = render(<HomeScreen previewState="pre-checkin" />);

    expect(screen.getByTestId('home-empty-state')).toBeOnTheScreen();
    expect(screen.queryByTestId('home-loading-state')).toBeNull();
    expect(screen.queryByTestId('home-routine-state')).toBeNull();

    view.rerender(<HomeScreen previewState="generating" />);
    expect(screen.queryByTestId('home-empty-state')).toBeNull();
    expect(screen.getByTestId('home-loading-state')).toBeOnTheScreen();
    expect(screen.queryByTestId('home-routine-state')).toBeNull();
    expect(screen.getByText('루틴 준비 중')).toBeOnTheScreen();
    expect(
      screen.getByTestId('routine-generation-message').props.children[0],
    ).toBe('끼끼가 오늘의 운동\n재료를 하나씩 모으는 중');
    expect(
      StyleSheet.flatten(
        screen.getByTestId('routine-loading-slot').props.style,
      ),
    ).toMatchObject({ backgroundColor: 'rgba(255, 248, 229, 0.62)' });

    view.rerender(<HomeScreen previewState="routine" />);
    expect(screen.queryByTestId('home-empty-state')).toBeNull();
    expect(screen.queryByTestId('home-loading-state')).toBeNull();
    expect(screen.getByTestId('home-routine-state')).toBeOnTheScreen();
    expect(screen.getByText('운동 준비 완료')).toBeOnTheScreen();
    expect(
      screen.getByText('컨디션에 맞춘 운동을 준비했어요'),
    ).toBeOnTheScreen();
    expect(screen.getByText('상체 근력 · 40분')).toBeOnTheScreen();
    expect(screen.queryByText('상체 근력 루틴')).toBeNull();
    expect(
      screen.getByText('운동 순서를 바꿔서 진행할 수 있어요'),
    ).toBeOnTheScreen();
  });

  it('shows API routine focus, type, and duration without a duplicate name', () => {
    render(<HomeScreen {...homePreviewProps('routine')} />);

    expect(screen.getByText('상체 · 근력 · 40분')).toBeOnTheScreen();
    expect(screen.queryByText('상체 근력 루틴')).toBeNull();
  });

  it('shows routine generation in the exercise-list slot for API requests', () => {
    const props = homePreviewProps('routine');
    const view = render(<HomeScreen {...props} busy="decision-generation" />);

    expect(screen.getByTestId('routine-loading-slot')).toBeOnTheScreen();
    expect(
      screen.getByTestId('routine-generation-message').props.children[0],
    ).toBe('끼끼가 오늘의 운동\n재료를 하나씩 모으는 중');
    expect(screen.queryByTestId('home-empty-state')).toBeNull();
    expect(screen.queryByTestId('home-routine-state')).toBeNull();

    view.rerender(
      <HomeScreen
        {...props}
        busy="decision-generation"
        routineLoadingPhaseCode="FINAL_VALIDATION"
      />,
    );
    expect(
      screen.getByTestId('routine-generation-message').props.children[0],
    ).toBe('조금만 기다려 주세요.\n안전한 루틴인지 마지막으로 확인하는 중');

    view.rerender(
      <HomeScreen
        {...props}
        busy="decision-generation"
        context={null}
        decision={null}
        routine={null}
      />,
    );
    expect(screen.getByTestId('routine-loading-slot')).toBeOnTheScreen();
    expect(screen.queryByText('기본 루틴이 아직 없어요')).toBeNull();
    const progressStyle = StyleSheet.flatten(
      screen.getByTestId('routine-generation-progress').props.style,
    );
    const placeholderStyle = StyleSheet.flatten(
      screen.getByTestId('routine-loading-placeholder-line-0', {
        includeHiddenElements: true,
      }).props.style,
    );
    expect(progressStyle.height).toBeGreaterThan(placeholderStyle.height);
    expect(progressStyle.borderWidth).toBeGreaterThan(0);
  });

  it('keeps the generation screen visible while Home data reloads on re-entry', () => {
    render(
      <HomeScreen
        busy="decision-generation"
        context={null}
        decision={null}
        routine={null}
        status="loading"
      />,
    );

    expect(screen.getByTestId('routine-generation-loading')).toBeOnTheScreen();
    expect(screen.queryByTestId('home-routine-lookup-loading')).toBeNull();
    expect(screen.queryByRole('button', { name: '운동 체크인' })).toBeNull();
  });

  it('reuses the setup screen while the saved base routine is being loaded', () => {
    render(
      <HomeScreen
        context={null}
        decision={null}
        routine={null}
        status="loading"
      />,
    );

    expect(
      screen.getByText('헬끼 준비 중이에요 조금만 기다려주세요!'),
    ).toBeOnTheScreen();
    const loadingSpinner = screen.getByTestId('home-routine-lookup-loading');
    expect(loadingSpinner).toHaveProp('color', colors.primary);
    expect(
      StyleSheet.flatten(
        screen.getByTestId('home-routine-lookup-state').props.style,
      ),
    ).toMatchObject({ paddingVertical: 19.2 });
    expect(screen.queryByRole('button', { name: '다시 준비하기' })).toBeNull();
    expect(screen.queryByTestId('routine-generation-loading')).toBeNull();
  });

  it('opens the exercise catalog from the shortcut below weekly progress', () => {
    const onOpenExerciseCatalog = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('pre-checkin')}
        onOpenExerciseCatalog={onOpenExerciseCatalog}
      />,
    );

    expect(screen.getByText('이번 주 운동 현황')).toBeOnTheScreen();
    const shortcut = screen.getByTestId('home-exercise-catalog');
    expect(shortcut).toBeEnabled();
    expect(screen.getByText('운동 리스트 보기')).toBeOnTheScreen();
    fireEvent.press(shortcut);
    expect(onOpenExerciseCatalog).toHaveBeenCalledTimes(1);
  });

  it('retries only the saved routine lookup from the reused failure screen', () => {
    const onRetry = jest.fn();
    render(
      <HomeScreen
        context={null}
        decision={null}
        onRetry={onRetry}
        routine={null}
        status="error"
      />,
    );

    expect(screen.getByText('운동 계획을 준비하지 못했어요')).toBeOnTheScreen();
    expect(
      screen.getByText(
        '운동 계획을 준비하는 중 문제가 생겼어요.\n잠시 후 다시 시도해 주세요.',
      ),
    ).toBeOnTheScreen();
    expect(screen.getByRole('alert')).toHaveTextContent(
      '운동 계획을 준비하는 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.',
    );
    expect(screen.queryByTestId('home-routine-lookup-loading')).toBeNull();

    const retry = screen.getByRole('button', {
      name: '다시 준비하기',
    });
    expect(StyleSheet.flatten(retry.props.style)).toMatchObject({
      borderColor: 'rgba(92, 148, 69, 0.82)',
      shadowColor: '#527D3F',
    });
    expect(
      screen.getByTestId('home-reload-routine-gradient').props.colors,
    ).toEqual(
      ['#E2F5C9', '#CDEDA9', '#B7E28C'].map((color) => processColor(color)),
    );

    fireEvent.press(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('uses one solid background color without a gradient', () => {
    render(<HomeScreen />);
    const background = screen.getByTestId('home-background');

    expect(HOME_BACKGROUND_COLOR).toBe('#FFF8E5');
    expect(StyleSheet.flatten(background.props.style)).toMatchObject({
      backgroundColor: '#FFF8E5',
    });
    expect(
      StyleSheet.flatten(screen.getByText('2026.08.11 (화)').props.style),
    ).toMatchObject({ color: colors.text });
    expect(screen.queryByTestId('home-gradient')).toBeNull();
  });

  it('uses monkey 10 by default and renders the profile image from My Page', () => {
    const view = render(<HomeScreen />);

    expect(screen.getByTestId('home-profile-avatar').props.source).toEqual(
      imageAssets.profileDefault,
    );

    view.rerender(
      <HomeScreen profileImageUrl="https://cdn.example.com/profile.jpg" />,
    );
    expect(screen.getByTestId('home-profile-avatar').props.source).toEqual({
      uri: 'https://cdn.example.com/profile.jpg',
    });

    fireEvent(screen.getByTestId('home-profile-avatar'), 'error');
    expect(screen.getByTestId('home-profile-avatar').props.source).toEqual(
      imageAssets.profileDefault,
    );
  });

  it('merges the weekly goal progress and the weekday row into one card', () => {
    render(
      <HomeScreen
        previewState="routine"
        weeklyCompletedCount={3}
        weeklyGoalCount={5}
      />,
    );

    expect(screen.getByText('이번 주 운동 현황')).toBeOnTheScreen();
    expect(screen.queryByText('이번 주 운동')).toBeNull();
    expect(screen.getByTestId('weekly-day-row')).toBeOnTheScreen();
    expect(screen.queryByTestId('weekly-progress-cells')).toBeNull();
    expect(screen.queryByTestId('day-todo-image')).toBeNull();
    expect(screen.queryByTestId('progress-complete-badge')).toBeNull();
    expect(screen.getByText('목표 5회 중 3회 완료')).toBeOnTheScreen();
    expect(screen.getByTestId('weekly-progress-percent')).toHaveTextContent(
      '60%',
    );
    expect(
      StyleSheet.flatten(screen.getByText('5회').props.style).fontSize,
    ).toBeLessThan(
      StyleSheet.flatten(
        screen.getByTestId('weekly-completed-count').props.style,
      ).fontSize,
    );
    expect(screen.getByTestId('weekly-progress-summary').props).toMatchObject({
      accessibilityRole: 'progressbar',
      accessibilityValue: { min: 0, max: 100, now: 60 },
    });
    fireEvent.press(
      screen.getByRole('button', { name: '이번 주 운동 현황 설명 보기' }),
    );
    expect(
      screen.getByText('이번 주 목표까지 얼마나 왔는지 확인해보세요.'),
    ).toBeOnTheScreen();
  });

  it('marks completed weekdays with the workout mascot inside the circle', () => {
    render(<HomeScreen previewState="routine" />);

    const completedImages = screen.getAllByTestId('day-done-image');
    expect(completedImages).toHaveLength(2);
    expect(
      completedImages.every(
        (image) =>
          image.props.source === imageAssets.weeklyProgressCompletedWorkout,
      ),
    ).toBe(true);
    expect(StyleSheet.flatten(completedImages[0]?.props.style)).toMatchObject({
      height: '92%',
      width: '92%',
    });
  });

  it('leaves every weekday circle empty before any completed session', () => {
    render(
      <HomeScreen
        {...homePreviewProps('routine')}
        localDate="2026-08-19"
        sessions={[]}
        week={null}
      />,
    );

    expect(screen.queryByTestId('day-done-image')).toBeNull();
    expect(screen.getAllByLabelText(/요일 기록 없음/)).toHaveLength(7);
  });

  it('renders seven weekday circles with the original completed and incomplete styles', () => {
    render(<HomeScreen previewState="routine" />);

    const labels = ['월', '화', '수', '목', '금', '토', '일'];
    for (const label of labels) {
      expect(screen.getByTestId(`week-day-${label}`)).toBeOnTheScreen();
    }
    expect(
      StyleSheet.flatten(screen.getByTestId('week-day-월').props.style),
    ).toMatchObject({
      backgroundColor: '#F6BA50',
      borderColor: '#F6BA50',
    });
    expect(
      StyleSheet.flatten(screen.getByTestId('week-day-수').props.style),
    ).toMatchObject({
      backgroundColor: '#FFFFFF',
      borderColor: '#D8D4CB',
      borderStyle: 'dashed',
    });
    expect(
      StyleSheet.flatten(screen.getByText('월').props.style),
    ).toMatchObject({ color: '#A45F00' });
    expect(
      StyleSheet.flatten(screen.getByText('수').props.style),
    ).toMatchObject({ color: '#B0ACA4' });
  });

  it('derives the API week label instead of leaking the preview fallback', () => {
    render(<HomeScreen localDate="2026-08-18" status="ready" week={null} />);

    expect(screen.getByText('8.17 ~ 8.23')).toBeOnTheScreen();
    expect(screen.queryByText('8.11 ~ 8.17 (1주차)')).toBeNull();
  });

  it('does not duplicate mascot-house content in Home API mode', () => {
    render(<HomeScreen {...homePreviewProps('routine')} />);

    expect(screen.queryByTestId('mascot-house-content')).toBeNull();
    expect(screen.queryByLabelText('끼끼와 운동 섬')).toBeNull();
  });

  it('shows the same set prescription on the Home routine', () => {
    render(<HomeScreen {...homePreviewProps('routine')} />);

    expect(screen.getByText('준비 운동 · 1세트 × 10회')).toBeOnTheScreen();
    expect(screen.getByText('푸시업 · 3세트 × 10회')).toBeOnTheScreen();
    expect(screen.queryByText(/세트 × \d+(?:분|초)/)).toBeNull();
  });

  it('uses session records for weekday completion when the week lookup is empty', () => {
    const props = homePreviewProps('routine');
    const completedSession = props.sessions?.[0];
    expect(completedSession).toBeDefined();

    render(
      <HomeScreen
        {...props}
        localDate={completedSession!.local_date}
        week={null}
        sessions={[completedSession!]}
      />,
    );

    expect(screen.getByLabelText('월요일 완료')).toBeOnTheScreen();
  });

  it('keeps weekday circles binary while exposing their completion state', () => {
    const props = homePreviewProps('routine');
    const session = props.sessions?.[0];
    expect(session).toBeDefined();

    render(
      <HomeScreen
        {...props}
        localDate="2026-08-19"
        week={null}
        sessions={[{ ...session!, local_date: '2026-08-17' }]}
      />,
    );

    expect(screen.getByLabelText('월요일 완료')).toBeOnTheScreen();
    expect(screen.getByLabelText('목요일 기록 없음')).toBeOnTheScreen();
  });

  it('leaves PARTIAL and NOT_COMPLETED weekdays unchecked', () => {
    const props = homePreviewProps('routine');
    const session = props.sessions?.[0];
    expect(session).toBeDefined();
    render(
      <HomeScreen
        {...props}
        localDate="2026-08-19"
        week={null}
        sessions={[
          {
            ...session!,
            local_date: '2026-08-17',
            status_code: 'PARTIAL',
          },
          {
            ...session!,
            session_id: 'session-preview-not-completed',
            local_date: '2026-08-19',
            status_code: 'NOT_COMPLETED',
          },
        ]}
      />,
    );

    expect(screen.getByLabelText('월요일 일부 완료')).toBeOnTheScreen();
    expect(screen.getByLabelText('수요일 휴식')).toBeOnTheScreen();
    expect(screen.getAllByLabelText(/요일 기록 없음/)).toHaveLength(5);
    expect(screen.queryByTestId('day-done-image')).toBeNull();
  });

  it('submits multiple transient discomfort areas and the selected location', () => {
    const onSubmitCheckin = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('pre-checkin')}
        onSubmitCheckin={onSubmitCheckin}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '운동 체크인' }));
    expect(screen.getByText('통증이 있는 부위가 있나요?')).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('button', { name: '헬스장' }));
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '위험 신호 없어요' }));
    fireEvent.press(screen.getByRole('button', { name: '통증 있어요' }));
    const bodyAreaButtonStyle = StyleSheet.flatten(
      screen.getByRole('button', { name: '손목·손' }).props.style,
    );
    expect(bodyAreaButtonStyle).toMatchObject({ flexBasis: '48%' });
    expect(bodyAreaButtonStyle.minHeight).toBeGreaterThanOrEqual(44);
    fireEvent.press(screen.getByRole('button', { name: '어깨' }));
    fireEvent.press(screen.getByRole('button', { name: '무릎' }));
    fireEvent(
      screen.getByTestId('checkin-pain-intensity-slider-어깨'),
      'accessibilityAction',
      { nativeEvent: { actionName: 'increment' } },
    );
    fireEvent(
      screen.getByTestId('checkin-pain-intensity-slider-무릎'),
      'accessibilityAction',
      { nativeEvent: { actionName: 'increment' } },
    );
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    expect(onSubmitCheckin).toHaveBeenCalledWith(
      expect.objectContaining({
        locationCode: 'GYM',
        pains: { SHOULDER: 2, KNEE: 2 },
        redFlagPresent: false,
      }),
    );
  });

  it.each([
    ['REST', 'BLOCKED'],
    ['STOP_AND_SEEK_HELP', 'BLOCKED'],
  ] as const)(
    'offers the existing check-in sheet again for a %s safety result',
    (actionCode, safetyStatusCode) => {
      const props = homePreviewProps('routine');
      render(
        <HomeScreen
          {...props}
          decision={{
            ...props.decision!,
            action_code: actionCode,
            safety_status_code: safetyStatusCode,
            final_plan: null,
            options: [],
          }}
        />,
      );

      const safetyCard = screen.getByTestId('home-safety-decision');
      const recheckButton = within(safetyCard).getByRole('button', {
        name: '다시 체크인하기',
      });
      expect(
        screen.getAllByRole('button', { name: '다시 체크인하기' }),
      ).toHaveLength(1);
      fireEvent.press(recheckButton);

      expect(
        screen.getByRole('header', { name: '컨디션 체크' }),
      ).toBeOnTheScreen();
      expect(
        screen.getByRole('button', { name: '집' }).props.accessibilityState
          .selected,
      ).toBe(true);
    },
  );

  it('offers re-check-in after the user already chose rest', () => {
    render(<HomeScreen {...homePreviewProps('rest')} />);

    expect(
      within(screen.getByTestId('home-rest-today')).getByRole('button', {
        name: '다시 체크인하기',
      }),
    ).toBeOnTheScreen();
    expect(screen.queryByRole('button', { name: '운동 체크인' })).toBeNull();
  });

  it('does not mount the preserved rest button after check-in', () => {
    const onChooseRest = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('routine')}
        onChooseRest={onChooseRest}
      />,
    );
    expect(screen.queryByRole('button', { name: '오늘은 쉬기' })).toBeNull();
    expect(screen.queryByTestId('home-rest-gradient')).toBeNull();
    expect(screen.queryByTestId('home-rest-icon')).toBeNull();
    expect(onChooseRest).not.toHaveBeenCalled();
  });

  it('temporarily hides available-time controls from check-in', () => {
    const onSubmitCheckin = jest.fn();
    const props = homePreviewProps('routine');
    render(
      <HomeScreen
        {...props}
        decision={null}
        context={{
          ...props.context!,
          available_slots: [
            {
              start_at: '2026-08-19T09:00:00+09:00',
              end_at: '2026-08-19T12:00:00+09:00',
            },
          ],
        }}
        onSubmitCheckin={onSubmitCheckin}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '운동 체크인' }));
    expect(screen.queryByText('오늘 운동 가능한 시간대')).toBeNull();
    expect(
      screen.queryByRole('button', { name: '가능 시간대 추가' }),
    ).toBeNull();
    expect(screen.queryByLabelText(/번째 가능 시간 (시작|종료)/)).toBeNull();
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    expect(onSubmitCheckin).toHaveBeenCalledWith(
      expect.objectContaining({
        availableSlots: [{ startTime: '09:00', endTime: '12:00' }],
      }),
    );
  });

  it('shows one posture action at its original size and keeps equipment actions hidden', () => {
    const props = homePreviewProps('routine');
    const getExerciseVariants = jest.fn(
      props.exerciseApi!.getExerciseVariants!,
    );
    render(
      <HomeScreen
        {...props}
        exerciseApi={{
          getExercise: props.exerciseApi!.getExercise,
          getExerciseVariants,
        }}
      />,
    );

    expect(screen.getAllByText('자세')).toHaveLength(3);
    const postureButton = screen.getByRole('button', {
      name: '밴드 로우 자세',
    });
    expect(
      screen.queryByRole('button', { name: /장비 (보기|안내 다시 확인)/ }),
    ).toBeNull();
    expect(screen.queryByText('장비')).toBeNull();
    const postureStyle = StyleSheet.flatten(postureButton.props.style);
    expect(postureStyle.width).toBeCloseTo(48 * 1.2);
    expect(screen.queryByTestId(/routine-equipment-slot-/)).toBeNull();
    expect(
      screen.getByTestId('routine-guide-actions-plan-item-1'),
    ).toBeVisible();
    expect(
      screen.getByTestId('routine-guide-actions-plan-item-2'),
    ).toBeVisible();
    expect(
      screen.getByTestId('routine-guide-actions-plan-item-3'),
    ).toBeVisible();
    expect(getExerciseVariants).not.toHaveBeenCalled();
  });

  it('opens reviewed posture guidance from an API routine item', async () => {
    const props = homePreviewProps('routine');
    render(
      <HomeScreen
        {...props}
        exerciseApi={{
          ...props.exerciseApi!,
          async getExercise(exerciseId, signal) {
            const detail = await props.exerciseApi!.getExercise(
              exerciseId,
              signal,
            );
            return {
              ...detail,
              media_asset_key: 'catalog-media/push-up.gif',
              media_url: 'https://cdn.example.com/push-up.gif',
            };
          },
        }}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '푸시업 자세' }));

    expect(screen.getByRole('header', { name: '푸시업' })).toBeOnTheScreen();
    expect(
      await screen.findByText('통증이 없는 범위에서 천천히 움직여주세요.'),
    ).toBeOnTheScreen();
    expect(screen.getByTestId('exercise-media-image')).toHaveProp('source', {
      uri: 'https://cdn.example.com/push-up.gif',
    });
    expect(screen.getByText('호흡을 멈추지 않기')).toBeOnTheScreen();
  });

  it('keeps posture guidance scrollable inside the capped sheet', async () => {
    render(<HomeScreen {...homePreviewProps('routine')} />);

    fireEvent.press(screen.getByRole('button', { name: '푸시업 자세' }));

    // The sheet frame caps its height, so content past the fold is only
    // reachable when it is rendered inside the sheet's scroll view.
    const scroll = await screen.findByTestId('exercise-guide-scroll');
    expect(
      await within(scroll).findByText('호흡을 멈추지 않기'),
    ).toBeOnTheScreen();
  });

  it('explains the recommendation with server-supplied per-agent reasoning', () => {
    const view = render(<HomeScreen {...homePreviewProps('adjusted')} />);
    fireEvent.press(
      screen.getByRole('button', { name: '이 루틴을 추천한 이유 >' }),
    );
    expect(
      screen.getByRole('header', { name: '이 루틴을 추천한 이유' }),
    ).toBeOnTheScreen();
    expect(screen.getByText('에이전트별 판단')).toBeOnTheScreen();
    expect(screen.getByText('최종 조정 이유')).toBeOnTheScreen();
    expect(screen.getByText('반영한 기준')).toBeOnTheScreen();
    expect(
      screen.queryByText(/저장된 체크인과 안전 기준을 바탕으로/),
    ).toBeNull();
    // Machine codes stay internal however the sections are composed.
    const tree = JSON.stringify(view.toJSON());
    for (const internal of [
      'MODERATE_FATIGUE_DOWNSHIFT',
      'COMMON_CANDIDATE_SELECTED',
    ]) {
      expect(tree).not.toContain(internal);
    }
  });

  it('keeps legacy recommendation reasons usable without agent summaries', () => {
    const props = homePreviewProps('adjusted');
    expect(props.decision).not.toBeNull();
    const decision = {
      ...props.decision!,
      public_agent_summaries: null,
    };

    render(<HomeScreen {...props} decision={decision} />);
    fireEvent.press(
      screen.getByRole('button', { name: '이 루틴을 추천한 이유 >' }),
    );

    expect(screen.queryByText('에이전트별 판단')).toBeNull();
    expect(screen.queryByText('최종 조정 이유')).toBeNull();
    // The reviewed criteria list still stands on its own for older decisions.
    expect(screen.getByText('반영한 기준')).toBeOnTheScreen();
  });

  it('shows a safety caution supplied through adjustment reason codes', () => {
    const props = homePreviewProps('adjusted');
    expect(props.decision).not.toBeNull();
    const decision = {
      ...props.decision!,
      reason_codes: [],
      adjustment_reason_codes: ['SAFETY_CAUTION_APPLIED'],
      safety_summary: null,
    };

    render(<HomeScreen {...props} decision={decision} />);

    fireEvent.press(
      screen.getByRole('button', { name: '이 루틴을 추천한 이유 >' }),
    );
    // The criteria list is collapsed until asked for.
    fireEvent.press(screen.getByRole('button', { name: '반영한 기준 펼치기' }));
    expect(
      screen.getByText('불편한 부위를 고려해 강도를 낮췄어요.'),
    ).toBeOnTheScreen();
  });

  it('distinguishes adjusted and unchanged API routines by action label', () => {
    const adjustedView = render(
      <HomeScreen {...homePreviewProps('adjusted')} />,
    );

    expect(screen.getByText('강도 낮춰 진행')).toBeOnTheScreen();
    expect(
      screen.getByLabelText('루틴 진행 방식: 강도 낮춰 진행'),
    ).toBeOnTheScreen();

    adjustedView.rerender(<HomeScreen {...homePreviewProps('routine')} />);
    expect(screen.queryByText('계획대로 진행')).toBeNull();
    expect(screen.queryByLabelText('루틴 진행 방식: 계획대로 진행')).toBeNull();
  });

  it('renders the matching action badge in preview mode', () => {
    const previewView = render(<HomeScreen previewState="routine" />);

    expect(screen.queryByLabelText('루틴 진행 방식: 계획대로 진행')).toBeNull();

    previewView.unmount();
    render(<HomeScreen previewState="adjusted" />);
    expect(
      screen.getByLabelText('루틴 진행 방식: 강도 낮춰 진행'),
    ).toBeOnTheScreen();
  });

  it('lets API exercise items be reordered from the three-line handles', () => {
    const onReorderPlan = jest.fn();
    const onNavigateTab = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('routine')}
        onNavigateTab={onNavigateTab}
        onReorderPlan={onReorderPlan}
      />,
    );

    fireEvent(
      screen.getByTestId('routine-drag-plan-item-1'),
      'accessibilityAction',
      { nativeEvent: { actionName: 'increment' } },
    );
    expect(onReorderPlan).toHaveBeenCalledWith(0, 1);
    fireEvent.press(screen.getByRole('button', { name: '세트·횟수 수정' }));
    expect(screen.getByText('푸시업')).toBeOnTheScreen();
    expect(screen.queryByRole('header', { name: /운동 장소/ })).toBeNull();
    expect(screen.getByLabelText('푸시업 세트 수')).toBeOnTheScreen();
    expect(screen.getByLabelText('푸시업 반복 횟수')).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: '저장하기' })).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '운동 시작하기' }).props
        .accessibilityState.disabled,
    ).toBe(true);
    expect(
      screen.getByRole('button', { name: '다른 루틴 추천 받기' }).props
        .accessibilityState.disabled,
    ).toBe(true);
    expect(screen.queryByTestId('routine-drag-plan-item-1')).toBeNull();
    expect(screen.getByTestId('home-start-gradient').props.colors).toEqual(
      ['#E7E5E2', '#E7E5E2'].map(processColor),
    );
    expect(
      StyleSheet.flatten(
        screen.getByRole('button', { name: '다른 루틴 추천 받기' }).props.style,
      ),
    ).toMatchObject({
      backgroundColor: '#F2F1EF',
      borderColor: '#D8D5D1',
    });
    fireEvent.changeText(screen.getByLabelText('푸시업 세트 수'), '9');
    fireEvent.press(screen.getByRole('tab', { name: '끼끼의 집' }));
    expect(onNavigateTab).toHaveBeenCalledWith('house');
    expect(screen.queryByRole('button', { name: '저장하기' })).toBeNull();
    expect(screen.getByText('푸시업 · 3세트 × 10회')).toBeOnTheScreen();
  });

  it('opens a live gap in both directions and commits immediately on drop', () => {
    const onReorderPlan = jest.fn();
    const timingCompletions: ((result: { finished: boolean }) => void)[] = [];
    const timingSpy = jest.spyOn(Animated, 'timing').mockImplementation(
      () =>
        ({
          start: (callback?: (result: { finished: boolean }) => void) => {
            if (callback) {
              timingCompletions.push(callback);
            }
          },
          stop: jest.fn(),
          reset: jest.fn(),
        }) as Animated.CompositeAnimation,
    );
    render(
      <HomeScreen
        {...homePreviewProps('routine')}
        onReorderPlan={onReorderPlan}
      />,
    );

    ['plan-item-1', 'plan-item-2', 'plan-item-3'].forEach((id, index) => {
      fireEvent(screen.getByTestId(`routine-row-${id}`), 'layout', {
        nativeEvent: {
          layout: { height: 44, width: 300, x: 0, y: index * 60 },
        },
      });
    });

    const handle = screen.getByTestId('routine-drag-plan-item-1');
    const panEvent = (currentY: number, previousY: number, time: number) => ({
      nativeEvent: { touches: [{}] },
      touchHistory: {
        indexOfSingleActiveTouch: 0,
        mostRecentTimeStamp: time,
        numberActiveTouches: 1,
        touchBank: [
          {
            touchActive: true,
            startPageX: 0,
            startPageY: 0,
            startTimeStamp: 1,
            currentPageX: 0,
            currentPageY: currentY,
            currentTimeStamp: time,
            previousPageX: 0,
            previousPageY: previousY,
            previousTimeStamp: Math.max(0, time - 1),
          },
        ],
      },
    });
    const startEvent = panEvent(0, 0, 1);
    const moveEvent = panEvent(35, 0, 2);
    expect(handle.props.onStartShouldSetResponderCapture(startEvent)).toBe(
      true,
    );
    expect(handle.props.onResponderTerminationRequest(startEvent)).toBe(false);

    fireEvent(handle, 'responderGrant', startEvent);
    fireEvent(handle, 'responderMove', moveEvent);
    expect(onReorderPlan).not.toHaveBeenCalled();
    expect(
      screen.getByTestId('routine-drop-placeholder-plan-item-2'),
    ).toBeOnTheScreen();
    fireEvent(handle, 'responderRelease', moveEvent);
    expect(onReorderPlan).toHaveBeenCalledWith(0, 1);
    expect(
      screen.queryByTestId('routine-drop-placeholder-plan-item-2'),
    ).toBeNull();
    act(() => timingCompletions.shift()?.({ finished: true }));

    const secondHandle = screen.getByTestId('routine-drag-plan-item-3');
    const secondStartEvent = panEvent(0, 0, 3);
    const middleMoveEvent = panEvent(-60, 0, 4);
    const upwardMoveEvent = panEvent(-160, -60, 5);
    fireEvent(secondHandle, 'responderGrant', secondStartEvent);
    fireEvent(secondHandle, 'responderMove', middleMoveEvent);
    const middlePlaceholder = screen.getByTestId(
      'routine-drop-placeholder-plan-item-2',
    );
    expect(StyleSheet.flatten(middlePlaceholder.props.style)).toMatchObject({
      backgroundColor: '#FFF3D4',
      borderColor: '#E0A742',
      borderStyle: 'dashed',
    });
    expect(
      screen.queryByTestId('routine-drop-placeholder-plan-item-3'),
    ).toBeNull();

    fireEvent(secondHandle, 'responderMove', upwardMoveEvent);
    expect(onReorderPlan).toHaveBeenCalledTimes(1);
    expect(
      screen.getByTestId('routine-drop-placeholder-plan-item-1'),
    ).toBeOnTheScreen();
    expect(
      screen.queryByTestId('routine-drop-placeholder-plan-item-2'),
    ).toBeNull();
    fireEvent(secondHandle, 'responderRelease', upwardMoveEvent);
    expect(onReorderPlan).toHaveBeenCalledTimes(2);
    act(() => timingCompletions.shift()?.({ finished: true }));

    expect(onReorderPlan).toHaveBeenNthCalledWith(1, 0, 1);
    expect(onReorderPlan).toHaveBeenNthCalledWith(2, 2, 0);
    expect(timingSpy).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        duration: 85,
        toValue: -60,
        useNativeDriver: true,
      }),
    );
    expect(timingSpy).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        duration: 85,
        toValue: 60,
        useNativeDriver: true,
      }),
    );
    expect(timingSpy).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        duration: 80,
        toValue: 0,
        useNativeDriver: true,
      }),
    );
    timingSpy.mockRestore();
  });

  it('uses a serious existing state card for a blocked plan revision', () => {
    const props = homePreviewProps('routine');
    render(
      <HomeScreen
        {...props}
        planRevision={{
          revision_id: 'revision-blocked',
          week_start: props.week?.week_start ?? '2026-08-17',
          week_end: props.week?.week_end ?? '2026-08-23',
          revision_sequence: 2,
          ai_revision_count: 1,
          source_code: 'AI',
          source_weekly_report_id: null,
          safety_status_code: 'BLOCKED',
          routine: null,
          selected_location_code: null,
          finalized: false,
          finalized_at: null,
          revision_reason_codes: ['SAFETY_OPINION_NOT_APPLIED'],
          finalization_reason_codes: ['REVISION_STATUS_BLOCKS_FINALIZE'],
          created_at: '2026-08-19T08:00:00+09:00',
        }}
      />,
    );

    expect(
      screen.getByTestId('home-action-error').props.accessibilityRole,
    ).toBe('alert');
    expect(screen.getByText('안전하게 진행할 수 없어요')).toBeOnTheScreen();
    expect(
      screen.getByText(/안전 기준을 충족하지 않아 조정을 적용하지 않았어요/),
    ).toBeOnTheScreen();
  });

  it('does not show a fake unread notification or enable an unwired bell', () => {
    const onNotifications = jest.fn();
    const onDismissNotificationPanel = jest.fn();
    const view = render(<HomeScreen previewState="routine" />);
    const disabledButton = screen.getByRole('button', { name: '알림 보기' });

    expect(disabledButton.props.accessibilityState.disabled).toBe(true);
    expect(StyleSheet.flatten(disabledButton.props.style)).toMatchObject({
      backgroundColor: colors.text,
    });
    expect(
      StyleSheet.flatten(screen.getByText('헬끼님').props.style),
    ).toMatchObject({ color: colors.greenText });
    expect(
      StyleSheet.flatten(
        screen.getByLabelText('읽지 않은 알림 있음', {
          includeHiddenElements: true,
        }).props.style,
      ),
    ).toMatchObject({ display: 'none' });

    view.rerender(
      <HomeScreen
        hasUnreadNotification
        onDismissNotificationPanel={onDismissNotificationPanel}
        onNotifications={onNotifications}
        previewState="routine"
      />,
    );
    const button = screen.getByRole('button', { name: '알림 보기' });
    expect(button.props.accessibilityState.disabled).toBe(false);
    const stopPropagation = jest.fn();
    fireEvent(button, 'pointerDown', { stopPropagation });
    expect(stopPropagation).toHaveBeenCalledTimes(1);
    fireEvent.press(button);
    expect(onNotifications).toHaveBeenCalledTimes(1);
    fireEvent(screen.getByTestId('home-screen'), 'pointerDown');
    expect(onDismissNotificationPanel).toHaveBeenCalledTimes(1);
  });

  it('shows only persisted check-in fields and keeps safe defaults', () => {
    render(<HomeScreen previewState="checkin" />);

    const choices = screen
      .getAllByRole('button')
      .filter((node) => node.props.accessibilityState?.selected !== undefined);
    expect(choices.map((node) => node.props.accessibilityLabel)).toEqual([
      ...HOME_CHECKIN_OPTIONS.fatigue,
      '통증 없어요',
      '통증 있어요',
      '위험 신호 없어요',
      '위험 신호 있어요',
    ]);
    expect(
      choices
        .filter((node) => node.props.accessibilityState.selected)
        .map((node) => node.props.accessibilityLabel),
    ).toEqual(['보통이에요', '통증 없어요']);
    expect(screen.queryByLabelText('운동 가능 시간 (분)')).toBeNull();
    expect(screen.getByLabelText('운동 가능 시간 30분')).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '운동 시간 10분 줄이기' }),
    ).toBeEnabled();
    expect(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    ).toBeEnabled();
    expect(screen.getByLabelText('수면 시간 (시간)').props.value).toBe('');
    expect(screen.queryByText('컨디션')).toBeNull();
    expect(screen.queryByLabelText('오늘 걸음 수')).toBeNull();
    expect(
      screen.queryByText('현재 상태에 맞춰 운동을 조정해드려요.'),
    ).toBeNull();
    expect(screen.getByText('운동 전 확인이 필요해요')).toBeOnTheScreen();
    expect(screen.queryByText('위 증상이 있나요?')).toBeNull();
    const redFlagGroup = screen.getByTestId('checkin-red-flag-section');
    expect(redFlagGroup).toHaveProp('role', 'group');
    expect(redFlagGroup).toHaveProp(
      'accessibilityLabel',
      '운동 전 확인이 필요해요',
    );
    expect(
      within(redFlagGroup).getByRole('button', { name: '위험 신호 없어요' }),
    ).toBeOnTheScreen();
    expect(
      within(redFlagGroup).getByRole('button', { name: '위험 신호 있어요' }),
    ).toBeOnTheScreen();
    expect(screen.queryByText('위험 신호 여부를 선택해주세요.')).toBeNull();
  });

  it('starts workout duration at 30 minutes and adjusts it by ten', () => {
    render(<HomeScreen {...homePreviewProps('pre-checkin')} />);

    fireEvent.press(screen.getByRole('button', { name: '운동 체크인' }));
    expect(screen.getByLabelText('운동 가능 시간 30분')).toBeOnTheScreen();
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );
    expect(screen.getByLabelText('운동 가능 시간 40분')).toBeOnTheScreen();
    expect(screen.getByText('운동 장소')).toBeOnTheScreen();
  });

  it('prefills onboarding persistent pains only for a new daily check-in', () => {
    render(
      <HomeScreen
        {...homePreviewProps('pre-checkin')}
        persistentPains={[
          { body_area_code: 'KNEE', intensity_score: 4 },
          { body_area_code: 'LOWER_BACK', intensity_score: 6 },
        ]}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '운동 체크인' }));
    expect(
      screen.getByRole('button', { name: '통증 있어요' }).props
        .accessibilityState.selected,
    ).toBe(true);
    expect(
      screen.getByTestId('checkin-pain-intensity-value-무릎'),
    ).toHaveTextContent('4');
    expect(
      screen.getByTestId('checkin-pain-intensity-value-허리'),
    ).toHaveTextContent('6');
    expect(
      StyleSheet.flatten(
        screen.getByTestId('checkin-pain-intensity-track-무릎').props.style,
      ).height,
    ).toBe(4);
    expect(
      StyleSheet.flatten(
        screen.getByTestId('checkin-pain-intensity-thumb-무릎').props.style,
      ).width,
    ).toBe(18);
  });

  it('uses the saved daily pains instead of persistent pain defaults on re-check-in', () => {
    const props = homePreviewProps('rest');
    render(
      <HomeScreen
        {...props}
        context={{
          ...props.context!,
          pain_present: true,
          pains: [{ body_area_code: 'SHOULDER', intensity_score: 7 }],
        }}
        persistentPains={[{ body_area_code: 'KNEE', intensity_score: 2 }]}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '다시 체크인하기' }));
    expect(
      screen.getByTestId('checkin-pain-intensity-value-어깨'),
    ).toHaveTextContent('7');
    expect(
      screen.queryByTestId('checkin-pain-intensity-value-무릎'),
    ).toBeNull();
  });

  it('uses the onboarding-style secondary control for additional pain areas', () => {
    render(<HomeScreen previewState="checkin" />);

    fireEvent.press(screen.getByRole('button', { name: '통증 있어요' }));
    const basicAreas = ['어깨', '허리', '무릎', '목', '손목·손', '발목·발'];
    const extraAreas = ['팔꿈치', '등 위쪽', '고관절', '가슴', '복부'];
    basicAreas.forEach((name) =>
      expect(screen.getByRole('button', { name })).toBeOnTheScreen(),
    );
    extraAreas.forEach((name) =>
      expect(screen.queryByRole('button', { name })).toBeNull(),
    );
    expect(
      screen.getByText('통증이 있는 부위를 모두 선택해주세요.'),
    ).toBeOnTheScreen();
    const toggle = screen.getByRole('button', { name: '다른 부위 보기' });
    expect(toggle.props.accessibilityState).toEqual({ expanded: false });
    fireEvent.press(toggle);
    extraAreas.forEach((name) =>
      expect(screen.getByRole('button', { name })).toBeOnTheScreen(),
    );
    expect(
      screen.getByRole('button', { name: '다른 부위 접기' }).props
        .accessibilityState,
    ).toEqual({ expanded: true });
    expect(screen.getByText('접기')).toBeOnTheScreen();
    expect(
      screen.getByTestId('checkin-extended-area-caret').props.style,
    ).toMatchObject({ transform: [{ rotate: '180deg' }] });
  });

  it('enables check-in only after every required safety input is complete', () => {
    const onSubmitCheckin = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('pre-checkin')}
        onSubmitCheckin={onSubmitCheckin}
      />,
    );
    fireEvent.press(screen.getByRole('button', { name: '운동 체크인' }));
    fireEvent.press(screen.getByRole('button', { name: '통증 있어요' }));
    const painPrompt = '통증이 있는 부위를 모두 선택해주세요.';
    expect(
      screen.getByText(painPrompt).props.accessibilityRole,
    ).toBeUndefined();
    expect(screen.queryByText('위험 신호 여부를 선택해주세요.')).toBeNull();
    expect(screen.getByRole('button', { name: '체크인 !' })).toBeDisabled();
    expect(onSubmitCheckin).not.toHaveBeenCalled();
    expect(screen.getAllByText(painPrompt)).toHaveLength(1);
    fireEvent.press(screen.getByRole('button', { name: '위험 신호 없어요' }));
    expect(screen.queryByText('위험 신호 여부를 선택해주세요.')).toBeNull();
    expect(screen.getByRole('button', { name: '체크인 !' })).toBeDisabled();
    expect(onSubmitCheckin).not.toHaveBeenCalled();
    fireEvent.press(screen.getByRole('button', { name: '목' }));
    expect(
      screen.getByText(painPrompt).props.accessibilityRole,
    ).toBeUndefined();
    const submit = screen.getByRole('button', { name: '체크인 !' });
    expect(submit).toBeEnabled();
    fireEvent.press(submit);
    expect(onSubmitCheckin).toHaveBeenCalledWith(
      expect.objectContaining({
        pains: { NECK: 1 },
        redFlagPresent: false,
      }),
    );
  });

  it('opens additional areas for saved elbow pain and retains it when collapsed', () => {
    const onSubmitCheckin = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('pre-checkin')}
        persistentPains={[{ body_area_code: 'ELBOW', intensity_score: 3 }]}
        onSubmitCheckin={onSubmitCheckin}
      />,
    );
    fireEvent.press(screen.getByRole('button', { name: '운동 체크인' }));
    expect(
      screen.getByRole('button', { name: '팔꿈치' }).props.accessibilityState
        .selected,
    ).toBe(true);
    fireEvent.press(screen.getByRole('button', { name: '다른 부위 접기' }));
    expect(
      screen.getByTestId('checkin-pain-intensity-value-팔꿈치'),
    ).toHaveTextContent('3');
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '위험 신호 없어요' }));
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));
    expect(onSubmitCheckin).toHaveBeenCalledWith(
      expect.objectContaining({ pains: { ELBOW: 3 } }),
    );
  });

  it('adjusts the requested duration by ten minutes and submits it', () => {
    const onSubmitCheckin = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('pre-checkin')}
        onSubmitCheckin={onSubmitCheckin}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '운동 체크인' }));
    for (let count = 0; count < 2; count += 1) {
      fireEvent.press(
        screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
      );
    }
    expect(screen.getByLabelText('운동 가능 시간 50분')).toBeOnTheScreen();
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 줄이기' }),
    );
    expect(screen.getByLabelText('운동 가능 시간 40분')).toBeOnTheScreen();
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '위험 신호 없어요' }));
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    expect(onSubmitCheckin).toHaveBeenCalledWith(
      expect.objectContaining({ availableTimeMinutes: 50 }),
    );
  });

  it('allows 90 minutes without showing a recommendation label', () => {
    const onSubmitCheckin = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('pre-checkin')}
        onSubmitCheckin={onSubmitCheckin}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '운동 체크인' }));
    expect(screen.queryByText(/권장 운동 시간/)).toBeNull();

    for (let count = 0; count < 6; count += 1) {
      fireEvent.press(
        screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
      );
    }

    expect(screen.getByLabelText('운동 가능 시간 90분')).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    ).toBeDisabled();
    expect(screen.queryByText(/권장 운동 시간/)).toBeNull();

    fireEvent.press(screen.getByRole('button', { name: '위험 신호 없어요' }));
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    expect(onSubmitCheckin).toHaveBeenCalledWith(
      expect.objectContaining({ availableTimeMinutes: 90 }),
    );
  });

  it('keeps check-in usable without recommendation guidance', () => {
    render(<HomeScreen previewState="checkin" />);

    expect(screen.queryByText(/권장 운동 시간/)).toBeNull();
    expect(screen.getByLabelText('운동 가능 시간 30분')).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    ).toBeEnabled();
  });

  it('requires one combined Red Flag answer without collecting symptom details', () => {
    render(<HomeScreen previewState="checkin" />);

    expect(screen.queryByText('심한 어지럼')).toBeNull();
    expect(screen.getByText('• 가슴 통증·압박감')).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: '체크인 !' })).toBeDisabled();
    expect(screen.queryByText('위험 신호 여부를 선택해주세요.')).toBeNull();
    expect(
      screen.getByRole('button', { name: '체크인 !' }).props.accessibilityState
        .disabled,
    ).toBe(true);

    fireEvent.press(screen.getByRole('button', { name: '위험 신호 있어요' }));
    expect(
      screen.getByRole('button', { name: '체크인 !' }).props.accessibilityState
        .disabled,
    ).toBe(false);
    expect(
      screen.getByRole('button', { name: '위험 신호 있어요' }).props
        .accessibilityState.selected,
    ).toBe(true);
  });

  it('explains what is missing when the dimmed check-in button is pressed', () => {
    // setSubmitAttempted only ever runs from this button's onPress. A truly
    // disabled Pressable never fires it, which left every message gated on it
    // unreachable and told a blocked user nothing.
    render(<HomeScreen previewState="checkin" />);

    const submitButton = screen.getByRole('button', { name: '체크인 !' });
    expect(submitButton).toBeDisabled();
    expect(screen.queryByText('위험 신호 여부를 선택해주세요.')).toBeNull();

    fireEvent.press(submitButton);

    expect(
      screen.getByText('위험 신호 여부를 선택해주세요.'),
    ).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: '체크인 !' })).toBeDisabled();
  });

  it('dims the check-in submit button while required inputs are missing', () => {
    render(<HomeScreen previewState="checkin" />);

    const submitButton = screen.getByRole('button', { name: '체크인 !' });
    expect(submitButton).toBeDisabled();
    const disabledButtonStyle = StyleSheet.flatten(submitButton.props.style);
    const disabledGradientStyle = StyleSheet.flatten(
      screen.getByTestId('home-checkin-submit-gradient').props.style,
    );
    const disabledLabelStyle = StyleSheet.flatten(
      screen.getByText('체크인 !').props.style,
    );

    expect(disabledButtonStyle.borderColor).toBe('#E3DAD0');
    expect(disabledButtonStyle.shadowOpacity).toBe(0);
    expect(disabledGradientStyle.opacity).toBe(0.35);
    expect(disabledLabelStyle.color).toBe('#AFA69B');

    fireEvent.press(screen.getByRole('button', { name: '위험 신호 없어요' }));

    expect(screen.getByRole('button', { name: '체크인 !' })).toBeEnabled();
    expect(
      StyleSheet.flatten(
        screen.getByRole('button', { name: '체크인 !' }).props.style,
      ).borderColor,
    ).toBe('rgba(244, 166, 42, 0.8)');
    expect(
      StyleSheet.flatten(
        screen.getByTestId('home-checkin-submit-gradient').props.style,
      ).opacity,
    ).toBeUndefined();
    expect(
      StyleSheet.flatten(screen.getByText('체크인 !').props.style).color,
    ).toBe('#5A4636');
  });

  it('isolates check-in draft changes until save and discards them on close', () => {
    render(<HomeScreen previewState="routine" />);

    fireEvent.press(screen.getByRole('button', { name: '운동 체크인' }));
    fireEvent.press(screen.getByRole('button', { name: '통증 있어요' }));
    fireEvent.press(screen.getByRole('button', { name: '어깨' }));
    expect(
      screen.queryByText('어깨 부담을 줄이도록 강도를 조정했어요.'),
    ).toBeNull();
    fireEvent.press(screen.getByRole('button', { name: '닫기' }));

    fireEvent.press(screen.getByRole('button', { name: '운동 체크인' }));
    expect(
      screen.getByRole('button', { name: '통증 없어요' }).props
        .accessibilityState.selected,
    ).toBe(true);
    expect(screen.queryByRole('button', { name: '어깨' })).toBeNull();

    fireEvent.press(screen.getByRole('button', { name: '통증 있어요' }));
    expect(
      screen.getByRole('button', { name: '어깨' }).props.accessibilityState
        .selected,
    ).toBe(false);
    fireEvent.press(screen.getByRole('button', { name: '어깨' }));
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));
    expect(
      screen.getByText('어깨 부담을 줄이도록 강도를 조정했어요.'),
    ).toBeOnTheScreen();
  });

  it('uses all three reroll labels and disables the action after two 900ms requests', () => {
    jest.useFakeTimers();
    render(<HomeScreen previewState="routine" />);

    expect(getHomeRerollLabel(0, false)).toBe('다른 루틴 · 2회 남음');
    expect(getHomeRerollLabel(0, true)).toBe('추천 받는 중…');
    expect(getHomeRerollLabel(2, false)).toBe('추천 횟수 소진');
    expect(screen.getByText('다른 루틴 · 2회 남음')).toBeOnTheScreen();

    fireEvent.press(
      screen.getByRole('button', { name: '다른 루틴 추천 받기' }),
    );
    expect(screen.getByTestId('home-loading-state')).toBeOnTheScreen();
    act(() => jest.advanceTimersByTime(900));
    expect(screen.getByText('다른 루틴 · 1회 남음')).toBeOnTheScreen();

    fireEvent.press(
      screen.getByRole('button', { name: '다른 루틴 추천 받기' }),
    );
    act(() => jest.advanceTimersByTime(900));
    expect(screen.getByText('추천 횟수 소진')).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '다른 루틴 추천 받기' }).props
        .accessibilityState.disabled,
    ).toBe(true);
    jest.useRealTimers();
  });

  it('hides the top check-in after a plan and opens a prefilled check-in for another routine', () => {
    const onRequestAlternativeCheckin = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('routine')}
        onRequestAlternativeCheckin={onRequestAlternativeCheckin}
      />,
    );

    expect(screen.queryByRole('button', { name: '운동 체크인' })).toBeNull();
    fireEvent.press(
      screen.getByRole('button', { name: '다른 루틴 추천 받기' }),
    );
    expect(
      screen.getByRole('button', { name: '집' }).props.accessibilityState
        .selected,
    ).toBe(true);
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));
    expect(onRequestAlternativeCheckin).toHaveBeenCalledWith(
      expect.objectContaining({ locationCode: 'HOME' }),
      false,
    );
  });

  it('applies set and repetition edits without consuming another-routine quota', () => {
    const onSubmitUserEdits = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('routine')}
        onSubmitUserEdits={onSubmitUserEdits}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '세트·횟수 수정' }));
    fireEvent.changeText(screen.getByLabelText('푸시업 세트 수'), '4');
    fireEvent.changeText(screen.getByLabelText('푸시업 반복 횟수'), '8');
    fireEvent.press(screen.getByRole('button', { name: '저장하기' }));

    expect(onSubmitUserEdits).toHaveBeenCalledWith(
      expect.objectContaining({
        itemOverrides: [
          {
            planItemId: 'plan-item-2',
            sets: 4,
            reps: 8,
            workSecondsPerSet: null,
          },
        ],
      }),
    );
    expect(screen.getByText('푸시업 · 4세트 × 8회')).toBeOnTheScreen();
    expect(screen.getByText('다른 루틴 · 2회 남음')).toBeOnTheScreen();
  });

  it('locks an active or safety-stopped routine while preserving progress', () => {
    const onReorderPlan = jest.fn();
    const activeView = render(
      <HomeScreen
        {...homePreviewProps('session-active')}
        onReorderPlan={onReorderPlan}
        onResumeWorkout={() => undefined}
      />,
    );
    expect(screen.getByRole('button', { name: '이어하기' })).toBeOnTheScreen();
    expect(screen.getByText('✓ 준비 운동 · 1세트 × 10회')).toBeOnTheScreen();
    expect(
      StyleSheet.flatten(
        screen.getByLabelText('완료: 준비 운동 · 1세트 × 10회').props.style,
      ).color,
    ).toBe('#AAA49D');
    expect(screen.queryByTestId('routine-drag-plan-item-1')).toBeNull();
    expect(screen.getByTestId('routine-drag-plan-item-2')).toBeOnTheScreen();
    fireEvent(
      screen.getByTestId('routine-drag-plan-item-2'),
      'accessibilityAction',
      { nativeEvent: { actionName: 'increment' } },
    );
    expect(onReorderPlan).toHaveBeenCalledWith(1, 2);
    expect(screen.queryByRole('button', { name: '세트·횟수 수정' })).toBeNull();
    expect(
      screen.queryByRole('button', { name: '다른 루틴 추천 받기' }),
    ).toBeNull();

    activeView.unmount();
    render(<HomeScreen {...homePreviewProps('session-safety-stopped')} />);
    expect(screen.getByText('안전 중단')).toBeOnTheScreen();
    expect(screen.queryByRole('button', { name: '이어하기' })).toBeNull();
    expect(screen.queryByRole('button', { name: '운동 시작하기' })).toBeNull();
    expect(screen.getByText(/진행 기록은 그대로 보관됩니다/)).toBeOnTheScreen();
    expect(screen.getByText('오늘은 회복에 집중해요')).toBeOnTheScreen();
    expect(screen.queryByText('컨디션에 맞춘 운동을 준비했어요')).toBeNull();
    expect(screen.queryByText('조금만 더 힘내요!')).toBeNull();
  });

  it('changes the routine heading for stopped and fully completed workouts', () => {
    const resumableView = render(
      <HomeScreen {...homePreviewProps('session-resumable')} />,
    );
    expect(screen.getByText('조금만 더 힘내요!')).toBeOnTheScreen();

    resumableView.unmount();
    const partialProps = homePreviewProps('session-completed');
    const partialView = render(
      <HomeScreen
        {...partialProps}
        todaySession={
          partialProps.todaySession
            ? { ...partialProps.todaySession, status_code: 'PARTIAL' }
            : null
        }
      />,
    );
    expect(screen.getByText('조금만 더 힘내요!')).toBeOnTheScreen();

    partialView.unmount();
    render(<HomeScreen {...homePreviewProps('session-completed')} />);
    expect(
      screen.getByText('오늘도 자신과의 싸움에서 승리했군요!'),
    ).toBeOnTheScreen();
  });

  it('parses and formats prescriptions only when both sets and reps exist', () => {
    expect(parseRoutineItem('푸시업 · 3세트 × 10회', 'push-up')).toEqual({
      id: 'push-up',
      name: '푸시업',
      sets: '3',
      reps: '10',
    });
    expect(formatRoutineItem({ id: 'warm-up', name: '준비 운동' })).toBe(
      '준비 운동',
    );
    expect(
      formatRoutineItem({ id: 'partial', name: '플랭크', sets: '3' }),
    ).toBe('플랭크');
    expect(
      formatRoutineItem({
        id: 'push-up',
        name: '푸시업',
        sets: '3',
        reps: '10',
      }),
    ).toBe('푸시업 · 3세트 × 10회');
  });

  it('supports edit, add, delete, reset, save, and removes blank-name rows', () => {
    const onSaveEdit = jest.fn();
    render(<HomeScreen onSaveEdit={onSaveEdit} previewState="editing" />);

    fireEvent.changeText(
      screen.getByLabelText('푸시업 운동명'),
      '인클라인 푸시업',
    );
    fireEvent.changeText(screen.getByLabelText('인클라인 푸시업 세트 수'), '4');
    fireEvent.changeText(screen.getByLabelText('인클라인 푸시업 횟수'), '8');
    fireEvent.changeText(screen.getByLabelText('추가할 운동명'), '스텝업');
    fireEvent.changeText(screen.getByLabelText('추가할 세트 수'), '2');
    fireEvent.changeText(screen.getByLabelText('추가할 횟수'), '12');
    fireEvent.press(screen.getByRole('button', { name: '운동 추가하기' }));
    expect(screen.getByLabelText('스텝업 운동명')).toBeOnTheScreen();

    const deleteButtons = screen.getAllByRole('button', { name: '항목 삭제' });
    fireEvent.press(deleteButtons[deleteButtons.length - 1]);
    expect(screen.queryByLabelText('스텝업 운동명')).toBeNull();

    fireEvent.changeText(screen.getByLabelText('준비 운동 운동명'), '');
    fireEvent.press(screen.getByRole('button', { name: '저장하기' }));
    const saved = onSaveEdit.mock.calls[0]?.[0] as HomeRoutineItem[];
    expect(saved).toHaveLength(4);
    expect(saved[0]).toMatchObject({
      name: '인클라인 푸시업',
      sets: '4',
      reps: '8',
    });
    expect(screen.getByText('인클라인 푸시업 · 4세트 × 8회')).toBeOnTheScreen();

    fireEvent.press(screen.getByRole('button', { name: '운동 수정하기' }));
    fireEvent.press(screen.getByRole('button', { name: '추천으로 되돌리기' }));
    expect(screen.getByLabelText('푸시업 운동명').props.value).toBe('푸시업');
  });

  it('persists both routine-card and edit-sheet reorder operations', () => {
    const onSaveEdit = jest.fn();
    render(<HomeScreen onSaveEdit={onSaveEdit} previewState="routine" />);

    expect(screen.getByTestId('routine-drag-warm-up')).toBeOnTheScreen();
    expect(screen.getByTestId('routine-drag-cool-down')).toBeOnTheScreen();
    fireEvent(
      screen.getByTestId('routine-drag-warm-up'),
      'accessibilityAction',
      {
        nativeEvent: { actionName: 'increment' },
      },
    );
    fireEvent(
      screen.getByTestId('routine-drag-push-up'),
      'accessibilityAction',
      {
        nativeEvent: { actionName: 'increment' },
      },
    );
    fireEvent.press(screen.getByRole('button', { name: '운동 수정하기' }));
    fireEvent(screen.getByTestId('edit-drag-push-up'), 'accessibilityAction', {
      nativeEvent: { actionName: 'increment' },
    });
    fireEvent.press(screen.getByRole('button', { name: '저장하기' }));

    const saved = onSaveEdit.mock.calls[0]?.[0] as HomeRoutineItem[];
    expect(saved.map((item) => item.id)).toEqual([
      'warm-up',
      'band-row',
      'shoulder-press',
      'push-up',
      'cool-down',
    ]);
  });

  it('exposes required accessibility labels and fixes the second tab label', () => {
    render(<HomeScreen previewState="routine" />);

    const labels = [
      '알림 보기',
      '프로필 열기',
      '이번 주 운동 현황 설명 보기',
      '월별·연별 기록 달력 보기',
      '운동 체크인',
      '운동 시작하기',
      '운동 수정하기',
      '다른 루틴 추천 받기',
      '순서 변경 핸들',
    ];
    for (const label of labels) {
      expect(screen.getAllByLabelText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getByRole('tab', { name: '끼끼의 집' })).toBeOnTheScreen();
    expect(screen.queryByLabelText('운동 기록')).toBeNull();

    fireEvent.press(screen.getByRole('button', { name: '운동 수정하기' }));
    expect(screen.getAllByLabelText('항목 삭제').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('닫기')).toBeOnTheScreen();
  });

  it('keeps the shared bottom navigation fixed across viewport widths', () => {
    const view = render(
      <ScaleViewportProvider viewport={{ width: 360, height: 844 }}>
        <HomeBottomNavigation activeTab="home" />
      </ScaleViewportProvider>,
    );
    const compactOuter = StyleSheet.flatten(
      screen.getByTestId('bottom-navigation').props.style,
    );
    const compactTab = StyleSheet.flatten(
      screen.getByRole('tab', { name: '홈' }).props.style,
    );

    view.rerender(
      <ScaleViewportProvider viewport={{ width: 430, height: 844 }}>
        <HomeBottomNavigation activeTab="home" />
      </ScaleViewportProvider>,
    );

    expect(
      StyleSheet.flatten(screen.getByTestId('bottom-navigation').props.style),
    ).toMatchObject({
      paddingTop: 8,
      paddingHorizontal: 14,
      paddingBottom: 26,
    });
    expect(
      StyleSheet.flatten(screen.getByRole('tab', { name: '홈' }).props.style),
    ).toMatchObject({ minHeight: 48, paddingVertical: 6 });
    expect(compactOuter).toMatchObject({
      paddingTop: 8,
      paddingHorizontal: 14,
      paddingBottom: 26,
    });
    expect(compactTab).toMatchObject({ minHeight: 48, paddingVertical: 6 });
    expect(bottomNavigationBottomPadding(0)).toBe(26);
    expect(bottomNavigationBottomPadding(20)).toBe(26);
    expect(bottomNavigationBottomPadding(34)).toBe(34);
  });

  it('renders a centered filled-gradient check-in CTA without the banana glyph', () => {
    render(
      <ScaleViewportProvider viewport={{ width: 390, height: 844 }}>
        <HomeScreen onStartWorkout={() => undefined} previewState="routine" />
      </ScaleViewportProvider>,
    );

    const button = screen.getByRole('button', { name: '운동 체크인' });
    const greetingStyle = StyleSheet.flatten(
      screen.getByRole('header', { name: /님, 오늘도 반가워요/ }).props.style,
    );
    const progressTitleStyle = StyleSheet.flatten(
      screen.getByText('이번 주 운동 현황').props.style,
    );
    const buttonStyle = StyleSheet.flatten(button.props.style);
    const labelStyle = StyleSheet.flatten(
      screen.getByText('운동 체크인').props.style,
    );
    const chevronStyle = StyleSheet.flatten(
      screen.getByTestId('home-checkin-chevron').props.style,
    );
    const gradient = screen.getByTestId('home-checkin-gradient');

    expect(screen.getAllByText('운동 체크인')).toHaveLength(1);
    expect(screen.queryByText('🍌')).toBeNull();
    expect(buttonStyle).toMatchObject({
      alignItems: 'center',
      borderColor: 'rgba(244, 166, 42, 0.8)',
      borderWidth: expect.any(Number),
      justifyContent: 'center',
      position: 'relative',
      shadowColor: '#AD741D',
      shadowOpacity: 0.11,
    });
    expect(buttonStyle.backgroundColor).toBeUndefined();
    expect(gradient.props.colors).toEqual(
      ['#FEE8B1', '#FEDA99', '#FFD790'].map(processColor),
    );
    expect(gradient.props.locations).toEqual([0, 0.55, 1]);
    expect(labelStyle).toMatchObject({
      color: colors.text,
      textAlign: 'center',
    });
    expect(labelStyle.fontFamily).toBeUndefined();
    expect(labelStyle.fontWeight).toBe(progressTitleStyle.fontWeight);
    expect(greetingStyle).toMatchObject({
      fontFamily: fontFamilies.slogan,
      fontWeight: '400',
    });
    expect(chevronStyle).toMatchObject({
      position: 'absolute',
      right: expect.any(Number),
    });
    const startButton = screen.getByRole('button', { name: '운동 시작하기' });
    const startButtonStyle = StyleSheet.flatten(startButton.props.style);
    const startLabels = screen.getAllByText('운동 시작하기');
    const startLabelStyle = StyleSheet.flatten(startLabels[0]?.props.style);
    const startGradient = screen.getByTestId('home-start-gradient');
    expect(startLabels).toHaveLength(1);
    expect(startButtonStyle).toMatchObject({
      minHeight: 58,
      position: 'relative',
      borderColor: 'rgba(218, 150, 30, 0.2)',
      borderRadius: 18,
      overflow: 'hidden',
      shadowColor: '#5A4636',
      shadowOpacity: 0.13,
    });
    expect(startButtonStyle.backgroundColor).toBeUndefined();
    expect(startGradient.props.colors).toEqual(
      ['#FFFDF8', '#FFF2D1', '#FFE2A3'].map(processColor),
    );
    expect(startGradient.props.locations).toEqual([0, 0.55, 1]);
    expect(startLabelStyle).toMatchObject({
      color: '#5A4636',
      fontSize: 17,
      fontWeight: '800',
      letterSpacing: -0.1,
      textAlign: 'center',
    });
    expect(startLabelStyle.fontFamily).toBeUndefined();
    expect(screen.queryByTestId('home-start-chevron-chip')).toBeNull();

    fireEvent.press(button);
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '위험 신호 없어요' }));
    const submitButton = screen.getByRole('button', { name: '체크인 !' });
    const submitButtonStyle = StyleSheet.flatten(submitButton.props.style);
    const submitLabelStyle = StyleSheet.flatten(
      screen.getByText('체크인 !').props.style,
    );
    const submitGradient = screen.getByTestId('home-checkin-submit-gradient');

    expect(submitLabelStyle.fontFamily).toBeUndefined();
    expect(labelStyle.fontWeight).toBe(submitLabelStyle.fontWeight);

    expect(submitButtonStyle).toMatchObject({
      borderColor: 'rgba(244, 166, 42, 0.8)',
      borderWidth: expect.any(Number),
      shadowColor: '#AD741D',
      shadowOpacity: 0.11,
    });
    expect(submitButtonStyle.backgroundColor).toBeUndefined();
    expect(submitButtonStyle.borderBottomWidth).toBeUndefined();
    expect(submitGradient.props.colors).toEqual(
      ['#FEE8B1', '#FEDA99', '#FFD790'].map(processColor),
    );
    expect(submitGradient.props.locations).toEqual([0, 0.55, 1]);
  });

  it('keeps source parity after splitting the home screen modules', () => {
    const moduleSources = [
      'HomeScreen.tsx',
      'HomeScreenContent.tsx',
      'HomeOverview.tsx',
      'HomeRoutineCard.tsx',
      'HomeChrome.tsx',
      'HomeCheckinSheet.tsx',
      'HomeEditRoutineSheet.tsx',
      'HomeSupport.tsx',
      'homeConstants.ts',
      'homeContentModel.ts',
      'homeRevisionNotice.ts',
      'homeStyles.tsx',
      'homeSheetStyles.ts',
    ].map((fileName) =>
      readFileSync(
        resolve(process.cwd(), 'src/features/home', fileName),
        'utf8',
      ),
    );
    moduleSources.forEach((moduleSource) => {
      expect(moduleSource.split(/\r?\n/).length).toBeLessThan(1_000);
    });
    const source = moduleSources.join('\n');
    expect(source.match(/<Svg\b/g)).toHaveLength(15);
  });
});
