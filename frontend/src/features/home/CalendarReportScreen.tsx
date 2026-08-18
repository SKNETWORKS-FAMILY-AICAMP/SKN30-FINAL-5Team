import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Card } from '../../components/primitives';
import { colors } from '../../components/theme';
import { HomeBottomNavigation } from './HomeScreen';
import {
  CALENDAR_DAY_VISUALS,
  CALENDAR_MONTH_STATS,
  CALENDAR_WEEK_CHIPS,
  CALENDAR_WEEKDAYS,
  CALENDAR_WEEKS,
  type CalendarDayStatus,
  type CalendarReportPreviewState,
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
  onNavigateTab?: (tab: 'home' | 'log' | 'report' | 'my') => void;
  onOpenWeeklyReport?: (weekId: string) => void;
  previewState?: CalendarReportPreviewState;
};

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
  onOpenWeeklyReport,
  previewState = 'calendar',
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
                <Text style={styles.monthTitle}>2026년 8월</Text>
                <Text style={styles.monthCaret}>⌄</Text>
              </Pressable>
              {pickerOpen ? (
                <MonthPicker onClose={() => setPickerOpen(false)} />
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
                label="다음 달"
                onPress={() => onChangeMonth?.('next')}
              />
            </View>
          </View>
          <View style={styles.monthStats}>
            {CALENDAR_MONTH_STATS.map((stat) => (
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
          {CALENDAR_WEEKS.map((week) => {
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
                  <View style={styles.dayRow}>
                    {week.days.map((day, index) => (
                      <View
                        key={`${week.id}-${day.day}`}
                        style={[
                          styles.dayCell,
                          !day.inCurrentMonth && styles.dayCellOutsideMonth,
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
                      </View>
                    ))}
                  </View>
                </Pressable>

                {expanded ? (
                  <WeekDetail
                    note={week.note}
                    onOpenReport={() => onOpenWeeklyReport?.(week.id)}
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
  label,
  onPress,
}: {
  direction: 'previous' | 'next';
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={styles.monthArrow}
    >
      <Text style={styles.monthArrowText}>
        {direction === 'previous' ? '‹' : '›'}
      </Text>
    </Pressable>
  );
}

function MonthPicker({ onClose }: { onClose: () => void }) {
  return (
    <View style={styles.picker}>
      <View style={styles.pickerColumns}>
        <View style={styles.pickerColumn}>
          <Text style={styles.pickerMuted}>2025년</Text>
          <Text style={styles.pickerSelected}>2026년</Text>
          <Text style={styles.pickerMuted}>2027년</Text>
        </View>
        <View style={styles.pickerColumn}>
          <Text style={styles.pickerMuted}>7월</Text>
          <Text style={styles.pickerSelected}>8월</Text>
          <Text style={styles.pickerMuted}>9월</Text>
        </View>
      </View>
      <Pressable
        accessibilityRole="button"
        onPress={onClose}
        style={styles.pickerDone}
      >
        <Text style={styles.pickerDoneText}>완료</Text>
      </Pressable>
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
  const disabled = state === 'upcoming';
  const actionLabel =
    state === 'progress'
      ? '진행 중 요약 보기'
      : state === 'upcoming'
        ? '예정된 주예요'
        : state === 'make'
          ? '주간 리포트 만들기'
          : '주간 리포트 보기';

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
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled }}
        disabled={disabled}
        onPress={onOpenReport}
        style={[
          styles.weekAction,
          state === 'progress' && styles.weekActionSecondary,
          state === 'make' && styles.weekActionMake,
          disabled && styles.weekActionDisabled,
        ]}
      >
        <Text
          style={[
            styles.weekActionText,
            state === 'progress' && styles.weekActionTextSecondary,
            state === 'make' && styles.weekActionTextMake,
            disabled && styles.weekActionTextDisabled,
          ]}
        >
          {actionLabel} ›
        </Text>
      </Pressable>
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
    zIndex: 30,
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
    elevation: 8,
  },
  pickerColumns: {
    flexDirection: 'row',
    overflow: 'hidden',
    borderRadius: 14,
    backgroundColor: '#FBFBF8',
  },
  pickerColumn: {
    flex: 1,
    alignItems: 'center',
    gap: 8,
    paddingVertical: 10,
  },
  pickerMuted: {
    color: '#B7B2A8',
    fontSize: 14,
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
