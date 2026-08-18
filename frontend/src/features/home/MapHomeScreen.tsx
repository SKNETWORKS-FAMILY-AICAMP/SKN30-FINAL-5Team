import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors } from '../../components/theme';
import { fontFamilies, useAuthFonts } from '../../app/fonts';
import { HomeBottomNavigation } from './HomeScreen';
import type { MapHomePreviewState } from './homeSecondaryModel';

const islandSource = require('../../assets/splash/splash-island.png') as number;

export const MAP_HOME_LAYOUT = {
  topPadding: 54,
  headerHorizontalPadding: 16,
  routineTop: 153,
  markerSize: 28,
  strengthMarkerLeft: 247,
  strengthMarkerTop: 73,
  conditionLeft: 223,
  conditionTop: 137,
} as const;

type MapHomeScreenProps = {
  onNavigateTab?: (tab: 'home' | 'log' | 'report' | 'my') => void;
  onOpenCheckin?: () => void;
  onSelectRest?: () => void;
  onStartWorkout?: () => void;
  previewState?: MapHomePreviewState;
};

export function MapHomeScreen({
  previewState = 'map',
  ...props
}: MapHomeScreenProps) {
  return (
    <MapHomeScreenContent
      key={previewState}
      {...props}
      previewState={previewState}
    />
  );
}

function MapHomeScreenContent({
  onNavigateTab,
  onOpenCheckin,
  onSelectRest,
  onStartWorkout,
  previewState = 'map',
}: MapHomeScreenProps) {
  const fonts = useAuthFonts();
  const [state, setState] = useState<MapHomePreviewState>(previewState);
  const usePixelFont = fonts.loaded && !fonts.failed;
  const pixelStyle = usePixelFont ? styles.pixelFont : undefined;

  return (
    <SafeAreaView edges={['left', 'right']} style={styles.screen}>
      <StatusBar style="light" />
      <View style={styles.content}>
        <View style={styles.topRow}>
          <View style={styles.dialogue}>
            <Text
              accessibilityRole="header"
              style={[styles.dialogueText, pixelStyle]}
            >
              {state === 'routine'
                ? '! 를 눌러서 운동 루틴을 확인할 수 있어요.'
                : '오늘의 운동 섬이에요. 표시를 눌러 루틴을 확인해보세요.'}
            </Text>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="오늘 체크인"
            onPress={onOpenCheckin}
            style={styles.mailbox}
          >
            <Text style={styles.mailboxIcon}>▣</Text>
            <Text style={[styles.mailboxLabel, pixelStyle]}>체크인</Text>
          </Pressable>
        </View>

        <View style={styles.mapStage}>
          <Image
            accessibilityLabel="운동 섬과 마스코트"
            resizeMode="contain"
            source={islandSource}
            style={styles.island}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="근력 운동 위치"
            onPress={() => setState(state === 'routine' ? 'map' : 'routine')}
            style={styles.routineMarker}
          >
            <Text style={[styles.markerText, pixelStyle]}>!</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="컨디션 창 열기"
            onPress={() =>
              setState(state === 'condition' ? 'map' : 'condition')
            }
            style={styles.conditionMarker}
          >
            <Text style={styles.conditionArrow}>⌄</Text>
          </Pressable>

          {state === 'condition' ? (
            <ConditionPopover pixelStyle={pixelStyle} />
          ) : null}
        </View>

        {state === 'routine' ? (
          <RoutinePanel
            onClose={() => setState('map')}
            onSelectRest={onSelectRest}
            onStartWorkout={onStartWorkout}
            pixelStyle={pixelStyle}
          />
        ) : null}
      </View>

      <HomeBottomNavigation activeTab="log" onNavigate={onNavigateTab} />
    </SafeAreaView>
  );
}

