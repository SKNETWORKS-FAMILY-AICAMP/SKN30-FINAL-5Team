import { LinearGradient } from 'expo-linear-gradient';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import Svg, { Path } from 'react-native-svg';

import {
  bodyAreaLabel,
  DEFAULT_BODY_AREA_OPTIONS,
  EXTENDED_BODY_AREA_OPTIONS,
  locationLabel,
} from '../../api/labels';
import { PainIntensitySlider } from '../../components/profile/PainIntensitySlider';
import { useScale } from '../../components/scale';
import {
  CHECKIN_AVAILABILITY_INPUT_ENABLED,
  CHECKIN_DURATION_MINUTES,
  EMPTY_AVAILABILITY_SLOT,
  TIME_HOURS,
  TIME_MINUTES,
  TIME_WHEEL_ACCELERATION_DELTA,
  TIME_WHEEL_GESTURE_IDLE_MS,
  TIME_WHEEL_ITEM_HEIGHT,
  TIME_WHEEL_MAX_ITEMS_PER_GESTURE,
  TIME_WHEEL_SINGLE_ITEM_DELTA,
} from './homeConstants';
import {
  HOME_CHECKIN_OPTIONS,
  validateAvailabilitySlots,
  type HomeAvailabilitySlot,
  type HomeCheckin,
} from './homeModel';
import { SheetFrame } from './HomeChrome';
import { useHomeStyles } from './homeStyles';
import { DeleteIcon } from './HomeSupport';

