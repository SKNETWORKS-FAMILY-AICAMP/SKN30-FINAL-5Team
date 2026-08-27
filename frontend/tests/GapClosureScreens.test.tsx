/**
 * Coverage for the gap-closure wiring: the reviewed exercise catalog browser
 * and the account screen's profile-goal and optional-consent editing.
 *
 * Screens render what the server answers and send only what the user changed;
 * nothing here invents catalog content or consent states client-side.
 */

import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';

import type { Api } from '../src/api/endpoints';
import { bodyFocusLabel, equipmentLabel } from '../src/api/labels';
import type {
  ConsentResponse,
  ExerciseListResponse,
  MeResponse,
} from '../src/api/types';
import { BackgroundBands } from '../src/components/brand/BrandChrome';
import { ExerciseCatalogScreen } from '../src/features/catalog/ExerciseCatalogScreen';
import { AccountScreen } from '../src/features/profile/AccountScreen';

function exercisePage(
  names: string[],
  nextCursor: string | null = null,
): ExerciseListResponse {
  return {
    items: names.map((name, index) => ({
      id: `ex-${index}-${name}`,
      name,
      training_type_code: 'STRENGTH',
      difficulty_code: 'BEGINNER',
      primary_body_area_codes: ['KNEE'],
      required_equipment_codes: ['MAT', 'STABILITY_BALL', 'CHAIR'],
      media_asset_key: null,
    })),
    next_cursor: nextCursor,
    catalog_version: 'catalog-test-v1',
  };
}

describe('ExerciseCatalogScreen', () => {
  // 첫 테스트는 모듈 변환 비용까지 흡수하므로 cold cache에서 여유를 둔다.
  it('lists the approved catalog and reloads when a filter changes', async () => {
    const queries: object[] = [];
    const api = {
      listExercises: async (query: object) => {
        queries.push(query);
        return exercisePage(['스쿼트', '런지']);
      },
      getExercise: async () => {
        throw new Error('not used');
      },
    } as unknown as Pick<Api, 'listExercises' | 'getExercise'>;

    const view = render(<ExerciseCatalogScreen api={api} onBack={() => {}} />);

    expect(await screen.findByText('스쿼트')).toBeTruthy();
    expect(view.UNSAFE_queryByType(BackgroundBands)).toBeNull();
    expect(screen.getByText('런지')).toBeTruthy();
    expect(screen.getAllByText('매트, 짐볼, 의자')).toHaveLength(2);
    expect(screen.getByText('카탈로그 버전 catalog-test-v1')).toBeTruthy();

    fireEvent.press(screen.getByText('스트레칭'));
    await waitFor(() => {
      expect(queries.length).toBeGreaterThanOrEqual(2);
    });
    expect(queries.at(-1)).toMatchObject({ trainingTypeCode: 'MOBILITY' });
  }, 15000);

  it('does not expose an unknown equipment machine code', () => {
    expect(equipmentLabel('FUTURE_EQUIPMENT')).toBe('확인되지 않은 항목');
  });

  it('labels catalog-v2 body focus and equipment codes', () => {
    expect(bodyFocusLabel('CHEST')).toBe('가슴');
    expect(bodyFocusLabel('HAMSTRINGS')).toBe('햄스트링');
    expect(bodyFocusLabel('CARDIO')).toBe('유산소');
    expect(bodyFocusLabel('MOBILITY')).toBe('가동성');
    expect(equipmentLabel('EZ_BAR')).toBe('이지바');
    expect(equipmentLabel('FOAM_ROLLER')).toBe('폼롤러');
  });

  it('pages with the server cursor instead of refetching page one', async () => {
    const cursors: (string | undefined)[] = [];
    const api = {
      listExercises: async (query: { cursor?: string }) => {
        cursors.push(query.cursor);
        return query.cursor === undefined
          ? exercisePage(['스쿼트'], 'cursor-2')
          : exercisePage(['플랭크'], null);
      },
      getExercise: async () => {
        throw new Error('not used');
      },
    } as unknown as Pick<Api, 'listExercises' | 'getExercise'>;

    render(<ExerciseCatalogScreen api={api} onBack={() => {}} />);

    fireEvent.press(await screen.findByText('더 보기'));

    expect(await screen.findByText('플랭크')).toBeTruthy();
    // 첫 페이지 항목은 그대로 유지된다.
    expect(screen.getByText('스쿼트')).toBeTruthy();
    expect(cursors).toEqual([undefined, 'cursor-2']);
  });
});

