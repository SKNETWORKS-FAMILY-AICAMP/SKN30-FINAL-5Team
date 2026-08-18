/**
 * Tab bar glyphs drawn from Views.
 *
 * The bar previously used single characters (⌂ ⌁ ▥ ●), which render
 * inconsistently across platforms and read as placeholders. These are drawn
 * instead of adding an icon package, matching how the mascot is already built,
 * and they inherit a single colour so active and inactive states stay in step.
 */

import { StyleSheet, View } from 'react-native';

export type TabIconName = 'home' | 'house' | 'report' | 'profile';

const SIZE = 22;

export function TabIcon({ name, color }: { name: TabIconName; color: string }) {
  return (
    <View
      style={styles.frame}
      accessibilityElementsHidden
      importantForAccessibility="no"
    >
      {name === 'home' ? <HomeGlyph color={color} /> : null}
      {name === 'house' ? <HouseGlyph color={color} /> : null}
      {name === 'report' ? <ReportGlyph color={color} /> : null}
      {name === 'profile' ? <ProfileGlyph color={color} /> : null}
    </View>
  );
}

/** A roof triangle over a body, with a doorway punched out. */
function HomeGlyph({ color }: { color: string }) {
  return (
    <>
      <View style={[styles.roof, { borderBottomColor: color }]} />
      <View style={[styles.homeBody, { borderColor: color }]}>
        <View style={[styles.door, { backgroundColor: color }]} />
      </View>
    </>
  );
}

/** The mascot's face: a rounded head with two eyes and a smile. */
function HouseGlyph({ color }: { color: string }) {
  return (
    <View style={[styles.head, { borderColor: color }]}>
      <View style={styles.eyeRow}>
        <View style={[styles.eye, { backgroundColor: color }]} />
        <View style={[styles.eye, { backgroundColor: color }]} />
      </View>
      <View style={[styles.smile, { borderBottomColor: color }]} />
    </View>
  );
}

/** Three bars of increasing height. */
function ReportGlyph({ color }: { color: string }) {
  return (
    <View style={styles.bars}>
      <View style={[styles.bar, styles.barShort, { backgroundColor: color }]} />
      <View style={[styles.bar, styles.barTall, { backgroundColor: color }]} />
      <View style={[styles.bar, styles.barMid, { backgroundColor: color }]} />
    </View>
  );
}

/** A head over shoulders. */
function ProfileGlyph({ color }: { color: string }) {
  return (
    <>
      <View style={[styles.avatarHead, { backgroundColor: color }]} />
      <View style={[styles.shoulders, { borderColor: color }]} />
    </>
  );
}

const styles = StyleSheet.create({
  frame: {
    width: SIZE,
    height: SIZE,
    alignItems: 'center',
    justifyContent: 'center',
  },
  roof: {
    width: 0,
    height: 0,
    borderLeftWidth: 9,
    borderRightWidth: 9,
    borderBottomWidth: 8,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
  },
  homeBody: {
    width: 14,
    height: 9,
    alignItems: 'center',
    justifyContent: 'flex-end',
    borderWidth: 1.6,
    borderTopWidth: 0,
    borderBottomLeftRadius: 2,
    borderBottomRightRadius: 2,
  },
  door: {
    width: 4,
    height: 5,
    borderTopLeftRadius: 2,
    borderTopRightRadius: 2,
  },
  head: {
    width: 18,
    height: 18,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
    borderWidth: 1.6,
    borderRadius: 9,
  },
  eyeRow: {
    flexDirection: 'row',
    gap: 4,
  },
  eye: {
    width: 2.5,
    height: 2.5,
    borderRadius: 1.25,
  },
  smile: {
    width: 8,
    height: 4,
    borderBottomWidth: 1.6,
    borderBottomLeftRadius: 6,
    borderBottomRightRadius: 6,
  },
  bars: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 3,
    height: 16,
  },
  bar: {
    width: 4,
    borderRadius: 1.5,
  },
  barShort: {
    height: 7,
  },
  barMid: {
    height: 11,
  },
  barTall: {
    height: 16,
  },
  avatarHead: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  shoulders: {
    marginTop: 2,
    width: 16,
    height: 8,
    borderWidth: 1.6,
    borderBottomWidth: 0,
    borderTopLeftRadius: 8,
    borderTopRightRadius: 8,
  },
});
