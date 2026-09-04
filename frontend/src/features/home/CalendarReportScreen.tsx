import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  Animated,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import { Card, GradientActionButton } from '../../components/primitives';
import { colors } from '../../components/theme';
import type { TabId } from '../../components/brand/BrandChrome';
import { HomeBottomNavigation } from './HomeScreen';
import {
  CALENDAR_DAY_VISUALS,
  CALENDAR_MONTH_STATS,
  CALENDAR_STATUS_ORDER,
  CALENDAR_WEEK_CHIPS,
  CALENDAR_WEEKDAYS,
  CALENDAR_WEEKS,
  type CalendarDayStatus,
  type CalendarDay,
  type CalendarMonthStat,
  type CalendarReportPreviewState,
  type CalendarWeek,
  type CalendarWeekState,
} from './homeSecondaryModel';

export const CALENDAR_REPORT_LAYOUT = {
  contentTopPadding: 58,
  contentHorizontalPadding: 16,
  contentBottomPadding: 20,
  weekGap: 8,
} as const;

type CalendarReportScreenProps = {
  onChangeMonth?: (direction: 'previous' | 'next') => void;
  onNavigateTab?: (tab: TabId) => void;
  onOpenWeeklyReport?: (weekId: string) => void;
  onOpenDay?: (day: CalendarDay) => void;
  previewState?: CalendarReportPreviewState;
  monthLabel?: string;
  monthStats?: readonly CalendarMonthStat[];
  weeks?: readonly CalendarWeek[];
  selectedMonth?: string;
  latestMonth?: string;
  routineStartLocalDate?: string;
  onSelectMonth?: (month: string) => void;
};

const MONTH_PICKER_ITEM_HEIGHT = 44;
const WEB_WHEEL_DELTA_PER_ITEM = 100;
const WEB_WHEEL_IDLE_MS = 60;

export function CalendarReportScreen({
  previewState = 'calendar',
  ...props
}: CalendarReportScreenProps) {
  return (
    <CalendarReportContent
      key={previewState}
      {...props}
      previewState={previewState}
    />
  );
}

