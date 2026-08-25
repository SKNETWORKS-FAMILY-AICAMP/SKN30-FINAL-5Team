import { describe, expect, it, jest } from '@jest/globals';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';

import type { Api } from '../src/api/endpoints';
import type { WeekResponse, WorkoutSessionLogSummary } from '../src/api/types';
import { imageAssets } from '../src/assets';
import {
  HOUSE_BACKDROP_ZOOM,
  HOUSE_MASCOT_SIZE,
  HOUSE_MASCOT_Y_OFFSET,
  houseBackdropSize,
} from '../src/features/house/MascotHouseContent';
import { MascotHouseScreen } from '../src/features/house/MascotHouseScreen';
import {
  housePoseArt,
  houseRoomArt,
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
    fireEvent.press(await screen.findByTestId('house-item-yoga_mat'));

    expect(screen.getByText('요가 매트를 집에 놓았어요.')).toBeTruthy();
    // Once in the room, once as an owned tile in the still-open panel.
    expect(screen.getAllByTestId('house-art-item-yoga_mat').length).toBe(2);

    fireEvent.press(screen.getByLabelText('집 꾸미기 닫기'));
    expect(screen.getAllByTestId('house-art-item-yoga_mat').length).toBe(1);
  });

  it('keeps the house open when the week fails, and offers a retry', async () => {
    const api = houseApi({ weekError: true });
    renderHouse(api);

    expect(await screen.findByTestId('house-scene')).toBeTruthy();
    expect(screen.getByText('목표를 불러오지 못했어요')).toBeTruthy();

    fireEvent.press(screen.getByLabelText('다시 시도'));
    await waitFor(() => expect(api.getWeek).toHaveBeenCalledTimes(2));
  });

  it('lets the user close the week-load warning', async () => {
    renderHouse(houseApi({ sessions: [], weekError: true }));

    await screen.findByText(
      '이번 주 목표를 불러오지 못했어요. 집은 그대로 있어요.',
    );
    fireEvent.press(screen.getByLabelText('알림 닫기'));

    expect(screen.queryByTestId('house-feedback')).toBeNull();
    expect(screen.getByTestId('house-feedback-slot')).toHaveStyle({
      height: 104,
    });
    expect(screen.getByTestId('house-scene')).toBeTruthy();
  });

  it('fills the screen with the scene instead of framing it in a card', async () => {
    renderHouse(houseApi());

    const scene = await screen.findByTestId('house-scene');
    expect(scene).toBeTruthy();
    // The backdrop is a sibling that fills the screen, not a child of the
    // stage, so it runs under the top bar and behind the tab bar.
    const backdrop = screen.getByLabelText('끼끼의 캠핑장 저녁 배경');
    expect(backdrop.props.source).toBe(
      imageAssets.houseCampingDinnerBackground,
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

  it('uses the selected monkey artwork for every temporary house pose', () => {
    expect(houseRoomArt.source).toBe(imageAssets.houseCampingDinnerBackground);
    expect(
      Object.values(housePoseArt).every(
        (slot) => slot.source === imageAssets.houseMascotMonkey01,
      ),
    ).toBe(true);
  });

  it('renders the house mascot at 75 percent of its former size', async () => {
    renderHouse(houseApi());

    const mascot = await screen.findByTestId('house-art-pose-greeting');
    expect(HOUSE_MASCOT_SIZE).toBe(111);
    expect(mascot).toHaveStyle({ width: 111, height: 111 });
  });

  it('keeps the mascot layout fixed while feedback opens and closes', async () => {
    renderHouse(houseApi());

    const initialMascot = await screen.findByTestId('house-art-pose-greeting');
    const mascotSlot = screen.getByTestId('house-mascot-slot');
    const feedbackSlot = await screen.findByTestId('house-feedback-slot');
    await screen.findByTestId('house-feedback');

    expect(mascotSlot).toHaveStyle({ height: 210 });
    expect(HOUSE_MASCOT_Y_OFFSET).toBe(24);
    expect(initialMascot).toHaveStyle({
      bottom: 18,
      width: 111,
      height: 111,
    });
    expect(feedbackSlot).toHaveStyle({ height: 104 });

    fireEvent.press(screen.getByLabelText('알림 닫기'));
    expect(screen.queryByTestId('house-feedback')).toBeNull();
    expect(screen.getByTestId('house-feedback-slot')).toHaveStyle({
      height: 104,
    });

    fireEvent.press(screen.getByTestId('house-feed-action'));
    expect(screen.getByTestId('house-art-pose-eating')).toHaveStyle({
      bottom: 18,
      width: 111,
      height: 111,
    });
    expect(screen.getByText('끼끼가 맛있게 먹었어요.')).toBeTruthy();

    fireEvent.press(screen.getByTestId('house-feedback-dismiss'));
    expect(screen.queryByTestId('house-feedback')).toBeNull();
    expect(screen.getByTestId('house-feedback-slot')).toHaveStyle({
      height: 104,
    });
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
