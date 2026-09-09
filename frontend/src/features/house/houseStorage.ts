/**
 * Where the house state is kept between visits.
 *
 * The house is not backed by an API yet, so this is the seam that will be
 * replaced when it is: the screen only ever sees `HouseStore`, never a
 * storage mechanism. Nothing here adds a dependency — the web build uses
 * `localStorage`, and every other platform keeps the state for the lifetime
 * of the process until a real store exists.
 *
 * Only the banana count, selected background id, owned decoration ids,
 * rewarded session ids and local dates are written. Tokens, raw identifiers
 * and health records must never reach this module.
 */

import {
  createHouseState,
  parseHouseState,
  type HouseState,
} from './houseModel';

export type HouseStore = {
  read(): Promise<HouseState | null>;
  write(state: HouseState): Promise<void>;
};

/**
 * One house per account, not per device.
 *
 * This was device-scoped so that no user identifier was written to storage, on
 * the reasoning that the house held nothing worth that trade. It does: signing
 * up on a device that had been used before showed the new account the previous
 * one's decorations and its record of what had already been paid for.
 *
 * The identifier concern is met without storing the identifier. The key carries
 * a short non-reversible digest of the user id, which cannot be read back into
 * an id and is useless against the API -- it only says "not the same account".
 */
const STORAGE_PREFIX = 'helkki.house.v1';

/**
 * The pre-partition key. Its contents belong to whichever account happened to
 * use the device last, so it is discarded rather than migrated: handing it to
 * the next account to sign in is the exact bug being fixed.
 */
const LEGACY_STORAGE_KEY = 'helkki.house.v1';

/** FNV-1a. Not a security boundary -- a short stable partition label. */
function accountDigest(accountId: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < accountId.length; index += 1) {
    hash ^= accountId.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

export function houseStorageKey(accountId: string): string {
  return `${STORAGE_PREFIX}.${accountDigest(accountId)}`;
}

/** Keeps the state alive across screen mounts when there is no web storage. */
export function createMemoryHouseStore(
  initial: HouseState | null = null,
): HouseStore {
  let held = initial;
  return {
    read: () => Promise.resolve(held),
    write: (state) => {
      held = state;
      return Promise.resolve();
    },
  };
}

function webStorage(): Storage | null {
  try {
    if (typeof globalThis.localStorage === 'undefined') return null;
    return globalThis.localStorage;
  } catch {
    // Reading the accessor itself throws when site data is blocked.
    return null;
  }
}

export function createHouseStore(accountId: string): HouseStore {
  const storage = webStorage();
  if (storage === null) return createMemoryHouseStore();
  const key = houseStorageKey(accountId);
  try {
    // Removed on first use so a device that predates the partition cannot leak
    // its house into any account, including this one.
    storage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // Nothing here depends on the removal succeeding.
  }

  return {
    read: () => {
      try {
        const raw = storage.getItem(key);
        if (raw === null) return Promise.resolve(null);
        return Promise.resolve(parseHouseState(JSON.parse(raw) as unknown));
      } catch {
        // Unreadable or corrupt storage starts the house over rather than
        // failing the screen.
        return Promise.resolve(null);
      }
    },
    write: (state) => {
      try {
        storage.setItem(key, JSON.stringify(state));
      } catch {
        // A full or blocked quota must not break the visit.
      }
      return Promise.resolve();
    },
  };
}

/** The value a first-time visitor starts from. */
export function initialHouseState(): HouseState {
  return createHouseState();
}
