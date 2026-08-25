/**
 * 끼끼의 집 — the mascot's home, and the user's real standing beside it.
 *
 * The container joins two sources: the server's week and workout sessions,
 * and the house's own local state. It deliberately does not load the routine.
 * Home is the signed-in entry point that shows the server's final routine, and
 * repeating it here would be a second place to keep in step.
 *
 * A week that fails to load does not take the house down with it. The room is
 * a place the user can visit; the failure is shown inline with a retry instead
 * of replacing the screen, and every value that depends on the week degrades
 * to "unknown" rather than to a guess.
 *
 * The mascot reacts to progress but never to a shortfall. A missed or
 * unfinished week is a learning signal, so the copy stays level and no
 * disappointed state exists here.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { Api } from '../../api/endpoints';
import type { WeekResponse, WorkoutSessionLogSummary } from '../../api/types';
import {
  localDateString,
  useAsyncData,
  weekStartString,
} from '../../api/useAsync';
import type { TabId } from '../../components/brand/BrandChrome';
import {
  LoadingState,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { HomeBottomNavigation } from '../home/HomeScreen';
import {
  BackgroundTestContent,
  type BackgroundTestFeedback,
} from './BackgroundTestContent';
import {
  buyItem,
  claimDailyGift,
  feedMascot,
  grantWorkoutRewards,
  objectParticle,
  petMascot,
  registerVisit,
  restingPose,
  buildHouseView,
  type HouseItemId,
  type HousePose,
  type HouseState,
} from './houseModel';
import {
  createHouseStore,
  initialHouseState,
  type HouseStore,
} from './houseStorage';

/** How long a reaction pose is held before the mascot settles back. */
const POSE_HOLD_MS = 2600;

type HouseRemote = {
  week: WeekResponse | null;
  sessions: WorkoutSessionLogSummary[];
  weekFailed: boolean;
};

