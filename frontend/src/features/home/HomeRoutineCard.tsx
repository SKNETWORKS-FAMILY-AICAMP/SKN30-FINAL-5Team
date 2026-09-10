import { LinearGradient } from 'expo-linear-gradient';
import { Animated, Pressable, Text, TextInput, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import { actionLabel } from '../../api/labels';
import type {
  ActionCode,
  ExerciseVariantsResponse,
  SessionStatusCode,
} from '../../api/types';
import { ExerciseVariantsAction } from '../workout/ExerciseVariants';
import {
  formatRoutineItem,
  getHomeRerollLabel,
  type HomeRoutineItem,
  type TodayRoutinePhase,
} from './homeModel';
import { DragHandle, useDragController } from './HomeEditRoutineSheet';
import { useHomeStyles } from './homeStyles';
import {
  EditIcon,
  RerollIcon,
  RestIcon,
  RoutineDragIcon,
  digitsOnly,
} from './HomeSupport';

const ROUTINE_NOTES: readonly string[] = [];

export function RoutineCard({
  actionCode,
  completedItemIds,
  currentPlanItemId,
  editDisabled,
  editing,
  editLabel,
  focus,
  items,
  locationCode,
  minutes,
  notes = ROUTINE_NOTES,
  onEdit,
  onChangePrescription,
  onMove,
  onOpenExerciseGuide,
  onOpenExerciseVariants,
  onOpenReasons,
  onRest,
  onRequestAlternative,
  onStart,
  painPart,
  pending,
  phase,
  rerolling,
  rerolls,
  revisionNotice,
  sessionStatusCode,
  startBlockedReason,
  variantApi,
}: {
  actionCode?: ActionCode;
  completedItemIds: readonly string[];
  currentPlanItemId: string | null;
  editDisabled: boolean;
  editing: boolean;
  editLabel: string;
  focus: string;
  items: readonly HomeRoutineItem[];
  locationCode?: string;
  minutes: string;
  notes?: readonly string[];
  onEdit?: () => void;
  onChangePrescription: (
    id: string,
    patch: Pick<Partial<HomeRoutineItem>, 'sets' | 'reps' | 'workSeconds'>,
  ) => void;
  onMove?: (from: number, to: number) => void;
  onOpenExerciseGuide?: (item: HomeRoutineItem) => void;
  onOpenExerciseVariants: (
    item: HomeRoutineItem,
    response: ExerciseVariantsResponse,
  ) => void;
  onOpenReasons?: () => void;
  onRest?: () => void;
  onRequestAlternative?: () => void;
  onStart?: () => void;
  painPart: string | null;
  pending: boolean;
  phase: TodayRoutinePhase;
  rerolling: boolean;
  rerolls: number;
  revisionNotice?: string;
  sessionStatusCode?: SessionStatusCode;
  startBlockedReason?: string | null;
  variantApi?: Partial<Pick<Api, 'getExerciseVariants'>>;
}) {
  const styles = useHomeStyles();
  const drag = useDragController(onMove ?? (() => undefined));
  const rerollLabel = getHomeRerollLabel(rerolls, rerolling);
  const routineActionLabel =
    actionCode === undefined || actionCode === 'KEEP'
      ? null
      : actionLabel(actionCode);
  const adjustedAction =
    actionCode === 'DOWNSHIFT' ||
    actionCode === 'CHANGE' ||
    actionCode === 'RECOVERY';
  const locked =
    phase === 'SESSION_ACTIVE' ||
    phase === 'STOPPED_RESUMABLE' ||
    phase === 'STOPPED_SAFETY' ||
    phase === 'COMPLETED';
  const interactionsDisabled = editing;
  const primaryActionLabel =
    phase === 'SESSION_ACTIVE' || phase === 'STOPPED_RESUMABLE'
      ? '이어하기'
      : '운동 시작하기';
  const statusCopy =
    phase === 'STOPPED_SAFETY'
      ? '안전 관련 중단으로 오늘은 이어서 진행할 수 없어요. 진행 기록은 그대로 보관됩니다.'
      : phase === 'COMPLETED'
        ? '오늘 운동 기록이에요. 완료한 운동과 진행 상태를 확인할 수 있어요.'
        : phase === 'SESSION_ACTIVE'
          ? '진행 중인 운동이에요. 완료한 항목부터 이어서 진행할 수 있어요.'
          : phase === 'STOPPED_RESUMABLE'
            ? '잠시 멈춘 운동이에요. 완료한 항목부터 이어서 진행할 수 있어요.'
            : null;
  const routineHeading =
    phase === 'STOPPED_RESUMABLE' ||
    sessionStatusCode === 'PARTIAL' ||
    sessionStatusCode === 'NOT_COMPLETED'
      ? '조금만 더 힘내요!'
      : phase === 'COMPLETED' && sessionStatusCode === 'COMPLETED'
        ? '오늘도 자신과의 싸움에서 승리했군요!'
        : '컨디션에 맞춘 운동을 준비했어요';
  return (
    <View style={styles.routineCard} testID="home-routine-state">
      <View style={styles.routineBadgeRow}>
        <View style={styles.routineBadge}>
          <Text style={styles.routineBadgeText}>
            {phase === 'STOPPED_SAFETY'
              ? '안전 중단'
              : phase === 'COMPLETED'
                ? '운동 기록'
                : locked
                  ? '운동 진행 중'
                  : '운동 준비 완료'}
          </Text>
        </View>
        {routineActionLabel === null ? null : (
          <View
            accessible
            accessibilityLabel={`루틴 진행 방식: ${routineActionLabel}`}
            style={[
              styles.routineActionBadge,
              adjustedAction && styles.routineActionBadgeAdjusted,
            ]}
          >
            <Text style={styles.routineActionBadgeText}>
              {routineActionLabel}
            </Text>
          </View>
        )}
      </View>
      <Text style={styles.routineTitle}>{routineHeading}</Text>
      <Text style={styles.routineSummary}>
        {focus} · {minutes}분
      </Text>
      {onOpenReasons ? (
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: interactionsDisabled }}
          disabled={interactionsDisabled}
          onPress={onOpenReasons}
          style={[
            styles.reasonLink,
            interactionsDisabled && styles.disabledControl,
          ]}
        >
          <Text
            style={[
              styles.reasonLinkText,
              interactionsDisabled && styles.disabledLabel,
            ]}
          >
            이 루틴을 추천한 이유 {'>'}
          </Text>
        </Pressable>
      ) : null}
      {statusCopy ? (
        <View style={styles.adjustmentNote}>
          <Text style={styles.adjustmentText}>{statusCopy}</Text>
        </View>
      ) : null}
      {notes.length > 0 ? (
        <View style={styles.routineNotes}>
          {notes.map((note) => (
            <Text key={note} style={styles.routineNote}>
              {note}
            </Text>
          ))}
        </View>
      ) : null}
      <View style={styles.routineList}>
        {onMove ? (
          <Text style={styles.orderHint}>
            운동 순서는 자유롭게 바꿀 수 있어요.
          </Text>
        ) : null}
        {items.map((item, index) => {
          const completed = completedItemIds.includes(item.id);
          const current = currentPlanItemId === item.id && !completed;
          const { activeIndex, targetIndex } = drag;
          const active = activeIndex === index;
          const dropTarget =
            activeIndex !== null &&
            targetIndex !== null &&
            targetIndex !== activeIndex &&
            targetIndex === index;
          return (
            <View
              key={item.id}
              onLayout={(event) => drag.register(index, event)}
              style={[
                styles.dragOuterRoutine,
                active && styles.dragOuterActive,
              ]}
              testID={`routine-row-${item.id}`}
            >
              {dropTarget ? (
                <View
                  pointerEvents="none"
                  style={styles.dropPlaceholder}
                  testID={`routine-drop-placeholder-${item.id}`}
                />
              ) : null}
              <Animated.View
                style={[
                  styles.routineRow,
                  completed && styles.routineRowCompleted,
                  active && styles.dragInnerRoutineActive,
                  {
                    transform: [
                      {
                        translateY: active
                          ? drag.dragY
                          : drag.getItemShift(index),
                      },
                    ],
                  },
                ]}
              >
                {onMove && !completed && !editing ? (
                  <DragHandle
                    disabled={interactionsDisabled}
                    index={index}
                    onEnd={drag.end}
                    onKeyboardMove={(direction) =>
                      drag.keyboardMove(index, direction, items.length)
                    }
                    onMove={drag.move}
                    onStart={drag.start}
                    style={[
                      styles.routineHandle,
                      interactionsDisabled && styles.disabledControl,
                    ]}
                    testID={`routine-drag-${item.id}`}
                  >
                    <RoutineDragIcon />
                  </DragHandle>
                ) : null}
                {editing ? (
                  <View
                    style={[
                      styles.inlinePrescriptionRow,
                      styles.inlinePrescriptionRowEditing,
                    ]}
                  >
                    <Text
                      adjustsFontSizeToFit
                      minimumFontScale={0.58}
                      numberOfLines={1}
                      style={[
                        styles.inlineExerciseName,
                        styles.inlineExerciseNameEditing,
                      ]}
                    >
                      {item.name}
                    </Text>
                    <Text
                      style={[
                        styles.inlinePrescriptionUnit,
                        styles.inlinePrescriptionUnitEditing,
                      ]}
                    >
                      ·
                    </Text>
                    <TextInput
                      accessibilityLabel={`${item.name} 세트 수`}
                      inputMode="numeric"
                      onChangeText={(sets) =>
                        onChangePrescription(item.id, {
                          sets: digitsOnly(sets),
                        })
                      }
                      style={[
                        styles.inlinePrescriptionInput,
                        styles.inlinePrescriptionInputEditing,
                      ]}
                      value={item.sets ?? ''}
                    />
                    <Text
                      style={[
                        styles.inlinePrescriptionUnit,
                        styles.inlinePrescriptionUnitEditing,
                      ]}
                    >
                      세트
                    </Text>
                    <Text
                      style={[
                        styles.inlinePrescriptionUnit,
                        styles.inlinePrescriptionUnitEditing,
                      ]}
                    >
                      ×
                    </Text>
                    {/*
                      Which number the item is measured in decides the field.
                      Both used to be the repetition input, so editing a
                      time-based block sent a duration as `reps` -- refused by
                      the server, and the failed edit blocked starting.
                    */}
                    {item.workSeconds === undefined ? (
                      <>
                        <TextInput
                          accessibilityLabel={`${item.name} 반복 횟수`}
                          inputMode="numeric"
                          onChangeText={(reps) =>
                            onChangePrescription(item.id, {
                              reps: digitsOnly(reps),
                            })
                          }
                          placeholder="0"
                          placeholderTextColor="#B8AA9E"
                          style={[
                            styles.inlinePrescriptionInput,
                            styles.inlinePrescriptionInputEditing,
                          ]}
                          value={item.reps ?? ''}
                        />
                        <Text
                          style={[
                            styles.inlinePrescriptionUnit,
                            styles.inlinePrescriptionUnitEditing,
                          ]}
                        >
                          회
                        </Text>
                      </>
                    ) : (
                      <>
                        <TextInput
                          accessibilityLabel={`${item.name} 세트당 시간(초)`}
                          inputMode="numeric"
                          onChangeText={(seconds) =>
                            onChangePrescription(item.id, {
                              workSeconds: digitsOnly(seconds),
                            })
                          }
                          placeholder="0"
                          placeholderTextColor="#B8AA9E"
                          style={[
                            styles.inlinePrescriptionInput,
                            styles.inlinePrescriptionInputEditing,
                          ]}
                          value={item.workSeconds}
                        />
                        <Text
                          style={[
                            styles.inlinePrescriptionUnit,
                            styles.inlinePrescriptionUnitEditing,
                          ]}
                        >
                          초
                        </Text>
                      </>
                    )}
                  </View>
                ) : (
                  <Text
                    accessibilityLabel={
                      completed
                        ? `완료: ${formatRoutineItem(item)}`
                        : current
                          ? `다음 운동: ${formatRoutineItem(item)}`
                          : undefined
                    }
                    style={[
                      styles.routineItemText,
                      completed && styles.routineItemCompleted,
                    ]}
                  >
                    {completed ? '✓ ' : ''}
                    {formatRoutineItem(item)}
                  </Text>
                )}
                {item.exerciseId &&
                (onOpenExerciseGuide || variantApi?.getExerciseVariants) ? (
                  <View
                    style={[
                      styles.routineGuideActions,
                      interactionsDisabled && styles.routineGuideActionsEditing,
                    ]}
                    testID={`routine-guide-actions-${item.id}`}
                  >
                    <View
                      style={[
                        styles.routineGuideSlot,
                        interactionsDisabled && styles.routineGuideSlotEditing,
                      ]}
                      testID={`routine-posture-slot-${item.id}`}
                    >
                      {onOpenExerciseGuide ? (
                        <Pressable
                          accessibilityLabel={`${item.name} 자세`}
                          accessibilityRole="button"
                          accessibilityState={{
                            disabled: interactionsDisabled,
                          }}
                          disabled={interactionsDisabled}
                          onPress={() => onOpenExerciseGuide(item)}
                          style={[
                            styles.routineGuideButton,
                            interactionsDisabled &&
                              styles.routineGuideButtonEditing,
                            interactionsDisabled &&
                              styles.routineGuideButtonDisabled,
                          ]}
                        >
                          <Text
                            style={[
                              styles.routineGuideButtonText,
                              interactionsDisabled &&
                                styles.routineGuideButtonTextEditing,
                              interactionsDisabled && styles.disabledLabel,
                            ]}
                            numberOfLines={1}
                          >
                            자세
                          </Text>
                        </Pressable>
                      ) : null}
                    </View>
                    <View
                      style={[
                        styles.routineGuideSlot,
                        interactionsDisabled && styles.routineGuideSlotEditing,
                      ]}
                      testID={`routine-equipment-slot-${item.id}`}
                    >
                      {variantApi ? (
                        <ExerciseVariantsAction
                          actionStyle={[
                            styles.routineGuideButton,
                            styles.routineEquipmentButton,
                            interactionsDisabled &&
                              styles.routineGuideButtonEditing,
                            interactionsDisabled &&
                              styles.routineGuideButtonDisabled,
                          ]}
                          actionTextStyle={[
                            styles.routineEquipmentButtonText,
                            interactionsDisabled &&
                              styles.routineGuideButtonTextEditing,
                            interactionsDisabled && styles.disabledLabel,
                          ]}
                          api={variantApi}
                          disabled={interactionsDisabled}
                          exerciseId={item.exerciseId}
                          exerciseName={item.name}
                          locationCode={locationCode}
                          onOpen={(response) =>
                            onOpenExerciseVariants(item, response)
                          }
                        />
                      ) : null}
                    </View>
                  </View>
                ) : null}
              </Animated.View>
            </View>
          );
        })}
      </View>

      {painPart ? (
        <View style={styles.adjustmentNote}>
          <Text style={styles.adjustmentText}>
            {painPart} 부담을 줄이도록 강도를 조정했어요.
          </Text>
        </View>
      ) : null}

      {revisionNotice ? (
        <View style={styles.adjustmentNote}>
          <Text style={styles.adjustmentText}>{revisionNotice}</Text>
        </View>
      ) : null}

      {startBlockedReason ? (
        <Text accessibilityRole="alert" style={styles.messageText}>
          {startBlockedReason}
        </Text>
      ) : null}

      {phase === 'STOPPED_SAFETY' || phase === 'COMPLETED' ? null : (
        <Pressable
          accessibilityLabel={primaryActionLabel}
          accessibilityRole="button"
          accessibilityState={{
            disabled: interactionsDisabled || pending || !onStart,
          }}
          disabled={interactionsDisabled || pending || !onStart}
          onPress={onStart}
          style={[
            styles.startButton,
            (interactionsDisabled || pending || !onStart) &&
              styles.startButtonDisabled,
          ]}
        >
          <LinearGradient
            colors={
              interactionsDisabled || pending || !onStart
                ? ['#E7E5E2', '#E7E5E2']
                : ['#FFFDF8', '#FFF2D1', '#FFE2A3']
            }
            end={{ x: 0.5, y: 1 }}
            locations={
              interactionsDisabled || pending || !onStart
                ? [0, 1]
                : [0, 0.55, 1]
            }
            pointerEvents="none"
            start={{ x: 0.5, y: 0 }}
            style={styles.startButtonGradient}
            testID="home-start-gradient"
          />
          <Text
            style={[
              styles.startLabel,
              interactionsDisabled && styles.startLabelDisabled,
            ]}
          >
            {primaryActionLabel}
          </Text>
        </Pressable>
      )}
      {locked ? null : (
        <View style={styles.routineActions}>
          {onEdit ? (
            <Pressable
              accessibilityLabel={editLabel}
              accessibilityRole="button"
              accessibilityState={{ disabled: editDisabled }}
              disabled={editDisabled}
              onPress={onEdit}
              style={[
                styles.routineAction,
                editDisabled && styles.routineActionDisabled,
              ]}
            >
              <EditIcon />
              <Text style={styles.editActionLabel}>{editLabel}</Text>
            </Pressable>
          ) : null}
          {onRequestAlternative ? (
            <Pressable
              accessibilityLabel="다른 루틴 추천 받기"
              accessibilityRole="button"
              accessibilityState={{
                disabled:
                  interactionsDisabled || pending || rerolling || rerolls >= 2,
              }}
              disabled={
                interactionsDisabled || pending || rerolling || rerolls >= 2
              }
              onPress={onRequestAlternative}
              style={[
                styles.routineAction,
                (interactionsDisabled || rerolls >= 2) &&
                  styles.routineActionDisabled,
                interactionsDisabled && styles.disabledAction,
              ]}
            >
              <RerollIcon
                color={
                  interactionsDisabled || rerolls >= 2 ? '#A8A49E' : '#A45F00'
                }
              />
              <Text
                numberOfLines={1}
                style={[
                  styles.rerollActionLabel,
                  (interactionsDisabled || rerolls >= 2) &&
                    styles.rerollActionLabelDisabled,
                ]}
              >
                {rerollLabel}
              </Text>
            </Pressable>
          ) : null}
        </View>
      )}
      {!locked && onRest ? (
        <Pressable
          accessibilityLabel="오늘은 쉬기"
          accessibilityRole="button"
          accessibilityState={{ disabled: interactionsDisabled || pending }}
          disabled={interactionsDisabled || pending}
          onPress={onRest}
          style={[
            styles.routineAction,
            styles.restAction,
            (interactionsDisabled || pending) && styles.restActionDisabled,
          ]}
        >
          <LinearGradient
            colors={
              interactionsDisabled || pending
                ? ['#F2F1EF', '#ECEAE7']
                : ['#FCFFF8', '#EEF5E2']
            }
            end={{ x: 1, y: 1 }}
            pointerEvents="none"
            start={{ x: 0, y: 0 }}
            style={styles.restActionGradient}
            testID="home-rest-gradient"
          />
          <View
            style={[
              styles.restActionIcon,
              (interactionsDisabled || pending) &&
                styles.restActionIconDisabled,
            ]}
            testID="home-rest-icon"
          >
            <RestIcon
              color={interactionsDisabled || pending ? '#98948E' : '#667A4F'}
            />
          </View>
          <Text
            style={[
              styles.restActionLabel,
              (interactionsDisabled || pending) && styles.disabledLabel,
            ]}
          >
            오늘은 쉬기
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}