function RoutinePanel({
  onClose,
  onSelectRest,
  onStartWorkout,
  pixelStyle,
}: {
  onClose: () => void;
  onSelectRest?: () => void;
  onStartWorkout?: () => void;
  pixelStyle?: object;
}) {
  const items = [
    '준비 운동',
    '푸시업 · 3세트 × 10회',
    '밴드 로우 · 3세트 × 12회',
    '숄더 프레스 · 2세트 × 10회',
    '마무리 스트레칭',
  ];

  return (
    <View style={styles.routinePanelPosition}>
      <View style={styles.routinePanel}>
        <View style={styles.routineHeader}>
          <Text style={[styles.routineHeading, pixelStyle]}>
            오늘의 운동 계획을 준비했어요
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="루틴 닫기"
            onPress={onClose}
            style={styles.collapseButton}
          >
            <Text style={[styles.collapseLabel, pixelStyle]}>접기</Text>
          </Pressable>
        </View>
        <Text style={[styles.routineSummary, pixelStyle]}>
          상체 근력 · 희망 운동 시간 40분
        </Text>
        <View style={styles.routineNotes}>
          <Text style={[styles.routineCopy, pixelStyle]}>
            오늘 컨디션과 운동 목표를 반영했어요.
          </Text>
          <Text style={[styles.routineCopy, pixelStyle]}>
            현재 장소와 장비로 진행할 수 있는 구성이에요.
          </Text>
        </View>
        <View style={styles.routineItems}>
          {items.map((item) => (
            <Text key={item} style={[styles.routineItem, pixelStyle]}>
              {item}
            </Text>
          ))}
        </View>
        <Pressable
          accessibilityRole="button"
          onPress={onStartWorkout}
          style={styles.startButton}
        >
          <Text style={[styles.startLabel, pixelStyle]}>
            이 루틴으로 시작하기
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={onSelectRest}
          style={styles.restButton}
        >
          <Text style={[styles.restLabel, pixelStyle]}>오늘은 휴식하기</Text>
        </Pressable>
      </View>
    </View>
  );
}

function ConditionPopover({ pixelStyle }: { pixelStyle?: object }) {
  return (
    <View style={styles.conditionPopover}>
      <View style={styles.conditionHeadingRow}>
        <Text style={[styles.conditionLabel, pixelStyle]}>컨디션</Text>
        <Text style={[styles.conditionValue, pixelStyle]}>보통</Text>
      </View>
      <View style={styles.conditionTrack}>
        <View style={styles.conditionFill} />
      </View>
      <ConditionRow label="피로도" value="보통" pixelStyle={pixelStyle} />
      <ConditionRow label="수면 시간" value="7시간" pixelStyle={pixelStyle} />
      <ConditionRow
        label="오늘 걸음 수"
        value="4,200"
        pixelStyle={pixelStyle}
      />
    </View>
  );
}

