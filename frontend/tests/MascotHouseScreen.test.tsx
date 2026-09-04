import { describe, expect, it, jest } from '@jest/globals';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import type { Api } from '../src/api/endpoints';
import type { WeekResponse, WorkoutSessionLogSummary } from '../src/api/types';
import { imageAssets } from '../src/assets';
import { BackgroundBands } from '../src/components/brand/BrandChrome';
import {
  MIN_COMPACT_INTERFACE_SCALE,
  ScaleViewportProvider,
} from '../src/components/scale';
import { colors } from '../src/components/theme';
import {
  HOUSE_ACTION_EFFECT_MS,
  HOUSE_BACKDROP_ZOOM,
  HOUSE_MASCOT_SIZE,
  houseBottomPanelTop,
  houseBackdropContinuationTop,
  houseBackdropMinimumHeight,
  houseBackdropSize,
  houseControlsTop,
  HOUSE_ITEM_CONTROL_CLEARANCE,
  houseItemPlacementMinY,
  houseItemPlacementMaxY,
  housePlacedItemSize,
  houseMascotSize,
  houseMascotTallScreenOffset,
  houseMascotTop,
  HOUSE_MASCOT_CONTROL_CLEARANCE,
  HOUSE_SPEECH_BUBBLE_DURATION_MS,
  HOUSE_TOUCH_HINT_RESERVED_HEIGHT,
} from '../src/features/house/MascotHouseContent';
import {
  FEED_POSE_HOLD_MS,
  MascotHouseScreen,
} from '../src/features/house/MascotHouseScreen';
import {
  houseBananaPoseArt,
  houseBackgroundArt,
  houseItemArt,
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

function renderHouse(
  api: Api,
  store = createMemoryHouseStore(),
  viewport?: { width: number; height: number },
) {
  const onNavigate = jest.fn();
  const house = (
    <MascotHouseScreen
      api={api}
      nickname="범중"
      now={NOW}
      onNavigate={onNavigate}
      store={store}
      timeZone={TIME_ZONE}
    />
  );
  const view = render(
    viewport ? (
      <ScaleViewportProvider viewport={viewport}>{house}</ScaleViewportProvider>
    ) : (
      house
    ),
  );
  return { ...view, onNavigate, store };
}

/**
 * What the house holds the moment it opens with the default fixture: one
 * completed session, plus the visit quest that replaced 오늘의 선물.
 */
const ARRIVAL_BANANAS = BANANA_REWARD.completed + DAILY_GIFT_BANANAS;

function loadPendingMascot() {
  fireEvent(
    screen.getByTestId('house-mascot-art-preload', {
      includeHiddenElements: true,
    }),
    'load',
  );
}

describe('MascotHouseScreen', () => {
  it('connects the reviewed decoration assets and leaves missing art pending', () => {
    expect(houseItemArt.cushion.source).toBe(imageAssets.houseCushion);
    expect(houseItemArt.lamp.source).toBe(imageAssets.houseLamp);
    expect(houseItemArt.plant.source).toBe(imageAssets.housePlant);
    expect(houseItemArt.dumbbell.source).toBe(imageAssets.houseDumbbell);
    expect(houseItemArt.yoga_mat.source).toBe(imageAssets.houseYogaMat);
    expect(houseItemArt.star_frame.source).toBeNull();
    expect(houseItemArt.window.source).toBeNull();
  });

  it('uses the shared solid canvas while the house is loading', () => {
    const pendingApi = {
      getWeek: jest.fn(() => new Promise<never>(() => undefined)),
      listWorkoutSessions: jest.fn(() => new Promise<never>(() => undefined)),
    } as unknown as Api;
    const view = renderHouse(pendingApi);

    expect(screen.getByText('불러오는 중이에요')).toBeTruthy();
    expect(view.UNSAFE_queryByType(BackgroundBands)).toBeNull();
  });

  it('shows the room, the two tiles and the bananas the week earned', async () => {
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
    // The panel lost its heading and its per-card blurb: two square tiles now
    // sit side by side where the horizontal list used to scroll.
    expect(screen.queryByText('끼끼와 놀기')).toBeNull();
    expect(screen.queryByText('떨어지는 바나나를 받아요')).toBeNull();
    expect(screen.queryByText('30초')).toBeNull();
    expect(screen.getByText('바나나 받기')).toBeTruthy();
    expect(screen.getByText('하루 1회 플레이 가능')).toBeTruthy();
    expect(screen.getByText('퀘스트')).toBeTruthy();
    expect(
      screen.getByTestId('house-mini-game-mascot-banana_catch', {
        includeHiddenElements: true,
      }).props.source,
    ).toBe(imageAssets.houseMascotCollectingBananasEmpty);
    expect(screen.queryByText('주 3회 운동하기')).toBeNull();
    expect(screen.queryByText('1 / 3 회')).toBeNull();
    expect(screen.queryByTestId('house-play-game-action')).toBeNull();
    expect(screen.queryByText('보유 바나나')).toBeNull();
    expect(
      within(screen.getByTestId('house-banana-count')).getByTestId(
        'house-banana-asset',
        { includeHiddenElements: true },
      ),
    ).toHaveStyle({ width: 40, height: 40 });
    await waitFor(() =>
      expect(screen.getByText(`${ARRIVAL_BANANAS}개`)).toBeTruthy(),
    );
    expect(
      screen.getByLabelText(`바나나 ${ARRIVAL_BANANAS}개 보유`),
    ).toBeTruthy();
  });

  it('pays the visit quest on arrival instead of offering a gift to claim', async () => {
    renderHouse(houseApi({ sessions: [] }));

    await screen.findByTestId('house-scene');

    expect(screen.queryByTestId('house-gift-button')).toBeNull();
    await waitFor(() =>
      expect(screen.getByText(`${DAILY_GIFT_BANANAS}개`)).toBeTruthy(),
    );
    fireEvent.press(screen.getByTestId('house-quest-tile'));
    expect(screen.getByTestId('house-quest-row-visit')).toBeTruthy();
  });

  it('opens the banana catch game and returns to the same house', async () => {
    renderHouse(houseApi());

    await screen.findByTestId('house-scene');
    fireEvent.press(screen.getByTestId('house-mini-game-banana_catch'));
    expect(screen.getByTestId('banana-catch-screen')).toBeTruthy();

    fireEvent.press(screen.getByLabelText('끼끼의 집으로 돌아가기'));
    expect(screen.getByTestId('house-scene')).toBeTruthy();
  });

  it('gives the feed button the full row and moves petting onto the mascot', async () => {
    renderHouse(houseApi());

    await screen.findByTestId('house-scene');
    expect(screen.getByTestId('house-feed-action')).toHaveStyle({
      flex: 1,
      flexBasis: 0,
      minWidth: 0,
      borderWidth: 1,
      paddingVertical: 15,
    });
    expect(
      within(screen.getByTestId('house-feed-action')).getByText(
        `-${HOUSE_ACTION_COST.feed}`,
      ),
    ).toHaveStyle({ color: colors.textSub, fontSize: 14 });

    // Petting is a touch on the mascot itself, inside the slot that is
    // anchored to the viewport rather than to the controls below it.
    expect(
      within(screen.getByTestId('house-mascot-slot')).getByTestId(
        'house-pet-action',
      ),
    ).toBeTruthy();
    expect(screen.getByTestId('house-touch-hint')).toBeTruthy();
    expect(screen.getByText('끼끼를 터치해보세요!')).toBeTruthy();
  });

  it('keeps the bottom panel at the height that fixes the backdrop boundary', async () => {
    renderHouse(houseApi());

    await screen.findByTestId('house-scene');
    // 16 + 150 + 16 = 182, what the panel measured when it held the 끼끼와 놀기
    // heading above one 122px card. `houseBottomPanelTop` reads this panel, so
    // the room behind the mascot moves if the height drifts. Anything that
    // needs more room goes above the panel — the intimacy row does.
    expect(screen.getByTestId('house-play-panel')).toHaveStyle({ padding: 16 });
    expect(
      within(screen.getByTestId('house-play-panel')).getByTestId(
        'house-quest-tile',
      ),
    ).toBeTruthy();
    expect(
      within(screen.getByTestId('house-play-panel')).queryByTestId(
        'house-intimacy-bonus',
      ),
    ).toBeNull();
    expect(screen.getByTestId('house-intimacy-bonus')).toBeTruthy();
  });

  it('shrinks buttons, cards, and navigation together on a short viewport', async () => {
    renderHouse(houseApi(), createMemoryHouseStore(), {
      width: 390,
      height: 620,
    });

    await screen.findByTestId('house-scene');
    const compactScale = MIN_COMPACT_INTERFACE_SCALE;

    expect(screen.getByTestId('house-feed-action')).toHaveStyle({
      minHeight: 44,
      paddingVertical: 15 * compactScale,
    });
    expect(screen.getByTestId('house-play-panel')).toHaveStyle({
      padding: 16 * compactScale,
    });
    expect(screen.getByTestId('house-mini-game-banana_catch')).toHaveStyle({
      padding: 12 * compactScale,
    });
    expect(screen.getByTestId('bottom-navigation')).toHaveStyle({
      paddingTop: 8 * compactScale,
      paddingHorizontal: 14 * compactScale,
      paddingBottom: 26 * compactScale,
    });
    expect(screen.getByTestId('bottom-navigation-tabs')).toHaveStyle({
      paddingVertical: 10 * compactScale,
      paddingHorizontal: 6 * compactScale,
    });
  });

  it('spends bananas on feeding and keeps the balance in the store', async () => {
    const { store } = renderHouse(houseApi());

    await waitFor(() =>
      expect(screen.getByText(`${ARRIVAL_BANANAS}개`)).toBeTruthy(),
    );
    expect(screen.getByText('바나나 주기')).toBeTruthy();
    fireEvent.press(screen.getByTestId('house-feed-action'));

    expect(
      within(screen.getByTestId('house-banana-count')).getByTestId(
        'house-action-effect-spend',
        { includeHiddenElements: true },
      ),
    ).toBeTruthy();
    expect(
      screen.getByTestId('house-action-effect-amount', {
        includeHiddenElements: true,
      }).props.children,
    ).toEqual(['-', HOUSE_ACTION_COST.feed]);

    const remaining = ARRIVAL_BANANAS - HOUSE_ACTION_COST.feed;
    expect(screen.getByText(`${remaining}개`)).toBeTruthy();
    await waitFor(async () =>
      expect((await store.read())?.bananas).toBe(remaining),
    );
  });

  it('places a decoration in the room once it is bought', async () => {
    renderHouse(houseApi());

    await waitFor(() =>
      expect(screen.getByText(`${ARRIVAL_BANANAS}개`)).toBeTruthy(),
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
    expect(
      within(screen.getByTestId('house-banana-count')).getByTestId(
        'house-action-effect-amount',
        { includeHiddenElements: true },
      ).props.children,
    ).toEqual(['-', 20]);
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

  it('allows drag placement only while 집 꾸미기 is open and keeps it above the controls', async () => {
    const { store } = renderHouse(houseApi());

    await waitFor(() =>
      expect(screen.getByText(`${ARRIVAL_BANANAS}개`)).toBeTruthy(),
    );
    fireEvent.press(screen.getByTestId('house-decorate-action'));
    fireEvent.press(screen.getByRole('tab', { name: '소품' }));
    fireEvent.press(screen.getByTestId('house-item-yoga_mat'));
    fireEvent(screen.getByTestId('house-decoration-canvas'), 'layout', {
      nativeEvent: { layout: { height: 844, width: 390, x: 0, y: 0 } },
    });
    fireEvent(screen.getByTestId('house-content-column'), 'layout', {
      nativeEvent: { layout: { height: 712, width: 390, x: 0, y: 40 } },
    });
    fireEvent(screen.getByTestId('house-scene'), 'layout', {
      nativeEvent: { layout: { height: 394, width: 358, x: 16, y: 8 } },
    });
    fireEvent(screen.getByTestId('house-top-left-controls'), 'layout', {
      nativeEvent: { layout: { height: 130, width: 84, x: 0, y: 0 } },
    });
    fireEvent(screen.getByTestId('house-top-center-controls'), 'layout', {
      nativeEvent: { layout: { height: 90, width: 140, x: 109, y: 0 } },
    });
    fireEvent(screen.getByTestId('house-top-right-controls'), 'layout', {
      nativeEvent: { layout: { height: 150, width: 84, x: 274, y: 0 } },
    });
    fireEvent(screen.getByTestId('house-action-area'), 'layout', {
      nativeEvent: { layout: { height: 310, width: 358, x: 16, y: 402 } },
    });

    const placed = screen.getByTestId('house-placed-item-yoga_mat');
    expect(
      screen.getByTestId('house-decoration-canvas').props.pointerEvents,
    ).toBe('box-none');
    expect(placed.props.onStartShouldSetResponder()).toBe(true);
    expect(placed).toHaveStyle({
      borderWidth: 1.5,
      borderStyle: 'dashed',
      borderColor: colors.brandOutline,
      height: 132,
      width: 132,
    });

    fireEvent(placed, 'responderGrant', {
      nativeEvent: { pageX: 100, pageY: 100 },
    });
    fireEvent(placed, 'responderMove', {
      nativeEvent: { pageX: 150, pageY: 700 },
    });
    fireEvent(placed, 'responderRelease');

    await waitFor(async () =>
      expect((await store.read())?.itemPlacements.yoga_mat).toEqual({
        x: 0.24 + 50 / (390 - 132),
        y: (442 - 132 - HOUSE_ITEM_CONTROL_CLEARANCE) / (844 - 132),
      }),
    );
    expect(screen.getByTestId('house-placed-item-yoga_mat')).toHaveStyle({
      top: 442 - 132 - HOUSE_ITEM_CONTROL_CLEARANCE,
    });

    const bottomClamped = screen.getByTestId('house-placed-item-yoga_mat');
    fireEvent(bottomClamped, 'responderGrant', {
      nativeEvent: { pageX: 150, pageY: 700 },
    });
    fireEvent(bottomClamped, 'responderMove', {
      nativeEvent: { pageX: 150, pageY: 0 },
    });
    fireEvent(bottomClamped, 'responderRelease');

    await waitFor(async () =>
      expect((await store.read())?.itemPlacements.yoga_mat).toEqual({
        x: 0.24 + 50 / (390 - 132),
        y: (40 + 8 + 150 + HOUSE_ITEM_CONTROL_CLEARANCE) / (844 - 132),
      }),
    );
    expect(screen.getByTestId('house-placed-item-yoga_mat')).toHaveStyle({
      top: 40 + 8 + 150 + HOUSE_ITEM_CONTROL_CLEARANCE,
    });

    fireEvent.press(screen.getByLabelText('집 꾸미기 닫기'));
    expect(
      screen.getByTestId('house-decoration-canvas').props.pointerEvents,
    ).toBe('none');
    expect(
      screen
        .getByTestId('house-placed-item-yoga_mat')
        .props.onStartShouldSetResponder(),
    ).toBe(false);
    expect(screen.getByTestId('house-placed-item-yoga_mat')).toHaveStyle({
      borderWidth: 0,
    });
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

  it('keeps the bottom tiles available when the week fails', async () => {
    const api = houseApi({ weekError: true });
    renderHouse(api);

    expect(await screen.findByTestId('house-scene')).toBeTruthy();
    expect(screen.getByTestId('house-mini-game-banana_catch')).toBeTruthy();
    expect(screen.getByTestId('house-quest-tile')).toBeTruthy();
    expect(screen.queryByText('목표를 불러오지 못했어요')).toBeNull();
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
    fireEvent(screen.getByTestId('house-play-panel'), 'layout', {
      nativeEvent: { layout: { height: 130, width: 358, x: 0, y: 200 } },
    });

    expect(houseBottomPanelTop(40, 760, 250, 130)).toBe(666);
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

    expect(houseBottomPanelTop(40, 910, 250, 130)).toBe(816);
    expect(screen.getByTestId('house-backdrop-continuation')).toHaveStyle({
      top: 812,
    });
    expect(screen.getByTestId('house-bottom-fade')).toHaveStyle({
      top: 812,
    });
  });

  /**
   * The shapes the app actually meets: a small phone, the reference phone, a
   * tall phone, a foldable, and two web windows including a short landscape
   * one. Nothing here assumes a device — the rule is derived from measured
   * layout, so the same assertion has to hold for all of them.
   */
  const CLEARANCE_VIEWPORTS = [
    { label: 'small phone', width: 320, height: 568 },
    { label: 'reference phone', width: 390, height: 844 },
    { label: 'tall phone', width: 430, height: 932 },
    { label: 'foldable', width: 412, height: 1024 },
    { label: 'web window', width: 1280, height: 720 },
    { label: 'short web window', width: 1024, height: 500 },
  ] as const;

  it.each(CLEARANCE_VIEWPORTS)(
    'never lets the mascot or its hint reach the controls on a $label',
    ({ height }) => {
      const mascotSize = houseMascotSize(height);
      const belowMascotHeight = HOUSE_TOUCH_HINT_RESERVED_HEIGHT + 8;

      // Sweep the whole range the controls can occupy rather than one guess at
      // their height: the design changes, the rule must not.
      for (
        let controlsTop = height * 0.3;
        controlsTop < height;
        controlsTop += 8
      ) {
        const top = houseMascotTop({
          belowMascotHeight,
          controlsTop,
          mascotSize,
          sceneTop: 0,
          viewportHeight: height,
        });
        // Either the clearance holds, or the viewport is too short for both
        // and the mascot has stopped at its floor rather than climbing behind
        // the top chips. It is never somewhere in between.
        const clears =
          top + mascotSize + belowMascotHeight <=
          controlsTop - HOUSE_MASCOT_CONTROL_CLEARANCE + 0.001;
        expect(clears || top === 0).toBe(true);
      }
    },
  );

  it('keeps the tuned anchor whenever the controls leave room for it', () => {
    const mascotSize = houseMascotSize(844);
    const anchored = 844 * 0.45 - mascotSize / 2;

    expect(
      houseMascotTop({
        belowMascotHeight: 42,
        // The controls as they were before the intimacy row was added.
        controlsTop: 508,
        mascotSize,
        sceneTop: 0,
        viewportHeight: 844,
      }),
    ).toBeCloseTo(anchored, 5);
  });

  it('lifts the mascot exactly as far as taller controls require', () => {
    const mascotSize = houseMascotSize(844);

    // 442 is where the action area now starts on the reference phone.
    expect(
      houseMascotTop({
        belowMascotHeight: 42,
        controlsTop: 442,
        mascotSize,
        sceneTop: 0,
        viewportHeight: 844,
      }),
    ).toBeCloseTo(442 - HOUSE_MASCOT_CONTROL_CLEARANCE - 42 - mascotSize, 5);
  });

  it('stops the mascot under the top chips rather than behind them', () => {
    // A viewport too short to hold both: the floor wins over the clamp.
    expect(
      houseMascotTop({
        belowMascotHeight: 42,
        controlsTop: 180,
        mascotSize: 111,
        sceneTop: 120,
        viewportHeight: 420,
      }),
    ).toBe(120);
  });

  it('holds the tuned anchor until the controls have been measured', () => {
    const mascotSize = houseMascotSize(844);

    expect(
      houseMascotTop({
        belowMascotHeight: 42,
        controlsTop: null,
        mascotSize,
        sceneTop: 0,
        viewportHeight: 844,
      }),
    ).toBeCloseTo(844 * 0.45 - mascotSize / 2, 5);
    expect(houseControlsTop(null, 712, 310)).toBeNull();
    expect(houseControlsTop(40, 712, 310)).toBe(442);
  });

  it('limits decoration placement to the area between top and bottom controls', () => {
    expect(houseItemPlacementMinY(844, 198)).toBe(
      (198 + HOUSE_ITEM_CONTROL_CLEARANCE) / (844 - 44),
    );
    expect(houseItemPlacementMinY(844, null)).toBe(0);
    expect(houseItemPlacementMaxY(844, 442)).toBe(
      (442 - 44 - HOUSE_ITEM_CONTROL_CLEARANCE) / (844 - 44),
    );
    expect(houseItemPlacementMaxY(844, null)).toBe(1);
    expect(houseItemPlacementMaxY(40, 20)).toBe(0);
  });

  it('sizes placed decoration artwork independently from its shop preview', () => {
    expect(housePlacedItemSize('yoga_mat')).toBe(132);
    expect(housePlacedItemSize('dumbbell')).toBe(44);
    expect(housePlacedItemSize('plant')).toBe(88);
    expect(housePlacedItemSize('cushion')).toBe(66);
    expect(housePlacedItemSize('lamp')).toBe(132);
  });

  it('keeps placed assets below the controls, mascot, and speech bubble', async () => {
    renderHouse(houseApi());

    await screen.findByTestId('house-scene');
    expect(screen.getByTestId('house-decoration-canvas')).toHaveStyle({
      zIndex: 1,
    });
    expect(screen.getByTestId('house-safe-area')).toHaveStyle({ zIndex: 2 });
    expect(screen.getByTestId('house-mascot-slot')).toHaveStyle({ zIndex: 3 });
  });

  it('hides speech after five seconds and shows it again for a new reaction', async () => {
    jest.useFakeTimers();
    try {
      renderHouse(houseApi());
      await waitFor(() =>
        expect(screen.getByTestId('house-speech-bubble')).toBeTruthy(),
      );

      act(() => jest.advanceTimersByTime(4800));
      expect(screen.getByTestId('house-speech-bubble')).toBeTruthy();
      act(() => jest.advanceTimersByTime(300));
      expect(screen.queryByTestId('house-speech-bubble')).toBeNull();

      fireEvent.press(screen.getByTestId('house-pet-action'));
      expect(screen.getByTestId('house-speech-bubble')).toBeTruthy();
      expect(HOUSE_SPEECH_BUBBLE_DURATION_MS).toBe(5000);
    } finally {
      jest.useRealTimers();
    }
  });

  it.each(CLEARANCE_VIEWPORTS)(
    'keeps decorations clear of both control groups on a $label',
    ({ height }) => {
      const topControlsBottom = height * 0.2;
      const bottomControlsTop = height * 0.7;

      for (const itemSize of [44, 66, 88, 132]) {
        const usableHeight = height - itemSize;
        const minimumTop =
          houseItemPlacementMinY(height, topControlsBottom, itemSize) *
          usableHeight;
        const maximumTop =
          houseItemPlacementMaxY(height, bottomControlsTop, itemSize) *
          usableHeight;

        expect(minimumTop).toBeCloseTo(
          topControlsBottom + HOUSE_ITEM_CONTROL_CLEARANCE,
        );
        expect(maximumTop + itemSize).toBeCloseTo(
          bottomControlsTop - HOUSE_ITEM_CONTROL_CLEARANCE,
        );
      }
    },
  );

  it('lifts the mascot off its anchor when the real controls grow into it', async () => {
    renderHouse(houseApi());
    await screen.findByTestId('house-scene');

    fireEvent(screen.getByTestId('mascot-house-content'), 'layout', {
      nativeEvent: { layout: { height: 844, width: 390, x: 0, y: 0 } },
    });
    fireEvent(screen.getByTestId('house-content-column'), 'layout', {
      nativeEvent: { layout: { height: 712, width: 390, x: 0, y: 40 } },
    });
    // The action area as it stands with the intimacy row above the tiles.
    fireEvent(screen.getByTestId('house-action-area'), 'layout', {
      nativeEvent: { layout: { height: 310, width: 358, x: 16, y: 402 } },
    });
    fireEvent(screen.getByTestId('house-touch-hint'), 'layout', {
      nativeEvent: { layout: { height: 34, width: 200, x: 0, y: 119 } },
    });

    const controlsTop = houseControlsTop(40, 712, 310);
    expect(controlsTop).toBe(442);

    const mascotSize = houseMascotSize(844);
    const belowMascotHeight = 34 + 8;
    const slotTop = StyleSheet.flatten(
      screen.getByTestId('house-mascot-slot').props.style,
    ).top as number;

    // The tuned 45% anchor would put the hint behind the feed button, so the
    // mascot is lifted — and lands exactly on the clearance, not further.
    expect(slotTop).toBeLessThan(844 * 0.45 - mascotSize / 2);
    expect(slotTop + mascotSize + belowMascotHeight).toBe(
      controlsTop! - HOUSE_MASCOT_CONTROL_CLEARANCE,
    );
  });

  it('keeps the control boundary below the minimum scene on short screens', () => {
    expect(houseBottomPanelTop(0, 456.8, 239.3, 123.4)).toBeCloseTo(337.9, 1);
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
      expect(screen.getByText(`${ARRIVAL_BANANAS}개`)).toBeTruthy(),
    );
    const expected = randomHousePettedPoseArt(
      housePoseArt.greeting.source,
      () => 0,
    );
    const random = jest.spyOn(Math, 'random').mockReturnValue(0);

    try {
      fireEvent.press(screen.getByTestId('house-pet-action'));

      expect(
        within(screen.getByTestId('house-mascot-slot')).getByTestId(
          'house-mascot-effect-sparkle',
          { includeHiddenElements: true },
        ),
      ).toBeTruthy();
      expect(
        within(screen.getByTestId('house-mascot-slot')).getByTestId(
          'house-mascot-effect-stars',
          { includeHiddenElements: true },
        ),
      ).toBeTruthy();
      // Petting costs nothing now, so the mascot sparkles and the banana
      // count shows no deduction at all.
      expect(
        within(screen.getByTestId('house-banana-count')).queryByTestId(
          'house-action-effect-amount',
          { includeHiddenElements: true },
        ),
      ).toBeNull();

      expect(screen.getByLabelText('인사하는 끼끼')).toBeTruthy();
      expect(
        screen.getByTestId('house-mascot-art-preload', {
          includeHiddenElements: true,
        }).props.source,
      ).toBe(expected.source);
      loadPendingMascot();

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
      expect(screen.getByText(`${ARRIVAL_BANANAS}개`)).toBeTruthy(),
    );
    const random = jest.spyOn(Math, 'random').mockReturnValue(0);
    jest.useFakeTimers();

    try {
      fireEvent.press(screen.getByTestId('house-feed-action'));

      expect(FEED_POSE_HOLD_MS).toBe(5600);
      expect(screen.getByLabelText('인사하는 끼끼')).toBeTruthy();
      expect(
        screen.getByTestId('house-mascot-art-preload', {
          includeHiddenElements: true,
        }).props.source,
      ).toBe(houseBananaPoseArt[0]?.source);
      expect(
        within(screen.getByTestId('house-mascot-slot')).getByTestId(
          'house-mascot-effect-banana',
          { includeHiddenElements: true },
        ),
      ).toBeTruthy();
      expect(
        within(screen.getByTestId('house-mascot-slot')).getByTestId(
          'house-mascot-effect-bananas',
          { includeHiddenElements: true },
        ),
      ).toBeTruthy();
      loadPendingMascot();
      expect(screen.getByLabelText('바나나를 먹는 끼끼').props.source).toBe(
        houseBananaPoseArt[0]?.source,
      );

      expect(
        within(screen.getByTestId('house-banana-count')).getByTestId(
          'house-action-effect-spend',
          { includeHiddenElements: true },
        ),
      ).toBeTruthy();
      act(() => jest.advanceTimersByTime(HOUSE_ACTION_EFFECT_MS));
      expect(
        within(screen.getByTestId('house-banana-count')).queryByTestId(
          'house-action-effect-spend',
          { includeHiddenElements: true },
        ),
      ).toBeNull();
      expect(screen.getByLabelText('바나나를 먹는 끼끼')).toBeTruthy();

      act(() =>
        jest.advanceTimersByTime(
          FEED_POSE_HOLD_MS - HOUSE_ACTION_EFFECT_MS - 1,
        ),
      );
      expect(screen.getByLabelText('바나나를 먹는 끼끼')).toBeTruthy();

      act(() => jest.advanceTimersByTime(1));
      expect(screen.getByLabelText('바나나를 먹는 끼끼')).toBeTruthy();
      expect(
        screen.getByTestId('house-mascot-art-preload', {
          includeHiddenElements: true,
        }).props.source,
      ).toBe(houseRegularPoseArt[0]?.source);
      loadPendingMascot();
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
    fireEvent(screen.getByTestId('mascot-house-content'), 'layout', {
      nativeEvent: { layout: { height: 844, width: 390, x: 0, y: 0 } },
    });
    expect(HOUSE_MASCOT_SIZE).toBe(111);
    expect(houseMascotSize(760)).toBe(111);
    expect(houseMascotSize(844)).toBe(111);
    expect(houseMascotSize(994)).toBe(117);
    expect(houseMascotSize(1200)).toBeCloseTo(125.2, 1);
    expect(houseMascotSize(1400)).toBe(126);
    expect(mascot).toHaveStyle({ width: 111, height: 111 });
  });

  it('lets the mascot follow tall backgrounds slightly without moving on reference screens', async () => {
    renderHouse(houseApi());

    const initialMascot = await screen.findByTestId('house-art-pose-greeting');
    const mascotSlot = screen.getByTestId('house-mascot-slot');

    expect(houseMascotTallScreenOffset(760)).toBe(0);
    expect(houseMascotTallScreenOffset(844)).toBe(0);
    expect(houseMascotTallScreenOffset(994)).toBe(15);
    expect(houseMascotTallScreenOffset(1200)).toBeCloseTo(35.6, 1);
    expect(houseMascotTallScreenOffset(1400)).toBe(50);

    fireEvent(screen.getByTestId('mascot-house-content'), 'layout', {
      nativeEvent: { layout: { height: 844, width: 390, x: 0, y: 0 } },
    });

    // The anchor is now resolved to pixels rather than a percentage plus a
    // transform, because it has to be clamped against the measured controls.
    // With no control layout reported yet it lands on the tuned 45%.
    expect(mascotSlot).toHaveStyle({
      position: 'absolute',
      top: 844 * 0.45 - 55.5,
      height: 111,
    });
    expect(screen.getByTestId('house-speech-bubble')).toHaveStyle({
      bottom: 119,
    });
    expect(initialMascot).toHaveStyle({
      top: 0,
      width: 111,
      height: 111,
    });

    fireEvent(screen.getByTestId('mascot-house-content'), 'layout', {
      nativeEvent: { layout: { height: 994, width: 390, x: 0, y: 0 } },
    });
    expect(mascotSlot).toHaveStyle({
      top: 994 * 0.45 - 58.5 + houseMascotTallScreenOffset(994),
      height: 117,
    });
    expect(screen.getByTestId('house-speech-bubble')).toHaveStyle({
      bottom: 125,
    });
    expect(initialMascot).toHaveStyle({
      top: 0,
      width: 117,
      height: 117,
    });
    expect(screen.queryByTestId('house-feedback-slot')).toBeNull();
    expect(screen.queryByTestId('house-feedback')).toBeNull();
    expect(screen.queryByTestId('house-feedback-overlay')).toBeNull();

    fireEvent.press(screen.getByTestId('house-feed-action'));
    expect(screen.getByTestId('house-art-pose-greeting')).toHaveStyle({
      top: 0,
      width: 117,
      height: 117,
    });
    loadPendingMascot();
    expect(screen.getByTestId('house-art-pose-eating')).toHaveStyle({
      top: 0,
      width: 117,
      height: 117,
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
    expect(screen.getByTestId('house-intimacy-chip')).toHaveStyle(translucent);
  });

  it('uses the full responsive width with Large phone proportional insets', async () => {
    renderHouse(houseApi());

    const column = await screen.findByTestId('house-content-column');
    expect(column).toHaveStyle({
      width: '100%',
      alignSelf: 'center',
      paddingHorizontal: '4%',
    });
    expect(StyleSheet.flatten(column.props.style).maxWidth).toBeUndefined();
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
    expect(screen.getByTestId('house-play-panel', covered)).toBeTruthy();
    expect(screen.getByTestId('house-scene')).toBeTruthy();

    fireEvent.press(screen.getByLabelText('집 꾸미기 닫기'));
    expect(screen.queryByTestId('house-decorate-panel')).toBeNull();
  });

  it('never offers an action it cannot pay for, and always offers petting', async () => {
    renderHouse(houseApi({ sessions: [] }));

    await screen.findByTestId('house-scene');
    await waitFor(() =>
      expect(screen.getByText(`${DAILY_GIFT_BANANAS}개`)).toBeTruthy(),
    );

    fireEvent.press(screen.getByTestId('house-feed-action'));
    expect(
      screen.getByText(`${DAILY_GIFT_BANANAS - HOUSE_ACTION_COST.feed}개`),
    ).toBeTruthy();
    expect(screen.getByTestId('house-feed-action')).toBeDisabled();

    // Petting is free, so it has no unaffordable state to fall into.
    expect(screen.getByTestId('house-pet-action')).not.toBeDisabled();
  });
});
