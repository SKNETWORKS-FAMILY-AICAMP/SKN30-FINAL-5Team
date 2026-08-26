import { describe, expect, it, jest } from '@jest/globals';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react-native';

import type { Api } from '../src/api/endpoints';
import type { WeekResponse, WorkoutSessionLogSummary } from '../src/api/types';
import { imageAssets } from '../src/assets';
import {
  HOUSE_BACKDROP_ZOOM,
  HOUSE_MASCOT_SIZE,
  houseBackdropContinuationTop,
  houseBackdropMinimumHeight,
  houseBackdropSize,
  houseWeekPanelTop,
} from '../src/features/house/MascotHouseContent';
import {
  FEED_POSE_HOLD_MS,
  MascotHouseScreen,
} from '../src/features/house/MascotHouseScreen';
import {
  houseBananaPoseArt,
  houseBackgroundArt,
  housePoseArt,
  houseRegularPoseArt,
  houseRoomArt,
  randomHouseBananaPoseArt,
  randomHousePettedPoseArt,
  randomHouseRegularPoseArt,
} from '../src/features/house/houseArtSlots';
import {
  BANANA_REWARD,
  DAILY_GIFT_BANANAS,
  HOUSE_ACTION_COST,
} from '../src/features/house/houseModel';
import { createMemoryHouseStore } from '../src/features/house/houseStorage';

const NOW = new Date('2026-08-22T10:00:00+09:00');
const TIME_ZONE = 'Asia/Seoul';

const OPEN_WEEK: WeekResponse = {
  week_id: 'week-1',
  week_start: '2026-08-17',
  week_end: '2026-08-23',
  timezone: TIME_ZONE,
  target_workout_count: 3,
  plan_origin_code: 'COLD_START',
  cold_start_applied: true,
  status_code: 'OPEN',
  closed_at: null,
  report_id: null,
  report_status_code: null,
};

function completedSession(
  sessionId: string,
  localDate: string,
): WorkoutSessionLogSummary {
  return {
    session_id: sessionId,
    local_date: localDate,
    status_code: 'COMPLETED',
    completed_item_count: 3,
    total_item_count: 3,
    requested_duration_minutes: 30,
    training_type_code: 'STRENGTH',
    not_completed_reason_code: null,
    started_at: null,
    finished_at: null,
  };
}

function houseApi({
  sessions = [completedSession('s1', '2026-08-18')],
  weekError = false,
}: {
  sessions?: WorkoutSessionLogSummary[];
  weekError?: boolean;
} = {}) {
  return {
    getWeek: jest.fn(async () => {
      if (weekError) throw new Error('offline');
      return OPEN_WEEK;
    }),
    listWorkoutSessions: jest.fn(async () => ({
      items: sessions,
      next_cursor: null,
    })),
  } as unknown as Api;
}

function renderHouse(api: Api, store = createMemoryHouseStore()) {
  const onNavigate = jest.fn();
  render(
    <MascotHouseScreen
      api={api}
      nickname="범중"
      now={NOW}
      onNavigate={onNavigate}
      store={store}
      timeZone={TIME_ZONE}
    />,
  );
  return { onNavigate, store };
}

