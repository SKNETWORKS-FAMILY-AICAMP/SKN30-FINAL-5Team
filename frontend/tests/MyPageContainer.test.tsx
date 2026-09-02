import { describe, expect, it, jest } from '@jest/globals';
import * as ImagePicker from 'expo-image-picker';
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
    uploadProfileImage: jest.fn(async () => ({
      profile_image_url: 'https://cdn.example.com/profiles/user-1.jpg',
      profile_version: 8,
      updated_at: '2026-08-19T09:00:00+09:00',
    })),
    deleteProfileImage: jest.fn(async () => ({
      profile_image_url: null,
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
    expect(screen.getAllByText('체력 증진').length).toBeGreaterThan(0);
    expect(screen.getAllByText('초급').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: '선호 운동 수정' })).toBeNull();
    expect(screen.queryByRole('button', { name: '장비 수정' })).toBeNull();
    expect(screen.queryByText('맨몸 · 밴드')).toBeNull();
    expect(screen.queryByText('캘린더 연동')).toBeNull();
    expect(screen.getAllByText('차근차근')).toHaveLength(1);
    expect(
      screen.getByRole('button', { name: '차근차근' }).props.accessibilityState,
    ).toEqual(expect.objectContaining({ selected: true }));
    expect(screen.queryByRole('button', { name: '나이 수정' })).toBeNull();
    expect(screen.queryByRole('button', { name: '시간대 수정' })).toBeNull();
    expect(screen.queryByText('BODYWEIGHT')).toBeNull();
    expect(screen.queryByText('완료 운동')).toBeNull();
    expect(screen.queryByText('연속 기록')).toBeNull();
    expect(screen.queryByText('이번 주')).toBeNull();
  });

  it('offers the onboarding goal, experience, and location choices', async () => {
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

    fireEvent.press(screen.getByRole('button', { name: '운동 목표 수정' }));
    expect(screen.getByText('다이어트')).toBeOnTheScreen();
    expect(screen.getByText('근력 증가')).toBeOnTheScreen();
    expect(screen.getByText('체력 증진')).toBeOnTheScreen();
    fireEvent.press(screen.getByTestId('profile-editor-backdrop'));

    fireEvent.press(screen.getByRole('button', { name: '운동 경험 수정' }));
    expect(screen.getByRole('radio', { name: '초급' })).toBeChecked();
    expect(screen.getByRole('radio', { name: '중급' })).toBeOnTheScreen();
    fireEvent.press(screen.getByTestId('profile-editor-backdrop'));

    fireEvent.press(screen.getByRole('button', { name: '운동 장소 수정' }));
    expect(
      screen.getByRole('header', { name: '운동 장소 수정' }),
    ).toBeOnTheScreen();
    expect(screen.getByRole('checkbox', { name: '집' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '헬스장' })).toBeOnTheScreen();
    expect(screen.queryByRole('checkbox', { name: '야외' })).toBeNull();
  });

  it('never exposes an unmapped machine code', async () => {
    const current = me();
    current.profile!.primary_goal_code = 'NEW_APPROVED_GOAL';

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
      screen.getByRole('header', { name: '프로필 수정' }),
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

  it('renders a saved profile image and can restore the bundled default', async () => {
    const current = me();
    current.profile!.profile_image_url =
      'https://cdn.example.com/profiles/user-1.jpg';
    const deleteProfileImage = jest.fn<Api['deleteProfileImage']>(async () => ({
      profile_image_url: null,
      profile_version: 8,
      updated_at: '2026-08-19T09:00:00+09:00',
    }));

    await render(
      <MyPageContainer
        api={accountApi({ deleteProfileImage })}
        me={current}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    expect(screen.getByTestId('my-page-profile-avatar').props.source).toEqual({
      uri: 'https://cdn.example.com/profiles/user-1.jpg',
    });

    fireEvent.press(screen.getByRole('button', { name: '프로필 수정' }));
    fireEvent.press(
      screen.getByRole('button', { name: '기본 이미지로 되돌리기' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '기본 정보 저장' }));

    await waitFor(() => expect(deleteProfileImage).toHaveBeenCalledWith(7));
  });

  it('selects a device image, previews it, and uploads the file on save', async () => {
    const updateProfileSettings = jest.fn<Api['updateProfileSettings']>();
    const uploadProfileImage = jest.fn<Api['uploadProfileImage']>(async () => ({
      profile_image_url: 'https://cdn.example.com/profiles/user-1.jpg',
      profile_version: 8,
      updated_at: '2026-08-19T09:00:00+09:00',
    }));
    jest
      .mocked(ImagePicker.requestMediaLibraryPermissionsAsync)
      .mockResolvedValueOnce({
        granted: true,
        status: ImagePicker.PermissionStatus.GRANTED,
        canAskAgain: true,
        expires: 'never',
      });
    jest.mocked(ImagePicker.launchImageLibraryAsync).mockResolvedValueOnce({
      canceled: false,
      assets: [
        {
          uri: 'file:///profile.jpg',
          width: 800,
          height: 800,
          type: 'image',
          fileName: 'profile.jpg',
          fileSize: 123_456,
          mimeType: 'image/jpeg',
        },
      ],
    });

    await render(
      <MyPageContainer
        api={accountApi({ updateProfileSettings, uploadProfileImage })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '프로필 수정' }));
    fireEvent.press(
      screen.getByRole('button', { name: '사진 보관함에서 선택' }),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId('profile-editor-avatar-preview').props.source,
      ).toEqual({ uri: 'file:///profile.jpg' }),
    );
    fireEvent.press(screen.getByRole('button', { name: '기본 정보 저장' }));

    await waitFor(() =>
      expect(uploadProfileImage).toHaveBeenCalledWith(
        expect.objectContaining({
          uri: 'file:///profile.jpg',
          fileName: 'profile.jpg',
          mimeType: 'image/jpeg',
          fileSize: 123_456,
        }),
        7,
      ),
    );
    expect(updateProfileSettings).not.toHaveBeenCalled();
  });

  it('shows guidance when photo-library permission is denied', async () => {
    const uploadProfileImage = jest.fn<Api['uploadProfileImage']>();
    jest
      .mocked(ImagePicker.requestMediaLibraryPermissionsAsync)
      .mockResolvedValueOnce({
        granted: false,
        status: ImagePicker.PermissionStatus.DENIED,
        canAskAgain: false,
        expires: 'never',
      });

    await render(
      <MyPageContainer
        api={accountApi({ uploadProfileImage })}
        me={me()}
        now={new Date('2026-08-19T03:00:00Z')}
        onNavigateTab={jest.fn()}
        onRefreshMe={jest.fn(async () => undefined)}
        onSignOut={jest.fn()}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '프로필 수정' }));
    fireEvent.press(
      screen.getByRole('button', { name: '사진 보관함에서 선택' }),
    );

    expect(
      await screen.findByText(
        '사진을 선택하려면 기기 설정에서 사진 보관함 접근을 허용해주세요.',
      ),
    ).toBeOnTheScreen();
    expect(uploadProfileImage).not.toHaveBeenCalled();
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

    fireEvent.press(screen.getByRole('button', { name: '운동 시간 수정' }));
    fireEvent.press(
      screen.getByRole('button', { name: '운동 시간 10분 늘리기' }),
    );
    expect(
      await screen.findByText(
        '운동 시간 값을 확인해주세요. 요청 값이 올바르지 않습니다.',
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

    fireEvent.press(screen.getByRole('button', { name: '운동 시간 수정' }));
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

    fireEvent.press(screen.getByRole('button', { name: '딱 필요한 만큼' }));
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

    fireEvent.press(screen.getByRole('button', { name: '운동 시간 수정' }));
    expect(
      screen.getByRole('header', { name: '운동 시간 수정' }),
    ).toBeOnTheScreen();
    expect(screen.getByText('변경한 내용은 바로 반영돼요.')).toBeOnTheScreen();
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
    // 저장 버튼이 없으므로 저장이 끝난 사실을 화면에서 알려준다.
    expect(
      await screen.findByText('변경 사항을 저장했어요.'),
    ).toBeOnTheScreen();
  });

  it('keeps notification switches off and marked as coming soon', async () => {
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

    expect(
      await screen.findByText('알림과 기기 연동 기능은 준비 중이에요.'),
    ).toBeOnTheScreen();
    expect(
      screen.getByText('예정된 운동 시간을 알려드려요.'),
    ).toBeOnTheScreen();
    expect(
      screen.getByText('이번 주 운동 리포트가 준비되면 알려드려요.'),
    ).toBeOnTheScreen();
    expect(
      screen.getByText('휴식일에는 알림을 보내지 않아요.'),
    ).toBeOnTheScreen();
    expect(screen.getAllByText('준비 중').length).toBeGreaterThanOrEqual(3);
    expect(
      screen.getByRole('switch', { name: '루틴 알림' }).props
        .accessibilityState,
    ).toEqual(expect.objectContaining({ checked: false, disabled: true }));
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

    fireEvent.press(screen.getByRole('button', { name: '운동 시간 수정' }));
    fireEvent.press(screen.getByTestId('profile-editor-sheet'), {
      stopPropagation: jest.fn(),
    });
    expect(
      screen.getByRole('header', { name: '운동 시간 수정' }),
    ).toBeOnTheScreen();

    fireEvent.press(screen.getByTestId('profile-editor-backdrop'));
    expect(screen.queryByRole('header', { name: '운동 시간 수정' })).toBeNull();
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

    fireEvent.press(
      screen.getByRole('button', { name: '평소 불편한 부위 수정' }),
    );
    expect(
      screen.getByRole('header', { name: '평소 불편한 부위 수정' }),
    ).toBeOnTheScreen();
    expect(screen.getByRole('checkbox', { name: '있어요' })).toBeChecked();
    expect(screen.getByText('불편한 부위')).toBeOnTheScreen();
    expect(screen.queryByRole('adjustable')).toBeNull();
    fireEvent.press(screen.getByRole('checkbox', { name: '없어요' }));

    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenCalledWith(
        { attention_area_codes: [] },
        7,
      ),
    );
    expect(screen.queryByText('불편한 부위')).toBeNull();
  });

  it('edits persisted pain scores when the additive profile contract is available', async () => {
    const current = me();
    current.profile!.pain_areas = [
      { body_area_code: 'KNEE', intensity_score: 4 },
      { body_area_code: 'SHOULDER', intensity_score: 2 },
    ];
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

    fireEvent.press(
      screen.getByRole('button', { name: '평소 불편한 부위 수정' }),
    );
    expect(
      screen
        .getAllByRole('adjustable')
        .map((control) => control.props.accessibilityLabel),
    ).toEqual(['어깨 통증 정도', '무릎 통증 정도']);
    const slider = screen.getByRole('adjustable', {
      name: '무릎 통증 정도',
    });
    expect(slider).toHaveAccessibilityValue({
      min: 1,
      max: 10,
      now: 4,
      text: '10점 중 4점',
    });

    fireEvent(slider, 'accessibilityAction', {
      nativeEvent: { actionName: 'increment' },
    });
    expect(slider).toHaveAccessibilityValue({
      min: 1,
      max: 10,
      now: 5,
      text: '10점 중 5점',
    });
    fireEvent.press(screen.getByRole('button', { name: '통증 정보 저장' }));

    await waitFor(() =>
      expect(updateProfileSettings).toHaveBeenCalledWith(
        {
          pain_present: true,
          pain_areas: [
            { body_area_code: 'SHOULDER', intensity_score: 2 },
            { body_area_code: 'KNEE', intensity_score: 5 },
          ],
        },
        7,
      ),
    );
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

    fireEvent.press(
      screen.getByRole('button', { name: '평소 불편한 부위 수정' }),
    );
    expect(
      screen.getByRole('button', { name: '다른 부위 접기' }).props
        .accessibilityState,
    ).toMatchObject({ expanded: true });
    expect(screen.getByRole('checkbox', { name: '목' })).toBeChecked();
  });

  it('uses the onboarding-style secondary control for additional pain areas', async () => {
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

    fireEvent.press(
      screen.getByRole('button', { name: '평소 불편한 부위 수정' }),
    );
    fireEvent.press(screen.getByRole('checkbox', { name: '있어요' }));

    const toggle = screen.getByRole('button', { name: '다른 부위 보기' });
    expect(toggle.props.accessibilityState).toMatchObject({ expanded: false });
    expect(
      screen.getByTestId('my-page-extended-area-caret').props.style,
    ).toBeUndefined();
    expect(screen.queryByRole('checkbox', { name: '목' })).toBeNull();

    fireEvent.press(toggle);

    expect(screen.getByText('접기')).toBeOnTheScreen();
    expect(
      screen.getByTestId('my-page-extended-area-caret').props.style,
    ).toMatchObject({ transform: [{ rotate: '180deg' }] });
    expect(screen.getByRole('checkbox', { name: '목' })).toBeOnTheScreen();
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

    fireEvent.press(
      screen.getByRole('button', { name: '평소 불편한 부위 수정' }),
    );
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

  it('uploads a picked image as multipart without overriding its boundary', async () => {
    const fetchImpl = jest.fn<typeof fetch>(async () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            profile_image_url: 'https://cdn.example.com/profiles/user-1.jpg',
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

    await api.uploadProfileImage(
      {
        uri: 'file:///profile.jpg',
        fileName: 'profile.jpg',
        mimeType: 'image/jpeg',
        webFile: new Blob(['image'], { type: 'image/jpeg' }),
      },
      7,
    );

    const [url, init] = fetchImpl.mock.calls[0] ?? [];
    expect(String(url)).toBe('http://127.0.0.1:8000/api/v1/me/profile-image');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBeInstanceOf(FormData);
    expect(init?.headers).toEqual(
      expect.objectContaining({
        Authorization: 'Bearer firebase-token',
        'If-Match': '"7"',
        'Idempotency-Key': expect.any(String),
      }),
    );
    expect(init?.headers).not.toEqual(
      expect.objectContaining({ 'Content-Type': expect.any(String) }),
    );
  });
});
