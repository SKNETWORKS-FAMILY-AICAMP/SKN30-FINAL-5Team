import { RoutineSections } from '../../components/RoutineSections';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  PanResponder,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
  type GestureResponderEvent,
  type LayoutChangeEvent,
  type PanResponderGestureState,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { type HomeRoutineItem } from './homeModel';
import { SheetFrame } from './HomeChrome';
import { useHomeStyles } from './homeStyles';
import { DeleteIcon, EditDragIcon, digitsOnly } from './HomeSupport';

export function EditRoutineSheet({
  items,
  newItem,
  onAdd,
  onChangeItems,
  onChangeNew,
  onClose,
  onMove,
  onReset,
  onSave,
}: {
  items: HomeRoutineItem[];
  newItem: HomeRoutineItem;
  onAdd: () => void;
  onChangeItems: (items: HomeRoutineItem[]) => void;
  onChangeNew: (item: HomeRoutineItem) => void;
  onClose: () => void;
  onMove: (from: number, to: number) => void;
  onReset: () => void;
  onSave: () => void;
}) {
  const styles = useHomeStyles();
  const canMoveItem = (index: number) => items[index] !== undefined;
  const canMoveTo = (from: number, to: number) =>
    canMoveItem(to) &&
    (items[from]?.phaseCode ?? 'MAIN') === (items[to]?.phaseCode ?? 'MAIN');
  const drag = useDragController(onMove, canMoveItem, canMoveTo);
  const patchItem = (id: string, patch: Partial<HomeRoutineItem>) => {
    const next: HomeRoutineItem[] = [];
    for (const item of items) {
      next.push(item.id === id ? { ...item, ...patch } : item);
    }
    onChangeItems(next);
  };
  const removeItem = (id: string) => {
    const next: HomeRoutineItem[] = [];
    for (const item of items) {
      if (item.id !== id) {
        next.push(item);
      }
    }
    onChangeItems(next);
  };
  return (
    <SheetFrame onClose={onClose} title="오늘의 운동 수정" zIndex={22}>
      <Text style={styles.sheetIntro}>
        항목을 직접 고치거나 추가하고, 핸들을 끌어 순서를 바꿀 수 있어요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.editScrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.editList}>
          <RoutineSections
            items={items}
            getPhase={(item) => item.phaseCode}
            renderItem={(item, index) => {
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
                    styles.dragOuterEdit,
                    active && styles.dragOuterActive,
                  ]}
                >
                  {dropTarget ? (
                    <View
                      pointerEvents="none"
                      style={styles.dropPlaceholder}
                      testID={`edit-drop-placeholder-${item.id}`}
                    />
                  ) : null}
                  <Animated.View
                    style={[
                      styles.editRow,
                      active && styles.dragInnerEditActive,
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
                    {canMoveItem(index) ? (
                      <DragHandle
                        disabled={false}
                        index={index}
                        onEnd={drag.end}
                        onKeyboardMove={(direction) =>
                          drag.keyboardMove(index, direction, items.length)
                        }
                        onMove={drag.move}
                        onStart={drag.start}
                        style={styles.editHandle}
                        testID={`edit-drag-${item.id}`}
                      >
                        <EditDragIcon />
                      </DragHandle>
                    ) : null}
                    <TextInput
                      accessibilityLabel={`${item.name || '빈 항목'} 운동명`}
                      onChangeText={(name) => patchItem(item.id, { name })}
                      placeholder="운동명"
                      placeholderTextColor="#B8AA9E"
                      style={styles.editNameInput}
                      value={item.name}
                    />
                    <TextInput
                      accessibilityLabel={`${item.name || '항목'} 세트 수`}
                      inputMode="numeric"
                      onChangeText={(sets) =>
                        patchItem(item.id, { sets: digitsOnly(sets) })
                      }
                      placeholder="0"
                      placeholderTextColor="#B8AA9E"
                      style={styles.editSetsInput}
                      value={item.sets ?? ''}
                    />
                    <Text style={styles.editUnit}>세트</Text>
                    <TextInput
                      accessibilityLabel={`${item.name || '항목'} 횟수`}
                      inputMode="numeric"
                      onChangeText={(reps) =>
                        patchItem(item.id, { reps: digitsOnly(reps) })
                      }
                      placeholder="0"
                      placeholderTextColor="#B8AA9E"
                      style={styles.editRepsInput}
                      value={item.reps ?? ''}
                    />
                    <Text style={styles.editUnit}>회</Text>
                    <Pressable
                      accessibilityLabel="항목 삭제"
                      accessibilityRole="button"
                      onPress={() => removeItem(item.id)}
                      style={styles.deleteButton}
                    >
                      <DeleteIcon />
                    </Pressable>
                  </Animated.View>
                </View>
              );
            }}
          />
        </View>
        <View style={styles.addBox}>
          <Text style={styles.addTitle}>운동 직접 추가</Text>
          <View style={styles.addInputRow}>
            <TextInput
              accessibilityLabel="추가할 운동명"
              onChangeText={(name) => onChangeNew({ ...newItem, name })}
              placeholder="운동명"
              placeholderTextColor="#B8AA9E"
              style={styles.addNameInput}
              value={newItem.name}
            />
            <TextInput
              accessibilityLabel="추가할 세트 수"
              inputMode="numeric"
              onChangeText={(sets) =>
                onChangeNew({ ...newItem, sets: digitsOnly(sets) })
              }
              placeholder="0"
              placeholderTextColor="#B8AA9E"
              style={styles.addSetsInput}
              value={newItem.sets ?? ''}
            />
            <Text style={styles.editUnit}>세트</Text>
            <TextInput
              accessibilityLabel="추가할 횟수"
              inputMode="numeric"
              onChangeText={(reps) =>
                onChangeNew({ ...newItem, reps: digitsOnly(reps) })
              }
              placeholder="0"
              placeholderTextColor="#B8AA9E"
              style={styles.addRepsInput}
              value={newItem.reps ?? ''}
            />
            <Text style={styles.editUnit}>회</Text>
          </View>
          <Pressable
            accessibilityLabel="운동 추가하기"
            accessibilityRole="button"
            accessibilityState={{ disabled: !newItem.name.trim() }}
            disabled={!newItem.name.trim()}
            onPress={onAdd}
            style={[
              styles.addButton,
              newItem.name.trim()
                ? styles.addButtonEnabled
                : styles.addButtonDisabled,
            ]}
          >
            <Text
              style={[
                styles.addButtonText,
                newItem.name.trim()
                  ? styles.addButtonTextEnabled
                  : styles.addButtonTextDisabled,
              ]}
            >
              + 운동 추가하기
            </Text>
          </Pressable>
        </View>
        <View style={styles.editActions}>
          <Pressable
            accessibilityLabel="추천으로 되돌리기"
            accessibilityRole="button"
            onPress={onReset}
            style={styles.resetButton}
          >
            <Text numberOfLines={1} style={styles.resetLabel}>
              추천으로 되돌리기
            </Text>
          </Pressable>
          <Pressable
            accessibilityLabel="저장하기"
            accessibilityRole="button"
            onPress={onSave}
            style={styles.editSaveButton}
          >
            <Text style={styles.sheetSaveLabel}>저장하기</Text>
          </Pressable>
        </View>
      </ScrollView>
    </SheetFrame>
  );
}

