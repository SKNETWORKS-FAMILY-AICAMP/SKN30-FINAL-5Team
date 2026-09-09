import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type GestureResponderEvent,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { decisionReasonLabel } from '../../api/labels';
import type { DecisionResponse } from '../../api/types';
import type { TabId } from '../../components/brand/BrandChrome';
import { getContainedInterfaceScale, useScale } from '../../components/scale';
import { HOME_BACKGROUND_COLOR, HOME_LAYOUT } from './homeConstants';
import { useHomeStyles } from './homeStyles';
import {
  HomeTabIcon,
  LogTabIcon,
  MyTabIcon,
  ReportTabIcon,
} from './HomeSupport';

type HomeTab = TabId;

const bottomNavigationShadow =
  Platform.select({
    ios: {
      shadowColor: '#5A4636',
      shadowOffset: { width: 0, height: -2 },
      shadowOpacity: 0.07,
      shadowRadius: 7,
    },
    android: { elevation: 2 },
    default: {
      shadowColor: '#5A4636',
      shadowOffset: { width: 0, height: -2 },
      shadowOpacity: 0.07,
      shadowRadius: 7,
    },
  }) ?? {};

const bottomNavigationStyles = StyleSheet.create({
  bottomBarOuter: {
    flexShrink: 0,
    backgroundColor: HOME_BACKGROUND_COLOR,
    paddingTop: 8,
    paddingHorizontal: HOME_LAYOUT.bottomBarHorizontalPadding,
    paddingBottom: HOME_LAYOUT.bottomBarBottomPadding,
  },
  bottomBar: {
    flexDirection: 'row',
    borderRadius: 22,
    backgroundColor: '#FFFFFF',
    paddingVertical: 10,
    paddingHorizontal: 6,
    ...bottomNavigationShadow,
  },
  tab: {
    minHeight: 48,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 6,
    paddingHorizontal: 2,
  },
  tabLabel: {
    color: '#B0ACA4',
    fontSize: 11.5,
    fontWeight: '700',
    textAlign: 'center',
  },
  tabActive: { color: '#A45F00' },
});

export function HomeBottomNavigation({
  activeTab,
  compact = false,
  onNavigate,
}: {
  activeTab: HomeTab;
  compact?: boolean;
  onNavigate?: (tab: HomeTab) => void;
}) {
  const insets = useSafeAreaInsets();
  const { height, width } = useScale();
  const controlScale = compact ? getContainedInterfaceScale(width, height) : 1;
  const scaled = (value: number) => value * controlScale;
  const homeColor = activeTab === 'home' ? '#A45F00' : '#B0ACA4';
  const logColor = activeTab === 'house' ? '#A45F00' : '#B0ACA4';
  const reportColor = activeTab === 'report' ? '#A45F00' : '#B0ACA4';
  const myColor = activeTab === 'my' ? '#A45F00' : '#B0ACA4';
  return (
    <View
      style={[
        bottomNavigationStyles.bottomBarOuter,
        {
          paddingTop: scaled(8),
          paddingHorizontal: scaled(HOME_LAYOUT.bottomBarHorizontalPadding),
          paddingBottom: bottomNavigationBottomPadding(
            insets.bottom,
            controlScale,
          ),
        },
      ]}
      testID="bottom-navigation"
    >
      <View
        accessibilityRole="tablist"
        style={[
          bottomNavigationStyles.bottomBar,
          {
            borderRadius: scaled(22),
            paddingVertical: scaled(10),
            paddingHorizontal: scaled(6),
          },
        ]}
        testID="bottom-navigation-tabs"
      >
        <TabButton
          active={activeTab === 'home'}
          controlScale={controlScale}
          icon={<HomeTabIcon color={homeColor} size={scaled(22)} />}
          label="홈"
          onPress={() => onNavigate?.('home')}
        />
        <TabButton
          active={activeTab === 'house'}
          controlScale={controlScale}
          icon={<LogTabIcon color={logColor} size={scaled(22)} />}
          label="끼끼의 집"
          onPress={() => onNavigate?.('house')}
        />
        <TabButton
          active={activeTab === 'report'}
          controlScale={controlScale}
          icon={<ReportTabIcon color={reportColor} size={scaled(22)} />}
          label="리포트"
          onPress={() => onNavigate?.('report')}
        />
        <TabButton
          active={activeTab === 'my'}
          controlScale={controlScale}
          icon={<MyTabIcon color={myColor} size={scaled(22)} />}
          label="마이페이지"
          onPress={() => onNavigate?.('my')}
        />
      </View>
    </View>
  );
}

export function bottomNavigationBottomPadding(
  safeAreaBottom: number,
  controlScale = 1,
) {
  return Math.max(
    HOME_LAYOUT.bottomBarBottomPadding * controlScale,
    safeAreaBottom,
  );
}

