import type { Api } from '../../api/endpoints';
import { ApiError } from '../../api/errors';
import type { ExerciseDetailResponse, ExerciseListItem } from '../../api/types';

export const EXERCISE_CATALOG_PREVIEW_OPTIONS = [
  { id: 'loaded', label: '목록 있음' },
  { id: 'empty', label: '목록 없음' },
  { id: 'error', label: '오류' },
] as const;

export type ExerciseCatalogPreviewState =
  (typeof EXERCISE_CATALOG_PREVIEW_OPTIONS)[number]['id'];

const EXERCISES: ExerciseListItem[] = [
  {
    id: 'preview-chair-squat',
    name: '의자 스쿼트',
    training_type_code: 'STRENGTH',
    difficulty_code: 'BEGINNER',
    primary_body_area_codes: ['HIP', 'KNEE'],
    required_equipment_codes: ['CHAIR'],
    media_asset_key: null,
  },
  {
    id: 'preview-band-row',
    name: '밴드 로우',
    training_type_code: 'STRENGTH',
    difficulty_code: 'BEGINNER',
    primary_body_area_codes: ['UPPER_BACK', 'ELBOW'],
    required_equipment_codes: ['RESISTANCE_BAND'],
    media_asset_key: null,
  },
  {
    id: 'preview-stationary-bike',
    name: '실내 자전거',
    training_type_code: 'CARDIO',
    difficulty_code: 'BEGINNER',
    primary_body_area_codes: ['HIP', 'KNEE'],
    required_equipment_codes: ['STATIONARY_BIKE'],
    media_asset_key: null,
  },
  {
    id: 'preview-shoulder-mobility',
    name: '밴드 어깨 가동성',
    training_type_code: 'MOBILITY',
    difficulty_code: 'BEGINNER',
    primary_body_area_codes: ['SHOULDER', 'UPPER_BACK'],
    required_equipment_codes: ['STRETCH_STRAP'],
    media_asset_key: null,
  },
  {
    id: 'preview-dead-bug',
    name: '데드 버그',
    training_type_code: 'STRENGTH',
    difficulty_code: 'INTERMEDIATE',
    primary_body_area_codes: ['ABDOMEN', 'LOWER_BACK'],
    required_equipment_codes: ['MAT'],
    media_asset_key: null,
  },
];

const EXERCISE_DETAILS: Record<string, ExerciseDetailResponse> = {
  'preview-chair-squat': {
    exercise_id: 'preview-chair-squat',
    exercise_name: '의자 스쿼트',
    training_type_code: 'STRENGTH',
    primary_body_area_codes: ['HIP', 'KNEE'],
    instruction_summary:
      '의자 앞에 서서 엉덩이를 뒤로 보내며 천천히 앉았다가 다시 일어나요.',
    form_cues: [
      '무릎과 발끝이 같은 방향을 향하게 해요.',
      '의자에 닿는 순간에도 몸의 긴장을 유지해요.',
    ],
    media_asset_key: null,
    mascot_animation_asset_key: null,
    instruction_content_version: 'preview-v1',
  },
  'preview-band-row': {
    exercise_id: 'preview-band-row',
    exercise_name: '밴드 로우',
    training_type_code: 'STRENGTH',
    primary_body_area_codes: ['UPPER_BACK', 'ELBOW'],
    instruction_summary:
      '밴드를 안정적으로 고정하고 팔꿈치를 몸 뒤로 당겨 등을 모아요.',
    form_cues: [
      '어깨가 귀 쪽으로 올라가지 않게 해요.',
      '허리를 곧게 유지해요.',
    ],
    media_asset_key: null,
    mascot_animation_asset_key: null,
    instruction_content_version: 'preview-v1',
  },
  'preview-stationary-bike': {
    exercise_id: 'preview-stationary-bike',
    exercise_name: '실내 자전거',
    training_type_code: 'CARDIO',
    primary_body_area_codes: ['HIP', 'KNEE'],
    instruction_summary: '편안한 강도로 페달을 일정하게 밟아요.',
    form_cues: ['무릎이 과하게 펴지지 않도록 안장 높이를 맞춰요.'],
    media_asset_key: null,
    mascot_animation_asset_key: null,
    instruction_content_version: 'preview-v1',
  },
  'preview-shoulder-mobility': {
    exercise_id: 'preview-shoulder-mobility',
    exercise_name: '밴드 어깨 가동성',
    training_type_code: 'MOBILITY',
    primary_body_area_codes: ['SHOULDER', 'UPPER_BACK'],
    instruction_summary:
      '스트랩을 넓게 잡고 통증 없는 범위에서 천천히 움직여요.',
    form_cues: ['반동을 쓰지 않아요.', '불편함이 생기면 범위를 줄여요.'],
    media_asset_key: null,
    mascot_animation_asset_key: null,
    instruction_content_version: 'preview-v1',
  },
  'preview-dead-bug': {
    exercise_id: 'preview-dead-bug',
    exercise_name: '데드 버그',
    training_type_code: 'STRENGTH',
    primary_body_area_codes: ['ABDOMEN', 'LOWER_BACK'],
    instruction_summary:
      '등을 바닥에 편안히 붙이고 팔다리를 번갈아 천천히 뻗어요.',
    form_cues: ['허리가 바닥에서 뜨지 않는 범위만 움직여요.'],
    media_asset_key: null,
    mascot_animation_asset_key: null,
    instruction_content_version: 'preview-v1',
  },
};

function previewError(): ApiError {
  return new ApiError({
    kind: 'unavailable',
    code: 'CATALOG_UNAVAILABLE',
    status: 503,
    message: '운동 카탈로그를 불러오지 못했어요.',
  });
}

export function createExerciseCatalogPreviewApi(
  state: ExerciseCatalogPreviewState,
): Pick<Api, 'listExercises' | 'getExercise'> {
  return {
    async listExercises(query = {}) {
      if (state === 'error') {
        throw previewError();
      }
      if (state === 'empty') {
        return {
          items: [],
          next_cursor: null,
          catalog_version: 'exercise-catalog-v2.0.0-final',
        };
      }

      const filtered = EXERCISES.filter(
        (exercise) =>
          (query.trainingTypeCode === undefined ||
            exercise.training_type_code === query.trainingTypeCode) &&
          (query.difficultyCode === undefined ||
            exercise.difficulty_code === query.difficultyCode) &&
          (query.bodyAreaCode === undefined ||
            exercise.primary_body_area_codes.includes(query.bodyAreaCode)) &&
          (query.equipmentCode === undefined ||
            exercise.required_equipment_codes.includes(query.equipmentCode)),
      );
      const secondPage = query.cursor === 'preview-page-2';

      return {
        items: secondPage ? filtered.slice(3) : filtered.slice(0, 3),
        next_cursor:
          !secondPage && filtered.length > 3 ? 'preview-page-2' : null,
        catalog_version: 'exercise-catalog-v2.0.0-final',
      };
    },

    async getExercise(exerciseId) {
      if (state === 'error') {
        throw previewError();
      }
      const detail = EXERCISE_DETAILS[exerciseId];
      if (detail === undefined) {
        throw new ApiError({
          kind: 'notFound',
          code: 'EXERCISE_NOT_FOUND',
          status: 404,
          message: '운동 설명을 찾을 수 없어요.',
        });
      }
      return detail;
    },
  };
}
