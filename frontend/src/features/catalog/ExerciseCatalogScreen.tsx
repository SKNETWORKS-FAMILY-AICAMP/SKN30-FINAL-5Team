/**
 * Reviewed exercise catalog browser.
 *
 * Everything shown here comes from the server's approved catalog list; this
 * screen never invents exercises, difficulty, or safety attributes, and it
 * plays no part in routine decisions — it is presentation only.
 */

import { useCallback, useState } from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import type { Api } from '../../api/endpoints';
import {
  bodyAreaLabel,
  bodyFocusLabel,
  equipmentLabel,
  experienceLevelLabel,
  trainingTypeLabel,
} from '../../api/labels';
import type { ExerciseListItem, ExerciseListResponse } from '../../api/types';
import { useAsyncData } from '../../api/useAsync';
import { Button, Card } from '../../components/primitives';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, radii, spacing } from '../../components/theme';
import {
  ExerciseDetailSheet,
  type ExerciseGuideContext,
} from '../workout/ExerciseDetailSheet';

const BODY_FOCUS_FILTER_CODES = [
  'CHEST',
  'BACK',
  'SHOULDERS',
  'BICEPS',
  'TRICEPS',
  'FOREARMS',
  'GLUTES',
  'QUADRICEPS',
  'HAMSTRINGS',
  'CALVES',
  'ADDUCTORS',
  'CORE',
  'FULL_BODY',
  'CARDIO',
  'MOBILITY',
] as const;

const BODY_FOCUS_FILTERS = [
  { code: undefined, label: '전체' },
  ...BODY_FOCUS_FILTER_CODES.map((code) => ({
    code,
    label: bodyFocusLabel(code),
  })),
] as const;

const difficultyLabel = (code: string) => experienceLevelLabel(code);

