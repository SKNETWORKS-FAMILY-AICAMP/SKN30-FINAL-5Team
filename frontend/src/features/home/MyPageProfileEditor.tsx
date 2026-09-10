import { CloseButton } from '../../components/CloseButton';
import * as ImagePicker from 'expo-image-picker';
import { useRef, useState } from 'react';
import {
  type GestureResponderEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import {
  bodyAreaLabel,
  experienceLevelLabel,
  primaryGoalLabel,
} from '../../api/labels';
import type {
  MeProfile,
  PainAreaInput,
  ProfileImageUpload,
  ProfileSettingsUpdateRequest,
} from '../../api/types';
import {
  Button,
  Card,
  GradientActionButton,
  InlineFeedback,
  StepCounter,
  TextField,
} from '../../components/primitives';
import { colors, radii, spacing } from '../../components/theme';
import {
  PAIN_INTENSITY_MIN,
  PainIntensitySlider,
} from '../../components/profile/PainIntensitySlider';
import { ProfileAvatar } from '../../components/profile/ProfileAvatar';
import {
  ONBOARDING_EXPERIENCE_OPTIONS,
  ONBOARDING_GOAL_OPTIONS,
  ONBOARDING_WEEKLY_COUNT,
} from '../onboarding/onboardingOptions';
import {
  BirthDateField,
  latestEligibleBirthdateIso,
} from '../onboarding/BirthDateField';
import type { MyPageProfileField } from './myPageModel';

export type MyPageEditableField = MyPageProfileField | 'basic_profile';
export type ProfileImageChange = ProfileImageUpload | null;

/**
 * A pending edit. `imageChange` only applies to the basic profile sheet, where
 * the picture is saved alongside the settings body.
 */
type EditorDraft = {
  body: ProfileSettingsUpdateRequest;
  imageChange?: ProfileImageChange;
};

type Props = {
  error?: string | null;
  field: MyPageEditableField;
  onBasicProfileChange?: (
    body: ProfileSettingsUpdateRequest,
    imageChange: ProfileImageChange | undefined,
  ) => void;
  onChange: (body: ProfileSettingsUpdateRequest) => void;
  onClose: () => void;
  pending?: boolean;
  profile: MeProfile;
};

const TITLES: Record<MyPageEditableField, string> = {
  basic_profile: '프로필 수정',
  primary_goal_code: '운동 목표 수정',
  experience_level_code: '운동 경험 수정',
  desired_weekly_workout_count: '주간 운동 횟수 수정',
  persistent_pains: '통증 부위 수정',
};

const MY_PAGE_DEFAULT_BODY_AREA_CODES = [
  'SHOULDER',
  'LOWER_BACK',
  'KNEE',
  'NECK',
  'WRIST_HAND',
  'ANKLE_FOOT',
] as const;
const MY_PAGE_EXTENDED_BODY_AREA_CODES = [
  'ELBOW',
  'UPPER_BACK',
  'HIP',
  'CHEST',
  'ABDOMEN',
] as const;
const MY_PAGE_DEFAULT_BODY_AREA_OPTIONS = MY_PAGE_DEFAULT_BODY_AREA_CODES.map(
  (code) => ({ code, label: bodyAreaLabel(code) }),
);
const MY_PAGE_EXTENDED_BODY_AREA_OPTIONS = MY_PAGE_EXTENDED_BODY_AREA_CODES.map(
  (code) => ({
    code,
    label: bodyAreaLabel(code),
  }),
);
const MY_PAGE_SELECTABLE_BODY_AREA_OPTIONS = [
  ...MY_PAGE_DEFAULT_BODY_AREA_OPTIONS,
  ...MY_PAGE_EXTENDED_BODY_AREA_OPTIONS,
];
const myPageBodyAreaOrder = new Map<string, number>(
  MY_PAGE_SELECTABLE_BODY_AREA_OPTIONS.map((option, index) => [
    option.code,
    index,
  ]),
);

export function MyPageProfileEditor({
  error = null,
  field,
  onBasicProfileChange,
  onChange,
  onClose,
  pending = false,
  profile,
}: Props) {
  const { bottom: bottomInset } = useSafeAreaInsets();
  const stopPropagation = (event: GestureResponderEvent) =>
    event.stopPropagation();
  // Edits collect into a draft; only the save button sends them. React's
  // "adjust state when inputs change" pattern: a request that stops pending
  // without an error succeeded, which clears the draft and reports the save.
  const [draft, setDraft] = useState<EditorDraft | null>(null);
  const [interactionPending, setInteractionPending] = useState(false);
  const [saveTracker, setSaveTracker] = useState({ pending, succeeded: false });
  if (saveTracker.pending !== pending) {
    const succeeded = saveTracker.pending && error === null;
    setSaveTracker({ pending, succeeded });
    if (succeeded) setDraft(null);
  }
  const saved = saveTracker.succeeded && !pending && error === null;
  const description = editorDescription(field);
  const submitDraft = () => {
    if (draft === null || pending) return;
    if (field !== 'basic_profile') {
      onChange(draft.body);
      return;
    }
    if (onBasicProfileChange) {
      onBasicProfileChange(draft.body, draft.imageChange);
    } else if (Object.keys(draft.body).length > 0) {
      onChange(draft.body);
    }
  };

  return (
    <Pressable
      accessibilityViewIsModal
      onPress={onClose}
      style={styles.overlay}
      testID="profile-editor-backdrop"
    >
      <Pressable
        onPress={stopPropagation}
        style={[styles.sheet, { paddingBottom: Math.max(16, bottomInset) }]}
        testID="profile-editor-sheet"
      >
        <View style={styles.headingRow}>
          <View style={styles.headingCopy}>
            <Text accessibilityRole="header" style={styles.title}>
              {TITLES[field]}
            </Text>
            {description ? (
              <Text style={styles.description}>{description}</Text>
            ) : null}
          </View>
          <CloseButton
            accessibilityLabel="프로필 편집 닫기"
            onPress={onClose}
          />
        </View>

        <ScrollView
          contentContainerStyle={styles.editorContent}
          keyboardShouldPersistTaps="handled"
        >
          <EditorBody
            field={field}
            onDraftChange={setDraft}
            onInteractionPendingChange={setInteractionPending}
            pending={pending}
            profile={profile}
          />
          {error ? <InlineFeedback message={error} tone="error" /> : null}
          {saved && !pending && error === null ? (
            <InlineFeedback
              message="변경 사항을 저장했어요."
              testID="profile-editor-saved"
              tone="success"
            />
          ) : null}
        </ScrollView>
        <View
          style={[
            styles.stickySaveArea,
            { paddingBottom: Math.max(spacing.sm, bottomInset) },
          ]}
        >
          <GradientActionButton
            accessibilityLabel="저장하기"
            disabled={draft === null || pending || interactionPending}
            label={pending ? '저장 중…' : '저장하기'}
            labelStyle={styles.saveLabel}
            onPress={submitDraft}
            showChevron={false}
            style={styles.saveButton}
            testID="profile-editor-save"
          />
        </View>
      </Pressable>
    </Pressable>
  );
}

function EditorBody({
  field,
  onDraftChange,
  onInteractionPendingChange,
  pending = false,
  profile,
}: Pick<Props, 'field' | 'pending' | 'profile'> & {
  onDraftChange: (draft: EditorDraft | null) => void;
  onInteractionPendingChange: (pending: boolean) => void;
}) {
  const reportBody = (body: ProfileSettingsUpdateRequest | null) =>
    onDraftChange(body === null ? null : { body });

  if (field === 'basic_profile') {
    return (
      <BasicProfileEditor
        onDraftChange={onDraftChange}
        onPickerPendingChange={onInteractionPendingChange}
        pending={pending}
        profile={profile}
      />
    );
  }

  if (field === 'primary_goal_code') {
    return (
      <SingleChoiceEditor
        current={profile.primary_goal_code}
        disabled={pending}
        onSelect={(code) =>
          reportBody(
            code === profile.primary_goal_code
              ? null
              : { primary_goal_code: code },
          )
        }
        options={mergeDescriptionOptions(
          ONBOARDING_GOAL_OPTIONS,
          profile.primary_goal_code,
          primaryGoalLabel,
        )}
      />
    );
  }

  if (field === 'experience_level_code') {
    return (
      <SingleChoiceEditor
        current={profile.experience_level_code}
        disabled={pending}
        onSelect={(code) =>
          reportBody(
            code === profile.experience_level_code
              ? null
              : { experience_level_code: code },
          )
        }
        options={mergeDescriptionOptions(
          ONBOARDING_EXPERIENCE_OPTIONS,
          profile.experience_level_code,
          experienceLevelLabel,
        )}
      />
    );
  }

  if (field === 'persistent_pains') {
    const storedPainAreas = profile.persistent_pains ?? profile.pain_areas;
    const initialPainAreas = storedPainAreas ?? [];
    return (
      <AttentionAreaEditor
        disabled={pending}
        initial={
          storedPainAreas !== undefined
            ? storedPainAreas.map((area) => area.body_area_code)
            : profile.attention_area_codes
        }
        initialPainAreas={initialPainAreas}
        onChange={(persistent_pains) =>
          reportBody(persistent_pains === null ? null : { persistent_pains })
        }
      />
    );
  }

  return (
    <DraftStepper
      decreaseLabel="주간 운동 횟수 1회 줄이기"
      increaseLabel="주간 운동 횟수 1회 늘리기"
      max={ONBOARDING_WEEKLY_COUNT.max}
      min={ONBOARDING_WEEKLY_COUNT.min}
      onDraftChange={(next) =>
        reportBody(
          next === null ? null : { desired_weekly_workout_count: next },
        )
      }
      pending={pending}
      prefix="주 "
      step={ONBOARDING_WEEKLY_COUNT.step}
      suffix="회"
      value={profile.desired_weekly_workout_count}
    />
  );
}

/** Keeps the highlighted choice local until the save button sends it. */
function SingleChoiceEditor({
  current,
  disabled,
  onSelect,
  options,
}: {
  current: string;
  disabled: boolean;
  onSelect: (code: string) => void;
  options: readonly { code: string; label: string; description: string }[];
}) {
  const [selected, setSelected] = useState(current);

  return (
    <ChoiceCard>
      {options.map((option) => (
        <DescriptionOption
          key={option.code}
          description={option.description}
          disabled={disabled}
          label={option.label}
          selected={selected === option.code}
          onPress={() => {
            setSelected(option.code);
            onSelect(option.code);
          }}
        />
      ))}
    </ChoiceCard>
  );
}

type BasicProfileForm = {
  dateOfBirth: string;
  dateOfBirthChanged: boolean;
  imageChange: ProfileImageChange | undefined;
  nickname: string;
  weightKg: string;
};

/**
 * The sheet footer owns the save button, so every edit reports the whole form
 * as a draft. An incomplete or unchanged form reports no draft, which keeps the
 * button disabled and leaves the stored profile untouched.
 */
function BasicProfileEditor({
  onDraftChange,
  onPickerPendingChange,
  pending,
  profile,
}: {
  onDraftChange: (draft: EditorDraft | null) => void;
  onPickerPendingChange: (pending: boolean) => void;
  pending: boolean;
  profile: MeProfile;
}) {
  const [form, setForm] = useState<BasicProfileForm>({
    dateOfBirth: latestEligibleBirthdateIso(),
    dateOfBirthChanged: false,
    imageChange: undefined,
    nickname: profile.nickname,
    weightKg: '',
  });
  const formRef = useRef(form);
  const [imagePickerError, setImagePickerError] = useState<string | null>(null);
  const [imagePickerPending, setImagePickerPending] = useState(false);
  const {
    dateOfBirth,
    imageChange: profileImageChange,
    nickname,
    weightKg,
  } = form;

  const nicknameError =
    nickname.trim().length < 1 || nickname.trim().length > 64
      ? '닉네임은 1~64자로 입력해주세요.'
      : null;
  const weightError = validateOptionalNumber(weightKg, 25, 300, '체중');

  const update = (patch: Partial<BasicProfileForm>) => {
    // An image picker can resolve after other fields changed. Always merge its
    // result into the latest form rather than the render that opened it.
    const next = { ...formRef.current, ...patch };
    formRef.current = next;
    setForm(next);
    onDraftChange(basicProfileDraft(next, profile));
  };

  const pickProfileImage = async () => {
    if (pending || imagePickerPending) return;
    setImagePickerPending(true);
    onPickerPendingChange(true);
    setImagePickerError(null);
    try {
      const permission =
        await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        setImagePickerError(
          '사진을 선택하려면 기기 설정에서 사진 보관함 접근을 허용해주세요.',
        );
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.85,
      });
      if (result.canceled || !result.assets[0]) return;

      const asset = result.assets[0];
      if (
        asset.type === 'video' ||
        (asset.mimeType && !asset.mimeType.startsWith('image/'))
      ) {
        setImagePickerError('이미지 파일만 프로필 사진으로 사용할 수 있어요.');
        return;
      }
      if (asset.fileSize && asset.fileSize > MAX_PROFILE_IMAGE_BYTES) {
        setImagePickerError('10MB 이하의 이미지를 선택해주세요.');
        return;
      }

      const mimeType = asset.mimeType ?? 'image/jpeg';
      update({
        imageChange: {
          uri: asset.uri,
          fileName: asset.fileName ?? defaultImageFileName(mimeType),
          mimeType,
          fileSize: asset.fileSize ?? undefined,
          webFile: asset.file ?? undefined,
        },
      });
    } catch {
      setImagePickerError(
        '사진 보관함을 열지 못했어요. 잠시 후 다시 시도해주세요.',
      );
    } finally {
      setImagePickerPending(false);
      onPickerPendingChange(false);
    }
  };

  return (
    <View style={styles.basicForm}>
      <InlineFeedback
        message="변경하지 않은 사항은 유지돼요"
        style={styles.privacyNotice}
        tone="warning"
      />
      <TextField
        accessibilityLabel="닉네임 입력"
        editable={!pending}
        error={nicknameError ?? undefined}
        label="닉네임"
        maxLength={64}
        onChangeText={(value) => update({ nickname: value })}
        value={nickname}
      />
      <View style={styles.profileImageEditor}>
        <ProfileAvatar
          profileImageUrl={
            profileImageChange === undefined
              ? profile.profile_image_url
              : profileImageChange?.uri
          }
          size={60}
          testID="profile-editor-avatar-preview"
        />
        <View style={styles.profileImageActions}>
          <Text style={styles.profileImageLabel}>프로필 사진</Text>
          <Button
            disabled={pending || imagePickerPending}
            label={
              imagePickerPending
                ? '사진 보관함 여는 중…'
                : '사진 보관함에서 선택'
            }
            onPress={() => void pickProfileImage()}
            style={styles.profileImageButton}
            tone="secondary"
          />
          {(profileImageChange?.uri ?? profile.profile_image_url) ? (
            <Button
              disabled={pending || imagePickerPending}
              label="기본 이미지로 되돌리기"
              onPress={() => {
                setImagePickerError(null);
                update({ imageChange: null });
              }}
              style={styles.profileImageButton}
              tone="secondary"
            />
          ) : null}
          <Text style={styles.profileImageHint}>이미지 파일 · 최대 10MB</Text>
        </View>
      </View>
      {imagePickerError ? (
        <InlineFeedback message={imagePickerError} tone="error" />
      ) : null}
      <BirthDateField
        compact
        disabled={pending}
        onChange={(value) =>
          update({ dateOfBirth: value, dateOfBirthChanged: true })
        }
        value={dateOfBirth}
      />
      <TextField
        accessibilityLabel="체중 입력"
        editable={!pending}
        error={weightError ?? undefined}
        inputMode="decimal"
        label="체중(kg)"
        onChangeText={(value) => update({ weightKg: value })}
        placeholder="25~300"
        value={weightKg}
      />
    </View>
  );
}

