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
import { StyleSheet } from 'react-native';

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
      body_focus_code: 'QUADRICEPS',
      primary_body_area_codes: ['KNEE'],
      required_equipment_codes: ['MAT', 'STABILITY_BALL', 'CHAIR'],
      media_asset_key: null,
    })),
    next_cursor: nextCursor,
    catalog_version: 'catalog-test-v1',
  };
}

describe('ExerciseCatalogScreen', () => {
  it('returns from a centered list header', async () => {
    const onBack = jest.fn();
    const api = {
      listExercises: async () => exercisePage([]),
      getExercise: async () => {
        throw new Error('not used');
      },
    } as unknown as Pick<Api, 'listExercises' | 'getExercise'>;

    render(<ExerciseCatalogScreen api={api} onBack={onBack} />);
    await screen.findByText('이 부위의 운동이 아직 없어요.');
    expect(
      screen.queryByText('운동 계획에 활용되는 운동을 모아봤어요.'),
    ).toBeNull();

    const backButton = screen.getByRole('button', { name: '돌아가기' });
    expect(StyleSheet.flatten(backButton.props.style)).toMatchObject({
      width: 44,
      height: 44,
      alignItems: 'center',
      justifyContent: 'center',
    });
    expect(
      StyleSheet.flatten(
        screen.getByTestId('exercise-catalog-back-icon').props.style,
      ),
    ).toMatchObject({
      width: 12,
      height: 12,
      borderBottomWidth: 2.5,
      borderLeftWidth: 2.5,
      transform: [{ rotate: '45deg' }],
    });
    expect(
      StyleSheet.flatten(
        screen.getByTestId('exercise-catalog-header-copy').props.style,
      ),
    ).toMatchObject({ flex: 1, alignItems: 'center' });
    expect(
      StyleSheet.flatten(
        screen.getByTestId('exercise-catalog-header-spacer').props.style,
      ),
    ).toMatchObject({ width: 44, height: 44 });

    fireEvent.press(backButton);
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  // 첫 테스트는 모듈 변환 비용까지 흡수하므로 cold cache에서 여유를 둔다.
  it('filters the approved catalog by its representative exercise focus', async () => {
    const queries: object[] = [];
    const api = {
      listExercises: async (query: object) => {
        queries.push(query);
        const page = exercisePage(['스쿼트', '푸시업']);
        return {
          ...page,
          items: page.items.map((item, index) => ({
            ...item,
            body_focus_code: index === 0 ? 'QUADRICEPS' : 'CHEST',
          })),
        };
      },
      getExercise: async () => {
        throw new Error('not used');
      },
    } as unknown as Pick<Api, 'listExercises' | 'getExercise'>;

    const view = render(<ExerciseCatalogScreen api={api} onBack={() => {}} />);

    expect(
      await screen.findByText('스쿼트', undefined, { timeout: 5000 }),
    ).toBeTruthy();
    expect(view.UNSAFE_queryByType(BackgroundBands)).toBeNull();
    expect(screen.getByText('푸시업')).toBeTruthy();
    expect(screen.getByText('근력 · 대퇴사두근')).toBeTruthy();
    expect(screen.getByText('근력 · 가슴')).toBeTruthy();
    expect(screen.queryByText('상세 부위 무릎')).toBeNull();
    expect(screen.getAllByText('매트, 짐볼, 의자')).toHaveLength(2);
    // 카탈로그 버전 같은 내부 정보는 사용자 화면에 노출하지 않는다.
    expect(screen.queryByText(/카탈로그 버전/)).toBeNull();

    fireEvent.press(screen.getByRole('button', { name: '가슴' }));
    expect(screen.queryByText('스쿼트')).toBeNull();
    expect(screen.getByText('푸시업')).toBeOnTheScreen();
    expect(queries).toEqual([{ cursor: undefined, limit: 100 }]);
  }, 15000);

  it('offers only an exercise-focus filter and hides equipment when an exercise needs none', async () => {
    const page = exercisePage(['맨몸 스쿼트']);
    const api = {
      listExercises: async () => ({
        ...page,
        items: page.items.map((item) => ({
          ...item,
          required_equipment_codes: [],
        })),
      }),
      getExercise: async () => {
        throw new Error('not used');
      },
    } as unknown as Pick<Api, 'listExercises' | 'getExercise'>;

    render(<ExerciseCatalogScreen api={api} onBack={() => {}} />);

    expect(await screen.findByText('맨몸 스쿼트')).toBeTruthy();
    expect(screen.getByText('운동 부위')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '전신' })).toBeNull();
    expect(screen.queryByText('운동 유형')).toBeNull();
    expect(screen.queryByText('난이도')).toBeNull();
    expect(screen.queryByText(/^장비/)).toBeNull();
    expect(screen.queryByText('장비 없음')).toBeNull();
  });

  it('does not repeat a focus that matches the training type', async () => {
    const page = exercisePage(['러닝', '모빌리티']);
    const api = {
      listExercises: async () => ({
        ...page,
        items: page.items.map((item, index) => ({
          ...item,
          training_type_code: index === 0 ? 'CARDIO' : 'MOBILITY',
          body_focus_code: index === 0 ? 'CARDIO' : 'MOBILITY',
        })),
      }),
      getExercise: async () => {
        throw new Error('not used');
      },
    } as unknown as Pick<Api, 'listExercises' | 'getExercise'>;

    render(<ExerciseCatalogScreen api={api} onBack={() => {}} />);

    expect(
      await screen.findByTestId('exercise-body-focus-ex-0-러닝'),
    ).toHaveTextContent(/^유산소$/);
    expect(
      screen.getByTestId('exercise-body-focus-ex-1-모빌리티'),
    ).toHaveTextContent(/^스트레칭$/);
  });

  it('shows the exercise GIF above reviewed catalog instructions', async () => {
    const api = {
      listExercises: async () => exercisePage(['스쿼트']),
      getExercise: async () => ({
        exercise_id: 'ex-0-스쿼트',
        exercise_name: '스쿼트',
        training_type_code: 'STRENGTH',
        primary_body_area_codes: ['KNEE'],
        instruction_summary: '발바닥을 고르게 디디고 천천히 앉아요.',
        form_cues: ['무릎과 발끝의 방향을 맞춰요.'],
        media_asset_key: 'catalog-media/squat.gif',
        media_url: 'https://cdn.example.com/squat.gif',
        mascot_animation_asset_key: null,
        instruction_content_version: 'catalog-guide-v1',
      }),
    } as unknown as Pick<Api, 'listExercises' | 'getExercise'>;

    render(<ExerciseCatalogScreen api={api} onBack={() => {}} />);

    fireEvent.press(
      await screen.findByRole('button', { name: '스쿼트 설명 열기' }),
    );

    expect(screen.getByRole('header', { name: '스쿼트' })).toBeOnTheScreen();
    expect(await screen.findByTestId('exercise-media-image')).toHaveProp(
      'source',
      { uri: 'https://cdn.example.com/squat.gif' },
    );
    const cue = screen.getByText('무릎과 발끝의 방향을 맞춰요.');
    expect(cue).toBeOnTheScreen();
    expect(StyleSheet.flatten(cue.props.style)).toMatchObject({
      fontSize: 15,
      lineHeight: 23,
    });
    expect(
      screen.queryByText('발바닥을 고르게 디디고 천천히 앉아요.'),
    ).toBeNull();
  });

  it('does not treat media_asset_key as a URL when media_url is null', async () => {
    const api = {
      listExercises: async () => exercisePage(['런지']),
      getExercise: async () => ({
        exercise_id: 'ex-0-런지',
        exercise_name: '런지',
        training_type_code: 'STRENGTH',
        primary_body_area_codes: ['KNEE'],
        instruction_summary: '검수된 런지 설명입니다.',
        form_cues: [],
        media_asset_key: 'https://legacy.example.com/must-not-render.gif',
        media_url: null,
        mascot_animation_asset_key: null,
        instruction_content_version: 'catalog-guide-v1',
      }),
    } as unknown as Pick<Api, 'listExercises' | 'getExercise'>;

    render(<ExerciseCatalogScreen api={api} onBack={() => {}} />);

    fireEvent.press(
      await screen.findByRole('button', { name: '런지 설명 열기' }),
    );

    expect(
      await screen.findByTestId('exercise-media-placeholder'),
    ).toBeOnTheScreen();
    expect(screen.queryByTestId('exercise-media-image')).toBeNull();
    // Nothing is being shown, so there is nothing to credit.
    expect(screen.queryByTestId('exercise-media-credit')).toBeNull();
  });

  it('credits the GIF source directly under the image', async () => {
    const api = {
      listExercises: async () => exercisePage(['스쿼트']),
      getExercise: async () => ({
        exercise_id: 'ex-0-스쿼트',
        exercise_name: '스쿼트',
        training_type_code: 'STRENGTH',
        primary_body_area_codes: ['KNEE'],
        instruction_summary: '검수된 스쿼트 설명입니다.',
        form_cues: [],
        media_asset_key: 'catalog-media/squat.gif',
        media_url: 'https://cdn.example.com/squat.gif',
        mascot_animation_asset_key: null,
        instruction_content_version: 'catalog-guide-v1',
      }),
    } as unknown as Pick<Api, 'listExercises' | 'getExercise'>;

    render(<ExerciseCatalogScreen api={api} onBack={() => {}} />);

    fireEvent.press(
      await screen.findByRole('button', { name: '스쿼트 설명 열기' }),
    );

    expect(await screen.findByTestId('exercise-media-image')).toBeOnTheScreen();
    expect(
      screen.getByText('© Gym visual - Aliaksandr Makatserchyk'),
    ).toBeOnTheScreen();
  });

  it('does not expose an unknown equipment machine code', () => {
    expect(equipmentLabel('FUTURE_EQUIPMENT')).toBe('확인되지 않은 항목');
  });

  it('labels catalog-v2 body focus and equipment codes', () => {
    expect(bodyFocusLabel('FUTURE_FOCUS')).toBe('확인되지 않은 항목');
    expect(bodyFocusLabel('CHEST')).toBe('가슴');
    expect(bodyFocusLabel('HAMSTRINGS')).toBe('햄스트링');
    expect(bodyFocusLabel('ADDUCTORS')).toBe('내전근');
    expect(bodyFocusLabel('CARDIO')).toBe('유산소');
    expect(bodyFocusLabel('MOBILITY')).toBe('가동성');
    expect(equipmentLabel('EZ_BAR')).toBe('이지바');
    expect(equipmentLabel('FOAM_ROLLER')).toBe('폼롤러');
  });

  it('uses detailed body areas when a legacy list item has no focus code', async () => {
    const page = exercisePage(['레거시 스쿼트']);
    const api = {
      listExercises: async () => ({
        ...page,
        items: page.items.map(({ body_focus_code: _focus, ...item }) => item),
      }),
      getExercise: async () => {
        throw new Error('not used');
      },
    } as unknown as Pick<Api, 'listExercises' | 'getExercise'>;

    render(<ExerciseCatalogScreen api={api} onBack={() => {}} />);

    expect(await screen.findByText('근력 · 무릎')).toBeOnTheScreen();
    expect(screen.queryByText('상세 부위 무릎')).toBeNull();
  });

  it('loads every server page so exercise-name search covers the full catalog', async () => {
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

    expect(await screen.findByText('플랭크')).toBeTruthy();
    // 첫 페이지 항목은 그대로 유지된다.
    expect(screen.getByText('스쿼트')).toBeTruthy();
    expect(cursors).toEqual([undefined, 'cursor-2']);

    fireEvent.changeText(screen.getByLabelText('운동명 검색'), '플랭');
    expect(screen.getByText('플랭크')).toBeOnTheScreen();
    expect(screen.queryByText('스쿼트')).toBeNull();
    fireEvent.changeText(screen.getByLabelText('운동명 검색'), '없는 운동');
    expect(
      screen.getByText('검색한 운동명을 찾지 못했어요.'),
    ).toBeOnTheScreen();
  });

  it('keeps the paged list mounted while an exercise detail is open', async () => {
    const api = {
      listExercises: async (query: { cursor?: string }) =>
        query.cursor === undefined
          ? exercisePage(['First exercise'], 'cursor-2')
          : exercisePage(['Target exercise'], null),
      getExercise: async () => ({
        exercise_id: 'ex-0-Target exercise',
        exercise_name: 'Target exercise',
        training_type_code: 'STRENGTH',
        primary_body_area_codes: ['KNEE'],
        instruction_summary: 'Reviewed target instructions.',
        form_cues: [],
        media_asset_key: null,
        media_url: null,
        mascot_animation_asset_key: null,
        instruction_content_version: 'catalog-guide-v1',
      }),
    } as unknown as Pick<Api, 'listExercises' | 'getExercise'>;

    render(<ExerciseCatalogScreen api={api} onBack={() => {}} />);

    expect(await screen.findByText('Target exercise')).toBeOnTheScreen();
    const listScroll = screen.getByTestId('exercise-catalog-list-scroll');

    fireEvent.press(
      screen.getByRole('button', {
        name: 'Target exercise 설명 열기',
      }),
    );
    expect(
      await screen.findByRole('header', { name: 'Target exercise' }),
    ).toBeOnTheScreen();
    expect(screen.getByTestId('exercise-catalog-list-scroll')).toBe(listScroll);

    fireEvent.press(screen.getByRole('button', { name: '목록으로' }));
    expect(await screen.findByText('First exercise')).toBeOnTheScreen();
    expect(screen.getByText('Target exercise')).toBeOnTheScreen();
    expect(screen.getByTestId('exercise-catalog-list-scroll')).toBe(listScroll);
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
    expect(screen.queryByText('웨어러블 연동')).toBeNull();
    fireEvent.press(screen.getByText('동의 변경 저장'));

    await waitFor(() => {
      expect(putConsents).toHaveLength(1);
    });
    expect(putConsents[0]).toMatchObject({
      general_personal_data: true,
      sensitive_data: true,
      wearable_integration: false,
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
      screen.getByText('필수 동의 항목은 여기에서 변경할 수 없어요.'),
    ).toBeTruthy();
  });
});
