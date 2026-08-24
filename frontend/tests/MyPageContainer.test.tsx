import { describe, expect, it, jest } from '@jest/globals';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';

import { ApiClient } from '../src/api/client';
import { createApi, type Api } from '../src/api/endpoints';
import { ApiError } from '../src/api/errors';
import type { ConsentValues, MeResponse } from '../src/api/types';
import { MyPageContainer } from '../src/features/home/MyPageContainer';
import { completionStreak } from '../src/features/home/myPageModel';

function me(): MeResponse {
  return {
    user_id: 'user-1',
    status_code: 'ACTIVE',
    onboarding_completed: true,
    premium_status_code: 'TRIAL',
    ai_trial_started_at: '2026-08-01T00:00:00+09:00',
    ai_trial_ends_at: '2026-08-31T00:00:00+09:00',
    profile: {
      nickname: '민지',
      age: 29,
      primary_goal_code: 'GENERAL_FITNESS',
      experience_level_code: 'BEGINNER',
      timezone: 'Asia/Seoul',
      preferred_location_code: 'HOME',
      available_location_codes: ['HOME'],
      default_requested_duration_minutes: 30,
      desired_weekly_workout_count: 4,
      coaching_style_code: 'SUPPORTIVE',
      equipment_codes: ['BODYWEIGHT', 'RESISTANCE_BAND'],
      attention_area_codes: ['KNEE'],
      preferred_exercise_type_codes: ['STRENGTH'],
      profile_version: 7,
      created_at: '2026-08-13T09:00:00+09:00',
      updated_at: '2026-08-18T09:00:00+09:00',
    },
  };
}

function accountApi(overrides: Partial<Api> = {}): Api {
  return {
    listWorkoutSessions: jest.fn(async () => ({
      items: [],
      next_cursor: null,
    })),
    updateProfileSettings: jest.fn(async () => ({
      profile_version: 8,
      updated_at: '2026-08-19T09:00:00+09:00',
    })),
    getConsents: jest.fn(async () => ({
      user_id: 'user-1',
      consents: [
        'GENERAL_PERSONAL_DATA',
        'SENSITIVE_DATA',
        'WEARABLE_INTEGRATION',
        'CALENDAR_INTEGRATION',
        'MARKETING',
      ].map((code) => ({
        consent_type_code: code,
        granted: code === 'GENERAL_PERSONAL_DATA' || code === 'SENSITIVE_DATA',
        policy_version: 'consent-v1',
        updated_at: '2026-08-19T09:00:00+09:00',
      })),
    })),
    replaceConsents: jest.fn(async (body: ConsentValues) => ({
      user_id: 'user-1',
      consents: Object.entries(body).map(([key, granted]) => ({
        consent_type_code: key.toUpperCase(),
        granted,
        policy_version: 'consent-v1',
        updated_at: '2026-08-19T09:00:00+09:00',
      })),
    })),
    requestAccountDeletion: jest.fn(async () => ({
      deletion_request_id: 'deletion-1',
      status_code: 'DELETION_PENDING',
      operational_data_delete_by: '2026-08-26T09:00:00+09:00',
      backup_expiry_days: 30,
    })),
    ...overrides,
  } as unknown as Api;
}