function meWith(): MeResponse {
  return {
    user_id: 'user-1',
    status_code: 'ACTIVE',
    onboarding_completed: true,
    premium_status_code: 'NOT_AVAILABLE',
    ai_trial_started_at: '2026-08-19T00:00:00+09:00',
    ai_trial_ends_at: '2026-08-27T00:00:00+09:00',
    profile: {
      nickname: '헬끼',
      age: null,
      primary_goal_code: 'GENERAL_FITNESS',
      experience_level_code: 'BEGINNER',
      timezone: 'Asia/Seoul',
      preferred_location_code: 'HOME',
      default_requested_duration_minutes: 30,
      desired_weekly_workout_count: 3,
      coaching_style_code: 'SUPPORTIVE',
      profile_version: 1,
      attention_area_codes: [],
      preferred_exercise_type_codes: [],
      available_location_codes: ['HOME'],
    },
  } as unknown as MeResponse;
}

function consentsOf(marketing: boolean): ConsentResponse {
  return {
    user_id: 'user-1',
    consents: [
      'GENERAL_PERSONAL_DATA',
      'SENSITIVE_DATA',
      'WEARABLE_INTEGRATION',
      'CALENDAR_INTEGRATION',
      'MARKETING',
    ].map((code) => ({
      consent_type_code: code,
      granted:
        code === 'GENERAL_PERSONAL_DATA' ||
        code === 'SENSITIVE_DATA' ||
        (code === 'MARKETING' && marketing),
      policy_version: 'consent-test-v1',
      updated_at: '2026-08-19T00:00:00+09:00',
    })),
  };
}

function accountApi() {
  const patched: object[] = [];
  const putConsents: object[] = [];
  const api = {
    getConsents: async () => consentsOf(false),
    replaceConsents: async (body: object) => {
      putConsents.push(body);
      return consentsOf(true);
    },
    updateProfileSettings: async (body: object) => {
      patched.push(body);
      return { profile_version: 2, updated_at: '2026-08-19T01:00:00+09:00' };
    },
    requestAccountDeletion: async () => {
      throw new Error('not used');
    },
  } as unknown as Api;
  return { api, patched, putConsents };
}

describe('AccountScreen editing', () => {
  it('shows the location label without an equipment profile row', async () => {
    const { api } = accountApi();
    render(
      <AccountScreen
        api={api}
        me={meWith()}
        onBack={() => {}}
        onSignOut={() => {}}
      />,
    );

    expect(screen.getByText('집')).toBeOnTheScreen();
    expect(screen.queryByText('장비')).toBeNull();
    expect(screen.queryByText('HOME')).toBeNull();
  });

  it('sends only the changed goal fields through PATCH /me/profile', async () => {
    const { api, patched } = accountApi();
    render(
      <AccountScreen
        api={api}
        me={meWith()}
        onBack={() => {}}
        onSignOut={() => {}}
      />,
    );

    fireEvent.press(await screen.findByLabelText('희망 운동 시간 늘리기'));
    fireEvent.press(screen.getByText('목표 저장'));

    await waitFor(() => {
      expect(patched).toHaveLength(1);
    });
    // 바꾸지 않은 주간 목표는 요청에 포함되지 않는다.
    expect(patched[0]).toEqual({ default_requested_duration_minutes: 35 });
  });

  it('toggles an optional consent and keeps the required pair granted', async () => {
    const { api, putConsents } = accountApi();
    render(
      <AccountScreen
        api={api}
        me={meWith()}
        onBack={() => {}}
        onSignOut={() => {}}
      />,
    );

    fireEvent.press(await screen.findByText('마케팅 정보 수신'));
    fireEvent.press(screen.getByText('동의 변경 저장'));

    await waitFor(() => {
      expect(putConsents).toHaveLength(1);
    });
    expect(putConsents[0]).toMatchObject({
      general_personal_data: true,
      sensitive_data: true,
      marketing: true,
    });
  });

  it('offers no withdrawal control for the required consents', async () => {
    const { api } = accountApi();
    render(
      <AccountScreen
        api={api}
        me={meWith()}
        onBack={() => {}}
        onSignOut={() => {}}
      />,
    );

    await screen.findByText('마케팅 정보 수신');
    expect(screen.queryByText('민감정보 수집')).toBeNull();
    expect(
      screen.getByText(
        '필수 동의는 서비스 이용에 필요해 여기서 바꿀 수 없어요.',
      ),
    ).toBeTruthy();
  });
});
