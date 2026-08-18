import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button, Card } from '../../components/primitives';
import { colors, spacing } from '../../components/theme';
import { fontFamilies, useBrandFonts } from '../../app/fonts';
import {
  HOME_CHECKIN_OPTIONS,
  HOME_ROUTINE_ITEMS,
  HOME_WEEK_DAYS,
  type HomePreviewState,
  type HomeRoutineItem,
} from './homeModel';

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

type CheckinKey = keyof typeof HOME_CHECKIN_OPTIONS;

type HomeScreenProps = {
  onEditRoutine?: () => void;
  onNavigateTab?: (tab: 'home' | 'log' | 'report' | 'my') => void;
  onOpenCheckin?: () => void;
  onRequestAlternative?: () => void;
  onSaveCheckin?: () => void;
  onSaveEdit?: (items: readonly HomeRoutineItem[]) => void;
  onStartWorkout?: () => void;
  previewState?: HomePreviewState;
};

export function HomeScreen({ previewState, ...props }: HomeScreenProps) {
  const initialState = previewState ?? 'pre-checkin';

  return (
    <HomeScreenContent
      key={initialState}
      {...props}
      initialState={initialState}
    />
  );
}

function HomeScreenContent({
  initialState,
  onEditRoutine,
  onNavigateTab,
  onOpenCheckin,
  onRequestAlternative,
  onSaveCheckin,
  onSaveEdit,
  onStartWorkout,
}: Omit<HomeScreenProps, 'previewState'> & {
  initialState: HomePreviewState;
}) {
  const brandFonts = useBrandFonts();
  const [screenState, setScreenState] =
    useState<HomePreviewState>(initialState);
  const [showWeeklyTip, setShowWeeklyTip] = useState(false);
  const [checkin, setCheckin] = useState({
    condition: '보통이에요',
    discomfort: '없음',
    fatigue: '보통이에요',
    sleep: '보통이에요',
  });
  const [minutes, setMinutes] = useState('40');
  const [steps, setSteps] = useState('');
  const [editItems, setEditItems] = useState<HomeRoutineItem[]>(() =>
    HOME_ROUTINE_ITEMS.map((item) => ({ ...item })),
  );
  const useJua = brandFonts.loaded && !brandFonts.failed;
  const showRoutine = ['routine', 'adjusted', 'editing'].includes(screenState);

  const openCheckin = () => {
    setScreenState('checkin');
    onOpenCheckin?.();
  };

  const saveCheckin = () => {
    setScreenState('generating');
    onSaveCheckin?.();
  };

  const openEdit = () => {
    setScreenState('editing');
    onEditRoutine?.();
  };

  const requestAlternative = () => {
    setScreenState('generating');
    onRequestAlternative?.();
  };

  const saveEdit = () => {
    setScreenState('routine');
    onSaveEdit?.(editItems);
  };

  const updateCheckin = (key: CheckinKey, value: string) => {
    setCheckin((current) => ({ ...current, [key]: value }));
  };

  return (
    <SafeAreaView edges={['left', 'right']} style={styles.screen}>
      <StatusBar style="light" />
      <View pointerEvents="none" style={styles.backgroundBands}>
        <View style={styles.backgroundGreen} />
        <View style={styles.backgroundMist} />
        <View style={styles.backgroundCanvas} />
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
      >
        <HomeHeader />
        <WeeklyRoutineCard />
        <WeeklyProgressCard
          showTip={showWeeklyTip}
          onToggleTip={() => setShowWeeklyTip((current) => !current)}
        />

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="오늘 루틴 체크인"
          onPress={openCheckin}
          style={({ pressed }) => [
            styles.checkinButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.checkinLabel, useJua && styles.juaLabel]}>
            오늘 루틴 체크인🍌
          </Text>
          <Text style={styles.checkinArrow}>›</Text>
        </Pressable>

        {screenState === 'pre-checkin' || screenState === 'checkin' ? (
          <EmptyRoutineCard />
        ) : null}

        {screenState === 'generating' ? <GeneratingRoutineCard /> : null}

        {showRoutine ? (
          <RoutineCard
            adjusted={screenState === 'adjusted'}
            items={editItems}
            onEdit={openEdit}
            onRequestAlternative={requestAlternative}
            onStart={onStartWorkout}
            useJua={useJua}
          />
        ) : null}
      </ScrollView>

      <HomeBottomNavigation activeTab="home" onNavigate={onNavigateTab} />

      {screenState === 'checkin' ? (
        <CheckinSheet
          checkin={checkin}
          minutes={minutes}
          onChange={updateCheckin}
          onChangeMinutes={setMinutes}
          onChangeSteps={setSteps}
          onClose={() => setScreenState('pre-checkin')}
          onSave={saveCheckin}
          steps={steps}
          useJua={useJua}
        />
      ) : null}

      {screenState === 'editing' ? (
        <EditRoutineSheet
          items={editItems}
          onChangeItems={setEditItems}
          onClose={() => setScreenState('routine')}
          onReset={() =>
            setEditItems(HOME_ROUTINE_ITEMS.map((item) => ({ ...item })))
          }
          onSave={saveEdit}
          useJua={useJua}
        />
      ) : null}
    </SafeAreaView>
  );
}

