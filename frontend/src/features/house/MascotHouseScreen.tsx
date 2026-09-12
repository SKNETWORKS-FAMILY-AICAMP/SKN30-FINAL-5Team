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
import { isApiError, messageForError } from '../../api/errors';
import type {
  BananaSpendRequest,
  BananaWalletResponse,
  WeekResponse,
  WorkoutSessionLogSummary,
} from '../../api/types';
import {
  localDateString,
  useAsyncAction,
  useAsyncData,
  weekStartString,
} from '../../api/useAsync';
import type { TabId } from '../../components/brand/BrandChrome';
import { LoadingState, ScreenShell } from '../../components/states/ScreenState';
import { HomeBottomNavigation } from '../home/HomeScreen';
import {
  BananaCatchGameScreen,
  type BananaCatchRewardState,
} from '../bananaCatch/BananaCatchGameScreen';
import { KikkiRunnerGameScreen } from '../kikkiRunner/KikkiRunnerGameScreen';
import { HelkkiPassScreen } from '../rewards/RewardsScreen';
import { MascotHouseContent, type HouseMiniGameId } from './MascotHouseContent';
import {
  housePoseArt,
  randomHouseBananaPoseArt,
  randomHousePettedPoseArt,
  randomHouseRegularPoseArt,
  type HouseArtSlot,
} from './houseArtSlots';
import {
  buyItem,
  feedMascot,
  grantWorkoutRewards,
  petMascot,
  placeHouseItem,
  recordGamePlay,
  registerVisit,
  restingPose,
  selectBackground,
  settleHouseDay,
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

function spendErrorMessage(error: unknown, fallback: string | null) {
  if (isApiError(error) && error.code === 'INSUFFICIENT_BANANA_BALANCE') {
    return '바나나 잔액이 부족해요. 지갑을 확인한 뒤 다시 시도해주세요.';
  }
  return fallback;
}

/** Feeding stays visible about three seconds longer than it did originally. */
export const FEED_POSE_HOLD_MS = POSE_HOLD_MS + 3000;

type HouseRemote = {
  week: WeekResponse | null;
  sessions: WorkoutSessionLogSummary[];
  wallet: BananaWalletResponse | null;
  walletError: string | null;
};

export function MascotHouseScreen({
  accountId,
  api,
  now,
  onNavigate,
  store,
  timeZone,
}: {
  /** Partitions stored house state so a second account starts its own house. */
  accountId: string;
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

  const houseStore = useMemo(
    () => store ?? createHouseStore(accountId),
    [accountId, store],
  );
  const [houseState, setHouseState] = useState<HouseState | null>(null);
  const [reactionPose, setReactionPose] = useState<HousePose | null>(null);
  const [reactionArt, setReactionArt] = useState<HouseArtSlot | null>(null);
  const [settledArt, setSettledArt] = useState<HouseArtSlot | null>(null);
  const [activeScreen, setActiveScreen] = useState<
    { kind: 'mini-game'; gameId: HouseMiniGameId } | { kind: 'pass' } | null
  >(null);
  const [bananaCatchRewardState, setBananaCatchRewardState] =
    useState<BananaCatchRewardState>({ status: 'idle' });
  const lastBananaArt = useRef<HouseArtSlot['source']>(null);
  const lastRegularArt = useRef<HouseArtSlot['source']>(null);
  const poseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** The latest house state, readable from an async callback without a stale closure. */
  const liveState = useRef<HouseState | null>(null);
  const serverBalance = useRef(0);
  /** Serializes wallet mutations so an older response cannot replace a newer balance. */
  const walletMutationQueue = useRef<Promise<void>>(Promise.resolve());

  const { setData: setRemoteData, state: remote } = useAsyncData<HouseRemote>(
    async (signal) => {
      // Neither request rejects: the house stays reachable offline, and the
      // week-aware mascot copy degrades locally instead of failing the screen.
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
      const rewards = await api
        .getRewards(signal)
        .then((wallet) => ({ wallet, walletError: null }))
        .catch((error: unknown) => ({
          wallet: null,
          walletError: messageForError(error),
        }));
      return {
        week: week === 'failed' ? null : week,
        sessions,
        ...rewards,
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

  const sessions = remote.status === 'ready' ? remote.data.sessions : null;
  const walletBalance =
    remote.status === 'ready' ? (remote.data.wallet?.balance ?? 0) : 0;

  useEffect(() => {
    serverBalance.current = walletBalance;
  }, [walletBalance]);

  /** Official completion, read off the server's status — never inferred here. */
  const workoutCompletedToday = useMemo(
    () =>
      (sessions ?? []).some(
        (session) =>
          session.status_code === 'COMPLETED' &&
          session.local_date === localDate,
      ),
    [localDate, sessions],
  );

  const persist = useCallback(
    (next: HouseState) => {
      // Every write settles the day. Any action on this screen can be the one
      // that finishes a quest, and a single seam means no caller has to
      // remember to pay it. Settling is idempotent within a day, so writing
      // twice never grants twice.
      const settled = settleHouseDay(next, {
        today: localDate,
        workoutCompletedToday,
      }).state;
      const serverBacked = { ...settled, bananas: serverBalance.current };
      liveState.current = serverBacked;
      setHouseState(serverBacked);
      void houseStore.write(serverBacked);
    },
    [houseStore, localDate, workoutCompletedToday],
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
  const spendRequest = useCallback(
    (body: BananaSpendRequest) => api.spendBananas(body),
    [api],
  );
  const spend = useAsyncAction(spendRequest);
  const claimBondingRequest = useCallback(() => api.claimBondingQuest(), [api]);
  const claimBonding = useAsyncAction(claimBondingRequest);
  const claimMiniGameRequest = useCallback(
    (score: number) => api.claimMiniGameReward({ score }),
    [api],
  );
  const claimMiniGame = useAsyncAction(claimMiniGameRequest);
  const claimGiftRequest = useCallback(() => api.claimDailyReward(), [api]);
  const claimGift = useAsyncAction(claimGiftRequest);
  const walletMutationPending =
    spend.pending ||
    claimGift.pending ||
    claimBonding.pending ||
    claimMiniGame.pending;
  const runWalletMutation = useCallback(
    <T,>(request: () => Promise<T | undefined>): Promise<T | undefined> => {
      // Dropping a request while another payout was in flight made a finished
      // mini-game appear to pay nothing (most often while the automatic
      // bonding quest was settling). Queue every wallet intent instead; each
      // endpoint still owns its own idempotency rule.
      const operation = walletMutationQueue.current.then(request);
      walletMutationQueue.current = operation.then(
        () => undefined,
        () => undefined,
      );
      return operation;
    },
    [],
  );

  // The bonding quest is settled locally, but the wallet is the only balance the
  // app shows, so the payout has to come from the server. The house used to add
  // it to its own stored number, which every write then overwrote with the
  // wallet balance -- the quest looked complete and paid nothing.
  const bondingClaimedFor = useRef<string | null>(null);
  useEffect(() => {
    if (houseState === null) return;
    if (houseState.questLocalDate !== localDate) return;
    if (!houseState.paidQuestIds.includes('pet')) return;
    if (bondingClaimedFor.current === localDate) return;
    bondingClaimedFor.current = localDate;
    void runWalletMutation(() => claimBonding.run()).then((result) => {
      if (!result) return;
      serverBalance.current = result.balance;
      if (remote.status !== 'ready') return;
      setRemoteData({
        ...remote.data,
        wallet: { balance: result.balance, daily_reward: result.daily_reward },
        walletError: null,
      });
    });
  }, [houseState, localDate]); // eslint-disable-line react-hooks/exhaustive-deps

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

  if (
    activeScreen?.kind === 'mini-game' &&
    activeScreen.gameId === 'banana_catch'
  ) {
    return (
      <BananaCatchGameScreen
        onBack={() => setActiveScreen(null)}
        onPlayed={(score) => {
          // This branch runs before the house state is guaranteed loaded, so
          // there is nothing to record against until it is.
          const base = liveState.current ?? houseState;
          if (base !== null)
            persist(recordGamePlay(base, 'banana_catch', localDate));
          setBananaCatchRewardState({ status: 'pending' });
          // The payout, its cap and the once-a-day limit are the server's; the
          // client only reports what the round scored. A scoreless round is
          // refused there, which is not worth interrupting the player over, so
          // the wallet is left exactly as it was and no error is surfaced.
          void runWalletMutation(() => claimMiniGame.run(score)).then(
            (result) => {
              if (!result) {
                setBananaCatchRewardState({ status: 'unavailable' });
                return;
              }
              serverBalance.current = result.balance;
              // The house was loaded to get here, but this branch sits above
              // the ready guard, so narrow before reading the wallet.
              if (remote.status === 'ready') {
                setRemoteData({
                  ...remote.data,
                  wallet: {
                    balance: result.balance,
                    daily_reward: result.daily_reward,
                  },
                  walletError: null,
                });
              }
              persist({
                ...(liveState.current ?? houseState ?? initialHouseState()),
                bananas: result.balance,
              });
              setBananaCatchRewardState({
                status: 'settled',
                amount: result.transaction.amount,
              });
            },
          );
        }}
        rewardState={bananaCatchRewardState}
      />
    );
  }

  if (
    activeScreen?.kind === 'mini-game' &&
    activeScreen.gameId === 'kikki_runner'
  ) {
    return (
      <KikkiRunnerGameScreen
        onBack={() => setActiveScreen(null)}
        onPlayed={(score) => {
          const base = liveState.current ?? houseState;
          if (base !== null)
            persist(recordGamePlay(base, 'kikki_runner', localDate));
          void runWalletMutation(() => claimMiniGame.run(score)).then(
            (result) => {
              if (!result) return;
              serverBalance.current = result.balance;
              if (remote.status !== 'ready') return;
              setRemoteData({
                ...remote.data,
                wallet: {
                  balance: result.balance,
                  daily_reward: result.daily_reward,
                },
                walletError: null,
              });
            },
          );
        }}
      />
    );
  }

  if (activeScreen?.kind === 'pass') {
    return <HelkkiPassScreen onBack={() => setActiveScreen(null)} />;
  }

  if (remote.status !== 'ready' || houseState === null) {
    return (
      <ScreenShell footer={tabBar}>
        <LoadingState />
      </ScreenShell>
    );
  }

  const dailyReward = remote.data.wallet?.daily_reward ?? null;
  const view = buildHouseView({
    state: { ...houseState, bananas: walletBalance },
    week: remote.data.week,
    sessions: remote.data.sessions,
    weekStart,
    today: localDate,
    dailyGift:
      dailyReward === null
        ? null
        : {
            amount: dailyReward.reward_amount,
            claimable: dailyReward.is_claimable && !dailyReward.is_claimed,
          },
  });

  return (
    <MascotHouseContent
      actionError={
        spendErrorMessage(spend.lastError, spend.error) ??
        claimGift.error ??
        (remote.status === 'ready' ? remote.data.walletError : null)
      }
      footer={tabBar}
      onBuyItem={async (itemId: HouseItemId) => {
        const current = {
          ...(liveState.current ?? houseState),
          bananas: serverBalance.current,
        };
        const next = buyItem(current, itemId);
        if (next === null) return false;
        const result = await runWalletMutation(() =>
          spend.run({
            action_code: 'PURCHASE_HOUSE_ITEM',
            house_item_code: itemId,
          }),
        );
        if (!result) return false;
        serverBalance.current = result.balance;
        setRemoteData({
          ...remote.data,
          wallet: {
            balance: result.balance,
            daily_reward: result.daily_reward,
          },
          walletError: null,
        });
        persist({ ...next, bananas: result.balance });
        react('happy');
        return true;
      }}
      giftPending={walletMutationPending}
      onClaimDailyGift={async () => {
        // The server owns "once a day": it answers with the same wallet on a
        // repeat, so nothing here has to remember whether today was paid.
        const result = await runWalletMutation(() => claimGift.run());
        if (!result) return false;
        serverBalance.current = result.balance;
        setRemoteData({
          ...remote.data,
          wallet: {
            balance: result.balance,
            daily_reward: result.daily_reward,
          },
          walletError: null,
        });
        persist(liveState.current ?? houseState);
        react('happy');
        return true;
      }}
      onFeed={async () => {
        const current = {
          ...(liveState.current ?? houseState),
          bananas: serverBalance.current,
        };
        const next = feedMascot(current, localDate);
        if (next === null) return false;
        const result = await runWalletMutation(() =>
          spend.run({ action_code: 'FEED_MASCOT' }),
        );
        if (!result) return false;
        serverBalance.current = result.balance;
        setRemoteData({
          ...remote.data,
          wallet: {
            balance: result.balance,
            daily_reward: result.daily_reward,
          },
          walletError: null,
        });
        persist({ ...next, bananas: result.balance });
        const bananaArt = randomHouseBananaPoseArt(lastBananaArt.current);
        const regularArt = randomHouseRegularPoseArt(lastRegularArt.current);
        lastBananaArt.current = bananaArt.source;
        lastRegularArt.current = regularArt.source;
        react('eating', bananaArt, FEED_POSE_HOLD_MS, regularArt);
        return true;
      }}
      onOpenPass={() => setActiveScreen({ kind: 'pass' })}
      onPet={() => {
        // Free and unlimited, so there is no failure case: the touch always
        // lands, and only the intimacy it pays is capped.
        persist(petMascot(liveState.current ?? houseState, localDate));
        const visibleArt =
          (reactionPose === null ? settledArt : reactionArt) ??
          housePoseArt[reactionPose ?? restingPose(view)];
        const pettedArt = randomHousePettedPoseArt(visibleArt.source);
        lastRegularArt.current = pettedArt.source;
        react('petted', pettedArt);
        return true;
      }}
      onPlayGame={(gameId) => {
        if (!view.canPlayGame[gameId]) return;
        // The play is counted when the round finishes, not here: spending it on
        // open meant backing out of the game still used up the day's only try.
        if (gameId === 'banana_catch') {
          setBananaCatchRewardState({ status: 'idle' });
        }
        setActiveScreen({ kind: 'mini-game', gameId });
      }}
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
      spendPending={walletMutationPending}
      view={view}
    />
  );
}