export function CheckinSheet({
  draft,
  onAddAvailabilitySlot,
  onChangeFatigue,
  onChangeLocation,
  onChangePainIntensity,
  onChangeSleepHours,
  onChangeWorkoutMinutes,
  onClearPains,
  onClose,
  onOpenTimePicker,
  onSave,
  onRemoveAvailabilitySlot,
  onSetRedFlag,
  onToggleBodyArea,
  locationCodes,
  locationRequired,
  recommendedDurationMinutes,
  pending,
}: {
  draft: HomeCheckin;
  onAddAvailabilitySlot: () => void;
  onChangeFatigue: (value: string) => void;
  onChangeLocation: (code: string) => void;
  onChangePainIntensity: (bodyAreaCode: string, intensityScore: number) => void;
  onChangeSleepHours: (value: string) => void;
  onChangeWorkoutMinutes: (value: string) => void;
  onClearPains: () => void;
  onClose: () => void;
  onOpenTimePicker: (index: number, field: keyof HomeAvailabilitySlot) => void;
  onSave: () => void;
  onRemoveAvailabilitySlot: (index: number) => void;
  onSetRedFlag: (present: boolean) => void;
  onToggleBodyArea: (code: string) => void;
  locationCodes: readonly string[];
  locationRequired: boolean;
  recommendedDurationMinutes: number | null;
  pending: boolean;
}) {
  const styles = useHomeStyles();
  const { s } = useScale();
  const [showDiscomfortDetails, setShowDiscomfortDetails] = useState(
    Object.keys(draft.pains).length > 0,
  );
  const selectedDiscomfortCodes = Object.keys(draft.pains);
  const [showExtendedAreas, setShowExtendedAreas] = useState(() =>
    selectedDiscomfortCodes.some((code) =>
      EXTENDED_BODY_AREA_OPTIONS.some((option) => option.code === code),
    ),
  );
  const selectableCodes = new Set<string>(
    [...DEFAULT_BODY_AREA_OPTIONS, ...EXTENDED_BODY_AREA_OPTIONS].map(
      (option) => option.code,
    ),
  );
  const legacySelectedCodes = selectedDiscomfortCodes.filter(
    (code) => !selectableCodes.has(code),
  );
  const sleepHours = draft.sleepHours.trim();
  const sleepInvalid =
    sleepHours !== '' &&
    (!Number.isFinite(Number(sleepHours)) ||
      Number(sleepHours) < 0 ||
      Number(sleepHours) > 24);
  const durationMissing = draft.workoutMinutes === '';
  const durationInvalid =
    !durationMissing &&
    (!/^\d+$/.test(draft.workoutMinutes) ||
      Number(draft.workoutMinutes) < CHECKIN_DURATION_MINUTES.min ||
      Number(draft.workoutMinutes) > CHECKIN_DURATION_MINUTES.max);
  const durationMinutes = Number(draft.workoutMinutes);
  const exceedsRecommendation =
    recommendedDurationMinutes !== null &&
    !durationMissing &&
    !durationInvalid &&
    durationMinutes > recommendedDurationMinutes;
  const canDecreaseDuration =
    !pending &&
    !durationInvalid &&
    durationMinutes > CHECKIN_DURATION_MINUTES.min;
  const canIncreaseDuration =
    !pending &&
    (durationMissing ||
      (!durationInvalid && durationMinutes < CHECKIN_DURATION_MINUTES.max));
  const availabilityError = CHECKIN_AVAILABILITY_INPUT_ENABLED
    ? validateAvailabilitySlots(draft.availableSlots)
    : null;
  const availabilitySlots =
    draft.availableSlots && draft.availableSlots.length > 0
      ? draft.availableSlots
      : [EMPTY_AVAILABILITY_SLOT];
  const discomfortSelectionMissing =
    showDiscomfortDetails && Object.keys(draft.pains).length === 0;
  const locationSelectionMissing =
    locationRequired &&
    (draft.locationCode === null ||
      !locationCodes.includes(draft.locationCode));
  const redFlagSelectionMissing = draft.redFlagPresent === null;
  const saveDisabled =
    pending ||
    sleepInvalid ||
    durationMissing ||
    durationInvalid ||
    availabilityError !== null ||
    discomfortSelectionMissing ||
    locationSelectionMissing ||
    redFlagSelectionMissing;
  return (
    <SheetFrame onClose={onClose} title="오늘 컨디션 체크" zIndex={20}>
      <Text style={styles.sheetIntro}>
        오늘 상태를 알려주면 루틴을 맞춰 조정해드려요.
      </Text>
      <ScrollView
        contentContainerStyle={styles.sheetScrollContent}
        showsVerticalScrollIndicator={false}
      >
        <ChoiceBlock label="피로도">
          {HOME_CHECKIN_OPTIONS.fatigue.map((option) => (
            <ChoiceButton
              key={option}
              label={option}
              onPress={() => onChangeFatigue(option)}
              selected={draft.fatigue === option}
            />
          ))}
        </ChoiceBlock>
        <View style={styles.numberRow}>
          <Text style={styles.numberLabel}>원하는 운동 시간</Text>
          <View style={styles.durationStepper}>
            <Pressable
              accessibilityLabel="운동 시간 10분 줄이기"
              accessibilityRole="button"
              accessibilityState={{ disabled: !canDecreaseDuration }}
              disabled={!canDecreaseDuration}
              onPress={() =>
                onChangeWorkoutMinutes(
                  String(
                    Math.max(
                      CHECKIN_DURATION_MINUTES.min,
                      durationMinutes - CHECKIN_DURATION_MINUTES.step,
                    ),
                  ),
                )
              }
              style={[
                styles.durationStepButton,
                !canDecreaseDuration && styles.durationStepButtonDisabled,
              ]}
            >
              <Text style={styles.durationStepButtonText}>−</Text>
            </Pressable>
            <Text
              accessibilityLabel={
                durationMissing
                  ? '원하는 운동 시간 미선택'
                  : `원하는 운동 시간 ${draft.workoutMinutes}분`
              }
              accessibilityLiveRegion="polite"
              style={styles.durationStepValue}
            >
              {durationMissing ? '선택' : `${draft.workoutMinutes}분`}
            </Text>
            <Pressable
              accessibilityLabel="운동 시간 10분 늘리기"
              accessibilityRole="button"
              accessibilityState={{ disabled: !canIncreaseDuration }}
              disabled={!canIncreaseDuration}
              onPress={() =>
                onChangeWorkoutMinutes(
                  String(
                    durationMissing
                      ? CHECKIN_DURATION_MINUTES.min
                      : Math.min(
                          CHECKIN_DURATION_MINUTES.max,
                          durationMinutes + CHECKIN_DURATION_MINUTES.step,
                        ),
                  ),
                )
              }
              style={[
                styles.durationStepButton,
                !canIncreaseDuration && styles.durationStepButtonDisabled,
              ]}
            >
              <Text style={styles.durationStepButtonText}>+</Text>
            </Pressable>
          </View>
        </View>
        {recommendedDurationMinutes !== null ? (
          <View style={styles.durationGuidance}>
            <Text style={styles.durationRecommendation}>
              1회 권장 운동 시간은 {recommendedDurationMinutes}분이에요.
            </Text>
            {exceedsRecommendation ? (
              <Text
                accessibilityLiveRegion="polite"
                style={styles.durationRecommendationDetail}
              >
                권장 시간보다 길게 선택해도 괜찮아요. 오늘 가능한 시간에 맞춰
                선택해주세요.
              </Text>
            ) : null}
          </View>
        ) : null}
        {durationMissing ? (
          <Text accessibilityRole="alert" style={styles.messageText}>
            오늘 가능한 운동 시간을 {CHECKIN_DURATION_MINUTES.min}~
            {CHECKIN_DURATION_MINUTES.max}분 중에서 선택해주세요.
          </Text>
        ) : null}
        {CHECKIN_AVAILABILITY_INPUT_ENABLED ? (
          <>
            <View style={styles.availabilitySection}>
              <View style={styles.availabilityHeader}>
                <Text style={styles.numberLabel}>오늘 운동 가능한 시간대</Text>
                <Text style={styles.optionalText}>(선택)</Text>
              </View>
              {availabilitySlots.map((slot, index) => (
                <View key={index} style={styles.availabilitySlotRow}>
                  <Pressable
                    accessibilityLabel={`${index + 1}번째 가능 시간 시작 ${slot.startTime || '미선택'} 선택`}
                    accessibilityRole="button"
                    disabled={pending}
                    onPress={() => onOpenTimePicker(index, 'startTime')}
                    style={styles.availabilityTimeButton}
                  >
                    <Text
                      style={[
                        styles.availabilityTimeText,
                        !slot.startTime && styles.availabilityTimePlaceholder,
                      ]}
                    >
                      {slot.startTime || '시간:분'}
                    </Text>
                  </Pressable>
                  <Text style={styles.availabilitySeparator}>~</Text>
                  <Pressable
                    accessibilityLabel={`${index + 1}번째 가능 시간 종료 ${slot.endTime || '미선택'} 선택`}
                    accessibilityRole="button"
                    disabled={pending}
                    onPress={() => onOpenTimePicker(index, 'endTime')}
                    style={styles.availabilityTimeButton}
                  >
                    <Text
                      style={[
                        styles.availabilityTimeText,
                        !slot.endTime && styles.availabilityTimePlaceholder,
                      ]}
                    >
                      {slot.endTime || '시간:분'}
                    </Text>
                  </Pressable>
                  {availabilitySlots.length > 1 ? (
                    <Pressable
                      accessibilityLabel={`${index + 1}번째 가능 시간대 삭제`}
                      accessibilityRole="button"
                      hitSlop={8}
                      onPress={() => onRemoveAvailabilitySlot(index)}
                      style={styles.availabilityRemoveButton}
                    >
                      <DeleteIcon />
                    </Pressable>
                  ) : null}
                </View>
              ))}
              <Pressable
                accessibilityLabel="가능 시간대 추가"
                accessibilityRole="button"
                accessibilityState={{
                  disabled: availabilitySlots.length >= 8,
                }}
                disabled={availabilitySlots.length >= 8}
                onPress={onAddAvailabilitySlot}
                style={[
                  styles.availabilityAddButton,
                  availabilitySlots.length >= 8 && styles.routineActionDisabled,
                ]}
              >
                <Text style={styles.availabilityAddLabel}>＋ 시간대 추가</Text>
              </Pressable>
              <Text style={styles.availabilityHelpText}>
                운동을 시작할 수 있는 시간 범위를 입력해주세요.
              </Text>
            </View>
            {availabilityError ? (
              <Text accessibilityRole="alert" style={styles.messageText}>
                {availabilityError}
              </Text>
            ) : null}
          </>
        ) : null}
        <View style={styles.numberRow}>
          <Text style={styles.numberLabel}>
            어젯밤 수면 시간 <Text style={styles.optionalText}>(선택)</Text>
          </Text>
          <View style={styles.numberInputGroup}>
            <TextInput
              accessibilityLabel="어젯밤 수면 시간 (시간)"
              inputMode="decimal"
              onChangeText={onChangeSleepHours}
              style={styles.numberInput}
              value={draft.sleepHours}
            />
            <Text style={styles.numberSuffix}>시간</Text>
          </View>
        </View>
        {sleepInvalid ? (
          <Text accessibilityRole="alert" style={styles.messageText}>
            수면 시간은 0~24 사이로 입력해주세요.
          </Text>
        ) : null}
        <ChoiceBlock label="오늘 어디에서 운동할까요?">
          {locationCodes.map((code) => (
            <ChoiceButton
              key={code}
              label={locationLabel(code)}
              onPress={() => onChangeLocation(code)}
              selected={draft.locationCode === code}
            />
          ))}
        </ChoiceBlock>
        {locationSelectionMissing ? (
          <Text accessibilityRole="alert" style={styles.messageText}>
            {locationCodes.length === 0
              ? '운동 장소 선택지를 불러오지 못했어요. 잠시 후 다시 시도해주세요.'
              : '집 또는 헬스장을 선택해주세요.'}
          </Text>
        ) : null}
        <ChoiceBlock label="오늘 통증이 있는 부위가 있나요?">
          <ChoiceButton
            accessibilityLabel="통증 없어요"
            label="없어요"
            onPress={() => {
              setShowDiscomfortDetails(false);
              onClearPains();
            }}
            selected={!showDiscomfortDetails}
          />
          <ChoiceButton
            accessibilityLabel="통증 있어요"
            label="있어요"
            onPress={() => setShowDiscomfortDetails(true)}
            selected={showDiscomfortDetails}
          />
        </ChoiceBlock>
        {showDiscomfortDetails ? (
          <>
            <ChoiceBlock
              label="지금 불편하거나 통증이 있는 부위를 모두 선택해주세요."
              twoColumn
            >
              {DEFAULT_BODY_AREA_OPTIONS.map((option) => (
                <ChoiceButton
                  key={option.code}
                  label={option.label}
                  numberOfLines={2}
                  onPress={() => onToggleBodyArea(option.code)}
                  selected={draft.pains[option.code] !== undefined}
                  twoColumn
                />
              ))}
              {showExtendedAreas
                ? EXTENDED_BODY_AREA_OPTIONS.map((option) => (
                    <ChoiceButton
                      key={option.code}
                      label={option.label}
                      numberOfLines={2}
                      onPress={() => onToggleBodyArea(option.code)}
                      selected={draft.pains[option.code] !== undefined}
                      twoColumn
                    />
                  ))
                : null}
            </ChoiceBlock>
            <Pressable
              accessibilityLabel={
                showExtendedAreas ? '다른 부위 접기' : '다른 부위 보기'
              }
              accessibilityRole="button"
              accessibilityState={{ expanded: showExtendedAreas }}
              onPress={() => setShowExtendedAreas((visible) => !visible)}
              style={styles.extendedAreaToggle}
              testID="checkin-extended-area-toggle"
            >
              <Text style={styles.extendedAreaToggleLabel}>
                {showExtendedAreas ? '접기' : '다른 부위 보기'}
              </Text>
              <View style={styles.extendedAreaToggleIcon}>
                <View
                  style={
                    showExtendedAreas
                      ? styles.extendedAreaToggleCaretUp
                      : undefined
                  }
                  testID="checkin-extended-area-caret"
                >
                  <Svg
                    aria-hidden
                    fill="none"
                    height={s(14)}
                    viewBox="0 0 24 24"
                    width={s(14)}
                  >
                    <Path
                      d="M6 9l6 6 6-6"
                      stroke="#958476"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2.4}
                    />
                  </Svg>
                </View>
              </View>
            </Pressable>
            {legacySelectedCodes.length > 0 ? (
              <ChoiceBlock label="이전에 저장된 부위 (해제만 가능)" twoColumn>
                {legacySelectedCodes.map((code) => (
                  <ChoiceButton
                    key={code}
                    label={bodyAreaLabel(code)}
                    numberOfLines={2}
                    onPress={() => onToggleBodyArea(code)}
                    selected
                    twoColumn
                  />
                ))}
              </ChoiceBlock>
            ) : null}
          </>
        ) : null}
        {discomfortSelectionMissing ? (
          <Text accessibilityRole="alert" style={styles.messageText}>
            불편한 부위를 한 곳 이상 선택해주세요.
          </Text>
        ) : null}
        {selectedDiscomfortCodes.map((code) => (
          <View
            key={code}
            style={styles.painSliderCard}
            testID={`checkin-pain-slider-card-${bodyAreaLabel(code)}`}
          >
            <PainIntensitySlider
              bodyArea={bodyAreaLabel(code)}
              disabled={pending}
              onChange={(value) => onChangePainIntensity(code, value)}
              testIDPrefix="checkin"
              value={draft.pains[code] ?? 1}
            />
          </View>
        ))}
        <View
          accessibilityLabel="오늘 위험 신호가 있나요?"
          role="group"
          style={styles.redFlagSection}
          testID="checkin-red-flag-section"
        >
          <Text style={styles.redFlagTitle}>오늘 위험 신호가 있나요?</Text>
          <Text style={styles.redFlagBody}>
            오늘 가슴 통증이나 압박감, 평소와 다른 심한 숨참, 심한 어지럼 또는
            실신할 것 같은 느낌, 심장이 매우 빠르거나 불규칙하게 뛰는 느낌 같은
            증상이 있나요?
          </Text>
          <View style={styles.choiceRow}>
            <ChoiceButton
              accessibilityLabel="위험 신호 없어요"
              label="없어요"
              onPress={() => onSetRedFlag(false)}
              selected={draft.redFlagPresent === false}
            />
            <ChoiceButton
              accessibilityLabel="위험 신호 있어요"
              label="있어요"
              onPress={() => onSetRedFlag(true)}
              selected={draft.redFlagPresent === true}
            />
          </View>
        </View>
        {redFlagSelectionMissing ? (
          <Text accessibilityRole="alert" style={styles.messageText}>
            위험 신호 여부를 선택해주세요.
          </Text>
        ) : null}
        <Pressable
          accessibilityLabel="체크인 !"
          accessibilityRole="button"
          accessibilityState={{ disabled: saveDisabled }}
          disabled={saveDisabled}
          onPress={onSave}
          style={[
            styles.sheetSaveButton,
            saveDisabled && styles.routineActionDisabled,
          ]}
        >
          <LinearGradient
            colors={['#FEE8B1', '#FEDA99', '#FFD790']}
            end={{ x: 0.5, y: 1 }}
            locations={[0, 0.55, 1]}
            pointerEvents="none"
            start={{ x: 0.5, y: 0 }}
            style={styles.sheetSaveGradient}
            testID="home-checkin-submit-gradient"
          />
          <Text style={styles.sheetSaveLabel}>
            {pending ? '보내는 중…' : '체크인 !'}
          </Text>
        </Pressable>
      </ScrollView>
    </SheetFrame>
  );
}

