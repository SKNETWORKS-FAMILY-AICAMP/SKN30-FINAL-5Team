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
 * rewarded session ids and local dates are written. Tokens, identifiers and
 * health records must never reach this module.
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
 * Device-scoped, not user-scoped: a per-user key would mean storing an
 * identifier, and the house holds nothing worth that trade. Two accounts on
 * one device share a house until the server owns this state.
 */
const STORAGE_KEY = 'helkki.house.v1';

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

export function createHouseStore(): HouseStore {
  const storage = webStorage();
  if (storage === null) return createMemoryHouseStore();

  return {
    read: () => {
      try {
        const raw = storage.getItem(STORAGE_KEY);
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
        storage.setItem(STORAGE_KEY, JSON.stringify(state));
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