describe('MyPageContainer', () => {
  it('renders editable profile information without the workout stats cards', async () => {
    await render(
      <MyPageContainer
        api={accountApi()}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    expect(await screen.findByText('민지님')).toBeOnTheScreen();
    expect(screen.getByText('함께한 지 7일째')).toBeOnTheScreen();
    expect(screen.getByText('근력')).toBeOnTheScreen();
    expect(screen.getByText('맨몸 · 밴드')).toBeOnTheScreen();
    expect(screen.queryByRole('button', { name: '나이 수정' })).toBeNull();
    expect(screen.queryByRole('button', { name: '시간대 수정' })).toBeNull();
    expect(screen.queryByText('BODYWEIGHT')).toBeNull();
    expect(screen.queryByText('완료 운동')).toBeNull();
    expect(screen.queryByText('연속 기록')).toBeNull();
    expect(screen.queryByText('이번 주')).toBeNull();
  });

  it('uses the stretching label consistently for the mobility preference', async () => {
    const current = me();
    current.profile!.preferred_exercise_type_codes = ['CARDIO', 'MOBILITY'];

    await render(
      <MyPageContainer
        api={accountApi()}
        me={current}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    expect(await screen.findByText('유산소 · 스트레칭')).toBeOnTheScreen();
    expect(screen.queryByText('유산소 · 가동성')).toBeNull();

    fireEvent.press(screen.getByRole('button', { name: '선호 운동 수정' }));
    expect(
      screen.getByRole('header', { name: '선호 운동 수정' }),
    ).toBeOnTheScreen();
    expect(screen.getByRole('checkbox', { name: '스트레칭' })).toBeChecked();
  });

  it('never exposes an unmapped machine code', async () => {
    const current = me();
    current.profile!.primary_goal_code = 'NEW_APPROVED_GOAL';
    current.profile!.equipment_codes = ['NEW_EQUIPMENT'];

    await render(
      <MyPageContainer
        api={accountApi()}
        me={current}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    expect(screen.queryByText('NEW_APPROVED_GOAL')).toBeNull();
    expect(screen.queryByText('NEW_EQUIPMENT')).toBeNull();
    expect(screen.getAllByText('확인되지 않은 항목').length).toBeGreaterThan(0);
  });

  it('renders loading, empty, error, and permission-denied states', async () => {
    const onRefreshMe = jest.fn(async () => undefined);
    const props = {
      api: accountApi(),
      me: me(),
      now: new Date('2026-08-19T03:00:00Z'),
      onNavigateTab: jest.fn(),
      onRefreshMe,
      onSignOut: jest.fn(),
    };
    const view = await render(
      <MyPageContainer {...props} previewState="loading" />,
    );
    expect(screen.getByText('프로필 정보를 불러오고 있어요')).toBeOnTheScreen();

    view.rerender(<MyPageContainer {...props} previewState="empty" />);
    expect(
      screen.getByText('아직 등록된 프로필 정보가 없어요.'),
    ).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('button', { name: '다시 불러오기' }));
    expect(onRefreshMe).toHaveBeenCalledTimes(1);

    view.rerender(<MyPageContainer {...props} previewState="error" />);
    expect(
      screen.getByText(
        '프로필 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.',
      ),
    ).toBeOnTheScreen();

    view.rerender(<MyPageContainer {...props} previewState="permission" />);
    expect(
      screen.getByText('이 계정으로는 프로필 정보에 접근할 수 없어요.'),
    ).toBeOnTheScreen();
    expect(screen.queryByRole('button', { name: '다시 시도' })).toBeNull();
  });

  it('shows an empty profile state instead of preview profile values', async () => {
    const current = me();
    current.profile = null;

    await render(
      <MyPageContainer
        api={accountApi()}
        me={current}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    expect(
      screen.getByText('아직 등록된 프로필 정보가 없어요.'),
    ).toBeOnTheScreen();
    expect(screen.queryByText('헬끼님')).toBeNull();
  });

  it('updates all basic profile fields from the profile entry point', async () => {
    const updateProfileSettings = jest.fn<Api['updateProfileSettings']>(
      async () => ({
        profile_version: 8,
        updated_at: '2026-08-19T09:00:00+09:00',
      }),
    );

    await render(
      <MyPageContainer
        api={accountApi({ updateProfileSettings })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '프로필 수정' }));
    expect(
      screen.getByRole('header', { name: '기본 정보 수정' }),
    ).toBeOnTheScreen();
    expect(
      screen.getByText(/개인정보 보호를 위해 기존 값을 다시 보여주지 않아요/),
    ).toBeOnTheScreen();
    expect(screen.queryByText('시간대')).toBeNull();
    expect(screen.queryByText('선택하지 않음')).toBeNull();
    expect(screen.queryByText(/변경할 때만/)).toBeNull();
    fireEvent.changeText(screen.getByLabelText('닉네임 입력'), '새 닉네임');
    fireEvent.press(screen.getByRole('button', { name: '연도 1997년' }));
    fireEvent.press(screen.getByRole('button', { name: '월 4월' }));
    fireEvent.press(screen.getByRole('button', { name: '일 3일' }));
    fireEvent.press(screen.getByRole('checkbox', { name: '여성' }));
    fireEvent.changeText(screen.getByLabelText('키 입력'), '168.5');
    fireEvent.changeText(screen.getByLabelText('체중 입력'), '58.2');
    fireEvent.press(screen.getByRole('button', { name: '기본 정보 저장' }));

    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenCalledWith(
        {
          nickname: '새 닉네임',
          date_of_birth: '1997-04-03',
          sex_code: 'FEMALE',
          height_cm: 168.5,
          weight_kg: 58.2,
        },
        7,
      ),
    );
  });

  it('explains which field failed to save', async () => {
    const updateProfileSettings = jest.fn<Api['updateProfileSettings']>(
      async () => {
        throw new ApiError({
          kind: 'validation',
          code: 'INVALID_REQUEST',
          status: 400,
          message: '요청 값이 올바르지 않습니다.',
          details: [{ field: 'body.default_requested_duration_minutes' }],
        });
      },
    );

    await render(
      <MyPageContainer
        api={accountApi({ updateProfileSettings })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '희망 시간 수정' }));
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );
    expect(
      await screen.findByText(
        '희망 시간 값을 확인해주세요. 요청 값이 올바르지 않습니다.',
      ),
    ).toBeOnTheScreen();
  });

  it('refreshes the profile after a stale-version save failure', async () => {
    const updateProfileSettings = jest.fn<Api['updateProfileSettings']>(
      async () => {
        throw new ApiError({
          kind: 'conflict',
          code: 'STALE_PROFILE',
          status: 409,
          message: '프로필이 변경되었습니다. 최신 상태로 다시 시도해주세요.',
        });
      },
    );
    const onRefreshMe = jest.fn(async () => undefined);

    await render(
      <MyPageContainer
        api={accountApi({ updateProfileSettings })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={onRefreshMe}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '희망 시간 수정' }));
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );
    expect(
      await screen.findByText(
        '프로필이 변경되었습니다. 최신 상태로 다시 시도해주세요.',
      ),
    ).toBeOnTheScreen();
    expect(onRefreshMe).toHaveBeenCalledTimes(1);
  });

  it('saves coaching style with the current profile version and refreshes me', async () => {
    const updateProfileSettings = jest.fn<Api['updateProfileSettings']>(
      async () => ({
        profile_version: 8,
        updated_at: '2026-08-19T09:00:00+09:00',
      }),
    );
    const onRefreshMe = jest.fn(async () => undefined);

    await render(
      <MyPageContainer
        api={accountApi({ updateProfileSettings })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={onRefreshMe}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '간결하게' }));
    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenCalledWith(
        { coaching_style_code: 'CONCISE' },
        7,
      ),
    );
    expect(onRefreshMe).toHaveBeenCalledTimes(1);
  });

  it('opens one field editor and saves a duration change immediately', async () => {
    const updateProfileSettings = jest.fn<Api['updateProfileSettings']>(
      async () => ({
        profile_version: 8,
        updated_at: '2026-08-19T09:00:00+09:00',
      }),
    );

    await render(
      <MyPageContainer
        api={accountApi({ updateProfileSettings })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '희망 시간 수정' }));
    expect(
      screen.getByRole('header', { name: '희망 시간 수정' }),
    ).toBeOnTheScreen();
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );

    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenCalledWith(
        { default_requested_duration_minutes: 40 },
        7,
      ),
    );
    expect(screen.queryByText('목표 저장')).toBeNull();
  });

  it('keeps the profile editor inside the screen and closes from its backdrop', async () => {
    await render(
      <MyPageContainer
        api={accountApi()}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '희망 시간 수정' }));
    fireEvent.press(screen.getByTestId('profile-editor-sheet'), {
      stopPropagation: jest.fn(),
    });
    expect(
      screen.getByRole('header', { name: '희망 시간 수정' }),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByTestId('profile-editor-backdrop'));
    expect(screen.queryByRole('header', { name: '희망 시간 수정' })).toBeNull();
  });

  it('saves an optional consent immediately without a save button', async () => {
    const replaceConsents = jest.fn<Api['replaceConsents']>(async (body) => ({
      user_id: 'user-1',
      consents: Object.entries(body).map(([key, granted]) => ({
        consent_type_code: key.toUpperCase(),
        granted,
        policy_version: 'consent-v1',
        updated_at: '2026-08-19T09:00:00+09:00',
      })),
    }));

    await render(
      <MyPageContainer
        api={accountApi({ replaceConsents })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(await screen.findByText('마케팅 정보 수신'));

    await waitFor(() =>
      expect(replaceConsents).toHaveBeenCalledWith(
        expect.objectContaining({
          general_personal_data: true,
          sensitive_data: true,
          marketing: true,
        }),
      ),
    );
    expect(screen.queryByText('동의 변경 저장')).toBeNull();
  });

  it('edits only the selected equipment field from its sheet', async () => {
    const updateProfileSettings = jest.fn<Api['updateProfileSettings']>(
      async () => ({
        profile_version: 8,
        updated_at: '2026-08-19T09:00:00+09:00',
      }),
    );

    await render(
      <MyPageContainer
        api={accountApi({ updateProfileSettings })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '장비 수정' }));
    expect(screen.getByRole('header', { name: '장비 수정' })).toBeOnTheScreen();
    expect(screen.queryByRole('header', { name: '주의 부위 수정' })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: '덤벨' })).toBeNull();
    expect(screen.getByRole('checkbox', { name: '맨몸' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '밴드' })).toBeChecked();
    fireEvent.press(screen.getByRole('checkbox', { name: '매트' }));

    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenCalledWith(
        { equipment_codes: ['BODYWEIGHT', 'RESISTANCE_BAND', 'MAT'] },
        7,
      ),
    );
  });

  it('updates both available and preferred workout locations', async () => {
    const updateProfileSettings = jest.fn<Api['updateProfileSettings']>(
      async () => ({
        profile_version: 8,
        updated_at: '2026-08-19T09:00:00+09:00',
      }),
    );

    await render(
      <MyPageContainer
        api={accountApi({ updateProfileSettings })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '운동 장소 수정' }));
    fireEvent.press(screen.getByRole('checkbox', { name: '헬스장' }));
    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenCalledWith(
        {
          available_location_codes: ['HOME', 'GYM'],
          preferred_location_code: 'HOME',
        },
        7,
      ),
    );

    fireEvent.press(screen.getByRole('radio', { name: '헬스장' }));
    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenLastCalledWith(
        {
          available_location_codes: ['HOME', 'GYM'],
          preferred_location_code: 'GYM',
        },
        7,
      ),
    );
  });

  it('uses the onboarding attention-area flow and can clear the selection', async () => {
    const updateProfileSettings = jest.fn<Api['updateProfileSettings']>(
      async () => ({
        profile_version: 8,
        updated_at: '2026-08-19T09:00:00+09:00',
      }),
    );

    await render(
      <MyPageContainer
        api={accountApi({ updateProfileSettings })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '주의 부위 수정' }));
    expect(screen.getByRole('checkbox', { name: '있어요' })).toBeChecked();
    expect(screen.getByText('통증 부위')).toBeOnTheScreen();
    fireEvent.press(screen.getByRole('checkbox', { name: '없어요' }));

    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenCalledWith(
        { attention_area_codes: [] },
        7,
      ),
    );
    expect(screen.queryByText('통증 부위')).toBeNull();
  });

  it('opens extended attention areas when an extended value is already selected', async () => {
    const current = me();
    current.profile!.attention_area_codes = ['NECK'];

    await render(
      <MyPageContainer
        api={accountApi()}
        me={current}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '주의 부위 수정' }));
    expect(
      screen.getByRole('checkbox', { name: '다른 부위 접기' }),
    ).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '목' })).toBeChecked();
  });

  it('renders a legacy attention area in Korean and only allows removing it', async () => {
    const current = me();
    current.profile!.attention_area_codes = ['GENERALIZED'];
    const updateProfileSettings = jest.fn<Api['updateProfileSettings']>(
      async () => ({
        profile_version: 8,
        updated_at: '2026-08-19T09:00:00+09:00',
      }),
    );

    await render(
      <MyPageContainer
        api={accountApi({ updateProfileSettings })}
        me={current}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '주의 부위 수정' }));
    expect(screen.getByText('이전에 저장된 부위 (해제만 가능)')).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: '전신' })).toBeChecked();
    fireEvent.press(screen.getByRole('checkbox', { name: '전신' }));

    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenCalledWith(
        { attention_area_codes: [] },
        7,
      ),
    );
    expect(screen.queryByRole('checkbox', { name: '전신' })).toBeNull();
  });

  it('opens the reviewed exercise catalog from the local my-page screen', async () => {
    const onOpenExerciseCatalog = jest.fn();

    await render(
      <MyPageContainer
        api={accountApi()}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onOpenExerciseCatalog={onOpenExerciseCatalog}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    expect(screen.getByText('운동 도구')).toBeOnTheScreen();
    fireEvent.press(screen.getByText('운동 카탈로그'));
    expect(onOpenExerciseCatalog).toHaveBeenCalledTimes(1);
  });

  it('connects logout and irreversible account deletion confirmations', async () => {
    const requestAccountDeletion = jest.fn<Api['requestAccountDeletion']>(
      async () => ({
        deletion_request_id: 'deletion-1',
        status_code: 'DELETION_PENDING',
        operational_data_delete_by: '2026-08-26T09:00:00+09:00',
        backup_expiry_days: 30,
      }),
    );
    const onSignOut = jest.fn();

    await render(
      <MyPageContainer
        api={accountApi({ requestAccountDeletion })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={onSignOut}
      />,
    );

    fireEvent.press(screen.getByText('회원 탈퇴'));
    fireEvent.press(screen.getByRole('button', { name: '탈퇴하기' }));
    expect(
      await screen.findByText(/운영 데이터는 2026-08-26까지 삭제돼요/),
    ).toBeOnTheScreen();
    expect(requestAccountDeletion).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '탈퇴하기' })).toBeNull(),
    );

    fireEvent.press(screen.getByText('로그아웃'));
    const logoutButtons = screen.getAllByRole('button', { name: '로그아웃' });
    fireEvent.press(logoutButtons[logoutButtons.length - 1]);
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });
});

