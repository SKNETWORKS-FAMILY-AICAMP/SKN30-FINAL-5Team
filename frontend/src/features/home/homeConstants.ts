import type { HomeAvailabilitySlot } from './homeModel';

export const HOME_BACKGROUND_COLOR = '#FFF8E5';

// Temporarily hide the optional availability-time editor while preserving its
// draft and API values so it can be restored without a contract change.
export const CHECKIN_AVAILABILITY_INPUT_ENABLED: boolean = false;

export const CHECKIN_DURATION_MINUTES = {
  min: 10,
  max: 60,
  step: 10,
} as const;

export const EMPTY_AVAILABILITY_SLOT: HomeAvailabilitySlot = {
  startTime: '',
  endTime: '',
};

export const TIME_WHEEL_ITEM_HEIGHT = 44;
export const TIME_WHEEL_GESTURE_IDLE_MS = 45;
export const TIME_WHEEL_SINGLE_ITEM_DELTA = 240;
export const TIME_WHEEL_ACCELERATION_DELTA = 70;
export const TIME_WHEEL_MAX_ITEMS_PER_GESTURE = 18;
export const TIME_HOURS = Array.from({ length: 24 }, (_, index) => index);
export const TIME_MINUTES = Array.from({ length: 12 }, (_, index) => index * 5);

export const HOME_LAYOUT = {
  contentHorizontalPadding: 18,
  contentTopPadding: 58,
  headerHorizontalPadding: 4,
  headerBottomPadding: 18,
  cardGap: 14,
  bottomBarHorizontalPadding: 14,
  bottomBarBottomPadding: 26,
  sheetHorizontalPadding: 18,
  sheetBottomPadding: 30,
} as const;
