/**
 * The house is per account, not per device.
 *
 * Signing up on a device someone else had used showed the new account the
 * previous one's decorations and its record of what had already been paid for.
 * These cover the partition and the one-time disposal of the shared key that
 * predates it.
 */

import { afterEach, beforeEach, describe, expect, it } from '@jest/globals';

import {
  createHouseState,
  type HouseItemId,
} from '../src/features/house/houseModel';
import {
  createHouseStore,
  houseStorageKey,
} from '../src/features/house/houseStorage';

const ACCOUNT_A = '11111111-1111-4111-8111-111111111111';
const ACCOUNT_B = '22222222-2222-4222-8222-222222222222';
const LEGACY_KEY = 'helkki.house.v1';

/** The native test environment has no web storage; the store needs a real one. */
function fakeStorage(): Storage {
  const entries = new Map<string, string>();
  return {
    get length() {
      return entries.size;
    },
    clear: () => entries.clear(),
    getItem: (key: string) => entries.get(key) ?? null,
    key: (index: number) => [...entries.keys()][index] ?? null,
    removeItem: (key: string) => {
      entries.delete(key);
    },
    setItem: (key: string, value: string) => {
      entries.set(key, value);
    },
  };
}

beforeEach(() => {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: fakeStorage(),
    writable: true,
  });
});

afterEach(() => {
  Reflect.deleteProperty(globalThis, 'localStorage');
});

function stateOwning(itemIds: HouseItemId[]) {
  return { ...createHouseState(), ownedItemIds: itemIds };
}

describe('house storage', () => {
  it('does not show one account what another account bought', async () => {
    const first = createHouseStore(ACCOUNT_A);
    await first.write(stateOwning(['yoga_mat']));

    const second = createHouseStore(ACCOUNT_B);

    expect(await second.read()).toBeNull();
    expect((await first.read())?.ownedItemIds).toEqual(['yoga_mat']);
  });

  it('keeps each account its own house across separate visits', async () => {
    await createHouseStore(ACCOUNT_A).write(stateOwning(['yoga_mat']));
    await createHouseStore(ACCOUNT_B).write(stateOwning(['plant']));

    expect((await createHouseStore(ACCOUNT_A).read())?.ownedItemIds).toEqual([
      'yoga_mat',
    ]);
    expect((await createHouseStore(ACCOUNT_B).read())?.ownedItemIds).toEqual([
      'plant',
    ]);
  });

  it('writes no raw identifier into the storage key', () => {
    const key = houseStorageKey(ACCOUNT_A);

    expect(key).not.toContain(ACCOUNT_A);
    expect(key.startsWith('helkki.house.v1.')).toBe(true);
    // Stable, so a returning account finds its own house.
    expect(key).toBe(houseStorageKey(ACCOUNT_A));
    expect(key).not.toBe(houseStorageKey(ACCOUNT_B));
  });

  it('discards the shared key rather than handing it to the next account', async () => {
    globalThis.localStorage.setItem(
      LEGACY_KEY,
      JSON.stringify(stateOwning(['yoga_mat'])),
    );

    const store = createHouseStore(ACCOUNT_B);

    expect(globalThis.localStorage.getItem(LEGACY_KEY)).toBeNull();
    expect(await store.read()).toBeNull();
  });
});