function CalendarReportContent({
  onChangeMonth,
  onNavigateTab,
  onOpenDay,
  onOpenWeeklyReport,
  previewState = 'calendar',
  monthLabel = '2026년 8월',
  monthStats = CALENDAR_MONTH_STATS,
  weeks = CALENDAR_WEEKS,
  selectedMonth = '2026-08',
  latestMonth = '2026-08',
  routineStartLocalDate,
  onSelectMonth,
}: CalendarReportScreenProps) {
  const [expandedWeek, setExpandedWeek] = useState<string | null>(
    previewState === 'week-detail' ? 'week-2' : null,
  );
  const [pickerOpen, setPickerOpen] = useState(previewState === 'month-picker');
  const hasOpenedPicker = useRef(previewState === 'month-picker');
  const [pickerInitialMonth, setPickerInitialMonth] = useState(latestMonth);
  const [caretRotation] = useState(
    () => new Animated.Value(pickerOpen ? 1 : 0),
  );

  useEffect(() => {
    const animation = Animated.timing(caretRotation, {
      toValue: pickerOpen ? 1 : 0,
      duration: 150,
      useNativeDriver: true,
    });
    animation.start();

    return () => animation.stop();
  }, [caretRotation, pickerOpen]);

  const toggleMonthPicker = () => {
    if (pickerOpen) {
      setPickerOpen(false);
      return;
    }

    setPickerInitialMonth(
      hasOpenedPicker.current ? selectedMonth : latestMonth,
    );
    hasOpenedPicker.current = true;
    setPickerOpen(true);
  };

  const caretRotate = caretRotation.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '180deg'],
  });

  return (
    <SafeAreaView edges={['left', 'right']} style={styles.screen}>
      <StatusBar style="dark" />
      <ScrollView
        showsVerticalScrollIndicator={false}
        style={styles.scroll}
        contentContainerStyle={styles.content}
      >
        <Card style={styles.monthCard}>
          <View style={styles.monthHeader}>
            <View style={styles.monthTitleArea}>
              <Text accessibilityRole="header" style={styles.eyebrow}>
                운동 캘린더
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="연도와 월 선택"
                accessibilityState={{ expanded: pickerOpen }}
                onPress={toggleMonthPicker}
                style={styles.monthPickerButton}
              >
                <Text style={styles.monthTitle}>{monthLabel}</Text>
                <Animated.View
                  style={{ transform: [{ rotate: caretRotate }] }}
                  testID="month-picker-caret"
                >
                  <Svg
                    aria-hidden
                    fill="none"
                    height={16}
                    viewBox="0 0 24 24"
                    width={16}
                  >
                    <Path
                      d="M6 9.5l6 6 6-6"
                      stroke="#8B8780"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2.4}
                    />
                  </Svg>
                </Animated.View>
              </Pressable>
              {pickerOpen ? (
                <MonthPicker
                  latestMonth={latestMonth}
                  selectedMonth={pickerInitialMonth}
                  onConfirm={(month) => {
                    onSelectMonth?.(month);
                    setPickerOpen(false);
                  }}
                />
              ) : null}
            </View>
            <View style={styles.monthActions}>
              <MonthArrow
                direction="previous"
                label="이전 달"
                onPress={() => onChangeMonth?.('previous')}
              />
              <MonthArrow
                direction="next"
                disabled={selectedMonth >= latestMonth}
                label="다음 달"
                onPress={() => onChangeMonth?.('next')}
              />
            </View>
          </View>
          <View style={styles.monthStats}>
            {monthStats.map((stat) => (
              <MonthStat
                key={stat.key}
                color={stat.color}
                label={stat.label}
                value={stat.value}
              />
            ))}
          </View>
        </Card>

        <View style={styles.legendRow}>
          {CALENDAR_STATUS_ORDER.map((status) => (
            <View key={status} style={styles.legendItem}>
              <CalendarStatusMark
                size={18}
                status={status}
                testID={`calendar-legend-${status}`}
              />
              <Text style={styles.legendLabel}>
                {CALENDAR_DAY_VISUALS[status].label}
              </Text>
            </View>
          ))}
        </View>

        <View style={styles.weekdayRow}>
          {CALENDAR_WEEKDAYS.map((weekday) => (
            <Text
              key={weekday.label}
              style={[styles.weekday, { color: weekday.color }]}
              testID={`calendar-weekday-${weekday.label}`}
            >
              {weekday.label}
            </Text>
          ))}
        </View>

        <View style={styles.weekList}>
          {weeks.map((week) => {
            const expanded = expandedWeek === week.id;
            const beforeRoutineStart =
              routineStartLocalDate !== undefined &&
              week.days.every(
                (day) =>
                  day.localDate !== undefined &&
                  day.localDate < routineStartLocalDate,
              );
            return (
              <View
                key={week.id}
                style={[
                  styles.weekBand,
                  expanded && styles.weekBandExpanded,
                  { backgroundColor: week.bandColor },
                  week.state === 'progress' && styles.weekBandCurrent,
                  week.state === 'make' && styles.weekBandReportReady,
                  (week.state === 'unread' || week.state === 'read') &&
                    styles.weekBandReportGenerated,
                  week.state === 'upcoming' && styles.weekBandUpcoming,
                  beforeRoutineStart && styles.weekBandBeforeRoutine,
                ]}
                testID={`calendar-week-${week.id}`}
              >
                <View style={styles.weekHeader}>
                  <View style={styles.weekHeadingRow}>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={
                        beforeRoutineStart
                          ? `${week.label} 루틴 시작 전, 선택할 수 없음`
                          : `${week.label} ${CALENDAR_WEEK_CHIPS[week.state].label}, 요약 ${expanded ? '접기' : '펼치기'}`
                      }
                      accessibilityState={{ disabled: beforeRoutineStart }}
                      disabled={beforeRoutineStart}
                      onPress={() => setExpandedWeek(expanded ? null : week.id)}
                      style={styles.weekTitleButton}
                    >
                      <View style={styles.weekTitleGroup}>
                        <Text style={styles.weekTitle}>{week.label}</Text>
                        <Text style={styles.weekSeparator}>·</Text>
                        <Text style={styles.weekRange}>{week.range}</Text>
                      </View>
                    </Pressable>
                    <StateChip
                      beforeRoutineStart={beforeRoutineStart}
                      onPress={
                        !beforeRoutineStart &&
                        (week.state === 'make' || week.state === 'unread')
                          ? () =>
                              onOpenWeeklyReport?.(week.weekStart ?? week.id)
                          : undefined
                      }
                      state={week.state}
                      weekId={week.id}
                      weekLabel={week.label}
                    />
                    {beforeRoutineStart ? null : (
                      <ExpandCaret
                        expanded={expanded}
                        onPress={() =>
                          setExpandedWeek(expanded ? null : week.id)
                        }
                        weekId={week.id}
                      />
                    )}
                  </View>
                </View>
                <View style={styles.dayRow}>
                  {week.days.map((day, index) => {
                    const beforeRoutineStart =
                      routineStartLocalDate !== undefined &&
                      day.localDate !== undefined &&
                      day.localDate < routineStartLocalDate;
                    const canOpen =
                      expanded &&
                      !beforeRoutineStart &&
                      day.localDate !== undefined &&
                      (day.sessionIds?.length ?? 0) > 0;
                    const isToday =
                      !beforeRoutineStart &&
                      (day.isToday === true || day.status === 'today');
                    return (
                      <Pressable
                        key={`${week.id}-${day.day}`}
                        accessibilityLabel={
                          beforeRoutineStart
                            ? `${day.localDate} 루틴 시작 전 날짜`
                            : canOpen
                              ? `${day.localDate} 운동 기록 보기`
                              : undefined
                        }
                        accessibilityRole={
                          canOpen || beforeRoutineStart ? 'button' : undefined
                        }
                        accessibilityState={
                          canOpen ? undefined : { disabled: true }
                        }
                        disabled={!canOpen}
                        onPress={() => onOpenDay?.(day)}
                        style={[
                          styles.dayCell,
                          !day.inCurrentMonth && styles.dayCellOutsideMonth,
                          canOpen && styles.dayCellSelectable,
                          isToday && styles.dayCellToday,
                          beforeRoutineStart && styles.dayCellBeforeRoutine,
                        ]}
                        testID={`calendar-day-${week.id}-${index}`}
                      >
                        <Text
                          style={[
                            styles.dayNumber,
                            isToday && styles.dayNumberToday,
                            beforeRoutineStart && styles.dayNumberBeforeRoutine,
                          ]}
                          testID={`calendar-day-${week.id}-${index}-number`}
                        >
                          {day.day}
                        </Text>
                        <CalendarStatusMark
                          beforeRoutineStart={beforeRoutineStart}
                          status={day.status}
                          testID={`calendar-day-${week.id}-${index}-mark`}
                        />
                      </Pressable>
                    );
                  })}
                </View>

                {expanded ? (
                  <WeekDetail
                    note={week.note}
                    onOpenReport={() =>
                      onOpenWeeklyReport?.(week.weekStart ?? week.id)
                    }
                    state={week.state}
                    stats={week.stats}
                  />
                ) : null}
              </View>
            );
          })}
        </View>
      </ScrollView>
      <HomeBottomNavigation activeTab="report" onNavigate={onNavigateTab} />
    </SafeAreaView>
  );
}

