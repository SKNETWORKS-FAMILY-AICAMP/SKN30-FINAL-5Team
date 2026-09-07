import { jest } from '@jest/globals';

import { ApiClient } from '../src/api/client';
import { createApi } from '../src/api/endpoints';
import type {
  ExerciseVariantsResponse,
  NotificationListResponse,
  PlanRevisionResponse,
} from '../src/api/types';

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

it('updates a decision plan item and order with revision guards and idempotency keys', async () => {
  const response = {
    decision_id: '11111111-1111-4111-8111-111111111111',
    plan_revision: 3,
    final_plan: {
      plan_id: '22222222-2222-4222-8222-222222222222',
      plan_revision: 3,
      action_code: 'KEEP',
      training_type_code: 'STRENGTH',
      body_focus_code: null,
      requested_duration_minutes: 30,
      estimated_duration_seconds: 1800,
      estimated_calories_burned: null,
      setup_seconds: 0,
      warmup_seconds: 60,
      cooldown_seconds: 60,
      items: [],
    },
  } satisfies PlanRevisionResponse;
  const fetchImpl = jest.fn<typeof fetch>(async () =>
    Promise.resolve({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(response),
    } as Response),
  );
  const api = createApi(
    new ApiClient({
      baseUrl: 'https://api.example.test',
      getToken: async () => null,
      fetchImpl,
    }),
  );
  const decisionId = response.decision_id;
  const planId = response.final_plan.plan_id;
  const itemId = '33333333-3333-4333-8333-333333333333';
  const itemKey = '44444444-4444-4444-8444-444444444444';
  const orderKey = '55555555-5555-4555-8555-555555555555';

  await api.updateDecisionPlanItem(
    decisionId,
    itemId,
    {
      expected_plan_id: planId,
      expected_plan_revision: 1,
      sets: 4,
      reps: 12,
    },
    itemKey,
  );
  await api.updateDecisionPlanOrder(
    decisionId,
    {
      expected_plan_id: planId,
      expected_plan_revision: 2,
      ordered_plan_item_ids: [itemId],
    },
    orderKey,
  );

  expect(fetchImpl).toHaveBeenNthCalledWith(
    1,
    `https://api.example.test/api/v1/decisions/${decisionId}/plan-items/${itemId}`,
    expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({
        expected_plan_id: planId,
        expected_plan_revision: 1,
        sets: 4,
        reps: 12,
      }),
      headers: expect.objectContaining({ 'Idempotency-Key': itemKey }),
    }),
  );
  expect(fetchImpl).toHaveBeenNthCalledWith(
    2,
    `https://api.example.test/api/v1/decisions/${decisionId}/plan-item-order`,
    expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({
        expected_plan_id: planId,
        expected_plan_revision: 2,
        ordered_plan_item_ids: [itemId],
      }),
      headers: expect.objectContaining({ 'Idempotency-Key': orderKey }),
    }),
  );
});