describe('My page completion streak', () => {
  it('uses distinct official completion dates and expires after a gap', () => {
    expect(
      completionStreak(
        ['2026-08-19', '2026-08-19', '2026-08-18', '2026-08-17'],
        '2026-08-19',
      ),
    ).toBe(3);
    expect(completionStreak(['2026-08-16'], '2026-08-19')).toBe(0);
  });
});

describe('profile settings API', () => {
  it('sends idempotency and quoted profile version headers', async () => {
    const fetchImpl = jest.fn<typeof fetch>(async () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            profile_version: 8,
            updated_at: '2026-08-19T09:00:00+09:00',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    );
    const api = createApi(
      new ApiClient({
        baseUrl: 'http://127.0.0.1:8000',
        getToken: async () => 'firebase-token',
        fetchImpl,
      }),
    );

    await api.updateProfileSettings({ coaching_style_code: 'CONCISE' }, 7);

    const [url, init] = fetchImpl.mock.calls[0] ?? [];
    expect(String(url)).toBe('http://127.0.0.1:8000/api/v1/me/profile');
    expect(init?.method).toBe('PATCH');
    expect(init?.headers).toEqual(
      expect.objectContaining({
        Authorization: 'Bearer firebase-token',
        'If-Match': '"7"',
        'Idempotency-Key': expect.any(String),
      }),
    );
  });
});