function HomeHeader() {
  return (
    <View style={styles.header}>
      <View style={styles.headerCopy}>
        <Text accessibilityRole="header" style={styles.greeting}>
          안녕하세요, <Text style={styles.greetingName}>헬끼님!</Text>
        </Text>
        <Text style={styles.date}>2026.08.11 (화)</Text>
      </View>
      <View style={styles.headerActions}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="알림 보기"
          style={styles.notificationButton}
        >
          <Text style={styles.notificationIcon}>♢</Text>
          <View accessibilityLabel="읽지 않은 알림 있음" style={styles.badge} />
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="프로필 열기"
          style={styles.profileButton}
        >
          <Text style={styles.profileMark}>헬</Text>
        </Pressable>
      </View>
    </View>
  );
}

function WeeklyRoutineCard() {
  return (
    <Card style={styles.summaryCard}>
      <Text style={styles.cardTitle}>
        이번 주 남은 루틴은 <Text style={styles.greenText}>2회</Text>예요
      </Text>
      <View style={styles.weekRow}>
        {HOME_WEEK_DAYS.map((day) => (
          <View key={day.label} style={styles.weekDay}>
            <View
              style={[
                styles.weekCircle,
                day.completed && styles.weekCircleCompleted,
              ]}
            >
              <Text
                style={[
                  styles.weekCircleText,
                  day.completed && styles.weekCircleTextCompleted,
                ]}
              >
                {day.completed ? '✓' : '·'}
              </Text>
            </View>
            <Text
              style={[
                styles.weekLabel,
                day.completed && styles.weekLabelCompleted,
              ]}
            >
              {day.label}
            </Text>
          </View>
        ))}
      </View>
    </Card>
  );
}

function WeeklyProgressCard({
  onToggleTip,
  showTip,
}: {
  onToggleTip: () => void;
  showTip: boolean;
}) {
  return (
    <Card style={styles.progressCard}>
      <View style={styles.progressHeader}>
        <View style={styles.progressTitleRow}>
          <Text style={styles.cardTitle}>주간 진행 현황</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="주간 진행 현황 설명 보기"
            onPress={onToggleTip}
            style={styles.iconTouch}
          >
            <Text style={styles.infoIcon}>ⓘ</Text>
          </Pressable>
        </View>
        <View style={styles.progressTitleRow}>
          <Text style={styles.weekRange}>8.11 ~ 8.17 (1주차)</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="월별·연별 기록 달력 보기"
            style={styles.iconTouch}
          >
            <Text style={styles.calendarIcon}>▦</Text>
          </Pressable>
        </View>
      </View>

      {showTip ? (
        <View accessibilityRole="summary" style={styles.tip}>
          <Text style={styles.tipText}>
            이번 주에 완료한 운동 횟수예요. 목표만큼 채우면 한 주가 마무리돼요.
          </Text>
        </View>
      ) : null}

      <View style={styles.countRow}>
        <Text style={styles.countLabel}>
          목표 <Text style={styles.countValue}>4</Text> 회
        </Text>
        <Text style={styles.countLabel}>
          완료 <Text style={styles.countValue}>2</Text> 회
        </Text>
      </View>
      <View style={styles.progressCells}>
        {[true, true, false, false].map((completed, index) => (
          <View
            key={`progress-${index}`}
            style={[
              styles.progressCell,
              completed && styles.progressCellCompleted,
            ]}
          >
            <Text style={styles.progressCellMark}>{completed ? '✓' : '•'}</Text>
          </View>
        ))}
      </View>
    </Card>
  );
}

