import { useEffect, useMemo, useRef } from 'react';
import {
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { colors, radii, spacing } from '../../components/theme';

const MINIMUM_AGE = 14;
const MIN_BIRTH_YEAR = 1900;
const WHEEL_ITEM_HEIGHT = 44;
const WEB_WHEEL_GESTURE_IDLE_MS = 45;
const WEB_WHEEL_SINGLE_ITEM_DELTA = 240;
const WEB_WHEEL_ACCELERATION_DELTA = 70;
const WEB_WHEEL_MAX_ITEMS_PER_GESTURE = 18;

type Props = {
  disabled?: boolean;
  onChange: (value: string) => void;
  value: string;
};

export function BirthDateField({ disabled = false, onChange, value }: Props) {
  const today = useMemo(() => new Date(), []);
  const latestEligibleBirthdate = useMemo(
    () => getLatestEligibleBirthdate(today),
    [today],
  );
  const selected = parseIsoDate(value) ?? dateParts(latestEligibleBirthdate);
  const birthYears = useMemo(
    () =>
      numberRange(
        MIN_BIRTH_YEAR,
        latestEligibleBirthdate.getFullYear(),
      ).reverse(),
    [latestEligibleBirthdate],
  );
  const birthMonths = useMemo(() => {
    const lastMonth =
      selected.year === latestEligibleBirthdate.getFullYear()
        ? latestEligibleBirthdate.getMonth() + 1
        : 12;
    return numberRange(1, lastMonth);
  }, [latestEligibleBirthdate, selected.year]);
  const birthDays = useMemo(() => {
    const lastDay =
      selected.year === latestEligibleBirthdate.getFullYear() &&
      selected.month === latestEligibleBirthdate.getMonth() + 1
        ? latestEligibleBirthdate.getDate()
        : monthDays(selected.year, selected.month);
    return numberRange(1, lastDay);
  }, [latestEligibleBirthdate, selected.month, selected.year]);

  const changeYear = (year: number) => {
    const latestYear = latestEligibleBirthdate.getFullYear();
    const month = Math.min(
      selected.month,
      year === latestYear ? latestEligibleBirthdate.getMonth() + 1 : 12,
    );
    const maximumDay =
      year === latestYear && month === latestEligibleBirthdate.getMonth() + 1
        ? latestEligibleBirthdate.getDate()
        : monthDays(year, month);
    onChange(toIsoDate(year, month, Math.min(selected.day, maximumDay)));
  };
  const changeMonth = (month: number) => {
    const maximumDay =
      selected.year === latestEligibleBirthdate.getFullYear() &&
      month === latestEligibleBirthdate.getMonth() + 1
        ? latestEligibleBirthdate.getDate()
        : monthDays(selected.year, month);
    onChange(
      toIsoDate(selected.year, month, Math.min(selected.day, maximumDay)),
    );
  };

  return (
    <View
      accessibilityLabel="생년월일 선택"
      style={[styles.birthdateBlock, disabled && styles.disabled]}
    >
      <Text style={styles.fieldLabel}>생년월일</Text>
      <View pointerEvents={disabled ? 'none' : 'auto'} style={styles.wheelRow}>
        <WheelColumn
          label="연도"
          onChange={changeYear}
          options={birthYears}
          selected={selected.year}
          suffix="년"
        />
        <WheelColumn
          label="월"
          onChange={changeMonth}
          options={birthMonths}
          selected={selected.month}
          suffix="월"
        />
        <WheelColumn
          label="일"
          onChange={(day) =>
            onChange(toIsoDate(selected.year, selected.month, day))
          }
          options={birthDays}
          selected={selected.day}
          suffix="일"
        />
      </View>
      <Text style={styles.hint}>
        만 {MINIMUM_AGE}세 이상만 선택할 수 있어요. 선택 가능한 최근 날짜는{' '}
        {formatDate(latestEligibleBirthdate)}예요.
      </Text>
    </View>
  );
}

export function latestEligibleBirthdateIso(today = new Date()): string {
  return formatDate(getLatestEligibleBirthdate(today));
}

function WheelColumn({
  label,
  onChange,
  options,
  selected,
  suffix,
}: {
  label: string;
  onChange: (value: number) => void;
  options: number[];
  selected: number;
  suffix: string;
}) {
  const scrollRef = useRef<ScrollView>(null);
  const selectedIndex = Math.max(0, options.indexOf(selected));
  const currentIndexRef = useRef(selectedIndex);
  const pendingInternalSelectionRef = useRef<number | null>(null);
  const webSettleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const webWheelGestureTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const webWheelDeltaRef = useRef(0);
  const draggingRef = useRef(false);

  const clearWebSettleTimer = () => {
    if (webSettleTimerRef.current !== null) {
      clearTimeout(webSettleTimerRef.current);
      webSettleTimerRef.current = null;
    }
  };

  const clearWebWheelGestureTimer = () => {
    if (webWheelGestureTimerRef.current !== null) {
      clearTimeout(webWheelGestureTimerRef.current);
      webWheelGestureTimerRef.current = null;
    }
  };

  const scrollToIndex = (index: number, animated: boolean) => {
    scrollRef.current?.scrollTo({ animated, y: index * WHEEL_ITEM_HEIGHT });
  };

  const commitIndex = (index: number) => {
    const boundedIndex = Math.max(0, Math.min(options.length - 1, index));
    const option = options[boundedIndex];
    if (option === undefined) return;
    currentIndexRef.current = boundedIndex;
    if (option !== selected) {
      pendingInternalSelectionRef.current = option;
      onChange(option);
    }
  };

  const selectIndex = (index: number, animated = true) => {
    const boundedIndex = Math.max(0, Math.min(options.length - 1, index));
    scrollToIndex(boundedIndex, animated);
    commitIndex(boundedIndex);
  };

  const settleAtOffset = (offsetY: number, align = true) => {
    const index = Math.max(
      0,
      Math.min(options.length - 1, Math.round(offsetY / WHEEL_ITEM_HEIGHT)),
    );
    const targetOffset = index * WHEEL_ITEM_HEIGHT;
    if (align && Math.abs(offsetY - targetOffset) > 1) {
      scrollToIndex(index, true);
    }
    commitIndex(index);
  };

  useEffect(() => {
    currentIndexRef.current = selectedIndex;
    if (pendingInternalSelectionRef.current === selected) {
      pendingInternalSelectionRef.current = null;
      return;
    }
    pendingInternalSelectionRef.current = null;
    scrollToIndex(selectedIndex, false);
  }, [options, selected, selectedIndex]);

  useEffect(
    () => () => {
      clearWebSettleTimer();
      clearWebWheelGestureTimer();
    },
    [],
  );

  const settleFromScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    clearWebSettleTimer();
    draggingRef.current = false;
    settleAtOffset(event.nativeEvent.contentOffset.y, false);
  };

  const handleScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (Platform.OS !== 'web' || draggingRef.current) return;
    const offsetY = event.nativeEvent.contentOffset.y;
    clearWebSettleTimer();
    webSettleTimerRef.current = setTimeout(() => {
      settleAtOffset(offsetY);
      webSettleTimerRef.current = null;
    }, 90);
  };

  const handleWheel = (
    event: NativeSyntheticEvent<{ deltaMode?: number; deltaY: number }>,
  ) => {
    event.preventDefault();
    queueWheelDelta(event.nativeEvent.deltaY, event.nativeEvent.deltaMode);
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const queueWheelDelta = (deltaY: number, deltaMode = 0) => {
    clearWebSettleTimer();
    if (deltaY === 0) return;
    const modeMultiplier =
      deltaMode === 1 ? 16 : deltaMode === 2 ? WHEEL_ITEM_HEIGHT * 3 : 1;
    const normalizedDelta = deltaY * modeMultiplier;
    if (
      webWheelDeltaRef.current !== 0 &&
      Math.sign(webWheelDeltaRef.current) !== Math.sign(normalizedDelta)
    ) {
      webWheelDeltaRef.current = 0;
    }
    webWheelDeltaRef.current += normalizedDelta;
    clearWebWheelGestureTimer();
    webWheelGestureTimerRef.current = setTimeout(() => {
      const accumulatedDelta = webWheelDeltaRef.current;
      webWheelDeltaRef.current = 0;
      webWheelGestureTimerRef.current = null;
      const magnitude = Math.abs(accumulatedDelta);
      const steps =
        magnitude <= WEB_WHEEL_SINGLE_ITEM_DELTA
          ? 1
          : Math.min(
              WEB_WHEEL_MAX_ITEMS_PER_GESTURE,
              1 +
                Math.round(
                  (magnitude - WEB_WHEEL_SINGLE_ITEM_DELTA) /
                    WEB_WHEEL_ACCELERATION_DELTA,
                ),
            );
      selectIndex(
        currentIndexRef.current + Math.sign(accumulatedDelta) * steps,
      );
    }, WEB_WHEEL_GESTURE_IDLE_MS);
  };

  useEffect(() => {
    if (Platform.OS !== 'web' || scrollRef.current === null) return;
    const scrollNode = scrollRef.current.getScrollableNode?.() as
      HTMLElement | undefined;
    if (scrollNode?.addEventListener === undefined) return;

    const preventNativeWheelScroll = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      queueWheelDelta(event.deltaY, event.deltaMode);
    };
    scrollNode.addEventListener('wheel', preventNativeWheelScroll, {
      passive: false,
    });
    return () =>
      scrollNode.removeEventListener('wheel', preventNativeWheelScroll);
  }, [queueWheelDelta]);

  const webWheelProps =
    Platform.OS === 'web' ? { onWheel: handleWheel } : undefined;

  return (
    <View style={styles.wheelColumn}>
      <Text style={styles.wheelLabel}>{label}</Text>
      <View style={styles.wheelViewport}>
        <View pointerEvents="none" style={styles.wheelSelection} />
        <ScrollView
          ref={scrollRef}
          accessibilityLabel={`${label} 선택 스크롤`}
          contentContainerStyle={styles.wheelContent}
          decelerationRate="fast"
          disableIntervalMomentum
          nestedScrollEnabled
          onMomentumScrollBegin={() => {
            draggingRef.current = true;
            clearWebSettleTimer();
          }}
          onMomentumScrollEnd={settleFromScroll}
          onScroll={handleScroll}
          onScrollBeginDrag={() => {
            draggingRef.current = true;
            clearWebSettleTimer();
          }}
          onScrollEndDrag={(event) => {
            draggingRef.current = false;
            const velocity = event.nativeEvent.velocity?.y;
            if (velocity !== undefined && Math.abs(velocity) < 0.1) {
              settleFromScroll(event);
              return;
            }
            const offsetY = event.nativeEvent.contentOffset.y;
            clearWebSettleTimer();
            webSettleTimerRef.current = setTimeout(() => {
              settleAtOffset(offsetY);
              webSettleTimerRef.current = null;
            }, 120);
          }}
          scrollEventThrottle={16}
          showsVerticalScrollIndicator={false}
          snapToAlignment="start"
          snapToInterval={WHEEL_ITEM_HEIGHT}
          style={styles.wheelScroll}
          {...webWheelProps}
        >
          {options.map((option, index) => {
            const selectedOption = selected === option;
            const optionLabel = `${option}${suffix}`;
            return (
              <Pressable
                accessibilityLabel={`${label} ${optionLabel}`}
                accessibilityRole="button"
                accessibilityState={{ selected: selectedOption }}
                key={option}
                onPress={() => selectIndex(index)}
                style={styles.wheelItem}
              >
                <Text
                  style={[
                    styles.wheelItemText,
                    selectedOption && styles.wheelItemTextSelected,
                  ]}
                >
                  {optionLabel}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>
    </View>
  );
}

function parseIsoDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (match === null) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  return { day, month, year };
}

function dateParts(value: Date) {
  return {
    day: value.getDate(),
    month: value.getMonth() + 1,
    year: value.getFullYear(),
  };
}

function getLatestEligibleBirthdate(today: Date) {
  const eligibleYear = today.getFullYear() - MINIMUM_AGE;
  const lastDay = monthDays(eligibleYear, today.getMonth() + 1);
  return new Date(
    eligibleYear,
    today.getMonth(),
    Math.min(today.getDate(), lastDay),
  );
}

function toIsoDate(year: number, month: number, day: number) {
  return `${year.toString().padStart(4, '0')}-${month
    .toString()
    .padStart(2, '0')}-${day.toString().padStart(2, '0')}`;
}

function formatDate(value: Date) {
  return toIsoDate(value.getFullYear(), value.getMonth() + 1, value.getDate());
}

function numberRange(start: number, end: number) {
  return Array.from({ length: Math.max(0, end - start + 1) }, (_, index) =>
    Number(start + index),
  );
}

function monthDays(year: number, month: number): number {
  if (month < 1 || month > 12) return 0;
  if (month === 2) {
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    return leap ? 29 : 28;
  }
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

const styles = StyleSheet.create({
  birthdateBlock: { gap: spacing.sm },
  disabled: { opacity: 0.45 },
  fieldLabel: { color: colors.text, fontSize: 13, fontWeight: '700' },
  wheelRow: { flexDirection: 'row', gap: spacing.sm },
  wheelColumn: { minWidth: 0, flex: 1, gap: 5 },
  wheelLabel: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: '700',
    textAlign: 'center',
  },
  wheelViewport: {
    height: WHEEL_ITEM_HEIGHT * 3,
    overflow: 'hidden',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.canvas,
  },
  wheelScroll: { zIndex: 1 },
  wheelContent: { paddingVertical: WHEEL_ITEM_HEIGHT },
  wheelSelection: {
    position: 'absolute',
    top: WHEEL_ITEM_HEIGHT,
    right: 5,
    left: 5,
    height: WHEEL_ITEM_HEIGHT,
    borderRadius: 9,
    backgroundColor: '#FFF3D4',
  },
  wheelItem: {
    height: WHEEL_ITEM_HEIGHT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  wheelItemText: { color: colors.textMuted, fontSize: 16 },
  wheelItemTextSelected: { color: colors.primary, fontWeight: '800' },
  hint: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
});
