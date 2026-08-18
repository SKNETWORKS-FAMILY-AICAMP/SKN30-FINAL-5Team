/**
 * Shared brand chrome: the green background bands, the mascot stage and the
 * bottom tab bar.
 *
 * These mirror the visual language already established in HomeScreen and
 * WorkoutScreen so the API-backed screens read as the same product. The
 * originals are fixture-only components with no seam for live data, so the
 * presentation is reproduced here rather than imported from them.
 *
 * `MascotStage` takes a `serious` flag because pain and adverse-response
 * screens must drop the playful mark, copy and colour entirely.
 */

import type { ReactNode } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { imageAssets } from '../../assets';
import { fontFamilies, useBrandFonts } from '../../app/fonts';
import { colors, radii, shadows, spacing } from '../theme';
import { TabIcon, type TabIconName } from './TabIcon';

export type TabId = 'home' | 'house' | 'report' | 'my';

const TABS: readonly { id: TabId; icon: TabIconName; label: string }[] = [
  { id: 'home', icon: 'home', label: '홈' },
  { id: 'house', icon: 'house', label: '끼끼의 집' },
  { id: 'report', icon: 'report', label: '리포트' },
  { id: 'my', icon: 'profile', label: '마이페이지' },
];

/** Green-to-canvas bands behind the content, as on the existing home screen. */
export function BackgroundBands({ tall = false }: { tall?: boolean }) {
  return (
    <View pointerEvents="none" style={styles.bands}>
      <View style={[styles.bandGreen, tall && styles.bandGreenTall]} />
      <View style={styles.bandMist} />
      <View style={styles.bandCanvas} />
    </View>
  );
}

export function useBrandFontFamily(): string | undefined {
  const { loaded, failed } = useBrandFonts();
  // Fall back to the system face rather than blocking the screen; the layout
  // reserves the same space either way.
  return loaded && !failed ? fontFamilies.brand : undefined;
}

export function BrandTitle({
  children,
  style,
}: {
  children: ReactNode;
  style?: object;
}) {
  const family = useBrandFontFamily();
  return (
    <Text
      accessibilityRole="header"
      style={[styles.brandTitle, family ? { fontFamily: family } : null, style]}
    >
      {children}
    </Text>
  );
}

/** Mascot artwork available to the stage. Ignored when `serious`. */
export type MascotArt = 'progress' | 'complete';

const MASCOT_ART = {
  progress: imageAssets.progressMascot,
  complete: imageAssets.mascotComplete,
} as const;

export function MascotStage({
  eyebrow,
  title,
  caption,
  serious = false,
  art = 'progress',
}: {
  eyebrow: string;
  title: string;
  caption: string;
  /** Suppresses the mascot mark, playful face and colour for safety screens. */
  serious?: boolean;
  art?: MascotArt;
}) {
  const family = useBrandFontFamily();

  return (
    <View
      accessibilityLabel={serious ? '안전 안내 화면' : `${title} 안내`}
      style={[styles.mascotStage, serious && styles.mascotStageSerious]}
    >
      <View style={[styles.mascot, serious && styles.mascotSerious]}>
        {serious ? (
          // Safety screens drop the mascot entirely. A pain or adverse-response
          // notice must not carry a character illustration.
          <Text style={[styles.mascotMark, styles.mascotMarkSerious]}>!</Text>
        ) : (
          <Image
            source={MASCOT_ART[art]}
            style={styles.mascotImage}
            resizeMode="contain"
            accessibilityElementsHidden
            importantForAccessibility="no"
          />
        )}
      </View>
      <View style={styles.mascotCopy}>
        <Text style={[styles.mascotEyebrow, serious && styles.seriousText]}>
          {eyebrow}
        </Text>
        <Text
          style={[
            styles.mascotTitle,
            !serious && family ? { fontFamily: family } : null,
            serious && styles.seriousText,
          ]}
        >
          {title}
        </Text>
        <Text style={[styles.mascotCaption, serious && styles.seriousText]}>
          {caption}
        </Text>
      </View>
    </View>
  );
}

export function BottomTabBar({
  activeTab,
  onNavigate,
}: {
  activeTab: TabId;
  onNavigate: (tab: TabId) => void;
}) {
  return (
    <View style={styles.bottomBarOuter}>
      <View accessibilityRole="tablist" style={styles.bottomBar}>
        {TABS.map((tab) => {
          const active = tab.id === activeTab;
          return (
            <Pressable
              key={tab.id}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={tab.label}
              onPress={() => onNavigate(tab.id)}
              style={styles.tab}
            >
              <TabIcon
                name={tab.icon}
                color={active ? colors.primary : colors.textFaint}
              />
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

const styles = StyleSheet.create({
  bands: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  bandGreen: {
    height: 245,
    backgroundColor: colors.splashBackground,
  },
  bandGreenTall: {
    height: 320,
  },
  bandMist: {
    height: 250,
    backgroundColor: '#D8E6B4',
  },
  bandCanvas: {
    flex: 1,
    backgroundColor: colors.canvas,
  },
  brandTitle: {
    color: colors.surface,
    fontSize: 24,
    fontWeight: '700',
  },
  mascotStage: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
    borderRadius: radii.card,
    backgroundColor: colors.surface,
    padding: spacing.xl,
    ...shadows.card,
  },
  mascotStageSerious: {
    backgroundColor: colors.dangerBg,
  },
  mascot: {
    width: 64,
    height: 64,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 32,
    backgroundColor: colors.brandFill,
  },
  mascotSerious: {
    backgroundColor: colors.dangerSurface,
    borderWidth: 1.5,
    borderColor: colors.dangerBorder,
  },
  mascotImage: {
    width: 46,
    height: 46,
  },
  mascotMark: {
    color: colors.brandOutline,
    fontSize: 26,
    fontWeight: '700',
  },
  mascotMarkSerious: {
    color: colors.dangerText,
  },
  mascotCopy: {
    flex: 1,
    gap: 3,
  },
  mascotEyebrow: {
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '700',
  },
  mascotTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '700',
  },
  mascotCaption: {
    color: colors.textSub,
    fontSize: 12,
    lineHeight: 18,
  },
  seriousText: {
    color: colors.dangerText,
  },
  bottomBarOuter: {
    paddingHorizontal: 14,
    paddingBottom: 26,
    paddingTop: spacing.sm,
    backgroundColor: 'transparent',
  },
  bottomBar: {
    flexDirection: 'row',
    borderRadius: 20,
    backgroundColor: colors.surface,
    paddingVertical: 10,
    ...shadows.card,
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    gap: 2,
  },
  tabIcon: {
    color: colors.textFaint,
    fontSize: 17,
  },
  tabLabel: {
    color: colors.textFaint,
    fontSize: 11,
    fontWeight: '600',
  },
  tabActive: {
    color: colors.primary,
  },
});