function MonthArrow({
  direction,
  disabled = false,
  label,
  onPress,
}: {
  direction: 'previous' | 'next';
  disabled?: boolean;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      hitSlop={6}
      onPress={onPress}
      style={[styles.monthArrow, disabled && styles.monthArrowDisabled]}
    >
      <Svg aria-hidden fill="none" height={18} viewBox="0 0 24 24" width={18}>
        <Path
          d={
            direction === 'previous'
              ? 'M14.5 5.5l-7 6.5 7 6.5'
              : 'M9.5 5.5l7 6.5-7 6.5'
          }
          stroke="#6F6B63"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2.2}
        />
      </Svg>
    </Pressable>
  );
}

function MonthPicker({
  latestMonth,
  selectedMonth,
  onConfirm,
}: {
  latestMonth: string;
  selectedMonth: string;
  onConfirm: (month: string) => void;
}) {
  const [initialYear, initialMonth] = selectedMonth.split('-').map(Number);
  const [latestYear, latestMonthNumber] = latestMonth.split('-').map(Number);
  const [year, setYear] = useState(initialYear ?? latestYear ?? 0);
  const [month, setMonth] = useState(initialMonth ?? 1);
  const maximumYear = latestYear ?? year;
  const minimumYear = Math.min(maximumYear - 10, year);
  const years = Array.from(
    { length: maximumYear - minimumYear + 1 },
    (_, index) => minimumYear + index,
  );
  const maximumMonth = year === maximumYear ? (latestMonthNumber ?? 12) : 12;
  const months = Array.from({ length: maximumMonth }, (_, index) => index + 1);

  const selectYear = (nextYear: number) => {
    const nextMaximumMonth =
      nextYear === maximumYear ? (latestMonthNumber ?? 12) : 12;
    setYear(nextYear);
    if (month > nextMaximumMonth) {
      setMonth(nextMaximumMonth);
    }
  };

  return (
    <View accessibilityViewIsModal style={styles.picker} testID="month-picker">
      <View style={styles.pickerColumns}>
        <View
          pointerEvents="none"
          style={styles.pickerSelectionBand}
          testID="month-picker-selection-band"
        />
        <MonthPickerWheel
          accessibilityLabel="연도 선택 휠"
          selectedValue={year}
          suffix="년"
          testID="month-picker-year-wheel"
          values={years}
          onSelect={selectYear}
        />
        <MonthPickerWheel
          accessibilityLabel="월 선택 휠"
          selectedValue={Math.min(month, maximumMonth)}
          suffix="월"
          testID="month-picker-month-wheel"
          values={months}
          onSelect={setMonth}
        />
      </View>
      <Pressable
        accessibilityRole="button"
        onPress={() =>
          onConfirm(
            `${year}-${String(Math.min(month, maximumMonth)).padStart(2, '0')}`,
          )
        }
        style={styles.pickerDone}
      >
        <Text style={styles.pickerDoneText}>완료</Text>
      </Pressable>
    </View>
  );
}