function EmptyRoutineCard() {
  return (
    <Card style={styles.messageCard}>
      <Text style={styles.messageTitle}>아직 오늘의 운동이 없어요</Text>
      <Text style={styles.messageText}>
        오늘 체크인을 하면 컨디션에 맞는 추천 루틴을 받아볼 수 있어요.
      </Text>
    </Card>
  );
}

function GeneratingRoutineCard() {
  return (
    <Card style={styles.messageCard}>
      <ActivityIndicator color="#4E8B3A" size="small" />
      <Text style={[styles.messageTitle, styles.loadingTitle]}>
        새로운 루틴을 받고 있어요
      </Text>
      <Text style={styles.messageText}>
        요청한 운동 시간에 맞춰 다시 구성하는 중이에요.
      </Text>
    </Card>
  );
}

function RoutineCard({
  adjusted,
  items,
  onEdit,
  onRequestAlternative,
  onStart,
  useJua,
}: {
  adjusted: boolean;
  items: readonly HomeRoutineItem[];
  onEdit: () => void;
  onRequestAlternative: () => void;
  onStart?: () => void;
  useJua: boolean;
}) {
  return (
    <Card style={styles.routineCard}>
      <View style={styles.routineBadge}>
        <Text style={styles.routineBadgeText}>오늘의 운동</Text>
      </View>
      <Text style={styles.routineTitle}>
        {adjusted ? '컨디션 맞춤 루틴' : '상체 근력 루틴'}
      </Text>
      <Text style={styles.routineSummary}>
        {adjusted
          ? '상체 근력 · 희망 운동 시간 40분'
          : '상체 근력 · 희망 운동 시간 40분'}
      </Text>
      <View style={styles.routineNotes}>
        <Text style={styles.routineNote}>
          오늘 컨디션과 운동 목표를 반영했어요.
        </Text>
        <Text style={styles.routineNote}>
          현재 장소와 장비로 진행할 수 있는 구성이에요.
        </Text>
      </View>

      <View style={styles.routineList}>
        <Text style={styles.orderHint}>핸들을 끌어 순서를 바꿔보세요</Text>
        {items.map((item) => (
          <View key={item.id} style={styles.routineRow}>
            <Text accessibilityLabel="순서 변경 핸들" style={styles.dragMark}>
              ≡
            </Text>
            <Text style={styles.routineItemText}>
              {item.name}
              {item.prescription ? ` · ${item.prescription}` : ''}
            </Text>
            <View style={styles.routineDot} />
          </View>
        ))}
      </View>

      {adjusted ? (
        <View style={styles.adjustmentNote}>
          <Text style={styles.adjustmentText}>
            무릎 부담을 줄이도록 강도를 조정했어요.
          </Text>
        </View>
      ) : null}

      <Button
        label="운동 시작하기  ›"
        labelStyle={[styles.startLabel, useJua && styles.juaLabel]}
        onPress={onStart}
        style={styles.startButton}
      />
      <View style={styles.routineActions}>
        <Button
          label="✎  운동 수정하기"
          labelStyle={styles.routineActionLabel}
          onPress={onEdit}
          style={styles.routineAction}
          tone="secondary"
        />
        <Button
          label="↻  다른 루틴 · 2회 남음"
          labelStyle={styles.routineActionLabel}
          onPress={onRequestAlternative}
          style={styles.routineAction}
          tone="secondary"
        />
      </View>
    </Card>
  );
}

