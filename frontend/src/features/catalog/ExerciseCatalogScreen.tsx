/**
 * Reviewed exercise catalog browser.
 *
 * Everything shown here comes from the server's approved catalog list; this
 * screen never invents exercises, difficulty, or safety attributes, and it
 * plays no part in routine decisions — it is presentation only.
 */

import { useCallback, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import {
  bodyAreaLabel,
  equipmentLabel,
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
  { code: 'MOBILITY', label: '가동성' },
] as const;

const DIFFICULTY_FILTERS = [
  { code: undefined, label: '전체' },
  { code: 'BEGINNER', label: '입문' },
  { code: 'INTERMEDIATE', label: '중급' },
] as const;

const DIFFICULTY_LABELS: Record<string, string> = {
  BEGINNER: '입문',
  INTERMEDIATE: '중급',
};

const difficultyLabel = (code: string) => DIFFICULTY_LABELS[code] ?? code;

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
  const [openExerciseId, setOpenExerciseId] = useState<string | null>(null);

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

  if (openExerciseId !== null) {
    return (
      <ScreenShell bands>
        <ScreenHeading title="운동 설명" onBand />
        <ExerciseDetailSheet api={api} exerciseId={openExerciseId} />
        <Button
          label="목록으로"
          tone="secondary"
          onPress={() => setOpenExerciseId(null)}
        />
      </ScreenShell>
    );
  }

  return (
    <ScreenShell bands>
      <ScreenHeading
        title="운동 카탈로그"
        subtitle="검수를 통과한 운동만 보여드려요"
        onBand
      />

      <View style={styles.filterGroup}>
        <FilterRow
          options={TRAINING_TYPE_FILTERS}
          selected={trainingType}
          onSelect={selectTrainingType}
        />
        <FilterRow
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
          onOpen={setOpenExerciseId}
          onLoadMore={(cursor) =>
            void loadMore.run(cursor).then((page) => {
              if (page) {
                setNextCursor(page.next_cursor);
              }
            })
          }
        />
      )}

      <Button label="돌아가기" tone="secondary" onPress={onBack} />
    </ScreenShell>
  );
}

function FilterRow<Code extends string | undefined>({
  options,
  selected,
  onSelect,
}: {
  options: readonly { code: Code; label: string }[];
  selected: string | undefined;
  onSelect: (code: Code) => void;
}) {
  return (
    <View style={styles.filterRow}>
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
  onOpen: (exerciseId: string) => void;
  onLoadMore: (cursor: string) => void;
}) {
  const items = [...firstPage.items, ...extraItems];

  if (items.length === 0) {
    return <EmptyState message="조건에 맞는 운동이 아직 없어요." />;
  }

  return (
    <ScrollView contentContainerStyle={styles.list}>
      {items.map((item) => (
        <Pressable
          key={item.id}
          accessibilityRole="button"
          accessibilityLabel={`${item.name} 설명 열기`}
          onPress={() => onOpen(item.id)}
        >
          <Card style={styles.itemCard}>
            <View style={styles.itemHeader}>
              <Text style={styles.itemName}>{item.name}</Text>
              <Text style={styles.itemBadge}>
                {difficultyLabel(item.difficulty_code)}
              </Text>
            </View>
            <Text style={styles.itemMeta}>
              {trainingTypeLabel(item.training_type_code)}
              {' · '}
              {item.primary_body_area_codes.map(bodyAreaLabel).join(', ')}
            </Text>
            <Text style={styles.itemEquipment}>
              {item.required_equipment_codes.map(equipmentLabel).join(', ') ||
                '장비 없음'}
            </Text>
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
      <Text style={styles.catalogVersion}>
        카탈로그 버전 {firstPage.catalog_version}
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  filterGroup: {
    gap: spacing.sm,
  },
  filterRow: {
    flexDirection: 'row',
    gap: spacing.sm,
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
  list: {
    gap: spacing.sm,
    paddingBottom: spacing.lg,
  },
  itemCard: {
    gap: spacing.xs,
  },
  itemHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  itemName: {
    flex: 1,
    color: colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  itemBadge: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '600',
  },
  itemMeta: {
    color: colors.textSub,
    fontSize: 13,
  },
  itemEquipment: {
    color: colors.textMuted,
    fontSize: 12,
  },
  catalogVersion: {
    color: colors.textMuted,
    fontSize: 11,
    textAlign: 'center',
    marginTop: spacing.sm,
  },
});
