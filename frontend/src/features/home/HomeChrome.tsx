import { useState } from 'react';
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

import { agentTypeLabel } from '../../api/labels';
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
  onClose,
  title,
  zIndex,
}: {
  children: React.ReactNode;
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
      <Pressable onPress={stopPropagation} style={styles.sheet}>
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
  const agentSummaries = decision.public_agent_summaries ?? [];
  const perspectiveSummaries = agentSummaries.filter(
    (summary) => summary.agent_type_code !== 'COORDINATOR',
  );
  const coordinatorSummary = agentSummaries.find(
    (summary) => summary.agent_type_code === 'COORDINATOR',
  );
  const [criteriaExpanded, setCriteriaExpanded] = useState(false);
  return (
    <SheetFrame onClose={onClose} title="추천 이유" zIndex={24}>
      <Text style={styles.sheetIntro}>
        저장된 체크인과 안전 기준을 바탕으로 서버가 결정한 내용이에요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.reasonSheetContent}
        showsVerticalScrollIndicator={false}
      >
        {perspectiveSummaries.length > 0 ? (
          <View style={styles.reasonSection}>
            <Text style={styles.checkinSectionTitle}>에이전트별 판단</Text>
            {perspectiveSummaries.map((summary) => (
              <View
                key={`${summary.agent_type_code}-${summary.summary}`}
                style={styles.agentSummary}
              >
                <Text style={styles.agentSummaryLabel}>
                  {agentTypeLabel(summary.agent_type_code)}
                </Text>
                <Text style={styles.reasonText}>{summary.summary}</Text>
              </View>
            ))}
          </View>
        ) : null}

        {coordinatorSummary ? (
          <View style={styles.reasonSection}>
            <Text style={styles.checkinSectionTitle}>최종 조정 이유</Text>
            <Text style={styles.reasonText}>{coordinatorSummary.summary}</Text>
          </View>
        ) : null}

        {reasons.length > 0 ? (
          <View style={styles.reasonSection}>
            <Pressable
              accessibilityLabel={`반영한 기준 ${criteriaExpanded ? '접기' : '펼치기'}`}
              accessibilityRole="button"
              accessibilityState={{ expanded: criteriaExpanded }}
              onPress={() => setCriteriaExpanded((current) => !current)}
              style={styles.reasonDisclosureHeader}
            >
              <Text style={styles.checkinSectionTitle}>반영한 기준</Text>
              <Text style={styles.reasonDisclosureAction}>
                {criteriaExpanded ? '접기' : '펼치기'}
              </Text>
            </Pressable>
            {criteriaExpanded
              ? reasons.map((reason) => (
                  <View key={reason} style={styles.reasonRow}>
                    <Text style={styles.reasonBullet}>•</Text>
                    <Text style={styles.reasonText}>{reason}</Text>
                  </View>
                ))
              : null}
          </View>
        ) : null}
      </ScrollView>
    </SheetFrame>
  );
}