/** Reports the pending basic-profile edit, or null when it is not savable. */
function basicProfileDraft(
  form: BasicProfileForm,
  profile: MeProfile,
): EditorDraft | null {
  const nickname = form.nickname.trim();
  if (nickname.length < 1 || nickname.length > 64) return null;
  if (validateOptionalNumber(form.weightKg, 25, 300, '체중')) return null;

  const body: ProfileSettingsUpdateRequest = {};
  if (nickname !== profile.nickname) body.nickname = nickname;
  if (form.dateOfBirthChanged) body.date_of_birth = form.dateOfBirth;
  if (form.weightKg) body.weight_kg = Number(form.weightKg);
  const changedImage = form.imageChange !== undefined;
  if (!changedImage && Object.keys(body).length === 0) return null;
  return changedImage ? { body, imageChange: form.imageChange } : { body };
}

const MAX_PROFILE_IMAGE_BYTES = 10 * 1024 * 1024;

function defaultImageFileName(mimeType: string): string {
  const extension = mimeType.split('/')[1]?.replace('jpeg', 'jpg') || 'jpg';
  return `profile.${extension}`;
}

function validateOptionalNumber(
  value: string,
  min: number,
  max: number,
  label: string,
): string | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= min && parsed <= max
    ? null
    : `${label}는 ${min}~${max} 범위로 입력해주세요.`;
}