function ConditionRow({
  label,
  pixelStyle,
  value,
}: {
  label: string;
  pixelStyle?: object;
  value: string;
}) {
  return (
    <View style={styles.conditionRow}>
      <Text style={[styles.conditionLabel, pixelStyle]}>{label}</Text>
      <Text style={[styles.conditionValue, pixelStyle]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: '#6565C6',
  },
  content: {
    position: 'relative',
    flex: 1,
    paddingTop: MAP_HOME_LAYOUT.topPadding,
  },
  pixelFont: {
    fontFamily: fontFamilies.loginHeading,
    fontWeight: '400',
  },
  topRow: {
    zIndex: 4,
    flexDirection: 'row',
    alignItems: 'stretch',
    gap: 10,
    paddingTop: 10,
    paddingHorizontal: MAP_HOME_LAYOUT.headerHorizontalPadding,
  },
  dialogue: {
    minHeight: 64,
    flex: 1,
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: '#FFFDF6',
    backgroundColor: '#1C2A16',
    paddingHorizontal: 12,
    paddingVertical: 10,
    shadowColor: '#142010',
    shadowOffset: { width: 4, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 0,
    elevation: 4,
  },
  dialogueText: {
    color: '#FFFDF6',
    fontSize: 14,
    lineHeight: 22,
  },
  mailbox: {
    width: 76,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: colors.text,
    backgroundColor: '#FFFDF6',
    paddingVertical: 5,
    shadowColor: colors.text,
    shadowOffset: { width: 3, height: 3 },
    shadowOpacity: 0.35,
    shadowRadius: 0,
    elevation: 3,
  },
  mailboxIcon: {
    color: '#3E7A32',
    fontSize: 30,
    lineHeight: 34,
  },
  mailboxLabel: {
    color: colors.text,
    fontSize: 12,
  },
  mapStage: {
    position: 'relative',
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 26,
  },
  island: {
    width: '118%',
    height: 340,
  },
  routineMarker: {
    position: 'absolute',
    left: MAP_HOME_LAYOUT.strengthMarkerLeft,
    top: MAP_HOME_LAYOUT.strengthMarkerTop,
    width: MAP_HOME_LAYOUT.markerSize,
    height: MAP_HOME_LAYOUT.markerSize,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: colors.text,
    borderRadius: 2,
    backgroundColor: '#F2C927',
    shadowColor: colors.text,
    shadowOffset: { width: 2, height: 2 },
    shadowOpacity: 0.4,
    shadowRadius: 0,
    elevation: 3,
  },
  markerText: {
    color: colors.text,
    fontSize: 20,
    lineHeight: 22,
  },
  conditionMarker: {
    position: 'absolute',
    left: MAP_HOME_LAYOUT.conditionLeft,
    top: MAP_HOME_LAYOUT.conditionTop,
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.6)',
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.55)',
  },
  conditionArrow: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '800',
  },
  routinePanelPosition: {
    position: 'absolute',
    zIndex: 8,
    top: MAP_HOME_LAYOUT.routineTop,
    left: 16,
    right: 16,
  },
  routinePanel: {
    borderWidth: 3,
    borderColor: '#FFFDF6',
    backgroundColor: '#F2C927',
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
  routineHeading: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 15,
    lineHeight: 20,
  },
  collapseButton: {
    borderWidth: 2,
    borderColor: colors.text,
    backgroundColor: '#FFFDF6',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  collapseLabel: {
    color: colors.text,
    fontSize: 12,
  },
  routineSummary: {
    marginTop: 8,
    color: '#7A4E00',
    fontSize: 14,
  },
  routineNotes: {
    gap: 3,
    marginTop: 10,
  },
  routineCopy: {
    color: colors.text,
    fontSize: 12.5,
    lineHeight: 19,
  },
  routineItems: {
    gap: 5,
    marginTop: 12,
    borderTopWidth: 2,
    borderTopColor: 'rgba(42,42,38,0.35)',
    borderStyle: 'dashed',
    paddingTop: 10,
  },
  routineItem: {
    color: colors.text,
    fontSize: 12.5,
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
  conditionPopover: {
    position: 'absolute',
    zIndex: 6,
    top: MAP_HOME_LAYOUT.conditionTop + 32,
    left: MAP_HOME_LAYOUT.conditionLeft,
    width: 158,
    borderWidth: 2,
    borderColor: colors.text,
    backgroundColor: '#FFFDF6',
    padding: 14,
    shadowColor: colors.text,
    shadowOffset: { width: 3, height: 3 },
    shadowOpacity: 0.35,
    shadowRadius: 0,
    elevation: 4,
  },
  conditionHeadingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  conditionTrack: {
    height: 14,
    marginTop: 6,
    borderWidth: 2,
    borderColor: colors.text,
    backgroundColor: '#9A9490',
    padding: 1,
  },
  conditionFill: {
    width: '60%',
    height: '100%',
    backgroundColor: '#EA1E3C',
  },
  conditionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 10,
  },
  conditionLabel: {
    color: colors.text,
    fontSize: 11,
  },
  conditionValue: {
    color: colors.primary,
    fontSize: 11,
  },
});