function MonthPickerWheel({
  accessibilityLabel,
  selectedValue,
  suffix,
  testID,
  values,
  onSelect,
}: {
  accessibilityLabel: string;
  selectedValue: number;
  suffix: string;
  testID: string;
  values: readonly number[];
  onSelect: (value: number) => void;
}) {
  const wheelRef = useRef<ScrollView | null>(null);
  const initialScrollApplied = useRef(false);
  const webWheelDelta = useRef(0);
  const webWheelIndex = useRef(Math.max(0, values.indexOf(selectedValue)));
  const webWheelTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [initialContentOffset] = useState(() => ({
    x: 0,
    y: Math.max(0, values.indexOf(selectedValue)) * MONTH_PICKER_ITEM_HEIGHT,
  }));

  useEffect(() => {
    webWheelIndex.current = Math.max(0, values.indexOf(selectedValue));
  }, [selectedValue, values]);

  useEffect(() => {
    if (Platform.OS !== 'web' || wheelRef.current === null) return;

    const scrollNode = wheelRef.current.getScrollableNode() as HTMLElement;
    const handleWheel = (event: WheelEvent) => {
      if (event.deltaY === 0) return;

      event.preventDefault();
      const modeMultiplier =
        event.deltaMode === 1
          ? 16
          : event.deltaMode === 2
            ? MONTH_PICKER_ITEM_HEIGHT * 5
            : 1;
      const normalizedDelta = event.deltaY * modeMultiplier;
      if (
        webWheelDelta.current !== 0 &&
        Math.sign(webWheelDelta.current) !== Math.sign(normalizedDelta)
      ) {
        webWheelDelta.current = 0;
      }
      webWheelDelta.current += normalizedDelta;

      if (webWheelTimer.current !== null) {
        clearTimeout(webWheelTimer.current);
      }
      webWheelTimer.current = setTimeout(() => {
        const accumulatedDelta = webWheelDelta.current;
        webWheelDelta.current = 0;
        webWheelTimer.current = null;

        const itemDelta =
          Math.sign(accumulatedDelta) *
          Math.max(
            1,
            Math.round(Math.abs(accumulatedDelta) / WEB_WHEEL_DELTA_PER_ITEM),
          );
        const nextIndex = Math.max(
          0,
          Math.min(values.length - 1, webWheelIndex.current + itemDelta),
        );
        if (nextIndex === webWheelIndex.current) return;

        webWheelIndex.current = nextIndex;
        wheelRef.current?.scrollTo({
          animated: true,
          x: 0,
          y: nextIndex * MONTH_PICKER_ITEM_HEIGHT,
        });
        const nextValue = values[nextIndex];
        if (nextValue !== undefined) onSelect(nextValue);
      }, WEB_WHEEL_IDLE_MS);
    };

    scrollNode.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      scrollNode.removeEventListener('wheel', handleWheel);
      if (webWheelTimer.current !== null) {
        clearTimeout(webWheelTimer.current);
        webWheelTimer.current = null;
      }
    };
  }, [onSelect, values]);

  const applyInitialScroll = () => {
    if (initialScrollApplied.current || wheelRef.current === null) return;

    wheelRef.current.scrollTo({
      ...initialContentOffset,
      animated: false,
    });
    initialScrollApplied.current = true;
  };
  const selectFromScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const index = Math.max(
      0,
      Math.min(
        values.length - 1,
        Math.round(
          event.nativeEvent.contentOffset.y / MONTH_PICKER_ITEM_HEIGHT,
        ),
      ),
    );
    const value = values[index];
    if (value !== undefined && value !== selectedValue) onSelect(value);
  };

  return (
    <View style={styles.pickerColumn}>
      <ScrollView
        ref={wheelRef}
        accessibilityLabel={accessibilityLabel}
        contentContainerStyle={styles.pickerWheelContent}
        contentOffset={initialContentOffset}
        decelerationRate="fast"
        nestedScrollEnabled
        onContentSizeChange={applyInitialScroll}
        onMomentumScrollEnd={selectFromScroll}
        onScroll={selectFromScroll}
        onScrollEndDrag={selectFromScroll}
        scrollEventThrottle={16}
        showsVerticalScrollIndicator={false}
        snapToAlignment="start"
        snapToInterval={MONTH_PICKER_ITEM_HEIGHT}
        style={styles.pickerWheel}
        testID={testID}
      >
        {values.map((value) => (
          <View key={value} style={styles.pickerWheelRow}>
            <Text
              accessibilityState={{ selected: value === selectedValue }}
              style={
                value === selectedValue
                  ? styles.pickerSelected
                  : styles.pickerMuted
              }
              testID={`${testID}-value-${value}`}
            >
              {value}
              {suffix}
            </Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

function MonthStat({
  color,
  label,
  value,
}: {
  color: string;
  label: string;
  value: number;
}) {
  return (
    <View style={styles.monthStat}>
      <Text style={[styles.monthStatValue, { color }]}>{value}</Text>
      <Text style={styles.monthStatLabel}>{label}</Text>
    </View>
  );
}

function CalendarStatusMark({
  beforeRoutineStart = false,
  size = 20,
  status,
  testID,
}: {
  beforeRoutineStart?: boolean;
  size?: number;
  status: CalendarDayStatus;
  testID: string;
}) {
  const visual = CALENDAR_DAY_VISUALS[status];

  return (
    <View
      style={[
        styles.statusMark,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: beforeRoutineStart
            ? '#A9A49B'
            : visual.backgroundColor,
          borderColor: beforeRoutineStart ? '#8B8780' : visual.borderColor,
        },
      ]}
      testID={testID}
    >
      <Text
        style={[
          styles.statusMarkText,
          { color: visual.color, fontSize: size * 0.6, lineHeight: size * 0.6 },
        ]}
        testID={`${testID}-glyph`}
      >
        {beforeRoutineStart ? '' : visual.glyph}
      </Text>
    </View>
  );
}

/**
 * Shows whether a week card can be expanded, and whether it already is. The
 * week title next to it is the labelled toggle, so this caret stays out of the
 * accessibility tree instead of announcing the same action twice.
 */
function ExpandCaret({
  expanded,
  onPress,
  weekId,
}: {
  expanded: boolean;
  onPress: () => void;
  weekId: string;
}) {
  return (
    <Pressable
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      hitSlop={8}
      onPress={onPress}
      style={[styles.expandCaret, expanded && styles.expandCaretExpanded]}
      testID={`calendar-week-caret-${weekId}`}
    >
      <Svg aria-hidden fill="none" height={16} viewBox="0 0 24 24" width={16}>
        <Path
          d="M6 9.5l6 6 6-6"
          stroke="#6F6B63"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2.4}
        />
      </Svg>
    </Pressable>
  );
}

function StateChip({
  beforeRoutineStart = false,
  onPress,
  state,
  weekId,
  weekLabel,
}: {
  beforeRoutineStart?: boolean;
  onPress?: () => void;
  state: CalendarWeekState;
  weekId: string;
  weekLabel: string;
}) {
  const chip = CALENDAR_WEEK_CHIPS[state];
  const [shakeX] = useState(() => new Animated.Value(0));
  const [reduceMotionEnabled, setReduceMotionEnabled] = useState(true);

  useEffect(() => {
    if (state !== 'make') return undefined;

    let mounted = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((enabled) => {
      if (mounted && !enabled) setReduceMotionEnabled(false);
    });
    const subscription = AccessibilityInfo.addEventListener(
      'reduceMotionChanged',
      setReduceMotionEnabled,
    );

    return () => {
      mounted = false;
      subscription.remove();
    };
  }, [state]);

  useEffect(() => {
    shakeX.stopAnimation();
    shakeX.setValue(0);
    if (state !== 'make' || reduceMotionEnabled) return undefined;

    const animation = Animated.loop(
      Animated.sequence([
        Animated.delay(700),
        Animated.timing(shakeX, {
          toValue: -4,
          duration: 55,
          useNativeDriver: true,
        }),
        Animated.timing(shakeX, {
          toValue: 4,
          duration: 80,
          useNativeDriver: true,
        }),
        Animated.timing(shakeX, {
          toValue: -3,
          duration: 70,
          useNativeDriver: true,
        }),
        Animated.timing(shakeX, {
          toValue: 3,
          duration: 70,
          useNativeDriver: true,
        }),
        Animated.timing(shakeX, {
          toValue: 0,
          duration: 55,
          useNativeDriver: true,
        }),
        Animated.delay(2400),
      ]),
    );
    animation.start();

    return () => {
      animation.stop();
      shakeX.setValue(0);
    };
  }, [reduceMotionEnabled, shakeX, state]);

  const chipStyle: StyleProp<ViewStyle> = [
    styles.stateChip,
    {
      backgroundColor: beforeRoutineStart ? '#C9C5BC' : chip.backgroundColor,
      borderColor: beforeRoutineStart ? '#9A968E' : chip.borderColor,
      borderStyle: beforeRoutineStart ? 'solid' : chip.borderStyle,
    },
  ];
  const label = beforeRoutineStart ? '가입 전' : chip.label;
  const chipText = (
    <Text
      style={[
        styles.stateChipText,
        { color: beforeRoutineStart ? '#5F5B55' : chip.color },
      ]}
      testID={`calendar-chip-${weekId}-label`}
    >
      {label}
    </Text>
  );

  return (
    <Animated.View
      style={{ transform: [{ translateX: shakeX }] }}
      testID={`calendar-chip-${weekId}-motion`}
    >
      {onPress === undefined ? (
        <View style={chipStyle} testID={`calendar-chip-${weekId}`}>
          {chipText}
        </View>
      ) : (
        <Pressable
          accessibilityLabel={`${weekLabel} ${label}`}
          accessibilityRole="button"
          onPress={onPress}
          style={chipStyle}
          testID={`calendar-chip-${weekId}`}
        >
          {chipText}
        </Pressable>
      )}
    </Animated.View>
  );
}

function WeekDetail({
  note,
  onOpenReport,
  state,
  stats,
}: {
  note: string;
  onOpenReport: () => void;
  state: CalendarWeekState;
  stats: readonly number[];
}) {
  const canOpenReport =
    state === 'make' || state === 'unread' || state === 'read';
  const actionLabel =
    state === 'make' ? '주간 리포트 만들기' : '주간 리포트 보기';
  const doneLabel = CALENDAR_DAY_VISUALS.done.label;
  const partialLabel = CALENDAR_DAY_VISUALS.partial.label;

  return (
    <View style={styles.weekDetail}>
      <Text style={styles.weekDetailTitle}>
        {`${doneLabel} ${stats[0] ?? 0}회 / ${partialLabel} ${stats[1] ?? 0}회`}
      </Text>
      <View style={styles.weekStats}>
        {CALENDAR_STATUS_ORDER.map((status, index) => (
          <View
            key={status}
            style={styles.weekStat}
            testID={`calendar-week-stat-${status}`}
          >
            <Text style={styles.weekStatLabel}>
              {CALENDAR_DAY_VISUALS[status].label}
            </Text>
            <Text
              style={[
                styles.weekStatValue,
                { color: CALENDAR_DAY_VISUALS[status].accentColor },
              ]}
            >
              {stats[index] ?? 0}
            </Text>
          </View>
        ))}
      </View>
      <Text style={styles.weekNote}>{note}</Text>
      {canOpenReport ? (
        <GradientActionButton
          label={actionLabel}
          labelStyle={styles.weekActionLabel}
          onPress={onOpenReport}
          style={styles.weekAction}
          testID="calendar-week-report-action"
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: colors.canvas,
  },
  scroll: {
    flex: 1,
  },
  content: {
    paddingTop: CALENDAR_REPORT_LAYOUT.contentTopPadding,
    paddingHorizontal: CALENDAR_REPORT_LAYOUT.contentHorizontalPadding,
    paddingBottom: CALENDAR_REPORT_LAYOUT.contentBottomPadding,
  },
  monthCard: {
    zIndex: 100,
    overflow: 'visible',
    borderRadius: 22,
    padding: 14,
    shadowColor: '#5A4636',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 2,
  },
  monthHeader: {
    zIndex: 20,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    paddingHorizontal: 2,
    paddingBottom: 12,
  },
  monthTitleArea: {
    position: 'relative',
    minWidth: 0,
    flex: 1,
  },
  eyebrow: {
    color: colors.textMuted,
    fontSize: 12.5,
    fontWeight: '700',
  },
  monthPickerButton: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 1,
    paddingVertical: 4,
  },
  monthTitle: {
    color: colors.text,
    fontSize: 22,
    fontWeight: '800',
  },
  monthActions: {
    flexDirection: 'row',
    gap: 8,
  },
  monthArrow: {
    width: 38,
    height: 38,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#EAE5DA',
    borderRadius: 999,
    backgroundColor: '#F7F5EF',
  },
  monthArrowDisabled: {
    borderColor: '#F1EEE7',
    backgroundColor: '#FBFAF6',
    opacity: 0.4,
  },
  monthStats: {
    flexDirection: 'row',
    gap: 6,
    borderTopWidth: 1,
    borderTopColor: '#F0EDE5',
    paddingTop: 12,
  },
  monthStat: {
    minWidth: 0,
    flex: 1,
    alignItems: 'center',
    borderRadius: 14,
    backgroundColor: '#F7F5EF',
    paddingHorizontal: 4,
    paddingVertical: 12,
  },
  monthStatValue: {
    fontSize: 26,
    fontWeight: '800',
    lineHeight: 29,
  },
  monthStatLabel: {
    marginTop: 4,
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: '700',
  },
  picker: {
    position: 'absolute',
    zIndex: 1000,
    top: 58,
    left: -4,
    width: 286,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 20,
    backgroundColor: colors.surface,
    padding: 12,
    shadowColor: '#5A4636',
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.2,
    shadowRadius: 15,
    elevation: 24,
  },
  pickerColumns: {
    position: 'relative',
    height: MONTH_PICKER_ITEM_HEIGHT * 5,
    flexDirection: 'row',
    overflow: 'hidden',
    borderRadius: 14,
    backgroundColor: '#FBFBF8',
  },
  pickerSelectionBand: {
    position: 'absolute',
    top: MONTH_PICKER_ITEM_HEIGHT * 2,
    right: 0,
    left: 0,
    height: MONTH_PICKER_ITEM_HEIGHT,
    borderWidth: 1.5,
    borderColor: '#F1D39A',
    borderRadius: 10,
    backgroundColor: '#FFF8E5',
  },
  pickerColumn: {
    zIndex: 1,
    flex: 1,
    height: MONTH_PICKER_ITEM_HEIGHT * 5,
  },
  pickerWheel: {
    flex: 1,
  },
  pickerWheelContent: {
    paddingVertical: MONTH_PICKER_ITEM_HEIGHT * 2,
  },
  pickerWheelRow: {
    height: MONTH_PICKER_ITEM_HEIGHT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pickerMuted: {
    color: '#B7B2A8',
    fontSize: 16,
    fontWeight: '600',
    textAlign: 'center',
  },
  pickerSelected: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '800',
    textAlign: 'center',
  },
  pickerDone: {
    alignItems: 'center',
    marginTop: 10,
    borderRadius: 14,
    backgroundColor: '#F6BA50',
    padding: 13,
  },
  pickerDoneText: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '800',
  },
  weekdayRow: {
    flexDirection: 'row',
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 6,
  },
  weekday: {
    flex: 1,
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: '700',
    textAlign: 'center',
  },
  weekList: {
    gap: CALENDAR_REPORT_LAYOUT.weekGap,
  },
  weekBand: {
    borderWidth: 1.5,
    borderColor: 'transparent',
    borderRadius: 20,
    backgroundColor: '#FFF8E5',
    padding: 10,
  },
  weekBandCurrent: {
    borderColor: '#E7D3A8',
    backgroundColor: '#FFF9EA',
  },
  weekBandReportReady: {
    borderWidth: 2,
    borderColor: '#79B1D2',
    backgroundColor: '#F3F9FC',
    shadowColor: '#356A85',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.14,
    shadowRadius: 7,
    elevation: 3,
  },
  weekBandReportGenerated: {
    borderColor: '#C8D7AC',
    backgroundColor: '#F6F9EF',
  },
  weekBandUpcoming: {
    borderColor: '#DFDBD2',
    borderStyle: 'dashed',
    opacity: 0.5,
  },
  weekBandBeforeRoutine: {
    borderColor: '#A9A49B',
    borderStyle: 'solid',
    backgroundColor: '#D9D6CF',
    opacity: 1,
  },
  weekBandExpanded: {
    borderColor: '#E0A742',
  },
  weekHeader: {
    padding: 2,
  },
  weekHeadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  weekTitleGroup: {
    minWidth: 0,
    flex: 1,
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 5,
  },
  weekTitleButton: {
    minWidth: 0,
    flex: 1,
    paddingVertical: 4,
  },
  weekSeparator: {
    color: '#B7B2A8',
    fontSize: 11,
    fontWeight: '700',
  },
  expandCaret: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 20,
    height: 20,
  },
  expandCaretExpanded: {
    transform: [{ rotate: '180deg' }],
  },
  weekTitle: {
    color: colors.text,
    fontSize: 12.5,
    fontWeight: '800',
  },
  weekRange: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: '600',
  },
  stateChip: {
    borderWidth: 1.5,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  stateChipText: {
    fontSize: 11,
    fontWeight: '800',
  },
  dayRow: {
    flexDirection: 'row',
    marginTop: 8,
  },
  dayCell: {
    flex: 1,
    alignItems: 'center',
    gap: 4,
    borderWidth: 1.5,
    borderColor: 'transparent',
    paddingVertical: 4,
  },
  dayCellOutsideMonth: {
    opacity: 0.35,
  },
  dayCellSelectable: {
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,.62)',
  },
  dayCellToday: {
    borderWidth: 1.5,
    borderColor: '#E0A742',
    borderRadius: 12,
    backgroundColor: '#FFF3D6',
  },
  dayCellBeforeRoutine: {
    borderRadius: 12,
    backgroundColor: '#C9C5BC',
    opacity: 1,
  },
  dayNumber: {
    color: '#6F6B63',
    fontSize: 12,
    fontWeight: '600',
  },
  dayNumberToday: {
    color: '#A45F00',
    fontWeight: '800',
  },
  dayNumberBeforeRoutine: {
    color: '#5F5B55',
    fontWeight: '700',
  },
  statusMark: {
    width: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderRadius: 10,
  },
  statusMarkText: {
    fontSize: 12,
    fontWeight: '800',
    lineHeight: 12,
    textAlign: 'center',
  },
  weekDetail: {
    marginTop: 10,
    borderRadius: 14,
    backgroundColor: colors.surface,
    paddingHorizontal: 12,
    paddingTop: 10,
    paddingBottom: 12,
  },
  weekDetailTitle: {
    color: colors.textMuted,
    fontSize: 11.5,
    fontWeight: '700',
  },
  weekStats: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    columnGap: 8,
    rowGap: 6,
    marginTop: 8,
  },
  weekStat: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  weekStatValue: {
    fontSize: 13,
    fontWeight: '800',
  },
  weekStatLabel: {
    color: '#6F6B63',
    fontSize: 11,
    fontWeight: '600',
  },
  weekNote: {
    marginTop: 10,
    color: '#6F6B63',
    fontSize: 12,
    lineHeight: 18,
  },
  weekAction: {
    height: 46,
    marginTop: 12,
  },
  weekActionLabel: {
    fontSize: 14,
    fontWeight: '800',
  },
  legendRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    columnGap: 8,
    rowGap: 6,
    marginTop: 14,
    paddingHorizontal: 6,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  legendLabel: {
    color: '#6F6B63',
    fontSize: 11.5,
    fontWeight: '600',
  },
});
