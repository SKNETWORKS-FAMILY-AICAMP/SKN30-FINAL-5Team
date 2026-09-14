import Svg, { Circle, G, Path, Rect } from 'react-native-svg';

import { colors } from '../../components/theme';
import type { HomeRoutineItem } from './homeModel';

export function NotificationIcon() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 3.5a5.5 5.5 0 0 0-5.5 5.5v3.2L5 15.5h14l-1.5-3.3V9A5.5 5.5 0 0 0 12 3.5Z"
        stroke={colors.surface}
        strokeWidth={1.7}
        strokeLinejoin="round"
      />
      <Path
        d="M10 18.2a2 2 0 0 0 4 0"
        stroke={colors.surface}
        strokeWidth={1.7}
        strokeLinecap="round"
      />
    </Svg>
  );
}

export function InfoIcon() {
  return (
    <Svg width={16} height={16} viewBox="0 0 24 24" fill="none">
      <Circle cx={12} cy={12} r={9} stroke="#AA9A8D" strokeWidth={1.6} />
      <Path
        d="M12 10.6v6"
        stroke="#AA9A8D"
        strokeWidth={1.8}
        strokeLinecap="round"
      />
      <Circle cx={12} cy={7.6} r={1.1} fill="#AA9A8D" />
    </Svg>
  );
}

export function CalendarIcon() {
  return (
    <Svg width={18} height={18} viewBox="0 0 24 24" fill="none">
      <Rect
        x={3.5}
        y={5.5}
        width={17}
        height={15}
        rx={3.5}
        stroke="#F6BA50"
        strokeWidth={1.7}
      />
      <Path
        d="M3.5 10h17M8.5 3.5v4M15.5 3.5v4"
        stroke="#F6BA50"
        strokeWidth={1.7}
        strokeLinecap="round"
      />
      <Circle cx={8.5} cy={14} r={1.2} fill="#F6BA50" />
      <Circle cx={12.5} cy={14} r={1.2} fill="#F6BA50" />
    </Svg>
  );
}

export function CheckinChevronIcon() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path
        d="M9 5.5L16 12l-7 6.5"
        stroke="#5A4636"
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function RoutineDragIcon() {
  return (
    <Svg width={18} height={14} viewBox="0 0 18 14" fill="none">
      <G stroke="#B4AEA2" strokeWidth={2} strokeLinecap="round">
        <Path d="M2 3h14" />
        <Path d="M2 7h14" />
        <Path d="M2 11h14" />
      </G>
    </Svg>
  );
}

export function EditIcon() {
  return (
    <Svg width={16} height={16} viewBox="0 0 24 24" fill="none">
      <Path
        d="M4 16.5 15.5 5l3.5 3.5L7.5 20H4v-3.5Z"
        stroke="#A45F00"
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function RerollIcon({ color }: { color: string }) {
  return (
    <Svg width={16} height={16} viewBox="0 0 24 24" fill="none">
      <Path
        d="M20 11a8 8 0 1 0-.8 4.5"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
      />
      <Path
        d="M20 4.5V11h-6"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function RestIcon({
  color,
  size = 18,
  testID,
}: {
  color: string;
  size?: number;
  testID?: string;
}) {
  return (
    <Svg
      accessible={false}
      width={size}
      height={size}
      testID={testID}
      viewBox="0 0 24 24"
      fill="none"
    >
      <Path
        d="M18.4 15.1A7.7 7.7 0 0 1 8.9 5.6a8.2 8.2 0 1 0 9.5 9.5Z"
        stroke={color}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.8}
      />
      <Circle cx={17.6} cy={6.6} r={1.1} fill={color} />
    </Svg>
  );
}

export function HomeTabIcon({
  color,
  size = 22,
}: {
  color: string;
  size?: number;
}) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M4 11.2 12 4.5l8 6.7V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1v-7.8Z"
        fill={color}
      />
    </Svg>
  );
}

export function LogTabIcon({
  color,
  size = 22,
}: {
  color: string;
  size?: number;
}) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M3.5 10v4M20.5 10v4M7 7.5v9M17 7.5v9M7 12h10"
        stroke={color}
        strokeWidth={2.2}
        strokeLinecap="round"
      />
    </Svg>
  );
}

export function ReportTabIcon({
  color,
  size = 22,
}: {
  color: string;
  size?: number;
}) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Rect x={4} y={12} width={3.6} height={7} rx={1.6} fill={color} />
      <Rect x={10.2} y={6} width={3.6} height={13} rx={1.6} fill={color} />
      <Rect x={16.4} y={9.5} width={3.6} height={9.5} rx={1.6} fill={color} />
    </Svg>
  );
}

export function MyTabIcon({
  color,
  size = 22,
}: {
  color: string;
  size?: number;
}) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx={12} cy={8} r={3.8} fill={color} />
      <Path d="M5 20c0-3.6 3.1-5.6 7-5.6s7 2 7 5.6" fill={color} />
    </Svg>
  );
}

export function EditDragIcon() {
  return (
    <Svg width={14} height={12} viewBox="0 0 18 14" fill="none">
      <G stroke="#B4AEA2" strokeWidth={2} strokeLinecap="round">
        <Path d="M2 3h14" />
        <Path d="M2 7h14" />
        <Path d="M2 11h14" />
      </G>
    </Svg>
  );
}

export function DeleteIcon() {
  return (
    <Svg width={15} height={15} viewBox="0 0 24 24" fill="none">
      <Path
        d="M6 6l12 12M18 6L6 18"
        stroke="#B4AEA2"
        strokeWidth={2.2}
        strokeLinecap="round"
      />
    </Svg>
  );
}

export function digitsOnly(value: string | undefined) {
  return String(value ?? '').replace(/[^0-9]/g, '');
}

export function clampNumericString(value: string, min: number, max?: number) {
  const parsed = Number.parseInt(digitsOnly(value), 10);
  const safe = Number.isFinite(parsed) ? parsed : min;
  return String(Math.max(min, max === undefined ? safe : Math.min(max, safe)));
}

export function cleanRoutineItems(items: readonly HomeRoutineItem[]) {
  const cleaned: HomeRoutineItem[] = [];
  for (const item of items) {
    const name = item.name.trim();
    if (!name) {
      continue;
    }
    cleaned.push({
      ...item,
      name,
      sets: item.sets ? clampNumericString(item.sets, 1, 20) : '',
      reps: item.reps ? clampNumericString(item.reps, 1, 200) : '',
    });
  }
  return cleaned;
}

export function hasInvalidRoutinePrescription(
  items: readonly HomeRoutineItem[],
) {
  return items.some((item) => {
    const sets = Number(item.sets);
    const reps = item.reps === undefined ? null : Number(item.reps);
    const workSeconds =
      item.workSeconds === undefined ? null : Number(item.workSeconds);
    return (
      !Number.isInteger(sets) ||
      sets < 1 ||
      (reps !== null && (!Number.isInteger(reps) || reps < 1)) ||
      (workSeconds !== null &&
        (!Number.isInteger(workSeconds) || workSeconds < 1))
    );
  });
}

export function patchRoutinePrescription(
  items: readonly HomeRoutineItem[],
  id: string,
  patch: Pick<Partial<HomeRoutineItem>, 'sets' | 'reps' | 'workSeconds'>,
) {
  return items.map((item) => (item.id === id ? { ...item, ...patch } : item));
}
