import { jest } from '@jest/globals';

import { ApiClient } from '../src/api/client';
import { createApi } from '../src/api/endpoints';
import type {
  BananaSpendResponse,
  BananaWalletResponse,
  DailyRewardClaimResponse,
  ExerciseVariantsResponse,
  NotificationListResponse,
} from '../src/api/types';

it('reads and mutates the server-backed banana wallet through reviewed endpoints', async () => {
  const wallet: BananaWalletResponse = {
    balance: 20,
    daily_reward: {
      local_date: '2026-09-07',
      reward_amount: 15,
      is_claimable: true,
      is_claimed: false,
      claimed_at: null,
    },
  };
  const claim: DailyRewardClaimResponse = {
    ...wallet,
    balance: 35,
    daily_reward: {
      ...wallet.daily_reward,
      is_claimable: false,
      is_claimed: true,
      claimed_at: '2026-09-07T14:00:00+09:00',
    },
    transaction: {
      transaction_id: 'transaction-claim',
      transaction_type: 'DAILY_REWARD',
      amount: 15,
      balance_after: 35,
      created_at: '2026-09-07T14:00:00+09:00',
    },
  };
  const spend: BananaSpendResponse = {
    ...claim,
    balance: 25,
    transaction: {
      transaction_id: 'transaction-spend',
      transaction_type: 'HOUSE_FEED',
      amount: -10,
      balance_after: 25,
      created_at: '2026-09-07T14:01:00+09:00',
    },
  };
  const responses = [wallet, claim, spend];
  const fetchImpl = jest.fn<typeof fetch>(async () => {
    const payload = responses.shift();
    return Promise.resolve({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(payload),
    } as Response);
  });
  const api = createApi(
    new ApiClient({
      baseUrl: 'https://api.example.test',
      getToken: async () => 'token',
      fetchImpl,
    }),
  );
  const controller = new AbortController();
  const spendKey = '11111111-1111-4111-8111-111111111111';

  await expect(api.getRewards(controller.signal)).resolves.toEqual(wallet);
  await expect(api.claimDailyReward()).resolves.toEqual(claim);
  await expect(
    api.spendBananas({ action_code: 'FEED_MASCOT' }, spendKey),
  ).resolves.toEqual(spend);

  expect(fetchImpl).toHaveBeenNthCalledWith(
    1,
    'https://api.example.test/api/v1/rewards',
    expect.objectContaining({
      method: 'GET',
      body: undefined,
      signal: controller.signal,
    }),
  );
  expect(fetchImpl).toHaveBeenNthCalledWith(
    2,
    'https://api.example.test/api/v1/rewards/daily-reward/claim',
    expect.objectContaining({
      method: 'POST',
      body: undefined,
      headers: expect.objectContaining({
        Authorization: 'Bearer token',
        'Idempotency-Key': expect.any(String),
      }),
    }),
  );
  expect(fetchImpl).toHaveBeenNthCalledWith(
    3,
    'https://api.example.test/api/v1/rewards/spend',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ action_code: 'FEED_MASCOT' }),
      headers: expect.objectContaining({
        Authorization: 'Bearer token',
        'Idempotency-Key': spendKey,
      }),
    }),
  );
});

it('calls the reviewed equipment-variant endpoint without a mutation body', async () => {
  const payload: ExerciseVariantsResponse = {
    source_exercise_id: 'exercise-1',
    source_required_equipment_codes: ['DUMBBELL'],
    items: [],
    catalog_version: 'catalog-v1',
    alternative_set_version: null,
  };
  const fetchImpl = jest.fn<typeof fetch>(async () =>
    Promise.resolve({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(payload),
    } as Response),
  );
  const api = createApi(
    new ApiClient({
      baseUrl: 'https://api.example.test',
      getToken: async () => null,
      fetchImpl,
    }),
  );
  const controller = new AbortController();

  await expect(
    api.getExerciseVariants('exercise-1', controller.signal),
  ).resolves.toEqual(payload);
  expect(fetchImpl).toHaveBeenCalledWith(
    'https://api.example.test/api/v1/exercises/exercise-1/variants',
    expect.objectContaining({
      method: 'GET',
      body: undefined,
      signal: controller.signal,
    }),
  );
});

it('lists notifications and marks one read through the reviewed endpoints', async () => {
  const list: NotificationListResponse = {
    items: [
      {
        notification_id: '11111111-1111-4111-8111-111111111111',
        type: 'KIKKI_RETURN',
        title: '끼끼가 기다리고 있어요',
        message: '끼끼의 집에 들러주세요.',
        created_at: '2026-09-04T09:00:00+09:00',
        read_at: null,
        is_read: false,
        action_type: 'OPEN_KIKKI_HOME',
        payload: {},
      },
    ],
    unread_count: 1,
  };
  const fetchImpl = jest.fn<typeof fetch>(async (input) => {
    const url = String(input);
    const payload = url.endsWith('/read') ? list.items[0] : list;
    return Promise.resolve({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(payload),
    } as Response);
  });
  const api = createApi(
    new ApiClient({
      baseUrl: 'https://api.example.test',
      getToken: async () => 'token',
      fetchImpl,
    }),
  );

  await expect(api.listNotifications()).resolves.toEqual(list);
  await expect(
    api.markNotificationRead('11111111-1111-4111-8111-111111111111'),
  ).resolves.toEqual(list.items[0]);

  expect(fetchImpl).toHaveBeenNthCalledWith(
    1,
    'https://api.example.test/api/v1/notifications',
    expect.objectContaining({ method: 'GET', body: undefined }),
  );
  expect(fetchImpl).toHaveBeenNthCalledWith(
    2,
    'https://api.example.test/api/v1/notifications/11111111-1111-4111-8111-111111111111/read',
    expect.objectContaining({
      method: 'PATCH',
      body: undefined,
      headers: expect.objectContaining({
        Authorization: 'Bearer token',
        'Idempotency-Key': expect.any(String),
      }),
    }),
  );
});
