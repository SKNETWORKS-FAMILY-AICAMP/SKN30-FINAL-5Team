import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { act, fireEvent, render, screen } from '@testing-library/react-native';
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
    ).toBe('끼끼가 오늘의 운동 재료를 하나씩 모으는 중');
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
      screen.getByText('오늘 컨디션에 맞춘 운동이 준비됐어요.'),
    ).toBeOnTheScreen();
    expect(screen.getByText('상체 근력 · 40분')).toBeOnTheScreen();
    expect(
      screen.getByText('운동 순서는 자유롭게 바꿀 수 있어요.'),
    ).toBeOnTheScreen();
  });

  it('shows routine generation in the exercise-list slot for API requests', () => {
    const props = homePreviewProps('routine');
    const view = render(<HomeScreen {...props} busy="decision-generation" />);

    expect(screen.getByTestId('routine-loading-slot')).toBeOnTheScreen();
    expect(
      screen.getByTestId('routine-generation-message').props.children[0],
    ).toBe('끼끼가 오늘의 운동 재료를 하나씩 모으는 중');
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
    ).toBe('조금만 기다려 주세요. 안전한 루틴인지 마지막으로 확인하는 중');

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

  it('reuses the setup screen while the saved base routine is being loaded', () => {
    render(
      <HomeScreen
        context={null}
        decision={null}
        routine={null}
        status="loading"
      />,
    );

    expect(screen.getByText('운동 계획을 준비하고 있어요')).toBeOnTheScreen();
    expect(screen.getByTestId('home-routine-lookup-loading')).toBeOnTheScreen();
    expect(screen.queryByRole('button', { name: '다시 준비하기' })).toBeNull();
    expect(screen.queryByTestId('routine-generation-loading')).toBeNull();
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
    expect(screen.getByLabelText('수요일 미수행')).toBeOnTheScreen();
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

    fireEvent.press(screen.getByRole('button', { name: '오늘 루틴 체크인' }));
    expect(
      screen.getByText('오늘 통증이 있는 부위가 있나요?'),
    ).toBeOnTheScreen();
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
    expect(bodyAreaButtonStyle.minHeight).toBeGreaterThanOrEqual(48);
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

      fireEvent.press(screen.getByRole('button', { name: '다시 체크인하기' }));

      expect(
        screen.getByRole('header', { name: '오늘 컨디션 체크' }),
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
      screen.getByRole('button', { name: '다시 체크인하기' }),
    ).toBeOnTheScreen();
    expect(
      screen.queryByRole('button', { name: '오늘 루틴 체크인' }),
    ).toBeNull();
  });

  it('styles rest as a calm full-width secondary action', () => {
    const onChooseRest = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('routine')}
        onChooseRest={onChooseRest}
      />,
    );

    const restButton = screen.getByRole('button', { name: '오늘은 쉬기' });
    expect(StyleSheet.flatten(restButton.props.style)).toMatchObject({
      alignSelf: 'stretch',
      minHeight: expect.any(Number),
      borderColor: '#BFD09F',
      backgroundColor: '#F4F8E9',
      overflow: 'hidden',
    });
    expect(screen.getByTestId('home-rest-gradient').props.colors).toEqual(
      ['#FCFFF8', '#EEF5E2'].map(processColor),
    );
    expect(screen.getByTestId('home-rest-icon')).toBeVisible();

    fireEvent.press(restButton);
    expect(onChooseRest).toHaveBeenCalledTimes(1);
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

    fireEvent.press(screen.getByRole('button', { name: '오늘 루틴 체크인' }));
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

  it('shows posture for every API item and variants only when the server returns them', async () => {
    render(<HomeScreen {...homePreviewProps('routine')} />);

    expect(screen.getAllByText('자세')).toHaveLength(3);
    const postureButton = screen.getByRole('button', {
      name: '밴드 로우 자세',
    });
    const equipmentButton = await screen.findByRole('button', {
      name: '밴드 로우 장비 보기',
    });
    expect(equipmentButton).toBeOnTheScreen();
    expect(
      screen.queryByRole('button', { name: '푸시업 장비 보기' }),
    ).toBeNull();
    expect(screen.getByText('장비')).toBeOnTheScreen();
    const postureStyle = StyleSheet.flatten(postureButton.props.style);
    const equipmentStyle = StyleSheet.flatten(equipmentButton.props.style);
    expect(equipmentStyle).toMatchObject({
      width: postureStyle.width,
      height: postureStyle.height,
      minHeight: postureStyle.minHeight,
      paddingHorizontal: postureStyle.paddingHorizontal,
      paddingVertical: postureStyle.paddingVertical,
      borderColor: '#9CC5DF',
      backgroundColor: '#E7F3FA',
    });
    const postureTextStyle = StyleSheet.flatten(
      screen.getAllByText('자세')[0]?.props.style,
    );
    expect(
      StyleSheet.flatten(screen.getByText('장비').props.style),
    ).toMatchObject({
      color: '#356A85',
      fontSize: postureTextStyle.fontSize,
      fontWeight: postureTextStyle.fontWeight,
    });
    expect(postureStyle).toMatchObject({
      height: expect.any(Number),
    });
    expect(postureStyle.width).toBeCloseTo(48 * 1.2);
    const emptyEquipmentSlot = screen.getByTestId(
      'routine-equipment-slot-plan-item-2',
    );
    const filledEquipmentSlot = screen.getByTestId(
      'routine-equipment-slot-plan-item-3',
    );
    expect(emptyEquipmentSlot).toBeVisible();
    expect(StyleSheet.flatten(emptyEquipmentSlot.props.style)).toEqual(
      StyleSheet.flatten(filledEquipmentSlot.props.style),
    );
    expect(
      screen.getByTestId('routine-guide-actions-plan-item-1'),
    ).toBeVisible();
    expect(
      screen.getByTestId('routine-guide-actions-plan-item-2'),
    ).toBeVisible();
    expect(
      screen.getByTestId('routine-guide-actions-plan-item-3'),
    ).toBeVisible();
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

  it('opens reviewed equipment variant guidance without replacing the routine item', async () => {
    render(<HomeScreen {...homePreviewProps('routine')} />);

    fireEvent.press(
      await screen.findByRole('button', { name: '밴드 로우 장비 보기' }),
    );

    expect(
      screen.getByRole('header', { name: '밴드 로우 장비 안내' }),
    ).toBeOnTheScreen();
    expect(screen.getByText('원래 운동의 필요 장비')).toBeOnTheScreen();
    expect(screen.getByText('밴드')).toBeOnTheScreen();
    expect(screen.getByText('엎드려 등 당기기')).toBeOnTheScreen();
    expect(
      screen.getByText(
        '이 안내는 운동을 교체하지 않으며 현재 루틴과 수행 기록도 바꾸지 않아요.',
      ),
    ).toBeOnTheScreen();
    expect(screen.queryByTestId('exercise-posture-guide')).toBeNull();
  });

  it('shows equipment guidance without a variant section when required equipment exists', async () => {
    const props = homePreviewProps('routine');
    render(
      <HomeScreen
        {...props}
        exerciseApi={{
          getExercise: props.exerciseApi!.getExercise,
          async getExerciseVariants(exerciseId) {
            return {
              source_exercise_id: exerciseId,
              source_required_equipment_codes:
                exerciseId === 'exercise-1'
                  ? ['BODYWEIGHT', 'MAT']
                  : ['BODYWEIGHT'],
              items: [],
              catalog_version: 'home-equipment-only-v1',
              alternative_set_version: null,
            };
          },
        }}
      />,
    );

    fireEvent.press(
      await screen.findByRole('button', { name: '푸시업 장비 보기' }),
    );

    expect(
      screen.getByRole('header', { name: '푸시업 장비 안내' }),
    ).toBeOnTheScreen();
    expect(screen.getByText('매트')).toBeOnTheScreen();
    expect(screen.queryByTestId('exercise-variants-list')).toBeNull();
    expect(
      screen.queryByText(
        '장비가 없을 때 아래 방법으로 동작을 변형할 수 있어요.',
      ),
    ).toBeNull();
  });

  it('hides variant actions while the backend capability is unavailable', () => {
    const props = homePreviewProps('routine');
    render(
      <HomeScreen
        {...props}
        exerciseApi={{
          async getExercise(exerciseId) {
            return {
              exercise_id: exerciseId,
              exercise_name: '푸시업',
              training_type_code: 'STRENGTH',
              primary_body_area_codes: ['CHEST'],
              instruction_summary: '검수된 자세 안내',
              form_cues: [],
              media_asset_key: null,
              media_url: null,
              mascot_animation_asset_key: null,
              instruction_content_version: 'current-backend-v1',
            };
          },
        }}
      />,
    );

    expect(screen.queryByText('장비')).toBeNull();
  });

  it('opens recommendation details without adding another Home card', () => {
    const view = render(<HomeScreen {...homePreviewProps('adjusted')} />);

    fireEvent.press(screen.getByRole('button', { name: '추천 이유 보기' }));
    expect(screen.getByRole('header', { name: '추천 이유' })).toBeOnTheScreen();
    expect(screen.getByText('에이전트별 판단')).toBeOnTheScreen();
    expect(screen.getByText('최종 조정 이유')).toBeOnTheScreen();
    expect(screen.queryByText('안전 확인')).toBeNull();
    expect(screen.getByText('트레이닝')).toBeOnTheScreen();
    expect(screen.getByText('회복')).toBeOnTheScreen();
    expect(screen.getByText('안전')).toBeOnTheScreen();
    expect(screen.getByText('실행 가능성')).toBeOnTheScreen();
    expect(screen.queryByText('조정')).toBeNull();
    expect(
      screen.getByText(
        '운동 목표와 희망 시간은 유지하고 세트와 강도만 조정했어요.',
      ),
    ).toBeOnTheScreen();

    const collapsedCriteria = screen.getByRole('button', {
      name: '반영한 기준 펼치기',
    });
    expect(collapsedCriteria.props.accessibilityState).toEqual({
      expanded: false,
    });
    expect(screen.queryByText('운동 목표를 유지했어요.')).toBeNull();

    const tree = JSON.stringify(view.toJSON());
    expect(tree.indexOf('에이전트별 판단')).toBeLessThan(
      tree.indexOf('최종 조정 이유'),
    );
    expect(tree.indexOf('최종 조정 이유')).toBeLessThan(
      tree.indexOf('반영한 기준'),
    );

    fireEvent.press(collapsedCriteria);
    expect(
      screen.getByRole('button', { name: '반영한 기준 접기' }).props
        .accessibilityState,
    ).toEqual({ expanded: true });
    expect(screen.getByText('운동 목표를 유지했어요.')).toBeOnTheScreen();
  });

  it('keeps the server summary order and never exposes machine codes', () => {
    const props = homePreviewProps('adjusted');
    expect(props.decision).not.toBeNull();

    const view = render(<HomeScreen {...props} />);
    fireEvent.press(screen.getByRole('button', { name: '추천 이유 보기' }));

    const tree = JSON.stringify(view.toJSON());
    expect(
      tree.indexOf('운동 목표와 희망 운동 시간을 유지했어요.'),
    ).toBeLessThan(
      tree.indexOf('오늘의 피로도를 고려해 운동 부담을 낮추도록 제안했어요.'),
    );
    expect(
      tree.indexOf('오늘의 피로도를 고려해 운동 부담을 낮추도록 제안했어요.'),
    ).toBeLessThan(
      tree.indexOf(
        '부담이 될 수 있는 운동 2개를 제외하고 강도를 중간 이하로 제한했어요.',
      ),
    );
    expect(
      tree.indexOf(
        '부담이 될 수 있는 운동 2개를 제외하고 강도를 중간 이하로 제한했어요.',
      ),
    ).toBeLessThan(
      tree.indexOf('희망 시간과 장소, 사용 가능한 장비에 맞는 구성이에요.'),
    );
    expect(
      tree.indexOf('희망 시간과 장소, 사용 가능한 장비에 맞는 구성이에요.'),
    ).toBeLessThan(
      tree.indexOf(
        '운동 목표와 희망 시간은 유지하고 세트와 강도만 조정했어요.',
      ),
    );
    expect(tree).not.toContain('MODERATE_FATIGUE_DOWNSHIFT');
    expect(tree).not.toContain('TIME_LOCATION_EQUIPMENT_MATCHED');
    expect(tree).not.toContain('COMMON_CANDIDATE_SELECTED');
  });

  it('keeps legacy recommendation reasons usable without agent summaries', () => {
    const props = homePreviewProps('adjusted');
    expect(props.decision).not.toBeNull();
    const decision = {
      ...props.decision!,
      public_agent_summaries: null,
    };

    render(<HomeScreen {...props} decision={decision} />);
    fireEvent.press(screen.getByRole('button', { name: '추천 이유 보기' }));

    expect(screen.queryByText('에이전트별 판단')).toBeNull();
    expect(screen.queryByText('최종 조정 이유')).toBeNull();
    expect(
      screen.getByRole('button', { name: '반영한 기준 펼치기' }),
    ).toBeOnTheScreen();
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

    fireEvent.press(screen.getByRole('button', { name: '추천 이유 보기' }));
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
    expect(screen.getByText('계획대로 진행')).toBeOnTheScreen();
    expect(
      screen.getByLabelText('루틴 진행 방식: 계획대로 진행'),
    ).toBeOnTheScreen();
  });

  it('renders the matching action badge in preview mode', () => {
    const previewView = render(<HomeScreen previewState="routine" />);

    expect(
      screen.getByLabelText('루틴 진행 방식: 계획대로 진행'),
    ).toBeOnTheScreen();

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
        onNotifications={onNotifications}
        previewState="routine"
      />,
    );
    const button = screen.getByRole('button', { name: '알림 보기' });
    expect(button.props.accessibilityState.disabled).toBe(false);
    fireEvent.press(button);
    expect(onNotifications).toHaveBeenCalledTimes(1);
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
    expect(screen.queryByLabelText('원하는 운동 시간 (분)')).toBeNull();
    expect(screen.getByLabelText('원하는 운동 시간 미선택')).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '운동 시간 10분 줄이기' }),
    ).toBeDisabled();
    expect(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    ).toBeEnabled();
    expect(screen.getByLabelText('어젯밤 수면 시간 (시간)').props.value).toBe(
      '',
    );
    expect(screen.queryByText('컨디션')).toBeNull();
    expect(screen.queryByLabelText('오늘 걸음 수')).toBeNull();
    expect(
      screen.getByText('오늘 상태를 알려주면 루틴을 맞춰 조정해드려요.'),
    ).toBeOnTheScreen();
    expect(screen.getByText('오늘 위험 신호가 있나요?')).toBeOnTheScreen();
  });

  it('starts workout duration empty and selects 10 minutes with plus', () => {
    render(<HomeScreen {...homePreviewProps('pre-checkin')} />);

    fireEvent.press(screen.getByRole('button', { name: '오늘 루틴 체크인' }));
    expect(screen.getByLabelText('원하는 운동 시간 미선택')).toBeOnTheScreen();
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );
    expect(screen.getByLabelText('원하는 운동 시간 10분')).toBeOnTheScreen();
    expect(screen.getByText('오늘 어디에서 운동할까요?')).toBeOnTheScreen();
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

    fireEvent.press(screen.getByRole('button', { name: '오늘 루틴 체크인' }));
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
    expect(
      screen.getByText('지금 불편하거나 통증이 있는 부위를 모두 선택해주세요.'),
    ).toBeOnTheScreen();
    const toggle = screen.getByRole('button', { name: '다른 부위 보기' });
    expect(toggle.props.accessibilityState).toEqual({ expanded: false });
    fireEvent.press(toggle);
    expect(
      screen.getByRole('button', { name: '다른 부위 접기' }).props
        .accessibilityState,
    ).toEqual({ expanded: true });
    expect(screen.getByText('접기')).toBeOnTheScreen();
    expect(
      screen.getByTestId('checkin-extended-area-caret').props.style,
    ).toMatchObject({ transform: [{ rotate: '180deg' }] });
  });

  it('adjusts the requested duration by ten minutes and submits it', () => {
    const onSubmitCheckin = jest.fn();
    render(
      <HomeScreen
        {...homePreviewProps('pre-checkin')}
        onSubmitCheckin={onSubmitCheckin}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '오늘 루틴 체크인' }));
    for (let count = 0; count < 5; count += 1) {
      fireEvent.press(
        screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
      );
    }
    expect(screen.getByLabelText('원하는 운동 시간 50분')).toBeOnTheScreen();
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 줄이기' }),
    );
    expect(screen.getByLabelText('원하는 운동 시간 40분')).toBeOnTheScreen();
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '위험 신호 없어요' }));
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    expect(onSubmitCheckin).toHaveBeenCalledWith(
      expect.objectContaining({ availableTimeMinutes: 50 }),
    );
  });

  it('requires one combined Red Flag answer without collecting symptom details', () => {
    render(<HomeScreen previewState="checkin" />);

    expect(screen.queryByText('심한 어지럼')).toBeNull();
    expect(screen.getByText(/오늘 가슴 통증이나 압박감/)).toBeOnTheScreen();
    expect(
      screen.getByRole('button', { name: '체크인 !' }).props.accessibilityState
        .disabled,
    ).toBe(true);

    fireEvent.press(screen.getByRole('button', { name: '위험 신호 있어요' }));
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );
    expect(
      screen.getByRole('button', { name: '체크인 !' }).props.accessibilityState
        .disabled,
    ).toBe(false);
    expect(
      screen.getByRole('button', { name: '위험 신호 있어요' }).props
        .accessibilityState.selected,
    ).toBe(true);
  });

  it('isolates check-in draft changes until save and discards them on close', () => {
    render(<HomeScreen previewState="routine" />);

    fireEvent.press(screen.getByRole('button', { name: '오늘 루틴 체크인' }));
    fireEvent.press(screen.getByRole('button', { name: '통증 있어요' }));
    fireEvent.press(screen.getByRole('button', { name: '어깨' }));
    expect(
      screen.queryByText('어깨 부담을 줄이도록 강도를 조정했어요.'),
    ).toBeNull();
    fireEvent.press(screen.getByRole('button', { name: '닫기' }));

    fireEvent.press(screen.getByRole('button', { name: '오늘 루틴 체크인' }));
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

    expect(
      screen.queryByRole('button', { name: '오늘 루틴 체크인' }),
    ).toBeNull();
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
        itemOverrides: [{ planItemId: 'plan-item-2', sets: 4, reps: 8 }],
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

    fireEvent(
      screen.getByTestId('routine-drag-warm-up'),
      'accessibilityAction',
      {
        nativeEvent: { actionName: 'increment' },
      },
    );
    fireEvent.press(screen.getByRole('button', { name: '운동 수정하기' }));
    fireEvent(screen.getByTestId('edit-drag-warm-up'), 'accessibilityAction', {
      nativeEvent: { actionName: 'increment' },
    });
    fireEvent.press(screen.getByRole('button', { name: '저장하기' }));

    const saved = onSaveEdit.mock.calls[0]?.[0] as HomeRoutineItem[];
    expect(saved.slice(0, 3).map((item) => item.id)).toEqual([
      'push-up',
      'band-row',
      'warm-up',
    ]);
  });

  it('exposes required accessibility labels and fixes the second tab label', () => {
    render(<HomeScreen previewState="routine" />);

    const labels = [
      '알림 보기',
      '프로필 열기',
      '이번 주 운동 현황 설명 보기',
      '월별·연별 기록 달력 보기',
      '오늘 루틴 체크인',
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

    const button = screen.getByRole('button', { name: '오늘 루틴 체크인' });
    const greetingStyle = StyleSheet.flatten(
      screen.getByRole('header').props.style,
    );
    const progressTitleStyle = StyleSheet.flatten(
      screen.getByText('이번 주 운동 현황').props.style,
    );
    const buttonStyle = StyleSheet.flatten(button.props.style);
    const labelStyle = StyleSheet.flatten(
      screen.getByText('오늘 루틴 체크인').props.style,
    );
    const chevronStyle = StyleSheet.flatten(
      screen.getByTestId('home-checkin-chevron').props.style,
    );
    const gradient = screen.getByTestId('home-checkin-gradient');

    expect(screen.getAllByText('오늘 루틴 체크인')).toHaveLength(1);
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

  it('keeps source parity after merging the weekly cards', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'src/features/home/HomeScreen.tsx'),
      'utf8',
    );
    expect(source.match(/<Svg\b/g)).toHaveLength(15);
  });
});