export function DragHandle({
  children,
  disabled,
  index,
  onEnd,
  onKeyboardMove,
  onMove,
  onStart,
  style,
  testID,
}: {
  children: React.ReactNode;
  disabled: boolean;
  index: number;
  onEnd: () => void;
  onKeyboardMove: (direction: -1 | 1) => void;
  onMove: (dy: number) => void;
  onStart: (index: number) => void;
  style: StyleProp<ViewStyle>;
  testID: string;
}) {
  const responder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => !disabled,
        onStartShouldSetPanResponderCapture: () => !disabled,
        onMoveShouldSetPanResponder: (
          _event: GestureResponderEvent,
          gesture: PanResponderGestureState,
        ) => !disabled && Math.abs(gesture.dy) > 2,
        onMoveShouldSetPanResponderCapture: (
          _event: GestureResponderEvent,
          gesture: PanResponderGestureState,
        ) => !disabled && Math.abs(gesture.dy) > 2,
        onPanResponderGrant: () => onStart(index),
        onPanResponderMove: (
          _event: GestureResponderEvent,
          gesture: PanResponderGestureState,
        ) => onMove(gesture.dy),
        onPanResponderRelease: onEnd,
        onPanResponderTerminate: onEnd,
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
      }),
    [disabled, index, onEnd, onMove, onStart],
  );
  return (
    <View
      {...responder.panHandlers}
      accessible
      accessibilityActions={[
        { name: 'increment', label: '아래로 이동' },
        { name: 'decrement', label: '위로 이동' },
      ]}
      accessibilityLabel="순서 변경 핸들"
      accessibilityRole="adjustable"
      accessibilityState={{ disabled }}
      onAccessibilityAction={(event) => {
        if (disabled) {
          return;
        }
        if (event.nativeEvent.actionName === 'increment') {
          onKeyboardMove(1);
        }
        if (event.nativeEvent.actionName === 'decrement') {
          onKeyboardMove(-1);
        }
      }}
      style={[
        style,
        Platform.OS === 'web'
          ? ({ touchAction: 'none' } as unknown as ViewStyle)
          : undefined,
      ]}
      testID={testID}
    >
      {children}
    </View>
  );
}

