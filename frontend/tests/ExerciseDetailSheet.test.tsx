import { render, screen } from '@testing-library/react-native';

import type { Api } from '../src/api/endpoints';
import { ApiError } from '../src/api/errors';
import type { ExerciseDetailResponse } from '../src/api/types';
import { ExerciseDetailSheet } from '../src/features/workout/ExerciseDetailSheet';

function detailApi(response: ExerciseDetailResponse): Pick<Api, 'getExercise'> {
  return {
    getExercise: jest.fn(async () => response),
  };
}

const baseDetail: ExerciseDetailResponse = {
  exercise_id: 'exercise-1',
  exercise_name: '의자 스쿼트',
  training_type_code: 'STRENGTH',
  body_focus_code: 'GLUTES',
  primary_body_area_codes: ['HIP', 'KNEE'],
  instruction_summary: '의자 앞에서 천천히 앉았다가 일어나요.',
  form_cues: ['무릎과 발끝의 방향을 맞춰요.'],
  media_asset_key: null,
  media_url: null,
  mascot_animation_asset_key: null,
  instruction_content_version: 'test-v1',
};

describe('ExerciseDetailSheet', () => {
  it('keeps the loading state while detail content is pending', () => {
    const api: Pick<Api, 'getExercise'> = {
      getExercise: jest.fn(
        () => new Promise<ExerciseDetailResponse>(() => undefined),
      ),
    };

    render(<ExerciseDetailSheet api={api} exerciseId="exercise-1" />);

    expect(screen.getByText('자세 정보를 불러오는 중이에요')).toBeOnTheScreen();
  });

  it('keeps the permission error and retry state', async () => {
    const api: Pick<Api, 'getExercise'> = {
      getExercise: jest.fn(async () => {
        throw new ApiError({
          kind: 'permission',
          code: 'ACCOUNT_DISABLED',
          status: 403,
          message: '이 계정으로는 운동 정보를 볼 수 없습니다.',
        });
      }),
    };

    render(<ExerciseDetailSheet api={api} exerciseId="exercise-1" />);

    expect(
      await screen.findByRole('alert', {
        name: '이 계정으로는 운동 정보를 볼 수 없습니다.',
      }),
    ).toBeOnTheScreen();
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeOnTheScreen();
  });

  it('shows server-separated steps and cautions in the requested section order', async () => {
    render(
      <ExerciseDetailSheet
        api={detailApi({
          ...baseDetail,
          instruction_steps: [
            '발을 골반 너비로 두고 서요.',
            '엉덩이를 뒤로 보내며 앉아요.',
          ],
          cautions: ['의자가 미끄러지지 않는지 확인해요.'],
        })}
        exerciseId="exercise-1"
      />,
    );

    await screen.findByTestId('exercise-instruction-content');

    expect(
      screen.getAllByRole('header').map((header) => header.props.children),
    ).toEqual(['사용 근육', '주의 부위', '자세 설명', '주의사항']);
    expect(
      screen.getByText('해당 부위에 통증이 있는 경우 주의가 필요해요.'),
    ).toBeOnTheScreen();
    expect(screen.getByText('둔근')).toBeOnTheScreen();
    expect(
      screen.getByText('1. 발을 골반 너비로 두고 서요.'),
    ).toBeOnTheScreen();
    expect(
      screen.getByText('2. 엉덩이를 뒤로 보내며 앉아요.'),
    ).toBeOnTheScreen();
    expect(
      screen.getByText('의자가 미끄러지지 않는지 확인해요.'),
    ).toBeOnTheScreen();
  }, 15000);

  it('uses the legacy summary and form cues when additive fields are absent', async () => {
    render(
      <ExerciseDetailSheet
        api={detailApi(baseDetail)}
        exerciseId="exercise-1"
      />,
    );

    expect(
      await screen.findByText('의자 앞에서 천천히 앉았다가 일어나요.'),
    ).toBeOnTheScreen();
    expect(screen.getByText('무릎과 발끝의 방향을 맞춰요.')).toBeOnTheScreen();
    expect(screen.queryByText(/^1\. /)).toBeNull();
  });

  it('shows every reviewed household-equipment guide field at home', async () => {
    render(
      <ExerciseDetailSheet
        api={detailApi({
          ...baseDetail,
          instruction_steps: ['의자 앞에 서요.'],
          cautions: ['의자의 고정 상태를 확인해요.'],
          household_equipment_guides: [
            {
              equipment_code: 'CHAIR',
              proposal_ko: '등받이가 있는 튼튼한 의자를 사용해요.',
              examples_ko: ['식탁 의자', '고정형 책상 의자'],
              cautions_ko: ['바퀴가 달린 의자는 사용하지 않아요.'],
            },
          ],
        })}
        exerciseId="exercise-1"
        guideContext={{
          locationCode: 'HOME',
          availableEquipmentCodes: ['CHAIR'],
        }}
      />,
    );

    expect(await screen.findByText('집 생활도구 안내')).toBeOnTheScreen();
    expect(screen.getByText('의자 활용')).toBeOnTheScreen();
    expect(
      screen.getByText('등받이가 있는 튼튼한 의자를 사용해요.'),
    ).toBeOnTheScreen();
    expect(screen.getByText('활용 예시')).toBeOnTheScreen();
    expect(screen.getByText('식탁 의자')).toBeOnTheScreen();
    expect(screen.getByText('사용 시 주의사항')).toBeOnTheScreen();
    expect(
      screen.getByText('바퀴가 달린 의자는 사용하지 않아요.'),
    ).toBeOnTheScreen();
  });

  it('shows only available gym equipment guidance as a reference', async () => {
    render(
      <ExerciseDetailSheet
        api={detailApi({
          ...baseDetail,
          household_equipment_guides: [
            {
              equipment_code: 'CHAIR',
              proposal_ko: '집에서만 보여야 해요.',
              examples_ko: [],
              cautions_ko: [],
            },
          ],
          gym_equipment_starting_guides: [
            {
              equipment_code: 'BARBELL',
              proposal_ko: '빈 바로 움직임을 확인해요.',
              examples_ko: ['20kg 올림픽 바'],
              cautions_ko: ['무게보다 자세를 먼저 확인해요.'],
            },
            {
              equipment_code: 'DUMBBELL',
              proposal_ko: '없는 장비 안내예요.',
              examples_ko: [],
              cautions_ko: [],
            },
          ],
        })}
        exerciseId="exercise-1"
        guideContext={{
          locationCode: 'GYM',
          availableEquipmentCodes: ['BARBELL'],
        }}
      />,
    );

    expect(await screen.findByText('헬스장 장비 시작 안내')).toBeOnTheScreen();
    expect(screen.getByText('빈 바로 움직임을 확인해요.')).toBeOnTheScreen();
    expect(screen.getByText(/시작 무게는 참고값/)).toBeOnTheScreen();
    expect(screen.queryByText('집에서만 보여야 해요.')).toBeNull();
    expect(screen.queryByText('없는 장비 안내예요.')).toBeNull();
  });

  it('keeps legacy focus rendering and hides guides when context is missing', async () => {
    render(
      <ExerciseDetailSheet
        api={detailApi({
          ...baseDetail,
          body_focus_code: undefined,
          household_equipment_guides: [
            {
              equipment_code: 'CHAIR',
              proposal_ko: '장소가 확인되어야 보여요.',
              examples_ko: [],
              cautions_ko: [],
            },
          ],
        })}
        exerciseId="exercise-1"
      />,
    );

    expect(await screen.findByText('고관절, 무릎')).toBeOnTheScreen();
    expect(screen.getByRole('header', { name: '사용 근육' })).toBeOnTheScreen();
    expect(screen.queryByRole('header', { name: '주의 부위' })).toBeNull();
    expect(screen.queryByText('장소가 확인되어야 보여요.')).toBeNull();
  });
});
