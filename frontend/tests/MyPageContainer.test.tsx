import { describe, expect, it, jest } from '@jest/globals';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react-native';

import { ApiClient } from '../src/api/client';
import { createApi, type Api } from '../src/api/endpoints';
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
    expect(screen.queryByText('BODYWEIGHT')).toBeNull();
    expect(screen.queryByText('완료 운동')).toBeNull();
    expect(screen.queryByText('연속 기록')).toBeNull();
    expect(screen.queryByText('이번 주')).toBeNull();
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
    fireEvent.press(screen.getByText('희망 운동 시간 늘리기'));

    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenCalledWith(
        { default_requested_duration_minutes: 35 },
        7,
      ),
    );
    expect(screen.queryByText('목표 저장')).toBeNull();
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

  it('edits only the selected equipment field from its modal', async () => {
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
    fireEvent.press(screen.getByRole('checkbox', { name: '매트' }));

    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenCalledWith(
        { equipment_codes: ['BODYWEIGHT', 'RESISTANCE_BAND', 'MAT'] },
        7,
      ),
    );
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
