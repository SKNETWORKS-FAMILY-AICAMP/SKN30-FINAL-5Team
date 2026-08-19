import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Card } from '../../components/primitives';
import { colors } from '../../components/theme';
import type { TabId } from '../../components/brand/BrandChrome';
import { HomeBottomNavigation } from './HomeScreen';
import {
  CALENDAR_DAY_VISUALS,
  CALENDAR_MONTH_STATS,
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
  onSelectMonth?: (month: string) => void;
};

const MONTH_PICKER_ITEM_HEIGHT = 44;

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
  onSelectMonth,
}: CalendarReportScreenProps) {
  const [expandedWeek, setExpandedWeek] = useState<string | null>(
    previewState === 'week-detail' ? 'week-2' : null,
  );
  const [pickerOpen, setPickerOpen] = useState(previewState === 'month-picker');

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
                onPress={() => setPickerOpen((current) => !current)}
                style={styles.monthPickerButton}
              >
                <Text style={styles.monthTitle}>{monthLabel}</Text>
                <Text style={styles.monthCaret}>⌄</Text>
              </Pressable>
              {pickerOpen ? (
                <MonthPicker
                  latestMonth={latestMonth}
                  selectedMonth={selectedMonth}
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
            return (
              <View
                key={week.id}
                style={[
                  styles.weekBand,
                  week.state === 'progress' && styles.weekBandCurrent,
                  week.state === 'upcoming' && styles.weekBandUpcoming,
                  expanded && styles.weekBandExpanded,
                  { backgroundColor: week.bandColor },
                ]}
              >
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`${week.label} ${CALENDAR_WEEK_CHIPS[week.state].label}, 요약 ${expanded ? '접기' : '펼치기'}`}
                  onPress={() => setExpandedWeek(expanded ? null : week.id)}
                  style={styles.weekHeader}
                >
                  <View style={styles.weekHeadingRow}>
                    <View style={styles.weekTitleGroup}>
                      <Text style={styles.weekTitle}>{week.label}</Text>
                      <Text style={styles.weekRange}>{week.range}</Text>
                    </View>
                    <StateChip state={week.state} weekId={week.id} />
                  </View>
                </Pressable>
                <View style={styles.dayRow}>
                  {week.days.map((day, index) => {
                    const canOpen =
                      expanded &&
                      day.localDate !== undefined &&
                      (day.sessionIds?.length ?? 0) > 0;
                    return (
                      <Pressable
                        key={`${week.id}-${day.day}`}
                        accessibilityLabel={
                          canOpen
                            ? `${day.localDate} 운동 기록 보기`
                            : undefined
                        }
                        accessibilityRole={canOpen ? 'button' : undefined}
                        accessibilityState={
                          canOpen ? undefined : { disabled: true }
                        }
                        disabled={!canOpen}
                        onPress={() => onOpenDay?.(day)}
                        style={[
                          styles.dayCell,
                          !day.inCurrentMonth && styles.dayCellOutsideMonth,
                          canOpen && styles.dayCellSelectable,
                        ]}
                      >
                        <Text
                          style={[
                            styles.dayNumber,
                            day.status === 'today' && styles.dayNumberToday,
                          ]}
                        >
                          {day.day}
                        </Text>
                        <CalendarStatusMark
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
                    title={`${week.label} · 완료 ${week.stats[0]}회 / 부분 ${week.stats[1]}회`}
                  />
                ) : null}
              </View>
            );
          })}
        </View>

        <View style={styles.legendCard}>
          <Text style={styles.legendTitle}>아이콘 안내</Text>
          <View style={styles.legendRow}>
            {(['done', 'partial', 'miss', 'rest'] as const).map((status) => (
              <View key={status} style={styles.legendItem}>
                <CalendarStatusMark
                  status={status}
                  testID={`calendar-legend-${status}`}
                />
                <Text style={styles.legendLabel}>
                  {CALENDAR_DAY_VISUALS[status].label}
                </Text>
              </View>
            ))}
          </View>
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
      onPress={onPress}
      style={[styles.monthArrow, disabled && styles.monthArrowDisabled]}
    >
      <Text style={styles.monthArrowText}>
        {direction === 'previous' ? '‹' : '›'}
      </Text>
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
        <MonthPickerWheel
          accessibilityLabel="연도 선택 휠"
          selectedValue={year}
          suffix="년"
          testID="month-picker-year-wheel"
          values={years}
          onSelect={selectYear}
        />
        <MonthPickerWheel
          key={`${year}-${maximumMonth}`}
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
  const selectedIndex = Math.max(0, values.indexOf(selectedValue));
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
        accessibilityLabel={accessibilityLabel}
        contentContainerStyle={styles.pickerWheelContent}
        contentOffset={{
          x: 0,
          y: selectedIndex * MONTH_PICKER_ITEM_HEIGHT,
        }}
        decelerationRate="fast"
        nestedScrollEnabled
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
              style={
                value === selectedValue
                  ? styles.pickerSelected
                  : styles.pickerMuted
              }
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
  status,
  testID,
}: {
  status: CalendarDayStatus;
  testID: string;
}) {
  const visual = CALENDAR_DAY_VISUALS[status];

  return (
    <View
      style={[
        styles.statusMark,
        {
          backgroundColor: visual.backgroundColor,
          borderColor: visual.borderColor,
        },
      ]}
      testID={testID}
    >
      <Text
        style={[styles.statusMarkText, { color: visual.color }]}
        testID={`${testID}-glyph`}
      >
        {visual.glyph}
      </Text>
    </View>
  );
}

