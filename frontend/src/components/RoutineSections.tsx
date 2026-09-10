import type { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { PlanPhaseCode } from '../api/types';

export const ROUTINE_PHASE_LABELS: Record<PlanPhaseCode, string> = {
  WARMUP: '웜업',
  MAIN: '메인 운동',
  COOLDOWN: '쿨다운',
};

/** Preserve the supplied execution order and original indexes for callbacks. */
export function RoutineSections<T>({
  items,
  getPhase,
  renderItem,
}: {
  items: readonly T[];
  getPhase: (item: T) => PlanPhaseCode | undefined;
  renderItem: (item: T, index: number) => ReactNode;
}) {
  const groups: {
    phase: PlanPhaseCode;
    entries: { item: T; index: number }[];
  }[] = [];
  items.forEach((item, index) => {
    const phase = getPhase(item) ?? 'MAIN';
    const previous = groups[groups.length - 1];
    if (previous?.phase === phase) previous.entries.push({ item, index });
    else groups.push({ phase, entries: [{ item, index }] });
  });

  return (
    <View style={styles.sections}>
      {groups.map(({ phase, entries }, groupIndex) => (
        <View
          key={`${phase}-${groupIndex}`}
          style={styles.section}
          testID={`routine-phase-${phase}`}
        >
          <Text accessibilityRole="header" style={styles.heading}>
            {ROUTINE_PHASE_LABELS[phase]}
          </Text>
          <View style={styles.items}>
            {entries.map(({ item, index }) => renderItem(item, index))}
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  sections: { gap: 10 },
  section: {
    borderRadius: 16,
    backgroundColor: 'rgba(149,132,118,0.055)',
    paddingHorizontal: 10,
    paddingVertical: 12,
    gap: 7,
  },
  heading: { color: '#958476', fontSize: 13, fontWeight: '700' },
  items: { gap: 6 },
});