export function HomeBottomNavigation({
  activeTab,
  onNavigate,
}: {
  activeTab: 'home' | 'log' | 'report' | 'my';
  onNavigate?: (tab: 'home' | 'log' | 'report' | 'my') => void;
}) {
  const tabs = [
    { id: 'home', icon: '⌂', label: '홈' },
    { id: 'log', icon: '⌁', label: '끼끼의 집' },
    { id: 'report', icon: '▥', label: '리포트' },
    { id: 'my', icon: '●', label: '마이페이지' },
  ] as const;

  return (
    <View style={styles.bottomBarOuter}>
      <View accessibilityRole="tablist" style={styles.bottomBar}>
        {tabs.map((tab) => {
          const active = tab.id === activeTab;
          return (
            <Pressable
              key={tab.id}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={tab.label}
              onPress={() => onNavigate?.(tab.id)}
              style={styles.tab}
            >
              <Text style={[styles.tabIcon, active && styles.tabActive]}>
                {tab.icon}
              </Text>
              <Text style={[styles.tabLabel, active && styles.tabActive]}>
                {tab.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function SheetFrame({
  children,
  onClose,
  title,
}: {
  children: React.ReactNode;
  onClose: () => void;
  title: string;
}) {
  return (
    <View accessibilityViewIsModal style={styles.sheetOverlay}>
      <View style={styles.sheet}>
        <View style={styles.sheetHeader}>
          <Text accessibilityRole="header" style={styles.sheetTitle}>
            {title}
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="닫기"
            onPress={onClose}
            style={styles.closeButton}
          >
            <Text style={styles.closeText}>×</Text>
          </Pressable>
        </View>
        {children}
      </View>
    </View>
  );
}

function CheckinSheet({
  checkin,
  minutes,
  onChange,
  onChangeMinutes,
  onChangeSteps,
  onClose,
  onSave,
  steps,
  useJua,
}: {
  checkin: Record<CheckinKey, string>;
  minutes: string;
  onChange: (key: CheckinKey, value: string) => void;
  onChangeMinutes: (value: string) => void;
  onChangeSteps: (value: string) => void;
  onClose: () => void;
  onSave: () => void;
  steps: string;
  useJua: boolean;
}) {
  return (
    <SheetFrame onClose={onClose} title="오늘 컨디션 체크">
      <Text style={styles.sheetIntro}>
        오늘 상태를 알려주면 루틴을 맞춰 조정해드려요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.sheetScrollContent}
        showsVerticalScrollIndicator={false}
      >
        {(Object.keys(HOME_CHECKIN_OPTIONS) as CheckinKey[]).map((key) => (
          <View key={key} style={styles.checkinSection}>
            <Text style={styles.checkinSectionTitle}>
              {getCheckinLabel(key)}
            </Text>
            <View style={styles.choiceRow}>
              {HOME_CHECKIN_OPTIONS[key].map((option) => {
                const selected = checkin[key] === option;
                return (
                  <Pressable
                    key={option}
                    accessibilityRole="button"
                    accessibilityState={{ selected }}
                    onPress={() => onChange(key, option)}
                    style={[
                      styles.choiceButton,
                      selected && styles.choiceButtonSelected,
                    ]}
                  >
                    <Text
                      style={[
                        styles.choiceButtonText,
                        selected && styles.choiceButtonTextSelected,
                      ]}
                    >
                      {option}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        ))}

        <View style={styles.numberRow}>
          <Text style={styles.numberLabel}>원하는 운동 시간</Text>
          <View style={styles.numberInputGroup}>
            <TextInput
              accessibilityLabel="원하는 운동 시간 (분)"
              inputMode="numeric"
              onChangeText={onChangeMinutes}
              style={styles.numberInput}
              value={minutes}
            />
            <Text style={styles.numberSuffix}>분</Text>
          </View>
        </View>
        <View style={styles.numberRow}>
          <Text style={styles.numberLabel}>
            걸음 수 <Text style={styles.optionalText}>(선택)</Text>
          </Text>
          <TextInput
            accessibilityLabel="오늘 걸음 수"
            inputMode="numeric"
            onChangeText={onChangeSteps}
            placeholder="0"
            placeholderTextColor={colors.placeholder}
            style={[styles.numberInput, styles.stepsInput]}
            value={steps}
          />
        </View>
        <Pressable
          accessibilityRole="button"
          onPress={onSave}
          style={({ pressed }) => [
            styles.sheetSaveButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.sheetSaveLabel, useJua && styles.juaLabel]}>
            체크인 !
          </Text>
        </Pressable>
      </ScrollView>
    </SheetFrame>
  );
}

function EditRoutineSheet({
  items,
  onChangeItems,
  onClose,
  onReset,
  onSave,
  useJua,
}: {
  items: HomeRoutineItem[];
  onChangeItems: (items: HomeRoutineItem[]) => void;
  onClose: () => void;
  onReset: () => void;
  onSave: () => void;
  useJua: boolean;
}) {
  const updateName = (id: string, name: string) => {
    onChangeItems(
      items.map((item) => (item.id === id ? { ...item, name } : item)),
    );
  };

  return (
    <SheetFrame onClose={onClose} title="오늘의 운동 수정">
      <Text style={styles.sheetIntro}>
        항목을 직접 고치고 추천 순서로 되돌릴 수 있어요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.editList}
        showsVerticalScrollIndicator={false}
      >
        {items.map((item) => (
          <View key={item.id} style={styles.editRow}>
            <Text style={styles.editHandle}>≡</Text>
            <TextInput
              accessibilityLabel={`${item.name} 운동명`}
              onChangeText={(value) => updateName(item.id, value)}
              style={styles.editNameInput}
              value={item.name}
            />
            <Text style={styles.editPrescription}>
              {item.prescription ?? '시간 자유'}
            </Text>
          </View>
        ))}
        <View style={styles.editActions}>
          <Button
            label="추천으로 되돌리기"
            labelStyle={styles.resetLabel}
            onPress={onReset}
            style={styles.resetButton}
            tone="secondary"
          />
          <Pressable
            accessibilityRole="button"
            onPress={onSave}
            style={({ pressed }) => [
              styles.editSaveButton,
              pressed && styles.pressed,
            ]}
          >
            <Text style={[styles.sheetSaveLabel, useJua && styles.juaLabel]}>
              저장하기
            </Text>
          </Pressable>
        </View>
      </ScrollView>
    </SheetFrame>
  );
}

function getCheckinLabel(key: CheckinKey) {
  return {
    condition: '컨디션',
    discomfort: '통증 부위',
    fatigue: '피로도',
    sleep: '수면',
  }[key];
}

const cardShadow = {
  shadowColor: '#2F5233',
  shadowOffset: { width: 0, height: 6 },
  shadowOpacity: 0.1,
  shadowRadius: 9,
  elevation: 3,
} as const;

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: colors.canvas,
  },
  backgroundBands: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  backgroundGreen: {
    height: 245,
    backgroundColor: '#8ECB4E',
  },
  backgroundMist: {
    height: 250,
    backgroundColor: '#D8E6B4',
  },
  backgroundCanvas: {
    flex: 1,
    backgroundColor: colors.canvas,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    gap: HOME_LAYOUT.cardGap,
    paddingTop: HOME_LAYOUT.contentTopPadding,
    paddingHorizontal: HOME_LAYOUT.contentHorizontalPadding,
    paddingBottom: 118,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingHorizontal: HOME_LAYOUT.headerHorizontalPadding,
    paddingBottom: HOME_LAYOUT.headerBottomPadding - HOME_LAYOUT.cardGap,
  },
  headerCopy: {
    minWidth: 0,
    flex: 1,
  },
  greeting: {
    color: colors.surface,
    fontSize: 22,
    fontWeight: '800',
    lineHeight: 28,
  },
  greetingName: {
    color: '#FFD84D',
  },
  date: {
    marginTop: 6,
    color: '#F3FBE4',
    fontSize: 13,
    fontWeight: '600',
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  notificationButton: {
    position: 'relative',
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 14,
    backgroundColor: '#FBF6DF',
  },
  notificationIcon: {
    color: colors.text,
    fontSize: 24,
    lineHeight: 26,
  },
  badge: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 8,
    height: 8,
    borderWidth: 1.5,
    borderColor: '#FBF6DF',
    borderRadius: 4,
    backgroundColor: '#E65D42',
  },
  profileButton: {
    width: 48,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: colors.surface,
    borderRadius: 24,
    backgroundColor: '#FBD24E',
  },
  profileMark: {
    color: '#3E512D',
    fontSize: 16,
    fontWeight: '900',
  },
  summaryCard: {
    ...cardShadow,
    borderRadius: 22,
    padding: 16,
  },
  cardTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
  },
  greenText: {
    color: '#3E7A32',
  },
  weekRow: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 14,
  },
  weekDay: {
    minWidth: 0,
    flex: 1,
    alignItems: 'center',
    gap: 6,
  },
  weekCircle: {
    width: 30,
    height: 30,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 15,
    backgroundColor: '#F0EEE8',
  },
  weekCircleCompleted: {
    backgroundColor: '#4E8B3A',
  },
  weekCircleText: {
    color: '#B7B1A7',
    fontSize: 16,
    fontWeight: '800',
  },
  weekCircleTextCompleted: {
    color: colors.surface,
  },
  weekLabel: {
    color: '#9A968E',
    fontSize: 11,
    fontWeight: '600',
  },
  weekLabelCompleted: {
    color: '#3E7A32',
    fontWeight: '800',
  },
  progressCard: {
    ...cardShadow,
    borderRadius: 22,
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 18,
  },
  progressHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 6,
  },
  progressTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconTouch: {
    width: 34,
    height: 34,
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: -10,
  },
  infoIcon: {
    color: '#9A968E',
    fontSize: 16,
  },
  weekRange: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '600',
  },
  calendarIcon: {
    color: '#4E8B3A',
    fontSize: 18,
  },
  tip: {
    marginTop: 10,
    borderRadius: 12,
    backgroundColor: '#F1F6E7',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  tipText: {
    color: '#4A5B44',
    fontSize: 12.5,
    lineHeight: 19,
  },
  countRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
    marginTop: 14,
  },
  countLabel: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
  },
  countValue: {
    color: '#3E7A32',
    fontSize: 22,
  },
  progressCells: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
  progressCell: {
    height: 58,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: '#F0EEE8',
  },
  progressCellCompleted: {
    backgroundColor: '#E3EFCF',
  },
  progressCellMark: {
    color: '#4E8B3A',
    fontSize: 20,
    fontWeight: '800',
  },
  checkinButton: {
    minHeight: 58,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 18,
    backgroundColor: '#FBD24E',
    paddingHorizontal: 18,
    shadowColor: '#A87814',
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 1,
    shadowRadius: 0,
    elevation: 4,
  },
  checkinLabel: {
    flex: 1,
    color: '#342E17',
    fontSize: 21,
    fontWeight: '800',
    letterSpacing: 0.5,
    textAlign: 'center',
    paddingLeft: 22,
  },
  juaLabel: {
    fontFamily: fontFamilies.slogan,
    fontWeight: '400',
  },
  checkinArrow: {
    color: colors.text,
    fontSize: 28,
    lineHeight: 30,
  },
  pressed: {
    opacity: 0.84,
  },
  messageCard: {
    ...cardShadow,
    alignItems: 'center',
    borderRadius: 24,
    paddingHorizontal: 20,
    paddingVertical: 28,
  },
  messageTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '800',
    textAlign: 'center',
  },
  loadingTitle: {
    marginTop: 14,
  },
  messageText: {
    marginTop: 8,
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 20,
    textAlign: 'center',
  },
  routineCard: {
    ...cardShadow,
    borderRadius: 24,
    paddingHorizontal: 18,
    paddingTop: 18,
    paddingBottom: 8,
  },
  routineBadge: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#4E8B3A',
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  routineBadgeText: {
    color: colors.surface,
    fontSize: 12,
    fontWeight: '700',
  },
  routineTitle: {
    marginTop: 12,
    color: colors.text,
    fontSize: 26,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  routineSummary: {
    marginTop: 10,
    color: '#3E7A32',
    fontSize: 14,
    fontWeight: '700',
  },
  routineNotes: {
    gap: 4,
    marginTop: 10,
  },
  routineNote: {
    color: '#6F6B63',
    fontSize: 13.5,
    fontWeight: '500',
    lineHeight: 21,
  },
  routineList: {
    gap: 8,
    marginTop: 14,
    borderTopWidth: 1,
    borderTopColor: '#E2DED4',
    borderStyle: 'dashed',
    paddingTop: 12,
  },
  orderHint: {
    color: '#A29B8E',
    fontSize: 11.5,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
  routineRow: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 12,
    backgroundColor: '#FAF7F1',
    paddingHorizontal: 10,
  },
  dragMark: {
    width: 24,
    color: '#B4AEA2',
    fontSize: 20,
    textAlign: 'center',
  },
  routineItemText: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 13.5,
    fontWeight: '700',
    lineHeight: 20,
  },
  routineDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#4E8B3A',
  },
  adjustmentNote: {
    marginTop: 12,
    borderRadius: 12,
    backgroundColor: '#F1F6E7',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  adjustmentText: {
    color: '#4A5B44',
    fontSize: 12.5,
    lineHeight: 19,
  },
  startButton: {
    minHeight: 54,
    marginTop: 16,
    borderRadius: 16,
    backgroundColor: '#4E8B3A',
  },
  startLabel: {
    color: colors.surface,
    fontSize: 17,
  },
  routineActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
    marginBottom: 10,
  },
  routineAction: {
    minWidth: 0,
    minHeight: 48,
    flex: 1,
    borderColor: '#CBDDB4',
    borderRadius: 16,
    paddingHorizontal: 6,
  },
  routineActionLabel: {
    color: '#3E7A32',
    fontSize: 12.5,
  },
  bottomBarOuter: {
    flexShrink: 0,
    backgroundColor: colors.canvas,
    paddingTop: 8,
    paddingHorizontal: HOME_LAYOUT.bottomBarHorizontalPadding,
    paddingBottom: HOME_LAYOUT.bottomBarBottomPadding,
  },
  bottomBar: {
    minHeight: 68,
    flexDirection: 'row',
    borderRadius: 22,
    backgroundColor: colors.surface,
    paddingHorizontal: 6,
    paddingVertical: 10,
    shadowColor: '#2F5233',
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.07,
    shadowRadius: 7,
    elevation: 2,
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
  },
  tabIcon: {
    color: '#B0ACA4',
    fontSize: 22,
    fontWeight: '800',
  },
  tabLabel: {
    color: '#B0ACA4',
    fontSize: 10.5,
    fontWeight: '700',
    textAlign: 'center',
  },
  tabActive: {
    color: '#3E7A32',
  },
  sheetOverlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 30,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(20, 32, 16, 0.42)',
  },
  sheet: {
    maxHeight: '88%',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: colors.canvas,
    paddingTop: 20,
    paddingHorizontal: HOME_LAYOUT.sheetHorizontalPadding,
    paddingBottom: HOME_LAYOUT.sheetBottomPadding,
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  sheetTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '800',
  },
  closeButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: -10,
    marginRight: -12,
    marginBottom: -10,
  },
  closeText: {
    color: colors.textMuted,
    fontSize: 22,
  },
  sheetIntro: {
    marginTop: 4,
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 20,
  },
  sheetScrollContent: {
    gap: 10,
    paddingTop: 14,
  },
  checkinSection: {
    borderRadius: 18,
    backgroundColor: colors.surface,
    padding: 16,
  },
  checkinSectionTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  choiceRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 10,
  },
  choiceButton: {
    minHeight: 40,
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: colors.canvas,
    paddingHorizontal: 10,
  },
  choiceButtonSelected: {
    borderColor: '#4E8B3A',
    backgroundColor: '#4E8B3A',
  },
  choiceButtonText: {
    color: colors.text,
    fontSize: 12.5,
    fontWeight: '700',
  },
  choiceButtonTextSelected: {
    color: colors.surface,
  },
  numberRow: {
    minHeight: 68,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderRadius: 18,
    backgroundColor: colors.surface,
    padding: 16,
  },
  numberLabel: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  optionalText: {
    color: colors.textMuted,
    fontWeight: '500',
  },
  numberInputGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  numberInput: {
    width: 84,
    minHeight: 42,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: colors.canvas,
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
    paddingHorizontal: 12,
    textAlign: 'right',
  },
  stepsInput: {
    width: 110,
  },
  numberSuffix: {
    color: colors.textMuted,
    fontSize: 13,
  },
  sheetSaveButton: {
    minHeight: 56,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
    marginBottom: 5,
    borderRadius: 18,
    backgroundColor: '#FBD24E',
    shadowColor: '#E0AF25',
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 1,
    shadowRadius: 0,
    elevation: 3,
  },
  sheetSaveLabel: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '800',
  },
  editList: {
    gap: 8,
    paddingTop: 14,
  },
  editRow: {
    minHeight: 58,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    backgroundColor: colors.surface,
    paddingHorizontal: 10,
  },
  editHandle: {
    color: '#B4AEA2',
    fontSize: 20,
  },
  editNameInput: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 13.5,
    fontWeight: '700',
    paddingVertical: 8,
  },
  editPrescription: {
    maxWidth: 96,
    color: colors.textMuted,
    fontSize: 11.5,
    textAlign: 'right',
  },
  editActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
    paddingBottom: 5,
  },
  resetButton: {
    width: 112,
    minHeight: 54,
    borderRadius: 18,
    paddingHorizontal: 8,
  },
  resetLabel: {
    color: colors.textMuted,
    fontSize: 12.5,
  },
  editSaveButton: {
    minHeight: 54,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 18,
    backgroundColor: '#FBD24E',
  },
});