export function BackgroundTestScreen({
  api,
  nickname,
  now,
  onNavigate,
  store,
  timeZone,
}: {
  api: Api;
  nickname: string;
  /** Injected by tests so the local date is not the wall clock. */
  now?: Date;
  onNavigate: (tab: TabId) => void;
  /** Injected by tests and previews in place of device storage. */
  store?: HouseStore;
  timeZone?: string;
}) {
  const referenceNow = now ?? new Date();
  const localDate = localDateString(referenceNow, timeZone);
  const weekStart = weekStartString(referenceNow, timeZone);

  const houseStore = useMemo(() => store ?? createHouseStore(), [store]);
  const [houseState, setHouseState] = useState<HouseState | null>(null);
  const [feedback, setFeedback] = useState<BackgroundTestFeedback | null>(null);
  const [dismissedWeekFailure, setDismissedWeekFailure] = useState<
    string | null
  >(null);
  const [reactionPose, setReactionPose] = useState<HousePose | null>(null);
  const poseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** The latest house state, readable from an async callback without a stale closure. */
  const liveState = useRef<HouseState | null>(null);

  const { state: remote, reload } = useAsyncData<HouseRemote>(
    async (signal) => {
      // Neither request rejects: the house stays reachable offline, and the
      // screen says which part is missing instead of failing whole.
      const week = await api
        .getWeek(weekStart, signal)
        .catch(() => 'failed' as const);
      const sessions = await api
        .listWorkoutSessions(
          { fromLocalDate: weekStart, toLocalDate: localDate, limit: 100 },
          signal,
        )
        .then((page) => page.items)
        .catch(() => []);
      return {
        week: week === 'failed' ? null : week,
        sessions,
        weekFailed: week === 'failed',
      };
    },
    [api, localDate, weekStart],
  );

  useEffect(
    () => () => {
      if (poseTimer.current !== null) clearTimeout(poseTimer.current);
    },
    [],
  );

  const persist = useCallback(
    (next: HouseState) => {
      liveState.current = next;
      setHouseState(next);
      void houseStore.write(next);
    },
    [houseStore],
  );

  const react = useCallback((pose: HousePose) => {
    setReactionPose(pose);
    if (poseTimer.current !== null) clearTimeout(poseTimer.current);
    poseTimer.current = setTimeout(() => setReactionPose(null), POSE_HOLD_MS);
  }, []);

  const sessions = remote.status === 'ready' ? remote.data.sessions : null;

  // Arrival: read the stored house once, then record the visit and pay out any
  // workout it has not paid for yet.
  //
  // The stored value is read only on the first pass. A later reload works from
  // the state already in hand, so a reward arriving mid-visit cannot overwrite
  // an action the user just took. Both rules return the state unchanged once
  // applied, which is what stops this from re-running itself.
  useEffect(() => {
    if (sessions === null) return;
    let active = true;
    const held = liveState.current;
    const load = held === null ? houseStore.read() : Promise.resolve(held);

    void load.then((stored) => {
      if (!active) return;
      const base = stored ?? initialHouseState();
      const rewarded = grantWorkoutRewards(
        registerVisit(base, localDate),
        sessions,
      );
      if (held !== null && rewarded.state === base) return;
      persist(rewarded.state);
      if (rewarded.granted > 0) {
        setFeedback({
          tone: 'success',
          message: `운동 기록으로 바나나 ${rewarded.granted}개가 들어왔어요.`,
        });
      }
    });

    return () => {
      active = false;
    };
  }, [houseStore, localDate, persist, sessions]);

  const tabBar = (
    <HomeBottomNavigation activeTab="house" onNavigate={onNavigate} />
  );

  if (remote.status !== 'ready' || houseState === null) {
    return (
      <ScreenShell bands tallBands footer={tabBar}>
        <ScreenHeading title="끼끼의 집" onBand />
        <LoadingState />
      </ScreenShell>
    );
  }

  const view = buildHouseView({
    state: houseState,
    week: remote.data.week,
    sessions: remote.data.sessions,
    weekStart,
    today: localDate,
  });

  const shownFeedback: BackgroundTestFeedback | null =
    remote.data.weekFailed && dismissedWeekFailure !== weekStart
      ? {
          tone: 'warning',
          message: '이번 주 목표를 불러오지 못했어요. 집은 그대로 있어요.',
          onRetry: reload,
        }
      : feedback;

  return (
    <BackgroundTestContent
      feedback={shownFeedback}
      footer={tabBar}
      nickname={nickname}
      onBuyItem={(itemId: HouseItemId) => {
        const item = view.lockedItems.find(
          (candidate) => candidate.id === itemId,
        );
        const next = buyItem(houseState, itemId);
        if (next === null) {
          setFeedback({
            tone: 'warning',
            message: `바나나가 조금 더 필요해요. 다음에 놓아 줘요.`,
          });
          return;
        }
        persist(next);
        const label = item?.label ?? '새 물건';
        setFeedback({
          tone: 'success',
          message: `${label}${objectParticle(label)} 집에 놓았어요.`,
        });
        react('happy');
      }}
      onClaimGift={() => {
        const claimed = claimDailyGift(houseState, localDate);
        if (claimed === null) {
          setFeedback({
            tone: 'warning',
            message: '오늘의 선물은 이미 받았어요. 내일 또 있어요.',
          });
          return;
        }
        persist(claimed.state);
        setFeedback({
          tone: 'success',
          message: `오늘의 선물로 바나나 ${claimed.granted}개를 받았어요.`,
        });
        react('happy');
      }}
      onDismissFeedback={() => {
        if (remote.data.weekFailed && dismissedWeekFailure !== weekStart) {
          setDismissedWeekFailure(weekStart);
          return;
        }
        setFeedback(null);
      }}
      onFeed={() => {
        const next = feedMascot(houseState, localDate);
        if (next === null) {
          setFeedback({
            tone: 'warning',
            message: '바나나가 조금 더 필요해요.',
          });
          return;
        }
        persist(next);
        setFeedback({
          tone: 'success',
          message: '끼끼가 맛있게 먹었어요.',
        });
        react('eating');
      }}
      onPet={() => {
        const next = petMascot(houseState, localDate);
        if (next === null) {
          setFeedback({
            tone: 'warning',
            message: '바나나가 조금 더 필요해요.',
          });
          return;
        }
        persist(next);
        setFeedback({
          tone: 'success',
          message: '끼끼가 기분이 좋아졌어요.',
        });
        react('petted');
      }}
      pose={reactionPose ?? restingPose(view)}
      view={view}
    />
  );
}
