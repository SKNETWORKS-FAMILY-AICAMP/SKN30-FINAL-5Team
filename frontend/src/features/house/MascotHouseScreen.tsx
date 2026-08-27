/**
 * 끼끼의 집 — the mascot's home, and the user's real standing beside it.
 *
 * The container joins two sources: the server's week and workout sessions,
 * and the house's own local state. It deliberately does not load the routine.
 * Home is the signed-in entry point that shows the server's final routine, and
 * repeating it here would be a second place to keep in step.
 *
 * A week that fails to load does not take the house down with it. The room is
 * a place the user can visit, and every value that depends on the week
 * degrades to "unknown" rather than to a guess.
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
import { LoadingState, ScreenShell } from '../../components/states/ScreenState';
import { HomeBottomNavigation } from '../home/HomeScreen';
import { BananaCatchGameScreen } from '../bananaCatch/BananaCatchGameScreen';
import { MascotHouseContent } from './MascotHouseContent';
import {
  housePoseArt,
  randomHouseBananaPoseArt,
  randomHousePettedPoseArt,
  randomHouseRegularPoseArt,
  type HouseArtSlot,
} from './houseArtSlots';
import {
  buyItem,
  claimDailyGift,
  feedMascot,
  grantWorkoutRewards,
  petMascot,
  placeHouseItem,
  registerVisit,
  restingPose,
  selectBackground,
  buildHouseView,
  type HouseBackgroundId,
  type HouseItemId,
  type HouseItemPlacement,
  type HousePose,
  type HouseState,
} from './houseModel';
import {
  createHouseStore,
  initialHouseState,
  type HouseStore,
} from './houseStorage';

/** How long ordinary reactions are held before the mascot settles back. */
const POSE_HOLD_MS = 2600;

/** Feeding stays visible about three seconds longer than it did originally. */
export const FEED_POSE_HOLD_MS = POSE_HOLD_MS + 3000;

type HouseRemote = {
  week: WeekResponse | null;
  sessions: WorkoutSessionLogSummary[];
};

export function MascotHouseScreen({
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
  const [reactionPose, setReactionPose] = useState<HousePose | null>(null);
  const [reactionArt, setReactionArt] = useState<HouseArtSlot | null>(null);
  const [settledArt, setSettledArt] = useState<HouseArtSlot | null>(null);
  const [playingBananaCatch, setPlayingBananaCatch] = useState(false);
  const lastBananaArt = useRef<HouseArtSlot['source']>(null);
  const lastRegularArt = useRef<HouseArtSlot['source']>(null);
  const poseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** The latest house state, readable from an async callback without a stale closure. */
  const liveState = useRef<HouseState | null>(null);

  const { state: remote } = useAsyncData<HouseRemote>(
    async (signal) => {
      // Neither request rejects: the house stays reachable offline, and the
      // weekly card degrades locally instead of failing the whole screen.
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

  const react = useCallback(
    (
      pose: HousePose,
      art: HouseArtSlot | null = null,
      holdMs: number = POSE_HOLD_MS,
      nextSettledArt: HouseArtSlot | null = null,
    ) => {
      setReactionPose(pose);
      setReactionArt(art);
      if (poseTimer.current !== null) clearTimeout(poseTimer.current);
      poseTimer.current = setTimeout(() => {
        setReactionPose(null);
        setReactionArt(null);
        if (nextSettledArt !== null) setSettledArt(nextSettledArt);
      }, holdMs);
    },
    [],
  );

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
    });

    return () => {
      active = false;
    };
  }, [houseStore, localDate, persist, sessions]);

  const tabBar = (
    <HomeBottomNavigation activeTab="house" onNavigate={onNavigate} />
  );

  if (playingBananaCatch) {
    return (
      <BananaCatchGameScreen onBack={() => setPlayingBananaCatch(false)} />
    );
  }

  if (remote.status !== 'ready' || houseState === null) {
    return (
      <ScreenShell footer={tabBar}>
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

  return (
    <MascotHouseContent
      footer={tabBar}
      nickname={nickname}
      onBuyItem={(itemId: HouseItemId) => {
        const next = buyItem(houseState, itemId);
        if (next === null) return;
        persist(next);
        react('happy');
      }}
      onClaimGift={() => {
        const claimed = claimDailyGift(houseState, localDate);
        if (claimed === null) return;
        persist(claimed.state);
        react('happy');
      }}
      onFeed={() => {
        const next = feedMascot(houseState, localDate);
        if (next === null) return;
        persist(next);
        const bananaArt = randomHouseBananaPoseArt(lastBananaArt.current);
        const regularArt = randomHouseRegularPoseArt(lastRegularArt.current);
        lastBananaArt.current = bananaArt.source;
        lastRegularArt.current = regularArt.source;
        react('eating', bananaArt, FEED_POSE_HOLD_MS, regularArt);
      }}
      onPet={() => {
        const next = petMascot(houseState, localDate);
        if (next === null) return;
        persist(next);
        const visibleArt =
          (reactionPose === null ? settledArt : reactionArt) ??
          housePoseArt[reactionPose ?? restingPose(view)];
        const pettedArt = randomHousePettedPoseArt(visibleArt.source);
        lastRegularArt.current = pettedArt.source;
        react('petted', pettedArt);
      }}
      onPlayGame={() => setPlayingBananaCatch(true)}
      onPlaceItem={(itemId: HouseItemId, placement: HouseItemPlacement) => {
        const base = liveState.current ?? houseState;
        const next = placeHouseItem(base, itemId, placement);
        if (next === null) return;
        persist(next);
      }}
      onSelectBackground={(backgroundId: HouseBackgroundId) => {
        const next = selectBackground(houseState, backgroundId);
        persist(next);
      }}
      mascotArt={
        (reactionPose === null ? settledArt : reactionArt) ?? undefined
      }
      pose={reactionPose ?? restingPose(view)}
      view={view}
    />
  );
}