function TabButton({
  active,
  controlScale,
  icon,
  label,
  onPress,
}: {
  active: boolean;
  controlScale: number;
  icon: React.ReactNode;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="tab"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={[
        bottomNavigationStyles.tab,
        {
          minHeight: Math.max(44, 48 * controlScale),
          gap: 4 * controlScale,
          paddingVertical: 6 * controlScale,
          paddingHorizontal: 2 * controlScale,
        },
      ]}
    >
      {icon}
      <Text
        style={[
          bottomNavigationStyles.tabLabel,
          { fontSize: 11.5 * controlScale },
          active && bottomNavigationStyles.tabActive,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export function SheetFrame({
  children,
  compact = false,
  onClose,
  title,
  zIndex,
}: {
  children: React.ReactNode;
  compact?: boolean;
  onClose: () => void;
  title: string;
  zIndex: number;
}) {
  const styles = useHomeStyles();
  const stopPropagation = (event: GestureResponderEvent) =>
    event.stopPropagation();
  return (
    <Pressable
      accessibilityViewIsModal
      onPress={onClose}
      style={[styles.sheetOverlay, { zIndex }]}
    >
      <Pressable
        onPress={stopPropagation}
        style={[styles.sheet, compact && styles.checkinSheet]}
      >
        <View style={styles.sheetHeader}>
          <Text accessibilityRole="header" style={styles.sheetTitle}>
            {title}
          </Text>
          <Pressable
            accessibilityLabel="닫기"
            accessibilityRole="button"
            onPress={onClose}
            style={styles.closeButton}
          >
            <Text style={styles.closeText}>×</Text>
          </Pressable>
        </View>
        {children}
      </Pressable>
    </Pressable>
  );
}

/**
 * Reviewed posture guidance in a height-capped sheet.
 *
 * `SheetFrame` caps itself at 88% of the screen, so instruction content has to
 * scroll inside it the way the check-in and equipment sheets already do.
 * Rendering the guide directly in the frame left every cue below the fold
 * unreachable.
 */
export function ExerciseGuideSheet({
  children,
  onClose,
  title,
}: {
  children: React.ReactNode;
  onClose: () => void;
  title: string;
}) {
  const styles = useHomeStyles();
  return (
    <SheetFrame onClose={onClose} title={title} zIndex={25}>
      <ScrollView
        contentContainerStyle={styles.sheetScrollContent}
        showsVerticalScrollIndicator={false}
        testID="exercise-guide-scroll"
      >
        {children}
      </ScrollView>
    </SheetFrame>
  );
}

export function RecommendationReasonSheet({
  decision,
  onClose,
  reasons,
}: {
  decision: DecisionResponse;
  onClose: () => void;
  reasons: readonly string[];
}) {
  const styles = useHomeStyles();
  const codes = [
    ...new Set([
      ...decision.reason_codes,
      ...(decision.adjustment_reason_codes ?? []),
      ...(decision.safety_summary?.reason_codes ?? []),
    ]),
  ];
  const goalCodes = codes.filter((code) => /GOAL|TIME|DURATION/.test(code));
  const environmentCodes = codes.filter((code) =>
    /LOCATION|EQUIPMENT/.test(code),
  );
  const conditionCodes = codes.filter(
    (code) => !goalCodes.includes(code) && !environmentCodes.includes(code),
  );
  const describe = (selectedCodes: string[], fallback: string) => {
    const labels = [...new Set(selectedCodes.map(decisionReasonLabel))].filter(
      (label): label is string => label !== null && reasons.includes(label),
    );
    return labels.length > 0 ? labels.join(' ') : fallback;
  };
  const sections = [
    {
      title: '운동 목표',
      text: describe(goalCodes, '목표와 운동 가능 시간을 고려했어요.'),
    },
    {
      title: '컨디션',
      text: describe(
        conditionCodes,
        '체크인에서 알려주신 몸 상태를 고려했어요.',
      ),
    },
    {
      title: '운동 환경',
      text: describe(
        environmentCodes,
        '운동 장소와 사용할 수 있는 장비를 고려했어요.',
      ),
    },
  ];
  return (
    <SheetFrame onClose={onClose} title="이 루틴을 추천한 이유" zIndex={24}>
      <ScrollView
        contentContainerStyle={styles.reasonSheetContent}
        showsVerticalScrollIndicator={false}
      >
        {sections.map((section) => (
          <View key={section.title} style={styles.reasonSection}>
            <Text style={styles.checkinSectionTitle}>{section.title}</Text>
            <Text style={styles.reasonText}>{section.text}</Text>
          </View>
        ))}
      </ScrollView>
    </SheetFrame>
  );
}