describe('MascotHouseScreen', () => {
  it('shows the room, the week standing and the bananas the week earned', async () => {
    renderHouse(houseApi());

    expect(await screen.findByTestId('house-scene')).toBeTruthy();
    expect(
      screen
        .getAllByTestId('house-banana-asset', {
          includeHiddenElements: true,
        })
        .every((banana) => banana.props.source === imageAssets.banana),
    ).toBe(true);
    expect(screen.queryByRole('header', { name: '끼끼의 집' })).toBeNull();
    expect(screen.getByText('주 3회 운동하기')).toBeTruthy();
    expect(screen.getByText('1 / 3 회')).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByText(`${BANANA_REWARD.completed}개`)).toBeTruthy(),
    );
  });

  it('grants the daily gift once and then reports it as already taken', async () => {
    renderHouse(houseApi({ sessions: [] }));

    const gift = await screen.findByTestId('house-gift-button');
    fireEvent.press(gift);

    expect(screen.getByText(`${DAILY_GIFT_BANANAS}개`)).toBeTruthy();
    expect(screen.getByLabelText('오늘의 선물, 이미 받았어요')).toBeDisabled();
  });

  it('opens the banana catch game and returns to the same house', async () => {
    renderHouse(houseApi());

    await screen.findByTestId('house-scene');
    fireEvent.press(screen.getByTestId('house-play-game-action'));
    expect(screen.getByTestId('banana-catch-screen')).toBeTruthy();

    fireEvent.press(screen.getByLabelText('끼끼의 집으로 돌아가기'));
    expect(screen.getByTestId('house-scene')).toBeTruthy();
  });

  it('spends bananas on feeding and keeps the balance in the store', async () => {
    const { store } = renderHouse(houseApi());

    await waitFor(() =>
      expect(screen.getByText(`${BANANA_REWARD.completed}개`)).toBeTruthy(),
    );
    fireEvent.press(screen.getByTestId('house-feed-action'));

    const remaining = BANANA_REWARD.completed - HOUSE_ACTION_COST.feed;
    expect(screen.getByText(`${remaining}개`)).toBeTruthy();
    await waitFor(async () =>
      expect((await store.read())?.bananas).toBe(remaining),
    );
  });

  it('places a decoration in the room once it is bought', async () => {
    renderHouse(houseApi());

    await waitFor(() =>
      expect(screen.getByText(`${BANANA_REWARD.completed}개`)).toBeTruthy(),
    );
    fireEvent.press(screen.getByTestId('house-decorate-action'));
    expect(
      within(screen.getByTestId('house-decorate-panel')).queryByText(
        `바나나 ${BANANA_REWARD.completed}개`,
      ),
    ).toBeNull();
    fireEvent.press(screen.getByRole('tab', { name: '소품' }));
    expect(screen.queryByText('가장 싼 소품은 바나나 20개예요.')).toBeNull();
    fireEvent.press(await screen.findByTestId('house-item-yoga_mat'));

    expect(screen.queryByTestId('house-feedback')).toBeNull();
    expect(screen.queryByText('요가 매트를 집에 놓았어요.')).toBeNull();
    // Once in the room, once as an owned tile in the still-open panel.
    expect(screen.getAllByTestId('house-art-item-yoga_mat').length).toBe(2);

    fireEvent.press(screen.getByLabelText('집 꾸미기 닫기'));
    expect(screen.getAllByTestId('house-art-item-yoga_mat').length).toBe(1);
  });

  it('uses scrolling responsive grids for backgrounds and decorations', async () => {
    renderHouse(houseApi());

    await screen.findByTestId('house-scene');
    fireEvent.press(screen.getByTestId('house-decorate-action'));

    expect(
      screen.queryByText('배경은 바나나 없이 자유롭게 바꿀 수 있어요.'),
    ).toBeNull();
    const backgroundList = screen.getByTestId('house-background-list');
    expect(backgroundList.props.horizontal).toBeFalsy();
    expect(backgroundList.props.contentContainerStyle).toEqual(
      expect.objectContaining({
        width: '100%',
      }),
    );
    expect(
      screen.getByTestId('house-background-grid-row-0').props.children,
    ).toHaveLength(2);
    expect(
      screen.getByTestId('house-background-grid-row-1').props.children,
    ).toHaveLength(2);
    expect(screen.getByTestId('house-background-morning_camp')).toHaveStyle({
      width: '100%',
    });

    fireEvent.press(screen.getByRole('tab', { name: '소품' }));
    const itemList = screen.getByTestId('house-item-list');

    expect(itemList.props.contentContainerStyle).toEqual(
      expect.objectContaining({
        width: '100%',
      }),
    );
    expect(
      screen.getByTestId('house-item-grid-row-0').props.children,
    ).toHaveLength(3);
    expect(
      screen.getByTestId('house-item-grid-row-1').props.children,
    ).toHaveLength(3);
    expect(
      screen.getByTestId('house-item-grid-row-2').props.children,
    ).toHaveLength(3);
    expect(screen.getByTestId('house-item-yoga_mat')).toHaveStyle({
      width: '100%',
    });
  });

  it('allows drag placement only while 집 꾸미기 is open and persists it', async () => {
    const { store } = renderHouse(houseApi());

    await waitFor(() =>
      expect(screen.getByText(`${BANANA_REWARD.completed}개`)).toBeTruthy(),
    );
    fireEvent.press(screen.getByTestId('house-decorate-action'));
    fireEvent.press(screen.getByRole('tab', { name: '소품' }));
    fireEvent.press(screen.getByTestId('house-item-yoga_mat'));
    fireEvent(screen.getByTestId('house-decoration-canvas'), 'layout', {
      nativeEvent: { layout: { height: 844, width: 390, x: 0, y: 0 } },
    });

    const placed = screen.getByTestId('house-placed-item-yoga_mat');
    expect(
      screen.getByTestId('house-decoration-canvas').props.pointerEvents,
    ).toBe('box-none');
    expect(placed.props.onStartShouldSetResponder()).toBe(true);
    expect(screen.getAllByTestId('house-art-item-yoga_mat')[0]).toHaveStyle({
      borderWidth: 0,
    });

    fireEvent(placed, 'responderGrant', {
      nativeEvent: { pageX: 100, pageY: 100 },
    });
    fireEvent(placed, 'responderMove', {
      nativeEvent: { pageX: 150, pageY: 180 },
    });
    fireEvent(placed, 'responderRelease');

    await waitFor(async () =>
      expect((await store.read())?.itemPlacements.yoga_mat).toEqual({
        x: 0.24 + 50 / (390 - 44),
        y: 0.57 + 80 / (844 - 44),
      }),
    );

    fireEvent.press(screen.getByLabelText('집 꾸미기 닫기'));
    expect(
      screen.getByTestId('house-decoration-canvas').props.pointerEvents,
    ).toBe('none');
    expect(
      screen
        .getByTestId('house-placed-item-yoga_mat')
        .props.onStartShouldSetResponder(),
    ).toBe(false);
  });

  it('lists background candidates and persists the selected room', async () => {
    const { store } = renderHouse(houseApi({ sessions: [] }));

    await screen.findByTestId('house-scene');
    fireEvent.press(screen.getByTestId('house-decorate-action'));

    expect(
      screen.getByRole('tab', { name: '배경' }).props.accessibilityState,
    ).toEqual({ selected: true });
    expect(screen.getByTestId('house-background-morning_camp')).toBeTruthy();
    expect(screen.getByTestId('house-background-dinner_camp')).toBeTruthy();
    expect(
      screen.getByTestId('house-background-indoor_treehouse'),
    ).toBeTruthy();
    expect(screen.getByTestId('house-background-snowing_onsen')).toBeTruthy();
    expect(
      screen
        .getAllByLabelText(houseBackgroundArt.morning_camp.label)
        .map((image) => image.props.source),
    ).toEqual(
      expect.arrayContaining([
        imageAssets.houseCampingMorningBackground,
        imageAssets.houseCampingMorningBackgroundThumbnail,
      ]),
    );
    expect(
      screen.getByLabelText(houseBackgroundArt.dinner_camp.label).props.source,
    ).toBe(imageAssets.houseCampingDinnerBackgroundThumbnail);
    expect(
      screen.getByLabelText(houseBackgroundArt.indoor_treehouse.label).props
        .source,
    ).toBe(imageAssets.houseIndoorBackgroundThumbnail);
    expect(
      screen.getByLabelText(houseBackgroundArt.snowing_onsen.label).props
        .source,
    ).toBe(imageAssets.houseSnowingOnsenBackgroundThumbnail);

    fireEvent.press(screen.getByTestId('house-background-snowing_onsen'));

    expect(screen.queryByTestId('house-feedback')).toBeNull();
    expect(screen.queryByText('집 배경을 바꿨어요.')).toBeNull();
    expect(
      screen.getByTestId('house-background-snowing_onsen').props
        .accessibilityState,
    ).toEqual({ disabled: true, selected: true });
    await waitFor(async () =>
      expect((await store.read())?.selectedBackgroundId).toBe('snowing_onsen'),
    );

    fireEvent.press(screen.getByLabelText('집 꾸미기 닫기'));
    expect(
      screen.getByLabelText('끼끼의 눈 내리는 온천 배경').props.source,
    ).toBe(imageAssets.houseSnowingOnsenBackground);

    fireEvent.press(screen.getByTestId('house-decorate-action'));
    expect(
      screen.getByTestId('house-background-snowing_onsen').props
        .accessibilityState,
    ).toEqual({ disabled: true, selected: true });
  });

  it('keeps the house open without showing a transient notice when the week fails', async () => {
    const api = houseApi({ weekError: true });
    renderHouse(api);

    expect(await screen.findByTestId('house-scene')).toBeTruthy();
    expect(screen.getByText('목표를 불러오지 못했어요')).toBeTruthy();
    expect(screen.queryByTestId('house-feedback')).toBeNull();
    expect(screen.queryByLabelText('다시 시도')).toBeNull();
    expect(api.getWeek).toHaveBeenCalledTimes(1);
  });

  it('fills the screen with the scene instead of framing it in a card', async () => {
    renderHouse(houseApi());

    const scene = await screen.findByTestId('house-scene');
    expect(scene).toBeTruthy();
    // The backdrop is a sibling that fills the screen, not a child of the
    // stage, so it runs under the top bar and behind the tab bar.
    const backdrop = screen.getByLabelText('끼끼의 캠핑장 아침 배경');
    expect(backdrop.props.source).toBe(
      imageAssets.houseCampingMorningBackground,
    );
    expect(backdrop.props.resizeMode).toBe('cover');
    expect(screen.getByTestId('house-backdrop')).toHaveStyle({
      alignItems: 'center',
      justifyContent: 'flex-start',
    });
    expect(screen.getByTestId('house-backdrop-surround')).toBeTruthy();
    expect(screen.getByTestId('house-backdrop-continuation')).toBeTruthy();
    const blurredBand = screen.getByTestId('house-backdrop-blurred-band');
    expect(blurredBand.props.vbWidth).toBe(1600);
    expect(blurredBand.props.vbHeight).toBe(160);
    expect(blurredBand.props.align).toBe('none');
    expect(screen.getByTestId('house-backdrop-blurred-source')).toBeTruthy();
    expect(screen.getByTestId('house-backdrop-continuation-fade')).toBeTruthy();
    expect(screen.getByTestId('house-bottom-fade')).toBeTruthy();
    expect(screen.getByTestId('house-safe-area').props.edges).toMatchObject({
      top: 'additive',
      bottom: 'off',
    });
    expect(screen.queryByTestId('moving-house-backdrop')).toBeNull();
    expect(screen.queryByTestId('background-test-content')).toBeNull();
  });

  it('zooms the top-aligned background out to half of its former cover size', () => {
    const reference = houseBackdropSize(390, 844);
    const wide = houseBackdropSize(844, 390);

    expect(HOUSE_BACKDROP_ZOOM).toBe(0.5);
    expect(reference.height).toBe(422);
    expect(reference.width).toBeCloseTo(691.8, 1);
    expect(wide.width).toBe(422);
    expect(wide.height).toBeCloseTo(257.4, 1);
  });

  it('crossfades before a short image ends and follows later image resizing', () => {
    expect(houseBackdropContinuationTop(700, 844, 526)).toBe(522);
    expect(houseBackdropContinuationTop(422, 844, 526)).toBe(374);
    expect(houseBackdropContinuationTop(422, 844, null)).toBe(374);
    expect(houseBackdropContinuationTop(422, 844, 0)).toBe(374);
    expect(houseBackdropContinuationTop(470, 844, 526)).toBe(422);
  });

  it('grows a portrait backdrop just enough to reach the control boundary', () => {
    const minimumHeight = houseBackdropMinimumHeight(844, 526);
    const art = houseBackdropSize(390, 844, 1312, 1199, minimumHeight);

    expect(minimumHeight).toBe(570);
    expect(art.height).toBe(570);
    expect(art.width / art.height).toBeCloseTo(1312 / 1199);
    expect(houseBackdropContinuationTop(art.height, 844, 526)).toBe(522);
  });

  it('keeps the blur boundary attached to the bottom controls when height changes', async () => {
    renderHouse(houseApi({ sessions: [] }));

    await screen.findByTestId('house-scene');
    fireEvent(screen.getByTestId('mascot-house-content'), 'layout', {
      nativeEvent: { layout: { height: 844, width: 390, x: 0, y: 0 } },
    });
    fireEvent(screen.getByTestId('house-content-column'), 'layout', {
      nativeEvent: { layout: { height: 760, width: 390, x: 0, y: 40 } },
    });
    fireEvent(screen.getByTestId('house-action-area'), 'layout', {
      nativeEvent: { layout: { height: 250, width: 358, x: 16, y: 510 } },
    });
    fireEvent(screen.getByTestId('house-week-panel'), 'layout', {
      nativeEvent: { layout: { height: 130, width: 358, x: 0, y: 200 } },
    });

    expect(houseWeekPanelTop(40, 760, 250, 130)).toBe(666);
    expect(screen.getByTestId('house-backdrop-continuation')).toHaveStyle({
      top: 662,
    });
    expect(screen.getByTestId('house-bottom-fade')).toHaveStyle({
      top: 662,
    });

    fireEvent(screen.getByTestId('mascot-house-content'), 'layout', {
      nativeEvent: { layout: { height: 994, width: 390, x: 0, y: 0 } },
    });
    fireEvent(screen.getByTestId('house-content-column'), 'layout', {
      nativeEvent: { layout: { height: 910, width: 390, x: 0, y: 40 } },
    });

    expect(houseWeekPanelTop(40, 910, 250, 130)).toBe(816);
    expect(screen.getByTestId('house-backdrop-continuation')).toHaveStyle({
      top: 812,
    });
    expect(screen.getByTestId('house-bottom-fade')).toHaveStyle({
      top: 812,
    });
  });

  it('keeps the control boundary below the minimum scene on short screens', () => {
    expect(houseWeekPanelTop(0, 456.8, 239.3, 123.4)).toBeCloseTo(337.9, 1);
  });

  it('uses the selected monkey artwork for every temporary house pose', () => {
    expect(houseRoomArt.source).toBe(imageAssets.houseCampingMorningBackground);
    expect(
      Object.values(housePoseArt).every(
        (slot) => slot.source === imageAssets.houseMascotMonkey01,
      ),
    ).toBe(true);
  });

  it('registers every banana mascot and can select the full random range', () => {
    expect(houseBananaPoseArt.map((slot) => slot.source)).toEqual([
      imageAssets.houseMascotBananaSheet01Monkey07,
      imageAssets.houseMascotBananaSheet01Monkey08,
      imageAssets.houseMascotBananaSheet02Monkey05,
      imageAssets.houseMascotBananaSheet02Monkey13,
      imageAssets.houseMascotBananaSheet02Monkey20,
      imageAssets.houseMascotBananaSheet02Monkey22,
    ]);
    expect(randomHouseBananaPoseArt(null, () => 0)).toBe(houseBananaPoseArt[0]);
    expect(randomHouseBananaPoseArt(null, () => 0.999999)).toBe(
      houseBananaPoseArt[houseBananaPoseArt.length - 1],
    );
  });

  it('registers only normal monkey poses for the post-feed random range', () => {
    expect(houseRegularPoseArt).toHaveLength(41);
    expect(houseRegularPoseArt.every((slot) => slot.id === 'pose-random')).toBe(
      true,
    );
    expect(randomHouseRegularPoseArt(null, () => 0)).toBe(
      houseRegularPoseArt[0],
    );
    expect(randomHouseRegularPoseArt(null, () => 0.999999)).toBe(
      houseRegularPoseArt[houseRegularPoseArt.length - 1],
    );
  });

  it('uses a random non-banana, non-unused pose when petted', async () => {
    renderHouse(houseApi());

    await waitFor(() =>
      expect(screen.getByText(`${BANANA_REWARD.completed}개`)).toBeTruthy(),
    );
    const expected = randomHousePettedPoseArt(
      housePoseArt.greeting.source,
      () => 0,
    );
    const random = jest.spyOn(Math, 'random').mockReturnValue(0);

    try {
      fireEvent.press(screen.getByTestId('house-pet-action'));

      const petted = screen.getByLabelText('쓰다듬어 주는 중');
      expect(petted.props.source).toBe(expected.source);
      expect(petted.props.source).not.toBe(housePoseArt.greeting.source);
      expect(houseRegularPoseArt.map((slot) => slot.source)).toContain(
        petted.props.source,
      );
      expect(houseBananaPoseArt.map((slot) => slot.source)).not.toContain(
        petted.props.source,
      );
    } finally {
      random.mockRestore();
    }
  });

  it('keeps the banana pose for 5.6 seconds, then settles on a normal pose', async () => {
    renderHouse(houseApi());

    await waitFor(() =>
      expect(screen.getByText(`${BANANA_REWARD.completed}개`)).toBeTruthy(),
    );
    const random = jest.spyOn(Math, 'random').mockReturnValue(0);
    jest.useFakeTimers();

    try {
      fireEvent.press(screen.getByTestId('house-feed-action'));

      expect(FEED_POSE_HOLD_MS).toBe(5600);
      expect(screen.getByLabelText('바나나를 먹는 끼끼').props.source).toBe(
        houseBananaPoseArt[0]?.source,
      );

      act(() => jest.advanceTimersByTime(FEED_POSE_HOLD_MS - 1));
      expect(screen.getByLabelText('바나나를 먹는 끼끼')).toBeTruthy();

      act(() => jest.advanceTimersByTime(1));
      expect(screen.queryByLabelText('바나나를 먹는 끼끼')).toBeNull();
      expect(screen.getByLabelText('다른 모습의 끼끼').props.source).toBe(
        houseRegularPoseArt[0]?.source,
      );
    } finally {
      jest.useRealTimers();
      random.mockRestore();
    }
  });

  it('renders the house mascot at 75 percent of its former size', async () => {
    renderHouse(houseApi());

    const mascot = await screen.findByTestId('house-art-pose-greeting');
    expect(HOUSE_MASCOT_SIZE).toBe(111);
    expect(mascot).toHaveStyle({ width: 111, height: 111 });
  });

  it('keeps the centered mascot stable and never renders interaction notices', async () => {
    renderHouse(houseApi());

    const initialMascot = await screen.findByTestId('house-art-pose-greeting');
    const mascotSlot = screen.getByTestId('house-mascot-slot');

    expect(mascotSlot).toHaveStyle({
      position: 'absolute',
      top: '45%',
      height: 111,
      transform: [{ translateY: -55.5 }],
    });
    expect(initialMascot).toHaveStyle({
      top: 0,
      width: 111,
      height: 111,
    });
    expect(screen.queryByTestId('house-feedback-slot')).toBeNull();
    expect(screen.queryByTestId('house-feedback')).toBeNull();
    expect(screen.queryByTestId('house-feedback-overlay')).toBeNull();

    fireEvent.press(screen.getByTestId('house-feed-action'));
    expect(screen.getByTestId('house-art-pose-eating')).toHaveStyle({
      top: 0,
      width: 111,
      height: 111,
    });
    expect(houseBananaPoseArt.map((slot) => slot.source)).toContain(
      screen.getByLabelText('바나나를 먹는 끼끼').props.source,
    );
    expect(screen.queryByText('끼끼가 맛있게 먹었어요.')).toBeNull();
    expect(screen.queryByTestId('house-feedback')).toBeNull();
    expect(screen.queryByTestId('house-feedback-overlay')).toBeNull();
  });

  it('uses translucent surfaces for every top control', async () => {
    renderHouse(houseApi({ sessions: [] }));

    await screen.findByTestId('house-scene');
    const translucent = {
      backgroundColor: 'rgba(255, 255, 255, 0.76)',
    };
    expect(screen.getByTestId('house-banana-count')).toHaveStyle(translucent);
    expect(screen.getByTestId('house-decorate-action')).toHaveStyle(
      translucent,
    );
    expect(screen.getByTestId('house-gift-button')).toHaveStyle(translucent);
  });

  it('keeps the controls phone-width on a wide viewport', async () => {
    renderHouse(houseApi());

    const column = await screen.findByTestId('house-content-column');
    expect(column).toHaveStyle({ maxWidth: 430, alignSelf: 'center' });
  });

  it('opens 집 꾸미기 over the buttons without moving the scene', async () => {
    renderHouse(houseApi());

    await screen.findByTestId('house-scene');
    fireEvent.press(screen.getByTestId('house-decorate-action'));

    // The panel is an overlay: the stack under it stays mounted, so the column
    // keeps its height and the backdrop and mascot do not shift. It is hidden
    // from assistive tech while covered, hence `includeHiddenElements`.
    expect(screen.getByTestId('house-decorate-panel')).toBeTruthy();
    const covered = { includeHiddenElements: true } as const;
    expect(screen.getByTestId('house-feed-action', covered)).toBeTruthy();
    expect(screen.getByTestId('house-pet-action', covered)).toBeTruthy();
    expect(screen.getByTestId('house-week-panel', covered)).toBeTruthy();
    expect(screen.getByTestId('house-scene')).toBeTruthy();

    fireEvent.press(screen.getByLabelText('집 꾸미기 닫기'));
    expect(screen.queryByTestId('house-decorate-panel')).toBeNull();
  });

  it('never offers an action it cannot pay for', async () => {
    renderHouse(houseApi({ sessions: [] }));

    await screen.findByTestId('house-scene');
    expect(screen.getByTestId('house-feed-action')).toBeDisabled();
    expect(screen.getByTestId('house-pet-action')).toBeDisabled();
  });
});
