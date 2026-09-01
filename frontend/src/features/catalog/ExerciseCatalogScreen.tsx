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
  View,
} from 'react-native';

import type { Api } from '../../api/endpoints';
import {
  bodyAreaLabel,
  equipmentLabel,
  experienceLevelLabel,
  trainingTypeLabel,
} from '../../api/labels';
import type { ExerciseListItem, ExerciseListResponse } from '../../api/types';
import { useAsyncAction, useAsyncData } from '../../api/useAsync';
import { Button, Card, InlineFeedback } from '../../components/primitives';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, radii, spacing } from '../../components/theme';
import { ExerciseDetailSheet } from '../workout/ExerciseDetailSheet';

const TRAINING_TYPE_FILTERS = [
  { code: undefined, label: '전체' },
  { code: 'STRENGTH', label: '근력' },
  { code: 'CARDIO', label: '유산소' },
  { code: 'MOBILITY', label: '스트레칭' },
] as const;

// Difficulty uses the same words as the onboarding experience step so one
// concept never appears as both 입문 and 초급.
const DIFFICULTY_FILTERS = [
  { code: undefined, label: '전체' },
  { code: 'BEGINNER', label: '초급' },
  { code: 'INTERMEDIATE', label: '중급' },
] as const;

const difficultyLabel = (code: string) => experienceLevelLabel(code);

export function ExerciseCatalogScreen({
  api,
  onBack,
}: {
  api: Pick<Api, 'listExercises' | 'getExercise'>;
  onBack: () => void;
}) {
  const [trainingType, setTrainingType] = useState<string | undefined>();
  const [difficulty, setDifficulty] = useState<string | undefined>();
  const [extraItems, setExtraItems] = useState<ExerciseListItem[]>([]);
  const [openExercise, setOpenExercise] = useState<ExerciseListItem | null>(
    null,
  );

  const { state, reload } = useAsyncData<ExerciseListResponse>(
    (signal) =>
      api.listExercises(
        { trainingTypeCode: trainingType, difficultyCode: difficulty },
        signal,
      ),
    // Changing a filter restarts from the first page.
    [api, trainingType, difficulty],
  );

  const loadMore = useAsyncAction(async (cursor: string) => {
    const page = await api.listExercises({
      trainingTypeCode: trainingType,
      difficultyCode: difficulty,
      cursor,
    });
    setExtraItems((current) => [...current, ...page.items]);
    return page;
  });
  const [nextCursor, setNextCursor] = useState<string | null | undefined>();

  const selectTrainingType = useCallback((code: string | undefined) => {
    setTrainingType(code);
    setExtraItems([]);
    setNextCursor(undefined);
  }, []);
  const selectDifficulty = useCallback((code: string | undefined) => {
    setDifficulty(code);
    setExtraItems([]);
    setNextCursor(undefined);
  }, []);

  return (
    <>
      <ScreenShell scroll={false} contentStyle={styles.screenContent}>
        <CatalogHeader onBack={onBack} />

        <View style={styles.filterGroup}>
          <FilterRow
            groupLabel="운동 유형"
            options={TRAINING_TYPE_FILTERS}
            selected={trainingType}
            onSelect={selectTrainingType}
          />
          <FilterRow
            groupLabel="난이도"
            options={DIFFICULTY_FILTERS}
            selected={difficulty}
            onSelect={selectDifficulty}
          />
        </View>

        {state.status === 'loading' ? (
          <LoadingState label="운동 목록을 불러오는 중이에요" />
        ) : state.status === 'error' ? (
          <ErrorState message={state.message} onRetry={reload} />
        ) : (
          <CatalogList
            firstPage={state.data}
            extraItems={extraItems}
            nextCursor={
              nextCursor === undefined ? state.data.next_cursor : nextCursor
            }
            loadingMore={loadMore.pending}
            loadMoreError={loadMore.error}
            onOpen={setOpenExercise}
            onLoadMore={(cursor) =>
              void loadMore.run(cursor).then((page) => {
                if (page) {
                  setNextCursor(page.next_cursor);
                }
              })
            }
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
            <ExerciseDetailSheet api={api} exerciseId={openExercise.id} />
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
        <Text style={styles.headerSubtitle}>
          운동 계획에 활용되는 운동을 모아봤어요.
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
    <View style={styles.filterRow}>
      <Text style={styles.filterGroupLabel}>{groupLabel}</Text>
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
    </View>
  );
}

function CatalogList({
  firstPage,
  extraItems,
  nextCursor,
  loadingMore,
  loadMoreError,
  onOpen,
  onLoadMore,
}: {
  firstPage: ExerciseListResponse;
  extraItems: ExerciseListItem[];
  nextCursor: string | null;
  loadingMore: boolean;
  loadMoreError: string | null;
  onOpen: (exercise: ExerciseListItem) => void;
  onLoadMore: (cursor: string) => void;
}) {
  const items = [...firstPage.items, ...extraItems];

  if (items.length === 0) {
    return <EmptyState message="조건에 맞는 운동이 아직 없어요." />;
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
            <Text style={styles.itemMeta}>
              {trainingTypeLabel(item.training_type_code)}
              {' · '}
              {item.primary_body_area_codes.map(bodyAreaLabel).join(', ')}
            </Text>
            <View style={styles.itemFooter}>
              {item.required_equipment_codes.length > 0 ? (
                <Text style={styles.itemEquipment}>
                  {`장비 ${item.required_equipment_codes
                    .map(equipmentLabel)
                    .join(', ')}`}
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

      {loadMoreError ? (
        <InlineFeedback tone="error" message={loadMoreError} />
      ) : null}
      {nextCursor !== null ? (
        <Button
          label={loadingMore ? '불러오는 중…' : '더 보기'}
          tone="secondary"
          disabled={loadingMore}
          onPress={() => onLoadMore(nextCursor)}
        />
      ) : null}
    </ScrollView>
  );
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
  headerSubtitle: {
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
  },
  headerSideSpacer: {
    width: 44,
    height: 44,
  },
  filterGroup: {
    gap: spacing.sm,
  },
  filterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  filterGroupLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '700',
  },
  filterChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
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
    gap: spacing.xs,
  },
  itemName: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  itemMeta: {
    color: colors.textSub,
    fontSize: 13,
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
    color: colors.textMuted,
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
