import { jest } from '@jest/globals';

import { ApiClient } from '../src/api/client';
import { createApi } from '../src/api/endpoints';
import type { ExerciseVariantsResponse } from '../src/api/types';

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