function AttentionAreaEditor({
  disabled,
  initial,
  initialPainAreas,
  onChange,
}: {
  disabled: boolean;
  initial: readonly string[];
  initialPainAreas: readonly PainAreaInput[];
  onChange: (painAreas: PainAreaInput[] | null) => void;
}) {
  const orderedInitial = orderMyPageBodyAreaCodes(initial);
  const [hasAreas, setHasAreas] = useState(orderedInitial.length > 0);
  const [selected, setSelected] = useState(orderedInitial);
  const [painIntensityScores, setPainIntensityScores] = useState<
    Partial<Record<string, number>>
  >(() =>
    Object.fromEntries(
      initialPainAreas.map((area) => [
        area.body_area_code,
        area.intensity_score,
      ]),
    ),
  );
  const [showExtendedAreas, setShowExtendedAreas] = useState(() =>
    orderedInitial.some((code) =>
      MY_PAGE_EXTENDED_BODY_AREA_OPTIONS.some((option) => option.code === code),
    ),
  );
  const selectableCodes = new Set<string>(
    MY_PAGE_SELECTABLE_BODY_AREA_OPTIONS.map((option) => option.code),
  );
  const legacySelected = selected.filter((code) => !selectableCodes.has(code));

  // An empty "있어요" selection is not savable, so it reports no draft.
  const reportDraft = (
    nextSelected: readonly string[],
    nextScores: Partial<Record<string, number>>,
    nextHasAreas: boolean,
  ) => {
    if (nextHasAreas && nextSelected.length === 0) {
      onChange(null);
      return;
    }
    onChange(
      nextSelected.map((body_area_code) => ({
        body_area_code,
        intensity_score: nextScores[body_area_code] ?? PAIN_INTENSITY_MIN,
      })),
    );
  };

  const toggleSelected = (code: string) => {
    const next = orderMyPageBodyAreaCodes(toggle(selected, code));
    const nextScores = { ...painIntensityScores };
    if (next.includes(code)) nextScores[code] = PAIN_INTENSITY_MIN;
    else delete nextScores[code];
    setSelected(next);
    setHasAreas(next.length > 0);
    setPainIntensityScores(nextScores);
    reportDraft(next, nextScores, next.length > 0);
  };

  return (
    <ChoiceCard>
      <ChipOption
        disabled={disabled}
        grow
        label="없어요"
        selected={!hasAreas}
        onPress={() => {
          setHasAreas(false);
          setSelected([]);
          setPainIntensityScores({});
          if (selected.length > 0) reportDraft([], {}, false);
        }}
      />
      <ChipOption
        disabled={disabled}
        grow
        label="있어요"
        selected={hasAreas}
        onPress={() => {
          setHasAreas(true);
          reportDraft(selected, painIntensityScores, true);
        }}
      />
      {hasAreas ? (
        <View style={styles.painDetails}>
          <View style={styles.painSection}>
            <Text style={styles.painSectionTitle}>불편한 부위</Text>
            <Text style={styles.hint}>해당하는 부위를 모두 선택해주세요.</Text>
            <View
              style={styles.optionGrid}
              testID="my-page-attention-area-grid"
            >
              {MY_PAGE_DEFAULT_BODY_AREA_OPTIONS.map((option) => (
                <ChipOption
                  key={option.code}
                  disabled={disabled}
                  grid
                  label={option.label}
                  selected={selected.includes(option.code)}
                  onPress={() => toggleSelected(option.code)}
                />
              ))}
              {showExtendedAreas
                ? MY_PAGE_EXTENDED_BODY_AREA_OPTIONS.map((option) => (
                    <ChipOption
                      key={option.code}
                      disabled={disabled}
                      grid
                      label={option.label}
                      selected={selected.includes(option.code)}
                      onPress={() => toggleSelected(option.code)}
                    />
                  ))
                : null}
            </View>
            <Pressable
              accessibilityLabel={
                showExtendedAreas ? '다른 부위 접기' : '다른 부위 보기'
              }
              accessibilityRole="button"
              accessibilityState={{ disabled, expanded: showExtendedAreas }}
              disabled={disabled}
              onPress={() => setShowExtendedAreas((visible) => !visible)}
              style={styles.extendedAreaToggle}
              testID="my-page-extended-area-toggle"
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
                  testID="my-page-extended-area-caret"
                >
                  <Svg
                    aria-hidden
                    fill="none"
                    height={14}
                    viewBox="0 0 24 24"
                    width={14}
                  >
                    <Path
                      d="M6 9l6 6 6-6"
                      stroke={colors.textMuted}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2.4}
                    />
                  </Svg>
                </View>
              </View>
            </Pressable>
            {legacySelected.length > 0 ? (
              <View style={styles.painSection}>
                <Text style={styles.painSectionTitle}>
                  이전에 저장된 부위 (해제만 가능)
                </Text>
                <View style={styles.optionGrid}>
                  {legacySelected.map((code) => (
                    <ChipOption
                      key={code}
                      disabled={disabled}
                      grid
                      label={bodyAreaLabel(code)}
                      selected
                      onPress={() => toggleSelected(code)}
                    />
                  ))}
                </View>
              </View>
            ) : null}
          </View>
          {selected.length > 0 ? (
            <View
              style={styles.painSliderList}
              testID="my-page-pain-slider-list"
            >
              {selected.map((code) => (
                <View
                  key={code}
                  style={styles.painSliderCard}
                  testID={`my-page-pain-slider-card-${bodyAreaLabel(code)}`}
                >
                  <PainIntensitySlider
                    bodyArea={bodyAreaLabel(code)}
                    disabled={disabled}
                    onChange={(value) => {
                      const nextScores = {
                        ...painIntensityScores,
                        [code]: value,
                      };
                      setPainIntensityScores(nextScores);
                      reportDraft(selected, nextScores, hasAreas);
                    }}
                    testIDPrefix="my-page"
                    value={painIntensityScores[code] ?? PAIN_INTENSITY_MIN}
                  />
                </View>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}
    </ChoiceCard>
  );
}

/** Keeps the stepped value local until the save button sends it. */
function DraftStepper({
  decreaseLabel,
  increaseLabel,
  max,
  min,
  onDraftChange,
  pending,
  prefix = '',
  step,
  suffix,
  value,
}: {
  decreaseLabel: string;
  increaseLabel: string;
  max: number;
  min: number;
  onDraftChange: (value: number | null) => void;
  pending: boolean;
  prefix?: string;
  step: number;
  suffix: string;
  value: number;
}) {
  const [current, setCurrent] = useState(value);

  return (
    <StepCounter
      compact
      decreaseLabel={decreaseLabel}
      disabled={pending}
      increaseLabel={increaseLabel}
      max={max}
      min={min}
      onChange={(next) => {
        setCurrent(next);
        onDraftChange(next === value ? null : next);
      }}
      prefix={prefix}
      step={step}
      suffix={suffix}
      value={current}
    />
  );
}

function ChoiceCard({ children }: { children: React.ReactNode }) {
  return <Card style={styles.choiceCard}>{children}</Card>;
}

function ChipOption({
  disabled,
  grid = false,
  grow = false,
  label,
  onPress,
  selected,
}: {
  disabled: boolean;
  grid?: boolean;
  grow?: boolean;
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked: selected, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.chip,
        grow && styles.chipGrow,
        grid && styles.chipGrid,
        selected && styles.chipSelected,
      ]}
    >
      <Text
        adjustsFontSizeToFit={grid}
        minimumFontScale={grid ? 0.85 : undefined}
        numberOfLines={grid ? 1 : undefined}
        style={[styles.chipLabel, selected && styles.chipLabelSelected]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function DescriptionOption({
  description,
  disabled,
  label,
  onPress,
  selected,
}: {
  description: string;
  disabled: boolean;
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="radio"
      accessibilityState={{ checked: selected, disabled }}
      disabled={disabled || selected}
      onPress={onPress}
      style={[styles.descriptionOption, selected && styles.chipSelected]}
    >
      <Text
        style={[styles.descriptionTitle, selected && styles.chipLabelSelected]}
      >
        {label}
      </Text>
      <Text
        style={[
          styles.descriptionText,
          selected && styles.descriptionTextSelected,
        ]}
      >
        {description}
      </Text>
    </Pressable>
  );
}

function editorDescription(field: MyPageEditableField): string {
  if (field === 'basic_profile') return '';
  if (field === 'persistent_pains') {
    return '부위와 통증 정도를 확인한 뒤 저장해주세요.';
  }
  return '';
}

function orderMyPageBodyAreaCodes(codes: readonly string[]): string[] {
  return [...codes].sort(
    (left, right) =>
      (myPageBodyAreaOrder.get(left) ?? Number.MAX_SAFE_INTEGER) -
      (myPageBodyAreaOrder.get(right) ?? Number.MAX_SAFE_INTEGER),
  );
}

function toggle(values: readonly string[], code: string): string[] {
  return values.includes(code)
    ? values.filter((value) => value !== code)
    : [...values, code];
}

function mergeDescriptionOptions(
  options: readonly { code: string; label: string; description: string }[],
  current: string,
  labelFor: (code: string) => string,
): readonly { code: string; label: string; description: string }[] {
  return options.some((option) => option.code === current)
    ? options
    : [
        { code: current, label: labelFor(current), description: '현재 선택' },
        ...options,
      ];
}

const styles = StyleSheet.create({
  overlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(20,28,16,0.5)',
    zIndex: 30,
    elevation: 30,
  },
  sheet: {
    maxHeight: '90%',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    backgroundColor: colors.canvas,
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 16,
  },
  headingRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  headingCopy: { flex: 1, gap: 3 },
  title: { color: colors.text, fontSize: 19, fontWeight: '800' },
  description: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  editorContent: { gap: 10, paddingTop: 12, paddingBottom: spacing.sm },
  stickySaveArea: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.canvas,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
  },
  saveButton: {
    width: 'auto',
    minWidth: 184,
    height: 48,
    alignSelf: 'center',
    paddingHorizontal: 32,
  },
  saveLabel: { fontSize: 17, fontWeight: '800' },
  basicForm: { gap: spacing.sm },
  privacyNotice: { paddingHorizontal: 11, paddingVertical: 8 },
  profileImageEditor: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  profileImageActions: { minWidth: 0, flex: 1, gap: 6 },
  profileImageButton: { minHeight: 44 },
  profileImageLabel: { color: colors.text, fontSize: 14, fontWeight: '700' },
  profileImageHint: { color: colors.textMuted, fontSize: 12 },
  choiceCard: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    padding: 14,
  },
  chip: {
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.canvas,
    paddingHorizontal: 15,
    paddingVertical: 12,
  },
  chipGrow: { minWidth: 72, flexGrow: 1, alignItems: 'center' },
  chipGrid: {
    width: '48.5%',
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.primary,
  },
  chipLabel: { color: colors.text, fontSize: 14, fontWeight: '600' },
  chipLabelSelected: { color: colors.surface },
  descriptionOption: {
    width: '100%',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.canvas,
    padding: 12,
  },
  descriptionTitle: { color: colors.text, fontSize: 14, fontWeight: '700' },
  descriptionText: {
    marginTop: 3,
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  descriptionTextSelected: { color: 'rgba(255, 255, 255, 0.75)' },
  painDetails: { width: '100%', gap: spacing.md },
  painSection: {
    width: '100%',
    gap: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
  },
  hint: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  optionGrid: {
    width: '100%',
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    columnGap: spacing.sm,
    rowGap: spacing.sm,
  },
  painSectionTitle: { color: colors.text, fontSize: 14, fontWeight: '700' },
  extendedAreaToggle: {
    minHeight: 36,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.sm,
  },
  extendedAreaToggleLabel: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '600',
  },
  extendedAreaToggleIcon: {
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: colors.surface,
  },
  extendedAreaToggleCaretUp: {
    transform: [{ rotate: '180deg' }],
  },
  painSliderList: { width: '100%', gap: spacing.sm },
  painSliderCard: {
    borderWidth: 1,
    borderColor: '#E8C3B8',
    borderRadius: 14,
    backgroundColor: '#FFFDFC',
    paddingVertical: 12,
    paddingHorizontal: 14,
  },
});