export function useDragController(
  onMoveItem: (from: number, to: number) => void,
  isMovable: (index: number) => boolean = () => true,
  isValidTarget: (from: number, to: number) => boolean = (_from, to) =>
    isMovable(to),
) {
  const movableRef = useRef(isMovable);
  const validTargetRef = useRef(isValidTarget);
  useEffect(() => {
    movableRef.current = isMovable;
    validTargetRef.current = isValidTarget;
  }, [isMovable, isValidTarget]);
  const canMoveItem = useCallback(
    (index: number) => movableRef.current(index),
    [],
  );
  const canMoveTo = useCallback(
    (from: number, to: number) => validTargetRef.current(from, to),
    [],
  );
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [targetIndex, setTargetIndex] = useState<number | null>(null);
  const activeRef = useRef<number | null>(null);
  const targetRef = useRef<number | null>(null);
  const originCenter = useRef(0);
  const dragOffset = useRef(0);
  const centers = useRef<number[]>([]);
  const [dragY] = useState(() => new Animated.Value(0));
  const itemShifts = useRef<Animated.Value[]>([]);
  const shiftAnimations = useRef<Animated.CompositeAnimation[]>([]);
  const settleAnimation = useRef<Animated.CompositeAnimation | null>(null);
  const getItemShift = useCallback((index: number) => {
    while (itemShifts.current.length <= index) {
      itemShifts.current.push(new Animated.Value(0));
    }
    return itemShifts.current[index]!;
  }, []);
  const stopShiftAnimations = useCallback(() => {
    for (const animation of shiftAnimations.current) {
      animation.stop();
    }
    shiftAnimations.current = [];
  }, []);
  const resetItemShifts = useCallback(() => {
    stopShiftAnimations();
    for (const shift of itemShifts.current) {
      shift.setValue(0);
    }
  }, [stopShiftAnimations]);
  const animateItemShifts = useCallback(
    (from: number, target: number) => {
      stopShiftAnimations();
      shiftAnimations.current = itemShifts.current.map((shift, index) => {
        let toValue = 0;
        if (from < target && index > from && index <= target) {
          const currentCenter = centers.current[index] ?? index * 60 + 30;
          const previousCenter =
            centers.current[index - 1] ?? (index - 1) * 60 + 30;
          toValue = previousCenter - currentCenter;
        } else if (from > target && index >= target && index < from) {
          const currentCenter = centers.current[index] ?? index * 60 + 30;
          const nextCenter =
            centers.current[index + 1] ?? (index + 1) * 60 + 30;
          toValue = nextCenter - currentCenter;
        }
        return Animated.timing(shift, {
          toValue,
          duration: 85,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true,
        });
      });
      for (const animation of shiftAnimations.current) {
        animation.start();
      }
    },
    [stopShiftAnimations],
  );
  const register = useCallback((index: number, event: LayoutChangeEvent) => {
    const { height, y } = event.nativeEvent.layout;
    centers.current[index] = y + height / 2;
  }, []);
  const start = useCallback(
    (index: number) => {
      if (!canMoveItem(index)) return;
      settleAnimation.current?.stop();
      settleAnimation.current = null;
      resetItemShifts();
      activeRef.current = index;
      targetRef.current = index;
      originCenter.current = centers.current[index] ?? index * 60 + 30;
      dragOffset.current = 0;
      dragY.setValue(0);
      setActiveIndex(index);
      setTargetIndex(index);
    },
    [canMoveItem, dragY, resetItemShifts],
  );
  const move = useCallback(
    (dy: number) => {
      const from = activeRef.current;
      if (from === null) {
        return;
      }
      const movableCenters = centers.current.filter((_, index) =>
        canMoveTo(from, index),
      );
      const boundedY =
        movableCenters.length === 0
          ? originCenter.current
          : Math.max(
              Math.min(...movableCenters),
              Math.min(Math.max(...movableCenters), originCenter.current + dy),
            );
      const boundedOffset = boundedY - originCenter.current;
      const pointerY = boundedY;
      let target = from;
      let closestDistance = Number.POSITIVE_INFINITY;
      for (let index = 0; index < centers.current.length; index += 1) {
        const center = centers.current[index];
        if (center === undefined || !canMoveTo(from, index)) {
          continue;
        }
        const distance = Math.abs(pointerY - center);
        if (distance < closestDistance) {
          closestDistance = distance;
          target = index;
        }
      }
      if (targetRef.current !== target) {
        targetRef.current = target;
        setTargetIndex(target);
        animateItemShifts(from, target);
      }
      dragOffset.current = boundedOffset;
      dragY.setValue(boundedOffset);
    },
    [animateItemShifts, canMoveTo, dragY],
  );
  const end = useCallback(() => {
    const from = activeRef.current;
    const target = targetRef.current;
    if (from === null || target === null) {
      return;
    }
    activeRef.current = null;
    targetRef.current = null;
    const targetCenter =
      centers.current[target] ?? originCenter.current + (target - from) * 60;
    const remainingOffset =
      dragOffset.current - (targetCenter - originCenter.current);
    resetItemShifts();
    dragY.setValue(remainingOffset);
    setActiveIndex(target);
    setTargetIndex(target);
    if (target !== from && canMoveItem(from) && canMoveTo(from, target)) {
      onMoveItem(from, target);
    }
    const animation = Animated.timing(dragY, {
      toValue: 0,
      duration: 80,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    });
    settleAnimation.current = animation;
    animation.start(({ finished }) => {
      if (settleAnimation.current === animation) {
        settleAnimation.current = null;
      }
      if (finished) {
        dragY.setValue(0);
        setActiveIndex(null);
        setTargetIndex(null);
      }
    });
  }, [canMoveItem, canMoveTo, dragY, onMoveItem, resetItemShifts]);
  useEffect(
    () => () => {
      settleAnimation.current?.stop();
      stopShiftAnimations();
    },
    [stopShiftAnimations],
  );
  const keyboardMove = useCallback(
    (index: number, direction: -1 | 1, length: number) => {
      const target = Math.max(0, Math.min(length - 1, index + direction));
      if (target !== index && canMoveItem(index) && canMoveTo(index, target)) {
        onMoveItem(index, target);
      }
    },
    [canMoveItem, canMoveTo, onMoveItem],
  );
  return {
    activeIndex,
    dragY,
    end,
    getItemShift,
    keyboardMove,
    move,
    register,
    start,
    targetIndex,
  };
}