export function TimePickerSheet({
  initialValue,
  onClose,
  onConfirm,
  targetField,
}: {
  initialValue: string;
  onClose: () => void;
  onConfirm: (value: string) => void;
  targetField: keyof HomeAvailabilitySlot;
}) {
  const styles = useHomeStyles();
  const match = /^(\d{2}):(\d{2})$/.exec(initialValue);
  const parsedMinute = match ? Number(match[2]) : 0;
  const normalizedMinute = Math.min(55, Math.round(parsedMinute / 5) * 5);
  const [hour, setHour] = useState(
    match ? Number(match[1]) : targetField === 'startTime' ? 0 : 12,
  );
  const [minute, setMinute] = useState(normalizedMinute);
  const title =
    targetField === 'startTime' ? '시작 시간 선택' : '종료 시간 선택';

  return (
    <SheetFrame onClose={onClose} title={title} zIndex={30}>
      <Text style={styles.timePickerIntro}>
        시간과 분을 스크롤해 선택해주세요.
      </Text>
      <View style={styles.timePickerRow}>
        <TimeWheelColumn
          accessibilityLabel="시간 선택 스크롤"
          onChange={setHour}
          options={TIME_HOURS}
          selected={hour}
          suffix="시"
        />
        <Text style={styles.timePickerColon}>:</Text>
        <TimeWheelColumn
          accessibilityLabel="분 선택 스크롤"
          onChange={setMinute}
          options={TIME_MINUTES}
          selected={minute}
          suffix="분"
        />
      </View>
      <View style={styles.timePickerActions}>
        <Pressable
          accessibilityRole="button"
          onPress={onClose}
          style={styles.timePickerCancelButton}
        >
          <Text style={styles.timePickerCancelLabel}>취소</Text>
        </Pressable>
        <Pressable
          accessibilityLabel="시간 선택 완료"
          accessibilityRole="button"
          onPress={() =>
            onConfirm(
              `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`,
            )
          }
          style={styles.timePickerConfirmButton}
        >
          <Text style={styles.timePickerConfirmLabel}>선택</Text>
        </Pressable>
      </View>
    </SheetFrame>
  );
}