function StateChip({
  state,
  weekId,
}: {
  state: CalendarWeekState;
  weekId: string;
}) {
  const chip = CALENDAR_WEEK_CHIPS[state];

  return (
    <View
      style={[
        styles.stateChip,
        {
          backgroundColor: chip.backgroundColor,
          borderColor: chip.borderColor,
          borderStyle: chip.borderStyle,
        },
      ]}
      testID={`calendar-chip-${weekId}`}
    >
      <Text
        style={[styles.stateChipText, { color: chip.color }]}
        testID={`calendar-chip-${weekId}-label`}
      >
        {chip.label}
      </Text>
    </View>
  );
}

function WeekDetail({
  note,
  onOpenReport,
  state,
  stats,
  title,
}: {
  note: string;
  onOpenReport: () => void;
  state: CalendarWeekState;
  stats: readonly number[];
  title: string;
}) {
  const labels = ['완료', '부분', '휴식', '미수행'];
  const canOpenReport =
    state === 'make' || state === 'unread' || state === 'read';
  const actionLabel =
    state === 'make' ? '주간 리포트 만들기' : '주간 리포트 보기';

  return (
    <View style={styles.weekDetail}>
      <Text style={styles.weekDetailTitle}>{title}</Text>
      <View style={styles.weekStats}>
        {stats.map((value, index) => (
          <View key={labels[index]} style={styles.weekStat}>
            <Text style={styles.weekStatValue}>{value}</Text>
            <Text style={styles.weekStatLabel}>{labels[index]}</Text>
          </View>
        ))}
      </View>
      <Text style={styles.weekNote}>{note}</Text>
      {canOpenReport ? (
        <Pressable
          accessibilityRole="button"
          onPress={onOpenReport}
          style={[styles.weekAction, state === 'make' && styles.weekActionMake]}
        >
          <Text
            style={[
              styles.weekActionText,
              state === 'make' && styles.weekActionTextMake,
            ]}
          >
            {actionLabel} ›
          </Text>
        </Pressable>
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
    shadowColor: '#2F5233',
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
  monthCaret: {
    color: '#4E8B3A',
    fontSize: 18,
    fontWeight: '800',
  },
  monthActions: {
    flexDirection: 'row',
  },
  monthArrow: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  monthArrowDisabled: {
    opacity: 0.28,
  },
  monthArrowText: {
    color: '#6F6B63',
    fontSize: 30,
    lineHeight: 32,
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
    paddingVertical: 10,
  },
  monthStatValue: {
    fontSize: 20,
    fontWeight: '800',
    lineHeight: 22,
  },
  monthStatLabel: {
    marginTop: 3,
    color: colors.textMuted,
    fontSize: 10.5,
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
    shadowColor: '#2F5233',
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.2,
    shadowRadius: 15,
    elevation: 24,
  },
  pickerColumns: {
    height: MONTH_PICKER_ITEM_HEIGHT * 3,
    flexDirection: 'row',
    overflow: 'hidden',
    borderRadius: 14,
    backgroundColor: '#FBFBF8',
  },
  pickerColumn: {
    flex: 1,
    height: MONTH_PICKER_ITEM_HEIGHT * 3,
  },
  pickerWheel: {
    flex: 1,
  },
  pickerWheelContent: {
    paddingVertical: MONTH_PICKER_ITEM_HEIGHT,
  },
  pickerWheelRow: {
    height: MONTH_PICKER_ITEM_HEIGHT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pickerMuted: {
    color: '#B7B2A8',
    fontSize: 14,
    textAlign: 'center',
  },
  pickerSelected: {
    width: '90%',
    borderWidth: 1.5,
    borderColor: '#CBDDB4',
    borderRadius: 10,
    backgroundColor: '#EFF4E6',
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
    paddingVertical: 10,
    textAlign: 'center',
  },
  pickerDone: {
    alignItems: 'center',
    marginTop: 10,
    borderRadius: 14,
    backgroundColor: '#FBD24E',
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
    paddingTop: 14,
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
    backgroundColor: '#EFF4E6',
    padding: 10,
  },
  weekBandCurrent: {
    borderColor: '#7FAE5C',
    backgroundColor: '#DCEBC4',
  },
  weekBandUpcoming: {
    borderColor: '#DFDBD2',
    borderStyle: 'dashed',
    opacity: 0.5,
  },
  weekBandExpanded: {
    borderColor: '#7FAE5C',
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
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 6,
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
    paddingVertical: 4,
  },
  dayCellOutsideMonth: {
    opacity: 0.35,
  },
  dayCellSelectable: {
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,.62)',
  },
  dayNumber: {
    color: '#6F6B63',
    fontSize: 12,
    fontWeight: '600',
  },
  dayNumberToday: {
    color: colors.text,
    fontWeight: '800',
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
  },
  weekDetail: {
    marginTop: 10,
    borderRadius: 14,
    backgroundColor: colors.surface,
    paddingHorizontal: 12,
    paddingTop: 12,
    paddingBottom: 14,
  },
  weekDetailTitle: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '800',
  },
  weekStats: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 10,
  },
  weekStat: {
    minWidth: 0,
    flex: 1,
    alignItems: 'center',
    borderRadius: 11,
    backgroundColor: '#F7F5EF',
    paddingHorizontal: 4,
    paddingVertical: 8,
  },
  weekStatValue: {
    color: '#3E7A32',
    fontSize: 15,
    fontWeight: '800',
  },
  weekStatLabel: {
    marginTop: 2,
    color: colors.textMuted,
    fontSize: 10.5,
    fontWeight: '700',
  },
  weekNote: {
    marginTop: 10,
    color: '#6F6B63',
    fontSize: 12.5,
    lineHeight: 19,
  },
  weekAction: {
    alignItems: 'center',
    marginTop: 12,
    borderRadius: 14,
    backgroundColor: '#4E8B3A',
    padding: 14,
  },
  weekActionSecondary: {
    borderWidth: 1.5,
    borderColor: '#CBDDB4',
    backgroundColor: colors.surface,
  },
  weekActionMake: {
    borderBottomWidth: 4,
    borderBottomColor: '#E0AF25',
    backgroundColor: '#FBD24E',
  },
  weekActionDisabled: {
    borderWidth: 1.5,
    borderColor: '#DFDBD2',
    borderStyle: 'dashed',
    backgroundColor: colors.surface,
  },
  weekActionText: {
    color: colors.surface,
    fontSize: 14,
    fontWeight: '800',
  },
  weekActionTextSecondary: {
    color: '#3E7A32',
  },
  weekActionTextMake: {
    color: colors.text,
  },
  weekActionTextDisabled: {
    color: '#B7B2A8',
  },
  legendCard: {
    marginTop: 14,
    borderRadius: 16,
    backgroundColor: colors.surface,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  legendTitle: {
    color: colors.textMuted,
    fontSize: 11.5,
    fontWeight: '800',
  },
  legendRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 14,
    marginTop: 9,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  legendLabel: {
    color: '#6F6B63',
    fontSize: 11.5,
    fontWeight: '600',
  },
});