export function ExerciseCatalogScreen({
  api,
  exerciseGuideContext,
  onBack,
}: {
  api: Pick<Api, 'listExercises' | 'getExercise'>;
  exerciseGuideContext?: ExerciseGuideContext;
  onBack: () => void;
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [bodyFocus, setBodyFocus] = useState<string | undefined>();
  const [openExercise, setOpenExercise] = useState<ExerciseListItem | null>(
    null,
  );

  const { state, reload } = useAsyncData<ExerciseListResponse>(
    (signal) => loadEntireCatalog(api, signal),
    [api],
  );

  const selectBodyFocus = useCallback((code: string | undefined) => {
    setBodyFocus(code);
  }, []);

  return (
    <>
      <ScreenShell scroll={false} contentStyle={styles.screenContent}>
        <CatalogHeader onBack={onBack} />

        <View style={styles.catalogControls}>
          <View style={styles.searchField}>
            <View
              accessibilityElementsHidden
              importantForAccessibility="no"
              style={styles.searchIcon}
            >
              <View style={styles.searchIconCircle} />
              <View style={styles.searchIconHandle} />
            </View>
            <TextInput
              accessibilityLabel="운동명 검색"
              autoCapitalize="none"
              autoCorrect={false}
              onChangeText={setSearchQuery}
              placeholder="운동명으로 검색"
              placeholderTextColor={colors.textMuted}
              returnKeyType="search"
              style={styles.searchInput}
              value={searchQuery}
            />
            {searchQuery.length > 0 ? (
              <Pressable
                accessibilityLabel="검색어 지우기"
                accessibilityRole="button"
                hitSlop={8}
                onPress={() => setSearchQuery('')}
                style={styles.searchClearButton}
              >
                <Text style={styles.searchClearText}>×</Text>
              </Pressable>
            ) : null}
          </View>
          <FilterRow
            groupLabel="운동 부위"
            options={BODY_FOCUS_FILTERS}
            selected={bodyFocus}
            onSelect={selectBodyFocus}
          />
        </View>

        {state.status === 'loading' ? (
          <LoadingState label="운동 목록을 불러오는 중이에요" />
        ) : state.status === 'error' ? (
          <ErrorState message={state.message} onRetry={reload} />
        ) : (
          <CatalogList
            items={filterCatalogItems(state.data.items, searchQuery, bodyFocus)}
            searchActive={searchQuery.trim().length > 0}
            onOpen={setOpenExercise}
          />
        )}
      </ScreenShell>

      {openExercise !== null ? (
        <Modal
          animationType="none"
          onRequestClose={() => setOpenExercise(null)}
          presentationStyle="fullScreen"
          testID="exercise-catalog-detail-modal"
          visible
        >
          <ScreenShell>
            <ScreenHeading title={openExercise.name} />
            <ExerciseDetailSheet
              api={api}
              exerciseId={openExercise.id}
              guideContext={exerciseGuideContext}
            />
            <Button
              label="목록으로"
              tone="secondary"
              onPress={() => setOpenExercise(null)}
            />
          </ScreenShell>
        </Modal>
      ) : null}
    </>
  );
}

function CatalogHeader({ onBack }: { onBack: () => void }) {
  return (
    <View style={styles.catalogHeader} testID="exercise-catalog-list-header">
      <Pressable
        accessibilityLabel="돌아가기"
        accessibilityRole="button"
        hitSlop={8}
        onPress={onBack}
        style={styles.backButton}
      >
        <View style={styles.backChevron} testID="exercise-catalog-back-icon" />
      </Pressable>
      <View style={styles.headerCopy} testID="exercise-catalog-header-copy">
        <Text accessibilityRole="header" style={styles.headerTitle}>
          운동 카탈로그
        </Text>
      </View>
      <View
        pointerEvents="none"
        style={styles.headerSideSpacer}
        testID="exercise-catalog-header-spacer"
      />
    </View>
  );
}

function FilterRow<Code extends string | undefined>({
  groupLabel,
  options,
  selected,
  onSelect,
}: {
  groupLabel: string;
  options: readonly { code: Code; label: string }[];
  selected: string | undefined;
  onSelect: (code: Code) => void;
}) {
  return (
    <View style={styles.filterSection}>
      <Text style={styles.filterGroupLabel}>{groupLabel}</Text>
      <ScrollView
        horizontal
        contentContainerStyle={styles.filterRow}
        showsHorizontalScrollIndicator={false}
      >
        {options.map(({ code, label }) => {
          const active = selected === code;
          return (
            <Pressable
              key={label}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              onPress={() => onSelect(code)}
              style={[styles.filterChip, active && styles.filterChipActive]}
            >
              <Text
                style={[
                  styles.filterChipText,
                  active && styles.filterChipTextActive,
                ]}
              >
                {label}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

function CatalogList({
  items,
  searchActive,
  onOpen,
}: {
  items: ExerciseListItem[];
  searchActive: boolean;
  onOpen: (exercise: ExerciseListItem) => void;
}) {
  if (items.length === 0) {
    return (
      <EmptyState
        message={
          searchActive
            ? '검색한 운동명을 찾지 못했어요.'
            : '이 부위의 운동이 아직 없어요.'
        }
      />
    );
  }

  return (
    <ScrollView
      style={styles.catalogScroll}
      contentContainerStyle={styles.list}
      testID="exercise-catalog-list-scroll"
    >
      {items.map((item) => (
        <Pressable
          key={item.id}
          accessibilityRole="button"
          accessibilityLabel={`${item.name} 설명 열기`}
          onPress={() => onOpen(item)}
        >
          <Card style={styles.itemCard}>
            <Text style={styles.itemName}>{item.name}</Text>
            <Text
              style={styles.itemSummary}
              testID={`exercise-body-focus-${item.id}`}
            >
              {catalogSummaryLabel(item)}
            </Text>
            <View style={styles.itemFooter}>
              {item.required_equipment_codes.length > 0 ? (
                <Text style={styles.itemEquipment}>
                  {item.required_equipment_codes.map(equipmentLabel).join(', ')}
                </Text>
              ) : null}
              <View style={styles.itemBadge}>
                <Text style={styles.itemBadgeText}>
                  {difficultyLabel(item.difficulty_code)}
                </Text>
              </View>
            </View>
          </Card>
        </Pressable>
      ))}
    </ScrollView>
  );
}

async function loadEntireCatalog(
  api: Pick<Api, 'listExercises'>,
  signal?: AbortSignal,
): Promise<ExerciseListResponse> {
  const items: ExerciseListItem[] = [];
  let cursor: string | null | undefined;
  let catalogVersion = '';
  const seenCursors = new Set<string>();

  do {
    const page = await api.listExercises(
      { cursor: cursor ?? undefined, limit: 100 },
      signal,
    );
    if (catalogVersion === '') catalogVersion = page.catalog_version;
    items.push(...page.items);
    cursor = page.next_cursor;
    if (cursor !== null) {
      if (seenCursors.has(cursor)) break;
      seenCursors.add(cursor);
    }
  } while (cursor !== null);

  return { items, next_cursor: null, catalog_version: catalogVersion };
}

function filterCatalogItems(
  items: ExerciseListItem[],
  searchQuery: string,
  bodyFocus: string | undefined,
): ExerciseListItem[] {
  const query = searchQuery.trim().toLocaleLowerCase('ko-KR');
  return items.filter(
    (item) =>
      (bodyFocus === undefined || item.body_focus_code === bodyFocus) &&
      (query.length === 0 ||
        item.name.toLocaleLowerCase('ko-KR').includes(query)),
  );
}

function catalogFocusLabel(item: ExerciseListItem): string {
  if (item.body_focus_code) {
    return bodyFocusLabel(item.body_focus_code);
  }
  const legacyAreas = item.primary_body_area_codes
    .map(bodyAreaLabel)
    .join(', ');
  return legacyAreas || '정보 없음';
}

function catalogSummaryLabel(item: ExerciseListItem): string {
  const trainingType = trainingTypeLabel(item.training_type_code);
  if (item.body_focus_code === item.training_type_code) {
    return trainingType;
  }
  return `${trainingType} · ${catalogFocusLabel(item)}`;
}

const styles = StyleSheet.create({
  screenContent: {
    paddingBottom: spacing.lg,
  },
  catalogHeader: {
    minHeight: 64,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  backButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: 22,
    backgroundColor: colors.surface,
  },
  backChevron: {
    width: 12,
    height: 12,
    borderBottomWidth: 2.5,
    borderLeftWidth: 2.5,
    borderColor: colors.textSub,
    transform: [{ rotate: '45deg' }],
  },
  headerCopy: {
    minWidth: 0,
    flex: 1,
    alignItems: 'center',
    gap: 4,
  },
  headerTitle: {
    color: colors.text,
    fontSize: 22,
    fontWeight: '800',
    textAlign: 'center',
  },
  headerSideSpacer: {
    width: 44,
    height: 44,
  },
  catalogControls: {
    gap: spacing.md,
    marginBottom: spacing.sm,
  },
  searchField: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.surface,
    paddingHorizontal: 14,
  },
  searchIcon: {
    width: 18,
    height: 18,
  },
  searchIconCircle: {
    position: 'absolute',
    top: 1,
    left: 1,
    width: 12,
    height: 12,
    borderWidth: 2,
    borderColor: colors.textMuted,
    borderRadius: 6,
  },
  searchIconHandle: {
    position: 'absolute',
    right: 1,
    bottom: 2,
    width: 7,
    height: 2,
    borderRadius: 1,
    backgroundColor: colors.textMuted,
    transform: [{ rotate: '45deg' }],
  },
  searchInput: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    fontSize: 15,
    paddingVertical: 0,
  },
  searchClearButton: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 16,
    backgroundColor: colors.surfaceAlt,
  },
  searchClearText: {
    marginTop: -2,
    color: colors.textMuted,
    fontSize: 20,
    lineHeight: 22,
  },
  filterSection: {
    gap: spacing.xs,
  },
  filterRow: {
    alignItems: 'center',
    gap: spacing.sm,
    paddingRight: spacing.sm,
  },
  filterGroupLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  filterChip: {
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radii.button,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  filterChipActive: {
    borderColor: colors.primary,
    backgroundColor: colors.primary,
  },
  filterChipText: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '600',
  },
  filterChipTextActive: {
    color: colors.surface,
  },
  catalogScroll: {
    flex: 1,
  },
  list: {
    gap: spacing.sm,
    paddingBottom: spacing.lg,
  },
  itemCard: {
    gap: 4,
    padding: 14,
  },
  itemName: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  itemSummary: {
    color: colors.textSub,
    fontSize: 13,
    fontWeight: '600',
  },
  itemFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  itemEquipment: {
    minWidth: 0,
    flex: 1,
    color: colors.textSub,
    fontSize: 12,
  },
  itemBadge: {
    marginLeft: 'auto',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  itemBadgeText: {
    color: colors.textSub,
    fontSize: 11.5,
    fontWeight: '700',
  },
});