function TimeWheelColumn({
  accessibilityLabel,
  onChange,
  options,
  selected,
  suffix,
}: {
  accessibilityLabel: string;
  onChange: (value: number) => void;
  options: readonly number[];
  selected: number;
  suffix: string;
}) {
  const styles = useHomeStyles();
  const scrollRef = useRef<ScrollView>(null);
  const selectedIndex = Math.max(0, options.indexOf(selected));
  const currentIndexRef = useRef(selectedIndex);
  const pendingInternalSelectionRef = useRef<number | null>(null);
  const webSettleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const webWheelGestureTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const webWheelDeltaRef = useRef(0);
  const draggingRef = useRef(false);

  const clearWebSettleTimer = useCallback(() => {
    if (webSettleTimerRef.current !== null) {
      clearTimeout(webSettleTimerRef.current);
      webSettleTimerRef.current = null;
    }
  }, []);

  const clearWebWheelGestureTimer = useCallback(() => {
    if (webWheelGestureTimerRef.current !== null) {
      clearTimeout(webWheelGestureTimerRef.current);
      webWheelGestureTimerRef.current = null;
    }
  }, []);

  const scrollToIndex = useCallback((index: number, animated: boolean) => {
    scrollRef.current?.scrollTo({
      animated,
      y: index * TIME_WHEEL_ITEM_HEIGHT,
    });
  }, []);

  const commitIndex = useCallback(
    (index: number) => {
      const boundedIndex = Math.max(0, Math.min(options.length - 1, index));
      const value = options[boundedIndex];
      if (value === undefined) return;
      currentIndexRef.current = boundedIndex;
      if (value !== selected) {
        pendingInternalSelectionRef.current = value;
        onChange(value);
      }
    },
    [onChange, options, selected],
  );

  const selectIndex = useCallback(
    (index: number, animated = true) => {
      const boundedIndex = Math.max(0, Math.min(options.length - 1, index));
      scrollToIndex(boundedIndex, animated);
      commitIndex(boundedIndex);
    },
    [commitIndex, options.length, scrollToIndex],
  );

  const settleAtOffset = useCallback(
    (offsetY: number, align = true) => {
      const index = Math.max(
        0,
        Math.min(
          options.length - 1,
          Math.round(offsetY / TIME_WHEEL_ITEM_HEIGHT),
        ),
      );
      const targetOffset = index * TIME_WHEEL_ITEM_HEIGHT;
      if (align && Math.abs(offsetY - targetOffset) > 1) {
        scrollToIndex(index, true);
      }
      commitIndex(index);
    },
    [commitIndex, options.length, scrollToIndex],
  );

  useEffect(() => {
    currentIndexRef.current = selectedIndex;
    if (pendingInternalSelectionRef.current === selected) {
      pendingInternalSelectionRef.current = null;
      return;
    }
    pendingInternalSelectionRef.current = null;
    scrollToIndex(selectedIndex, false);
  }, [scrollToIndex, selected, selectedIndex]);

  useEffect(
    () => () => {
      clearWebSettleTimer();
      clearWebWheelGestureTimer();
    },
    [clearWebSettleTimer, clearWebWheelGestureTimer],
  );

  const settleFromScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    clearWebSettleTimer();
    draggingRef.current = false;
    settleAtOffset(event.nativeEvent.contentOffset.y, false);
  };

  const handleScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (Platform.OS !== 'web' || draggingRef.current) return;
    const offsetY = event.nativeEvent.contentOffset.y;
    clearWebSettleTimer();
    webSettleTimerRef.current = setTimeout(() => {
      settleAtOffset(offsetY);
      webSettleTimerRef.current = null;
    }, 90);
  };

  const queueWheelDelta = useCallback(
    (deltaY: number, deltaMode = 0) => {
      clearWebSettleTimer();
      if (deltaY === 0) return;
      const modeMultiplier =
        deltaMode === 1 ? 16 : deltaMode === 2 ? TIME_WHEEL_ITEM_HEIGHT * 3 : 1;
      const normalizedDelta = deltaY * modeMultiplier;
      if (
        webWheelDeltaRef.current !== 0 &&
        Math.sign(webWheelDeltaRef.current) !== Math.sign(normalizedDelta)
      ) {
        webWheelDeltaRef.current = 0;
      }
      webWheelDeltaRef.current += normalizedDelta;
      clearWebWheelGestureTimer();
      webWheelGestureTimerRef.current = setTimeout(() => {
        const accumulatedDelta = webWheelDeltaRef.current;
        webWheelDeltaRef.current = 0;
        webWheelGestureTimerRef.current = null;
        const magnitude = Math.abs(accumulatedDelta);
        const steps =
          magnitude <= TIME_WHEEL_SINGLE_ITEM_DELTA
            ? 1
            : Math.min(
                TIME_WHEEL_MAX_ITEMS_PER_GESTURE,
                1 +
                  Math.round(
                    (magnitude - TIME_WHEEL_SINGLE_ITEM_DELTA) /
                      TIME_WHEEL_ACCELERATION_DELTA,
                  ),
              );
        selectIndex(
          currentIndexRef.current + Math.sign(accumulatedDelta) * steps,
        );
      }, TIME_WHEEL_GESTURE_IDLE_MS);
    },
    [clearWebSettleTimer, clearWebWheelGestureTimer, selectIndex],
  );

  const handleWheel = (
    event: NativeSyntheticEvent<{
      deltaMode?: number;
      deltaY: number;
    }>,
  ) => {
    event.preventDefault();
    queueWheelDelta(event.nativeEvent.deltaY, event.nativeEvent.deltaMode);
  };

  useEffect(() => {
    if (Platform.OS !== 'web' || scrollRef.current === null) return;
    const scrollNode = scrollRef.current.getScrollableNode?.() as
      HTMLElement | undefined;
    if (scrollNode?.addEventListener === undefined) return;
    const preventNativeWheelScroll = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      queueWheelDelta(event.deltaY, event.deltaMode);
    };
    scrollNode.addEventListener('wheel', preventNativeWheelScroll, {
      passive: false,
    });
    return () => {
      scrollNode.removeEventListener('wheel', preventNativeWheelScroll);
    };
  }, [queueWheelDelta]);

  const webWheelProps =
    Platform.OS === 'web' ? { onWheel: handleWheel } : undefined;

  return (
    <View style={styles.timeWheelColumn}>
      <ScrollView
        ref={scrollRef}
        accessibilityLabel={accessibilityLabel}
        contentContainerStyle={styles.timeWheelContent}
        decelerationRate="fast"
        disableIntervalMomentum
        nestedScrollEnabled
        onMomentumScrollBegin={() => {
          draggingRef.current = true;
          clearWebSettleTimer();
        }}
        onMomentumScrollEnd={settleFromScroll}
        onScroll={handleScroll}
        onScrollBeginDrag={() => {
          draggingRef.current = true;
          clearWebSettleTimer();
        }}
        onScrollEndDrag={(event) => {
          draggingRef.current = false;
          const velocity = event.nativeEvent.velocity?.y;
          if (velocity !== undefined && Math.abs(velocity) < 0.1) {
            settleFromScroll(event);
            return;
          }
          const offsetY = event.nativeEvent.contentOffset.y;
          clearWebSettleTimer();
          webSettleTimerRef.current = setTimeout(() => {
            settleAtOffset(offsetY);
            webSettleTimerRef.current = null;
          }, 120);
        }}
        scrollEventThrottle={16}
        showsVerticalScrollIndicator={false}
        snapToAlignment="start"
        snapToInterval={TIME_WHEEL_ITEM_HEIGHT}
        style={styles.timeWheelScroll}
        {...webWheelProps}
      >
        {options.map((value, index) => {
          const selectedOption = selected === value;
          const padded = String(value).padStart(2, '0');
          return (
            <Pressable
              accessibilityLabel={`${accessibilityLabel.startsWith('시간') ? '시간' : '분'} ${padded}${suffix}`}
              accessibilityRole="button"
              accessibilityState={{ selected: selectedOption }}
              key={value}
              onPress={() => selectIndex(index)}
              style={styles.timeWheelItem}
            >
              <Text
                style={[
                  styles.timeWheelItemText,
                  selectedOption && styles.timeWheelItemTextSelected,
                ]}
              >
                {padded}
                <Text style={styles.timeWheelItemSuffix}> {suffix}</Text>
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
      <View pointerEvents="none" style={styles.timeWheelSelection} />
    </View>
  );
}

function ChoiceBlock({
  children,
  label,
  twoColumn = false,
}: {
  children: React.ReactNode;
  label: string;
  twoColumn?: boolean;
}) {
  const styles = useHomeStyles();
  return (
    <View style={styles.checkinSection}>
      <Text style={styles.checkinSectionTitle}>{label}</Text>
      <View style={[styles.choiceRow, twoColumn && styles.choiceRowTwoColumn]}>
        {children}
      </View>
    </View>
  );
}

function ChoiceButton({
  accessibilityLabel,
  label,
  numberOfLines = 1,
  onPress,
  selected,
  twoColumn = false,
}: {
  accessibilityLabel?: string;
  label: string;
  numberOfLines?: number;
  onPress: () => void;
  selected: boolean;
  twoColumn?: boolean;
}) {
  const styles = useHomeStyles();
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.choiceButton,
        twoColumn && styles.choiceButtonTwoColumn,
        selected && styles.choiceButtonSelected,
      ]}
    >
      <Text
        numberOfLines={numberOfLines}
        style={[
          styles.choiceButtonText,
          selected && styles.choiceButtonTextSelected,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}
