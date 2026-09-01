import { StatusBar } from 'expo-status-bar';
import {
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { trainingTypeLabel } from '../../api/labels';
import type { RoutineResponse, WeekResponse } from '../../api/types';
import { colors } from '../../components/theme';
import { fontFamilies, useAuthFonts } from '../../app/fonts';
import type { TabId } from '../../components/brand/BrandChrome';
import { HomeBottomNavigation } from './HomeScreen';
import type { MapHomePreviewState } from './homeSecondaryModel';

const islandSource = require('../../assets/splash/splash-island.png') as number;

export const MAP_HOME_LAYOUT = {
  topPadding: 24,
  routineMaxHeight: 334,
} as const;

type MapHomeScreenProps = {
  onNavigateTab?: (tab: TabId) => void;
  onOpenCheckin?: () => void;
  onSelectRest?: () => void;
  onStartWorkout?: () => void;
  previewState?: MapHomePreviewState;
  routine?: RoutineResponse | null;
  week?: WeekResponse | null;
};

export function MapHomeScreen({
  onNavigateTab,
  onSelectRest,
  onStartWorkout,
  routine = null,
  week = null,
}: MapHomeScreenProps) {
  const fonts = useAuthFonts();
  const usePixelFont = fonts.loaded && !fonts.failed;
  const pixelStyle = usePixelFont ? styles.pixelFont : undefined;

  return (
    <SafeAreaView edges={['left', 'right']} style={styles.screen}>
      <StatusBar style="light" />
      <View style={styles.content}>
        <View style={styles.mapStage} testID="home-map-stage">
          <Image
            accessibilityLabel="운동 섬과 마스코트"
            resizeMode="contain"
            source={islandSource}
            style={styles.island}
          />
        </View>

        <RoutinePanel
          onSelectRest={onSelectRest}
          onStartWorkout={onStartWorkout}
          pixelStyle={pixelStyle}
          routine={routine}
          week={week}
        />
      </View>

      <HomeBottomNavigation activeTab="house" onNavigate={onNavigateTab} />
    </SafeAreaView>
  );
}

function RoutinePanel({
  onSelectRest,
  onStartWorkout,
  pixelStyle,
  routine,
  week,
}: {
  onSelectRest?: () => void;
  onStartWorkout?: () => void;
  pixelStyle?: object;
  routine: RoutineResponse | null;
  week: WeekResponse | null;
}) {
  const day = routine?.days[0];
  const weekCaption =
    week === null
      ? '주간 정보를 불러오지 못했어요. 잠시 후 다시 확인해 주세요.'
      : week.status_code === 'CLOSED'
        ? '마감된 주예요. 리포트를 확인할 수 있어요.'
        : '진행 중인 주예요. 편한 날에 하나씩 채워요.';

  return (
    <View style={styles.routinePanelPosition} testID="home-map-api-section">
      <View style={styles.routinePanel}>
        <View style={styles.routineHeader}>
          <View style={styles.weekSummary}>
            <Text style={[styles.weekEyebrow, pixelStyle]}>이번 주</Text>
            <Text
              accessibilityRole="header"
              style={[styles.routineHeading, pixelStyle]}
            >
              {week === null
                ? '목표를 확인할 수 없어요'
                : `목표 ${week.target_workout_count}회`}
            </Text>
          </View>
        </View>
        <Text style={[styles.weekCaption, pixelStyle]}>{weekCaption}</Text>

        <View style={styles.routineSection}>
          <Text style={[styles.routineTitle, pixelStyle]}>지금 내 루틴</Text>
          {day ? (
            <>
              <Text style={[styles.routineSummary, pixelStyle]}>
                {trainingTypeLabel(day.training_type_code)} ·{' '}
                {day.requested_duration_minutes}분 · 블록 {day.items.length}개
              </Text>
              <ScrollView
                contentContainerStyle={styles.routineItems}
                nestedScrollEnabled
                showsVerticalScrollIndicator
                style={styles.routineItemsViewport}
              >
                {day.items.map((item) => (
                  <View key={item.id} style={styles.routineItemRow}>
                    <Text style={[styles.routineItemName, pixelStyle]}>
                      {item.exercise_name}
                    </Text>
                    <Text style={[styles.routineItemMeta, pixelStyle]}>
                      {item.sets}세트
                      {item.reps === null
                        ? ` · ${item.work_seconds_per_set ?? 0}초`
                        : ` × ${item.reps}회`}
                    </Text>
                  </View>
                ))}
              </ScrollView>
            </>
          ) : (
            <Text style={[styles.emptyRoutineCopy, pixelStyle]}>
              아직 보여줄 루틴이 없어요. 홈에서 기본 루틴을 다시 불러와 주세요.
            </Text>
          )}
        </View>

        {day && onStartWorkout ? (
          <Pressable
            accessibilityRole="button"
            onPress={onStartWorkout}
            style={styles.startButton}
          >
            <Text style={[styles.startLabel, pixelStyle]}>
              이 루틴으로 시작하기
            </Text>
          </Pressable>
        ) : null}
        {onSelectRest ? (
          <Pressable
            accessibilityRole="button"
            onPress={onSelectRest}
            style={styles.restButton}
          >
            <Text style={[styles.restLabel, pixelStyle]}>오늘은 휴식하기</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: '#F7C65A',
  },
  content: {
    flex: 1,
    paddingTop: MAP_HOME_LAYOUT.topPadding,
  },
  pixelFont: {
    fontFamily: fontFamilies.loginHeading,
    fontWeight: '400',
  },
  mapStage: {
    flex: 1,
    minHeight: 190,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  island: {
    width: '118%',
    height: '100%',
  },
  routinePanelPosition: {
    maxHeight: MAP_HOME_LAYOUT.routineMaxHeight,
    paddingHorizontal: 16,
    paddingBottom: 12,
  },
  routinePanel: {
    borderWidth: 3,
    borderColor: '#FFFDF6',
    backgroundColor: '#FFF3D4',
    padding: 14,
    shadowColor: '#142010',
    shadowOffset: { width: 4, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 0,
    elevation: 5,
  },
  routineHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  weekSummary: {
    minWidth: 0,
    flex: 1,
    gap: 2,
  },
  weekEyebrow: {
    color: '#7A4E00',
    fontSize: 11,
    lineHeight: 16,
  },
  routineHeading: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 15,
    lineHeight: 20,
  },
  routineSummary: {
    marginTop: 4,
    color: '#7A4E00',
    fontSize: 14,
  },
  weekCaption: {
    marginTop: 7,
    color: colors.text,
    fontSize: 12.5,
    lineHeight: 19,
  },
  routineSection: {
    marginTop: 12,
    borderTopWidth: 2,
    borderTopColor: 'rgba(42,42,38,0.35)',
    borderStyle: 'dashed',
    paddingTop: 10,
  },
  routineTitle: {
    color: colors.text,
    fontSize: 14,
    lineHeight: 20,
  },
  routineItems: {
    gap: 6,
    paddingTop: 10,
    paddingBottom: 2,
  },
  routineItemsViewport: {
    maxHeight: 104,
  },
  routineItemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  routineItemName: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 12.5,
    lineHeight: 18,
  },
  routineItemMeta: {
    color: '#7A4E00',
    fontSize: 12,
    lineHeight: 18,
  },
  emptyRoutineCopy: {
    marginTop: 6,
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
  },
  startButton: {
    alignItems: 'center',
    marginTop: 14,
    borderWidth: 2,
    borderColor: colors.text,
    backgroundColor: colors.primary,
    padding: 11,
  },
  startLabel: {
    color: '#FFFDF6',
    fontSize: 14,
  },
  restButton: {
    alignItems: 'center',
    marginTop: 7,
    borderWidth: 2,
    borderColor: colors.text,
    backgroundColor: '#FFFDF6',
    padding: 9,
  },
  restLabel: {
    color: colors.textMuted,
    fontSize: 13,
  },
});
