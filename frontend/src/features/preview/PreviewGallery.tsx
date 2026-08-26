import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';

import type { Api } from '../../api/endpoints';
import type {
  DecisionResponse,
  WorkoutSessionDetailResponse,
} from '../../api/types';
import { moveWorkoutPlanItem } from '../../api/workoutPlan';
import {
  ScaleViewportProvider,
  WEB_APP_MAX_WIDTH,
} from '../../components/scale';
import type { TabId } from '../../components/brand/BrandChrome';
import { LoginScreen } from '../auth/LoginScreen';
import {
  LOGIN_PREVIEW_OPTIONS,
  type LoginPreviewState,
  SIGN_UP_PREVIEW_OPTIONS,
  type SignUpPreviewState,
} from '../auth/previewStates';
import { SignInScreen } from '../auth/SignInScreen';
import { SignUpScreen } from '../auth/SignUpScreen';
import { CalendarReportContainer } from '../home/CalendarReportContainer';
import { CalendarReportScreen } from '../home/CalendarReportScreen';
import { HOME_PREVIEW_OPTIONS, type HomePreviewState } from '../home/homeModel';
import { HomeScreen } from '../home/HomeScreen';
import {
  CALENDAR_REPORT_PREVIEW_OPTIONS,
  CALENDAR_WEEKS,
  type CalendarDay,
  type CalendarDayStatus,
  type CalendarReportPreviewState,
  MAP_HOME_PREVIEW_OPTIONS,
  type MapHomePreviewState,
  MY_PAGE_PREVIEW_OPTIONS,
  type MyPagePreviewState,
} from '../home/homeSecondaryModel';
import { MapHomeScreen } from '../home/MapHomeScreen';
import { MyPageContainer } from '../home/MyPageContainer';
import { MyPageScreen } from '../home/MyPageScreen';
import { PreviousHomeScreen } from '../home/PreviousHomeScreen';
import { WorkoutHistorySheet } from '../home/WorkoutHistorySheet';
import { BackgroundTestScreen } from '../house/BackgroundTestScreen';
import { MascotHouseScreen } from '../house/MascotHouseScreen';
import { createMemoryHouseStore } from '../house/houseStorage';
import {
  ONBOARDING_STEPS,
  OnboardingScreen,
} from '../onboarding/OnboardingScreen';
import {
  PROFILE_PREVIEW_OPTIONS,
  type ProfilePreviewState,
  PROFILE_STEPS,
} from '../profile/profileModel';
import { ProfileScreen } from '../profile/ProfileScreen';
import { AccountScreen } from '../profile/AccountScreen';
import { SplashScreen } from '../splash/SplashScreen';
import { WeeklyReportScreen } from '../weekly/WeeklyReportScreen';
import { SessionResultScreen } from '../workout/SessionResultScreen';
import { SessionScreen, type SessionOutcome } from '../workout/SessionScreen';
import { WorkoutScreen } from '../workout/WorkoutScreen';
import {
  WORKOUT_PREVIEW_OPTIONS,
  type WorkoutPreviewState,
} from '../workout/workoutModel';
import { authPreviewAdapter } from './authPreview';
import { homePreviewProps } from './homePreview';
import { onboardingPreviewApi } from './onboardingPreview';
import {
  accountPreviewApi,
  createHousePreviewApi,
  createSessionPreviewApi,
  createWeeklyReportPreviewApi,
  HOUSE_PREVIEW_OPTIONS,
  type HousePreviewState,
  PREVIEW_OPEN_WEEK,
  PREVIEW_PLAN,
  PREVIEW_ROUTINE,
  SESSION_PREVIEW_OPTIONS,
  type SessionPreviewState,
  SESSION_RESULT_PREVIEW_OPTIONS,
  type SessionResultPreviewState,
  sessionResultPreviewApi,
  sessionResultPreviewOutcome,
  WEEKLY_REPORT_PREVIEW_OPTIONS,
  type WeeklyReportPreviewState,
} from './backendPreview';
import {
  PREVIEW_ME,
  previousHomePreviewProps,
  TODAY_PREVIEW_OPTIONS,
  type TodayPreviewState,
} from './todayPreview';

const APP_CANVAS = { width: 390, height: 844 } as const;
export const DEVICE_PREVIEWS = [
  {
    id: 'compact',
    label: 'Android compact · 360 × 800',
    width: 360,
    height: 800,
  },
  {
    id: 'reference',
    label: '원본 기준 · 390 × 844',
    width: 390,
    height: 844,
  },
  {
    id: 'large',
    label: 'Large phone · 430 × 932',
    width: 430,
    height: 932,
  },
  {
    id: 'web-desktop',
    label: 'Web desktop · 1440 × 900',
    width: 1440,
    height: 900,
  },
] as const;
export const SPLASH_DEVICE_PREVIEWS = DEVICE_PREVIEWS;
export type PreviewScreenId =
  | 'splash'
  | 'loading'
  | 'auth'
  | 'login'
  | 'signup'
  | 'onboarding'
  | 'profile'
  | 'home'
  | 'today'
  | 'home-map'
  | 'workout'
  | 'session'
  | 'mascot-house'
  | 'background_test'
  | 'calendar-report'
  | 'weekly-report'
  | 'my-page'
  | 'account';

type PreviewScreen = {
  id: PreviewScreenId;
  label: string;
};

const PREVIEW_SCREEN_GROUPS = [
  {
    label: 'App boot',
    screens: [{ id: 'splash', label: 'Splash (API)' }],
  },
  {
    label: 'States',
    screens: [{ id: 'loading', label: 'Page loading (API)' }],
  },
  {
    label: 'Auth',
    screens: [
      { id: 'auth', label: 'Auth (mock)' },
      { id: 'login', label: 'Login (API)' },
      { id: 'signup', label: 'SignUp (API)' },
    ],
  },
  {
    label: 'Onboarding',
    screens: [
      { id: 'onboarding', label: 'Onboarding (API)' },
      { id: 'profile', label: 'Profile (mock)' },
    ],
  },
  {
    label: 'Home',
    screens: [
      { id: 'home', label: 'Home (API)' },
      { id: 'today', label: 'Home previous (mock)' },
      { id: 'home-map', label: 'Home map (mock)' },
    ],
  },
  {
    label: 'Workout',
    screens: [
      { id: 'workout', label: 'Workout (API)' },
      { id: 'session', label: 'Workout session (mock)' },
    ],
  },
  {
    label: 'Mascot house',
    screens: [
      { id: 'mascot-house', label: 'Mascot house (API)' },
      { id: 'background_test', label: 'background_test (mock)' },
    ],
  },
  {
    label: 'Calendar / report',
    screens: [
      { id: 'calendar-report', label: 'Calendar/report (API)' },
      { id: 'weekly-report', label: 'Weekly report (API)' },
    ],
  },
  {
    label: 'My page',
    screens: [
      { id: 'my-page', label: 'My page (API)' },
      { id: 'account', label: 'Account (mock)' },
    ],
  },
] as const satisfies readonly {
  label: string;
  screens: readonly PreviewScreen[];
}[];

type WorkoutResultGalleryState =
  | 'result-completed'
  | 'result-partial'
  | 'result-not-completed'
  | 'result-safety-stop';

type WorkoutGalleryState =
  'api-flow' | WorkoutPreviewState | WorkoutResultGalleryState;

const WORKOUT_RESULT_GALLERY_OPTIONS = [
  {
    id: 'result-completed',
    label: `결과 · ${SESSION_RESULT_PREVIEW_OPTIONS[0].label}`,
  },
  {
    id: 'result-partial',
    label: `결과 · ${SESSION_RESULT_PREVIEW_OPTIONS[1].label}`,
  },
  {
    id: 'result-not-completed',
    label: `결과 · ${SESSION_RESULT_PREVIEW_OPTIONS[2].label}`,
  },
  {
    id: 'result-safety-stop',
    label: `결과 · ${SESSION_RESULT_PREVIEW_OPTIONS[3].label}`,
  },
] as const satisfies readonly {
  id: WorkoutResultGalleryState;
  label: string;
}[];

const WORKOUT_DETAIL_PREVIEW_OPTIONS = WORKOUT_PREVIEW_OPTIONS.filter(
  (option) => option.id !== 'completed' && option.id !== 'stopped',
);

const WORKOUT_GALLERY_OPTIONS = [
  { id: 'api-flow', label: 'API 실제 흐름' },
  ...WORKOUT_DETAIL_PREVIEW_OPTIONS,
  ...WORKOUT_RESULT_GALLERY_OPTIONS,
] as const satisfies readonly {
  id: WorkoutGalleryState;
  label: string;
}[];

function workoutResultStateFor(
  state: WorkoutGalleryState,
): SessionResultPreviewState | null {
  switch (state) {
    case 'result-completed':
      return 'completed';
    case 'result-partial':
      return 'partial';
    case 'result-not-completed':
      return 'not-completed';
    case 'result-safety-stop':
      return 'safety-stop';
    default:
      return null;
  }
}

function isWorkoutPreviewState(
  state: WorkoutGalleryState,
): state is WorkoutPreviewState {
  return WORKOUT_PREVIEW_OPTIONS.some((option) => option.id === state);
}

type SplashPreviewState = 'pending' | 'error';
type PageLoadingPreviewState = 'home' | 'house' | 'calendar-report' | 'my-page';

const PAGE_LOADING_PREVIEW_OPTIONS = [
  { id: 'home', label: 'Home · 오늘 상태' },
  { id: 'house', label: '끼끼의 집' },
  { id: 'calendar-report', label: '운동 캘린더' },
  { id: 'my-page', label: '마이페이지' },
] as const satisfies readonly {
  id: PageLoadingPreviewState;
  label: string;
}[];

function neverResolve<T>(): Promise<T> {
  return new Promise(() => undefined);
}

/** Keeps production containers in their first-load branch without a request. */
const PAGE_LOADING_PREVIEW_API = {
  getWeek: () => neverResolve(),
  listWorkoutSessions: () => neverResolve(),
} as unknown as Api;

type DevicePreview = (typeof DEVICE_PREVIEWS)[number];
type DevicePreviewId = DevicePreview['id'] | 'custom';

const CANVAS_WIDTH_RANGE = { min: 320, max: 1920, step: 10 } as const;
const CANVAS_HEIGHT_RANGE = { min: 568, max: 1440, step: 10 } as const;

const HOME_TAB_SCREENS: Record<TabId, PreviewScreenId> = {
  home: 'home',
  // 끼끼의 집 goes to the house itself. 'Home map' stays in the gallery as the
  // `Home-p2 v1.dc.html` transcription, reachable from the screen list.
  house: 'mascot-house',
  report: 'calendar-report',
  my: 'my-page',
};

/** Pins date-sensitive gallery screens to the fixture week on every run. */
const GALLERY_PREVIEW_NOW = new Date('2026-08-22T10:00:00+09:00');

type CalendarHistoryPreviewDay = {
  localDate: string;
  sessionIds: readonly string[];
};

function addPreviewDays(localDate: string, amount: number): string {
  const value = new Date(`${localDate}T00:00:00.000Z`);
  value.setUTCDate(value.getUTCDate() + amount);
  return value.toISOString().slice(0, 10);
}

function isRecordedStatus(
  status: CalendarDayStatus,
): status is 'done' | 'partial' | 'miss' {
  return status === 'done' || status === 'partial' || status === 'miss';
}

const CALENDAR_HISTORY_PREVIEW_WEEKS = CALENDAR_WEEKS.map((week) => ({
  ...week,
  days: week.days.map((day, index) => {
    const localDate = addPreviewDays(week.weekStart, index);
    return {
      ...day,
      localDate,
      sessionIds: isRecordedStatus(day.status)
        ? [`calendar-history-${day.status}-${localDate}`]
        : [],
    };
  }),
}));

function calendarHistoryPreviewDetail(
  sessionId: string,
): WorkoutSessionDetailResponse {
  const match =
    /^calendar-history-(done|partial|miss)-(\d{4}-\d{2}-\d{2})$/.exec(
      sessionId,
    );
  if (match === null) {
    throw new Error('Unknown calendar history preview session');
  }
  const status = match[1] as 'done' | 'partial' | 'miss';
  const localDate = match[2]!;
  const completedItemCount =
    status === 'done' ? 3 : status === 'partial' ? 2 : 0;
  const items = [
    { name: '의자 스쿼트', sets: 3, reps: 10, workSeconds: null },
    { name: '벽 푸시업', sets: 3, reps: 8, workSeconds: null },
    { name: '데드 버그', sets: 2, reps: null, workSeconds: 30 },
  ].map((item, index) => ({
    plan_item_id: `${sessionId}-item-${index + 1}`,
    exercise_id: `calendar-preview-exercise-${index + 1}`,
    exercise_name: item.name,
    status_code:
      index < completedItemCount
        ? ('COMPLETED' as const)
        : ('PENDING' as const),
    sets: item.sets,
    reps: item.reps,
    work_seconds_per_set: item.workSeconds,
    completed_at:
      index < completedItemCount
        ? `${localDate}T19:${String(10 + index * 8).padStart(2, '0')}:00+09:00`
        : null,
  }));

  return {
    session_id: sessionId,
    local_date: localDate,
    status_code:
      status === 'done'
        ? 'COMPLETED'
        : status === 'partial'
          ? 'PARTIAL'
          : 'NOT_COMPLETED',
    completed_item_count: completedItemCount,
    total_item_count: items.length,
    requested_duration_minutes: 30,
    items,
    feedback:
      status === 'miss'
        ? null
        : {
            perceived_difficulty_code:
              status === 'done' ? 'APPROPRIATE' : 'HARD',
            post_workout_discomfort_reported: false,
          },
    not_completed_reason_code: status === 'miss' ? 'SCHEDULE_CHANGE' : null,
    started_at: status === 'miss' ? null : `${localDate}T19:00:00+09:00`,
    finished_at:
      status === 'miss'
        ? `${localDate}T19:00:00+09:00`
        : `${localDate}T19:${status === 'done' ? '30' : '20'}:00+09:00`,
  };
}

const calendarHistoryPreviewApi = {
  async getWorkoutSession(sessionId: string) {
    return calendarHistoryPreviewDetail(sessionId);
  },
} satisfies Pick<Api, 'getWorkoutSession'>;

export function PreviewGallery({
  initialScreenId = 'splash',
}: {
  initialScreenId?: PreviewScreenId | 'session-result';
}) {
  const { width } = useWindowDimensions();
  const [screenId, setScreenId] = useState<PreviewScreenId>(
    initialScreenId === 'session-result' ? 'workout' : initialScreenId,
  );
  const [splashState, setSplashState] = useState<SplashPreviewState>('pending');
  const [pageLoadingState, setPageLoadingState] =
    useState<PageLoadingPreviewState>('home');
  const [devicePreviewId, setDevicePreviewId] =
    useState<DevicePreviewId>('reference');
  const [customViewport, setCustomViewport] = useState<{
    width: number;
    height: number;
  }>({ ...APP_CANVAS });
  const [loginState, setLoginState] = useState<LoginPreviewState>('idle');
  const [signUpState, setSignUpState] = useState<SignUpPreviewState>('idle');
  const [profileStep, setProfileStep] = useState(1);
  const [profileState, setProfileState] =
    useState<ProfilePreviewState>('editing');
  const [onboardingStep, setOnboardingStep] = useState(1);
  const [homeState, setHomeState] = useState<HomePreviewState>('pre-checkin');
  const [homeDecisionOverride, setHomeDecisionOverride] = useState<
    DecisionResponse | undefined
  >(undefined);
  const homeTransitionTimer = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const [todayState, setTodayState] =
    useState<TodayPreviewState>('pre-checkin');
  const [sessionState, setSessionState] =
    useState<SessionPreviewState>('active');
  const [houseState, setHouseState] = useState<HousePreviewState>('loaded');
  const [weeklyReportState, setWeeklyReportState] =
    useState<WeeklyReportPreviewState>('closed');
  const [mapHomeState, setMapHomeState] = useState<MapHomePreviewState>('map');
  const [calendarReportState, setCalendarReportState] =
    useState<CalendarReportPreviewState>('calendar');
  const [calendarHistoryDay, setCalendarHistoryDay] =
    useState<CalendarHistoryPreviewDay | null>(null);
  const [myPageState, setMyPageState] = useState<MyPagePreviewState>('profile');
  const [workoutOutcome, setWorkoutOutcome] = useState<SessionOutcome | null>(
    null,
  );
  const [workoutRunKey, setWorkoutRunKey] = useState(0);
  const [workoutApi, setWorkoutApi] = useState(() =>
    createSessionPreviewApi('active'),
  );
  const [workoutState, setWorkoutState] = useState<WorkoutGalleryState>(
    initialScreenId === 'session-result' ? 'result-completed' : 'api-flow',
  );
  const selectedWorkoutResultState = workoutResultStateFor(workoutState);
  const [reducedMotion, setReducedMotion] = useState(false);
  const navigateHomeTab = useCallback((tab: TabId) => {
    setScreenId(HOME_TAB_SCREENS[tab]);
  }, []);
  const useWideLayout = width >= 920;
  const selectedDevicePreview = DEVICE_PREVIEWS.find(
    (preview) => preview.id === devicePreviewId,
  );
  const canvasViewport = selectedDevicePreview ?? customViewport;
  const usesBoundedWebCanvas = canvasViewport.width > WEB_APP_MAX_WIDTH;
  const stageAvailableWidth = Math.max(
    320,
    useWideLayout ? width - 400 : width - 48,
  );
  const canvasPreviewScale = Math.min(
    1,
    stageAvailableWidth / canvasViewport.width,
  );
  const canvasFrame = {
    width: canvasViewport.width * canvasPreviewScale,
    height: canvasViewport.height * canvasPreviewScale,
  };
  const selectDevicePreview = useCallback((preview: DevicePreview) => {
    setDevicePreviewId(preview.id);
    setCustomViewport({ width: preview.width, height: preview.height });
  }, []);
  const setCustomCanvasDimension = useCallback(
    (dimension: 'width' | 'height', value: number) => {
      setCustomViewport((current) => ({
        ...(devicePreviewId === 'custom'
          ? current
          : {
              width: selectedDevicePreview?.width ?? APP_CANVAS.width,
              height: selectedDevicePreview?.height ?? APP_CANVAS.height,
            }),
        [dimension]: value,
      }));
      setDevicePreviewId('custom');
    },
    [devicePreviewId, selectedDevicePreview],
  );
  const sessionApi = useMemo(
    () => createSessionPreviewApi(sessionState),
    [sessionState],
  );
  const houseApi = useMemo(
    () => createHousePreviewApi(houseState),
    [houseState],
  );
  // The house state lives in the gallery, not on the device: switching preview
  // states must not leave bananas behind in a designer's browser.
  const housePreviewStore = useMemo(() => createMemoryHouseStore(), []);
  const backgroundTestPreviewStore = useMemo(
    () => createMemoryHouseStore(),
    [],
  );
  const weeklyReportApi = useMemo(
    () => createWeeklyReportPreviewApi(weeklyReportState),
    [weeklyReportState],
  );
  const selectHomeState = useCallback((next: HomePreviewState) => {
    if (homeTransitionTimer.current !== null) {
      clearTimeout(homeTransitionTimer.current);
      homeTransitionTimer.current = null;
    }
    setHomeDecisionOverride(undefined);
    setHomeState(next);
  }, []);
  const reorderHomePlan = useCallback(
    (from: number, to: number) => {
      setHomeDecisionOverride((current) => {
        const decision = current ?? homePreviewProps(homeState).decision;
        if (
          decision?.final_plan === null ||
          decision?.final_plan === undefined
        ) {
          return current;
        }
        const finalPlan = moveWorkoutPlanItem(decision.final_plan, from, to);
        return finalPlan === decision.final_plan
          ? decision
          : { ...decision, final_plan: finalPlan };
      });
    },
    [homeState],
  );
  const runHomeTransition = useCallback(
    (next: HomePreviewState) => {
      selectHomeState('generating');
      homeTransitionTimer.current = setTimeout(() => {
        setHomeState(next);
        homeTransitionTimer.current = null;
      }, 600);
    },
    [selectHomeState],
  );
  const resetWorkoutFlow = useCallback(() => {
    setWorkoutOutcome(null);
    setWorkoutApi(createSessionPreviewApi('active'));
    setWorkoutRunKey((current) => current + 1);
  }, []);
  const startWorkoutPreview = useCallback(() => {
    resetWorkoutFlow();
    setWorkoutState('api-flow');
    setScreenId('workout');
  }, [resetWorkoutFlow]);

  useEffect(
    () => () => {
      if (homeTransitionTimer.current !== null) {
        clearTimeout(homeTransitionTimer.current);
      }
    },
    [],
  );

  return (
    <ScrollView
      style={styles.page}
      contentContainerStyle={[
        styles.pageContent,
        useWideLayout && styles.pageContentWide,
      ]}
    >
      <View accessibilityLabel="Preview controls" style={styles.controls}>
        <View style={styles.developmentBadge}>
          <Text style={styles.developmentBadgeText}>DEVELOPMENT ONLY</Text>
        </View>
        <Text accessibilityRole="header" style={styles.title}>
          Preview Gallery
        </Text>
        <Text style={styles.description}>
          앱 UI를 빠르게 비교하기 위한 개발 전용 화면입니다. 아래 제어는 앱
          캔버스에 포함되지 않습니다.
        </Text>
        <Text style={styles.controlHint}>
          (API)는 실제 앱 흐름에서 사용하는 UI, (mock)은 실제 앱에서 사용하지
          않는 참고·레거시 UI입니다. 모든 갤러리 데이터와 어댑터는 네트워크 없는
          개발용 mock입니다.
        </Text>

        <ControlGroup label="화면">
          {PREVIEW_SCREEN_GROUPS.map((group) => (
            <View key={group.label} style={styles.screenGroup}>
              <Text style={styles.screenGroupLabel}>{group.label}</Text>
              <View style={styles.optionRow}>
                {group.screens.map((screen) => (
                  <OptionButton
                    key={screen.id}
                    label={screen.label}
                    selected={screenId === screen.id}
                    onPress={() => setScreenId(screen.id)}
                  />
                ))}
              </View>
            </View>
          ))}
        </ControlGroup>

        <ControlGroup label="캔버스 비율">
          <View style={styles.deviceOptionColumn}>
            {DEVICE_PREVIEWS.map((preview) => (
              <OptionButton
                key={preview.id}
                label={preview.label}
                selected={devicePreviewId === preview.id}
                onPress={() => selectDevicePreview(preview)}
              />
            ))}
          </View>
          <View style={styles.dimensionControls}>
            <DimensionSlider
              label="가로 픽셀"
              max={CANVAS_WIDTH_RANGE.max}
              min={CANVAS_WIDTH_RANGE.min}
              onChange={(value) => setCustomCanvasDimension('width', value)}
              step={CANVAS_WIDTH_RANGE.step}
              value={canvasViewport.width}
            />
            <DimensionSlider
              label="세로 픽셀"
              max={CANVAS_HEIGHT_RANGE.max}
              min={CANVAS_HEIGHT_RANGE.min}
              onChange={(value) => setCustomCanvasDimension('height', value)}
              step={CANVAS_HEIGHT_RANGE.step}
              value={canvasViewport.height}
            />
          </View>
          <Text style={styles.controlHint}>
            프리셋을 고르거나 바를 움직여 직접 조절할 수 있습니다. 캔버스는 실제
            viewport 크기로 렌더링한 뒤 프리뷰 영역에 맞춰 축소해 표시합니다.
          </Text>
        </ControlGroup>

        {screenId === 'splash' ? (
          <>
            <ControlGroup label="Splash mock 상태">
              <View style={styles.optionRow}>
                <OptionButton
                  label="pending"
                  selected={splashState === 'pending'}
                  onPress={() => setSplashState('pending')}
                />
                <OptionButton
                  label="error"
                  selected={splashState === 'error'}
                  onPress={() => setSplashState('error')}
                />
              </View>
            </ControlGroup>

            <View style={styles.switchRow}>
              <View style={styles.switchCopy}>
                <Text style={styles.controlLabel}>Reduced motion</Text>
                <Text style={styles.controlHint}>
                  물음표 움직임을 멈춰 확인합니다.
                </Text>
              </View>
              <Switch
                accessibilityLabel="Reduced motion"
                value={reducedMotion}
                onValueChange={setReducedMotion}
              />
            </View>
          </>
        ) : null}

        {screenId === 'loading' ? (
          <>
            <PreviewStateOptions
              label="페이지 전환 로딩"
              options={PAGE_LOADING_PREVIEW_OPTIONS}
              selected={pageLoadingState}
              onSelect={setPageLoadingState}
            />
            <Text style={styles.contractNotice}>
              실제 앱에서 주요 탭으로 이동한 직후 표시되는 로딩 UI입니다. 비교를
              위해 API 응답만 대기 상태로 고정했으며 네트워크 요청은 보내지
              않습니다.
            </Text>
          </>
        ) : null}

        {screenId === 'auth' ? (
          <Text style={styles.contractNotice}>
            이전 통합 SignInScreen의 mock입니다. 현재 앱의 인증 진입에는
            사용하지 않습니다.
          </Text>
        ) : null}

        {screenId === 'login' ? (
          <PreviewStateOptions
            label="Login API 상태"
            options={LOGIN_PREVIEW_OPTIONS}
            selected={loginState}
            onSelect={setLoginState}
          />
        ) : null}

        {screenId === 'signup' ? (
          <>
            <PreviewStateOptions
              label="SignUp API 상태"
              options={SIGN_UP_PREVIEW_OPTIONS}
              selected={signUpState}
              onSelect={setSignUpState}
            />
            <Text style={styles.contractNotice}>
              실제 앱의 Firebase 이메일·비밀번호 회원가입 UI입니다. 갤러리
              상태는 계정과 네트워크를 변경하지 않는 fixture입니다.
            </Text>
          </>
        ) : null}

        {screenId === 'profile' ? (
          <>
            <ControlGroup label="Profile 단계">
              <View style={styles.optionRow}>
                {PROFILE_STEPS.map((step, index) => (
                  <OptionButton
                    key={step.key}
                    label={`${index + 1}. ${step.key}`}
                    selected={profileStep === index + 1}
                    onPress={() => setProfileStep(index + 1)}
                  />
                ))}
              </View>
            </ControlGroup>
            <PreviewStateOptions
              label="Profile mock 상태"
              options={PROFILE_PREVIEW_OPTIONS}
              selected={profileState}
              onSelect={(state) => {
                setProfileState(state);
                if (['saving', 'save-error', 'done'].includes(state)) {
                  setProfileStep(PROFILE_STEPS.length);
                } else if (state === 'validation-error') {
                  setProfileStep(4);
                } else if (state === 'reason') {
                  setProfileStep(1);
                }
              }}
            />
            <Text style={styles.contractNotice}>
              시각 참고 전용입니다. 실제 백엔드 필드에 연결되는 가입 후 입력은
              Onboarding (API) 화면에서 확인할 수 있습니다.
            </Text>
          </>
        ) : null}

        {screenId === 'onboarding' ? (
          <>
            <ControlGroup label="Onboarding 단계">
              <View style={styles.optionRow}>
                {ONBOARDING_STEPS.map((step, index) => (
                  <OptionButton
                    key={step.key}
                    label={`${index + 1}. ${step.key}`}
                    selected={onboardingStep === index + 1}
                    onPress={() => setOnboardingStep(index + 1)}
                  />
                ))}
              </View>
            </ControlGroup>
            <Text style={styles.contractNotice}>
              개발 확인 전용 API를 사용합니다. 입력 내용은 저장되거나 네트워크로
              전송되지 않지만, 실제 화면과 동일한 요청 필드로 구성됩니다.
            </Text>
          </>
        ) : null}

        {screenId === 'home' ? (
          <>
            <PreviewStateOptions
              label="Home mock 상태"
              options={HOME_PREVIEW_OPTIONS}
              selected={homeState}
              onSelect={selectHomeState}
            />
            <Text style={styles.contractNotice}>
              시각 참고 전용: 체크인·루틴 생성·조정 결과는 fixture이며 최종 추천
              1개만 표시합니다.
            </Text>
          </>
        ) : null}

        {screenId === 'today' ? (
          <>
            <PreviewStateOptions
              label="Previous Home API 응답 상태"
              options={TODAY_PREVIEW_OPTIONS}
              selected={todayState}
              onSelect={setTodayState}
            />
            <Text style={styles.contractNotice}>
              비교 전용: Git의 이전 API 연동형 Home에 서버 응답 fixture를
              주입합니다. 현재 Home과 실제 앱 경로는 변경하지 않습니다.
            </Text>
          </>
        ) : null}

        {screenId === 'session' ? (
          <>
            <PreviewStateOptions
              label="Workout session mock 상태"
              options={SESSION_PREVIEW_OPTIONS}
              selected={sessionState}
              onSelect={setSessionState}
            />
            <Text style={styles.contractNotice}>
              세션 시작, 블록 완료, 타이머 이벤트, 안전 중단과 미수행 기록을
              실제 API 응답 형태의 개발용 fixture로 확인합니다.
            </Text>
          </>
        ) : null}

        {screenId === 'mascot-house' ? (
          <>
            <PreviewStateOptions
              label="Mascot house API 응답 상태"
              options={HOUSE_PREVIEW_OPTIONS}
              selected={houseState}
              onSelect={setHouseState}
            />
            <Text style={styles.contractNotice}>
              주간 목표와 운동 기록을 백엔드 응답 형태의 fixture에서 읽습니다.
              바나나·꾸미기 상태는 아직 서버에 없어 기기에만 저장됩니다.
            </Text>
          </>
        ) : null}

        {screenId === 'background_test' ? (
          <>
            <PreviewStateOptions
              label="background_test mock 상태"
              options={HOUSE_PREVIEW_OPTIONS}
              selected={houseState}
              onSelect={setHouseState}
            />
            <Text style={styles.contractNotice}>
              독립된 background_test 화면에서 moving_temp 레이어의 반복 움직임만
              시험합니다.
            </Text>
          </>
        ) : null}

        {screenId === 'weekly-report' ? (
          <>
            <PreviewStateOptions
              label="Weekly report API 응답 상태"
              options={WEEKLY_REPORT_PREVIEW_OPTIONS}
              selected={weeklyReportState}
              onSelect={setWeeklyReportState}
            />
            <Text style={styles.contractNotice}>
              주 마감 상태, 리포트 생성과 사용자 확인 흐름을 개발용 응답으로
              확인합니다.
            </Text>
          </>
        ) : null}

        {screenId === 'account' ? (
          <Text style={styles.contractNotice}>
            프로필 응답과 계정 삭제 접수 흐름을 확인합니다. 실제 계정이나
            데이터는 변경되지 않습니다.
          </Text>
        ) : null}

        {screenId === 'home-map' ? (
          <>
            <PreviewStateOptions
              label="Home map mock 상태"
              options={MAP_HOME_PREVIEW_OPTIONS}
              selected={mapHomeState}
              onSelect={setMapHomeState}
            />
            <Text style={styles.contractNotice}>
              제품 경계: 원본의 lighter/original 공개 선택지는 이관하지 않고
              최종 추천 1개와 휴식 동작만 표시합니다.
            </Text>
          </>
        ) : null}

        {screenId === 'calendar-report' ? (
          <>
            <PreviewStateOptions
              label="Calendar/report mock 상태"
              options={CALENDAR_REPORT_PREVIEW_OPTIONS}
              selected={calendarReportState}
              onSelect={(state) => {
                setCalendarHistoryDay(null);
                setCalendarReportState(state);
              }}
            />
            <Text style={styles.contractNotice}>
              시각 참고 전용: 날짜별 수행 상태와 상세 운동 기록은 fixture이며
              리포트 생성·확인은 저장하지 않습니다.
            </Text>
          </>
        ) : null}

        {screenId === 'my-page' ? (
          <>
            <PreviewStateOptions
              label="My page(API) mock 상태"
              options={MY_PAGE_PREVIEW_OPTIONS}
              selected={myPageState}
              onSelect={setMyPageState}
            />
            <Text style={styles.contractNotice}>
              프로필·운동 기록·목표·선택 동의·계정 삭제 API 흐름을 개발용
              응답으로 확인합니다. 실제 계정이나 데이터는 변경되지 않습니다.
            </Text>
          </>
        ) : null}

        {screenId === 'workout' ? (
          <>
            <PreviewStateOptions
              label="Workout 세부 화면"
              options={WORKOUT_GALLERY_OPTIONS}
              selected={workoutState}
              onSelect={(state) => {
                setWorkoutState(state);
                if (state === 'api-flow') {
                  resetWorkoutFlow();
                }
              }}
            />
            <Text style={styles.contractNotice}>
              {workoutState === 'api-flow'
                ? '개발 확인 전용 API를 사용합니다. 시작·타이머·블록·중단·안전 보고·피드백은 실제 프론트엔드 API 계약으로 연결되며, 데이터는 네트워크로 전송되지 않습니다.'
                : selectedWorkoutResultState !== null
                  ? '실제 앱 흐름의 Workout 결과 UI입니다. 서버가 확정한 완료·일부 완료·미수행·안전 중단 결과를 갤러리 fixture로 표시합니다.'
                  : '세부 화면 시각 확인용 fixture입니다. 타이머와 블록 체크는 공식 완료를 결정하지 않습니다.'}
            </Text>
          </>
        ) : null}

        <Text style={styles.directLinkHint}>
          단독 진입: ?preview={screenId}
        </Text>
      </View>

      <View style={styles.stage}>
        <View style={styles.canvasHeading}>
          <Text style={styles.canvasTitle}>App canvas</Text>
          {usesBoundedWebCanvas ? (
            <Text style={styles.canvasLimit}>App max 640px</Text>
          ) : null}
          <Text style={styles.canvasSize}>
            {canvasViewport.width} × {canvasViewport.height}
          </Text>
        </View>
        <View
          testID="preview-canvas-frame"
          style={[styles.canvasFrame, canvasFrame]}
        >
          <View
            testID="preview-app-canvas"
            style={[
              styles.canvas,
              {
                width: canvasViewport.width,
                height: canvasViewport.height,
                transform: [{ scale: canvasPreviewScale }],
              },
            ]}
          >
            <View
              style={[
                styles.previewAppShell,
                usesBoundedWebCanvas && styles.previewWebAppShell,
              ]}
            >
              <View
                style={[
                  styles.previewAppContent,
                  usesBoundedWebCanvas && styles.previewWebAppContent,
                ]}
                testID="preview-app-content"
              >
                <ScaleViewportProvider viewport={canvasViewport}>
                  {screenId === 'splash' ? (
                    <SplashScreen
                      bootStatus={splashState}
                      onRetry={() => setSplashState('pending')}
                      reducedMotionOverride={reducedMotion}
                      viewportOverride={canvasViewport}
                    />
                  ) : null}
                  {screenId === 'loading' && pageLoadingState === 'home' ? (
                    <HomeScreen
                      {...homePreviewProps('pre-checkin')}
                      status="loading"
                    />
                  ) : null}
                  {screenId === 'loading' && pageLoadingState === 'house' ? (
                    <MascotHouseScreen
                      api={PAGE_LOADING_PREVIEW_API}
                      nickname={PREVIEW_ME.profile?.nickname ?? '미리보기'}
                      now={GALLERY_PREVIEW_NOW}
                      onNavigate={navigateHomeTab}
                      store={housePreviewStore}
                      timeZone="Asia/Seoul"
                    />
                  ) : null}
                  {screenId === 'loading' &&
                  pageLoadingState === 'calendar-report' ? (
                    <CalendarReportContainer
                      api={PAGE_LOADING_PREVIEW_API}
                      now={GALLERY_PREVIEW_NOW}
                      onNavigateTab={navigateHomeTab}
                      onOpenWeeklyReport={() => undefined}
                      routineStartLocalDate="2026-08-01"
                      timeZone="Asia/Seoul"
                    />
                  ) : null}
                  {screenId === 'loading' && pageLoadingState === 'my-page' ? (
                    <MyPageScreen
                      me={PREVIEW_ME}
                      onNavigateTab={navigateHomeTab}
                      previewState="loading"
                    />
                  ) : null}
                  {screenId === 'auth' ? (
                    <SignInScreen auth={authPreviewAdapter} />
                  ) : null}
                  {screenId === 'login' ? (
                    <LoginScreen
                      onRetry={() => setLoginState('idle')}
                      onSignUp={() => setScreenId('signup')}
                      previewState={loginState}
                    />
                  ) : null}
                  {screenId === 'signup' ? (
                    <SignUpScreen
                      onBack={() => setScreenId('login')}
                      previewState={signUpState}
                    />
                  ) : null}
                  {screenId === 'profile' ? (
                    <ProfileScreen
                      initialStep={profileStep}
                      onStepChange={setProfileStep}
                      previewState={profileState}
                    />
                  ) : null}
                  {screenId === 'onboarding' ? (
                    <OnboardingScreen
                      api={onboardingPreviewApi}
                      initialStep={onboardingStep}
                      onCompleted={() => undefined}
                      onSignOut={() => undefined}
                      onStepChange={setOnboardingStep}
                    />
                  ) : null}
                  {screenId === 'home' ? (
                    <HomeScreen
                      {...homePreviewProps(homeState)}
                      decision={
                        homeDecisionOverride ??
                        homePreviewProps(homeState).decision
                      }
                      onChooseRest={() => selectHomeState('rest')}
                      onNavigateTab={navigateHomeTab}
                      onOpenCalendar={() => setScreenId('calendar-report')}
                      onProfile={() => setScreenId('my-page')}
                      onReorderPlan={reorderHomePlan}
                      onRequestAiRevision={() => runHomeTransition('adjusted')}
                      onStartWorkout={startWorkoutPreview}
                      onSubmitCheckin={() => runHomeTransition('routine')}
                      onSubmitUserEdits={() => runHomeTransition('adjusted')}
                    />
                  ) : null}
                  {screenId === 'today' ? (
                    <PreviousHomeScreen
                      {...previousHomePreviewProps(todayState)}
                    />
                  ) : null}
                  {screenId === 'session' ? (
                    <SessionScreen
                      key={sessionState}
                      api={sessionApi}
                      sessionId="session-preview"
                      plan={PREVIEW_PLAN}
                      onOutcome={() => undefined}
                    />
                  ) : null}
                  {screenId === 'mascot-house' ? (
                    <MascotHouseScreen
                      key={houseState}
                      api={houseApi}
                      nickname={PREVIEW_ME.profile?.nickname ?? '미리보기'}
                      now={GALLERY_PREVIEW_NOW}
                      onNavigate={navigateHomeTab}
                      store={housePreviewStore}
                      timeZone="Asia/Seoul"
                    />
                  ) : null}
                  {screenId === 'background_test' ? (
                    <BackgroundTestScreen
                      key={houseState}
                      api={houseApi}
                      nickname={PREVIEW_ME.profile?.nickname ?? '미리보기'}
                      now={GALLERY_PREVIEW_NOW}
                      onNavigate={navigateHomeTab}
                      store={backgroundTestPreviewStore}
                      timeZone="Asia/Seoul"
                    />
                  ) : null}
                  {screenId === 'weekly-report' ? (
                    <WeeklyReportScreen
                      key={weeklyReportState}
                      api={weeklyReportApi}
                      now={GALLERY_PREVIEW_NOW}
                      onBack={() => setScreenId('calendar-report')}
                      onNavigateTab={navigateHomeTab}
                      timeZone="Asia/Seoul"
                    />
                  ) : null}
                  {screenId === 'account' ? (
                    <AccountScreen
                      api={accountPreviewApi}
                      me={PREVIEW_ME}
                      onBack={() => undefined}
                      onSignOut={() => undefined}
                    />
                  ) : null}
                  {screenId === 'home-map' ? (
                    <MapHomeScreen
                      onNavigateTab={navigateHomeTab}
                      previewState={mapHomeState}
                      routine={PREVIEW_ROUTINE}
                      week={PREVIEW_OPEN_WEEK}
                    />
                  ) : null}
                  {screenId === 'calendar-report' ? (
                    <>
                      <CalendarReportScreen
                        onNavigateTab={navigateHomeTab}
                        onOpenDay={(day: CalendarDay) => {
                          if (day.localDate && day.sessionIds?.length) {
                            setCalendarHistoryDay({
                              localDate: day.localDate,
                              sessionIds: day.sessionIds,
                            });
                          }
                        }}
                        onOpenWeeklyReport={() => setScreenId('weekly-report')}
                        previewState={calendarReportState}
                        weeks={CALENDAR_HISTORY_PREVIEW_WEEKS}
                      />
                      {calendarHistoryDay ? (
                        <WorkoutHistorySheet
                          api={calendarHistoryPreviewApi}
                          localDate={calendarHistoryDay.localDate}
                          onClose={() => setCalendarHistoryDay(null)}
                          sessionIds={calendarHistoryDay.sessionIds}
                        />
                      ) : null}
                    </>
                  ) : null}
                  {screenId === 'my-page' ? (
                    <MyPageContainer
                      api={accountPreviewApi}
                      me={PREVIEW_ME}
                      onNavigateTab={navigateHomeTab}
                      onRefreshMe={async () => undefined}
                      onSignOut={() => undefined}
                      previewState={myPageState}
                    />
                  ) : null}
                  {screenId === 'workout' ? (
                    selectedWorkoutResultState !== null ? (
                      <SessionResultScreen
                        key={selectedWorkoutResultState}
                        api={sessionResultPreviewApi}
                        sessionId="session-preview"
                        outcome={sessionResultPreviewOutcome(
                          selectedWorkoutResultState,
                        )}
                        onDone={() => undefined}
                      />
                    ) : isWorkoutPreviewState(workoutState) ? (
                      <WorkoutScreen previewState={workoutState} />
                    ) : workoutOutcome === null ? (
                      <WorkoutScreen
                        key={workoutRunKey}
                        api={workoutApi}
                        sessionId="session-preview"
                        plan={PREVIEW_PLAN}
                        onOutcome={setWorkoutOutcome}
                      />
                    ) : (
                      <SessionResultScreen
                        api={workoutApi}
                        sessionId="session-preview"
                        outcome={workoutOutcome}
                        onDone={() => {
                          resetWorkoutFlow();
                          setScreenId('home');
                        }}
                      />
                    )
                  ) : null}
                </ScaleViewportProvider>
              </View>
            </View>
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

function PreviewStateOptions<T extends string>({
  label,
  onSelect,
  options,
  selected,
}: {
  label: string;
  onSelect: (state: T) => void;
  options: readonly { id: T; label: string }[];
  selected: T;
}) {
  return (
    <ControlGroup label={label}>
      <View style={styles.optionRow}>
        {options.map((option) => (
          <OptionButton
            key={option.id}
            label={option.label}
            selected={selected === option.id}
            onPress={() => onSelect(option.id)}
          />
        ))}
      </View>
    </ControlGroup>
  );
}

function ControlGroup({
  children,
  label,
}: {
  children: React.ReactNode;
  label: string;
}) {
  return (
    <View style={styles.controlGroup}>
      <Text style={styles.controlLabel}>{label}</Text>
      {children}
    </View>
  );
}

function OptionButton({
  label,
  onPress,
  selected,
}: {
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={[styles.optionButton, selected && styles.optionButtonSelected]}
    >
      <Text
        style={[styles.optionLabel, selected && styles.optionLabelSelected]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function DimensionSlider({
  label,
  max,
  min,
  onChange,
  step,
  value,
}: {
  label: string;
  max: number;
  min: number;
  onChange: (value: number) => void;
  step: number;
  value: number;
}) {
  const [trackWidth, setTrackWidth] = useState(0);
  const boundedValue = Math.min(max, Math.max(min, value));
  const [draftValue, setDraftValue] = useState<string | null>(null);
  const progress = (boundedValue - min) / (max - min);

  const commitDraftValue = () => {
    const parsedValue = Number.parseInt(draftValue ?? '', 10);
    const nextValue = Number.isFinite(parsedValue)
      ? Math.min(max, Math.max(min, parsedValue))
      : boundedValue;
    setDraftValue(null);
    onChange(nextValue);
  };
  const updateFromTrack = (locationX: number) => {
    if (trackWidth <= 0) {
      return;
    }
    const ratio = Math.min(1, Math.max(0, locationX / trackWidth));
    const stepped = Math.round((min + ratio * (max - min)) / step) * step;
    onChange(Math.min(max, Math.max(min, stepped)));
  };
  const adjust = (direction: -1 | 1) => {
    onChange(Math.min(max, Math.max(min, boundedValue + direction * step)));
  };

  return (
    <View style={styles.dimensionControl}>
      <View style={styles.dimensionLabelRow}>
        <Text style={styles.dimensionLabel}>{label}</Text>
        <View style={styles.dimensionInputRow}>
          <TextInput
            accessibilityLabel={`${label} 직접 입력`}
            inputMode="numeric"
            keyboardType="number-pad"
            onBlur={commitDraftValue}
            onChangeText={(text) => setDraftValue(text.replace(/\D/g, ''))}
            onFocus={() => setDraftValue(String(boundedValue))}
            onSubmitEditing={commitDraftValue}
            returnKeyType="done"
            selectTextOnFocus
            style={styles.dimensionValueInput}
            value={draftValue ?? String(boundedValue)}
          />
          <Text style={styles.dimensionUnit}>px</Text>
        </View>
      </View>
      <View
        accessible
        accessibilityActions={[
          { name: 'increment', label: `${label} 늘리기` },
          { name: 'decrement', label: `${label} 줄이기` },
        ]}
        accessibilityLabel={label}
        accessibilityRole="adjustable"
        accessibilityValue={{
          max,
          min,
          now: boundedValue,
          text: `${boundedValue} 픽셀`,
        }}
        onAccessibilityAction={(event) => {
          if (event.nativeEvent.actionName === 'increment') {
            adjust(1);
          } else if (event.nativeEvent.actionName === 'decrement') {
            adjust(-1);
          }
        }}
        onLayout={(event) => setTrackWidth(event.nativeEvent.layout.width)}
        onMoveShouldSetResponder={() => true}
        onResponderGrant={(event) =>
          updateFromTrack(event.nativeEvent.locationX)
        }
        onResponderMove={(event) =>
          updateFromTrack(event.nativeEvent.locationX)
        }
        onStartShouldSetResponder={() => true}
        style={styles.sliderTouchTarget}
      >
        <View pointerEvents="none" style={styles.sliderTrack}>
          <View style={[styles.sliderFill, { width: `${progress * 100}%` }]} />
          <View style={[styles.sliderThumb, { left: `${progress * 100}%` }]} />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {
    flex: 1,
    backgroundColor: '#EEF1F4',
  },
  pageContent: {
    minHeight: '100%',
    alignItems: 'center',
    padding: 24,
  },
  pageContentWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'center',
    gap: 32,
  },
  controls: {
    width: '100%',
    maxWidth: 320,
    borderWidth: 1,
    borderColor: '#D7DCE2',
    borderRadius: 20,
    backgroundColor: '#FFFFFF',
    padding: 20,
  },
  developmentBadge: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#FFF0C2',
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  developmentBadgeText: {
    color: '#785400',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.7,
  },
  title: {
    marginTop: 14,
    color: '#16202A',
    fontSize: 26,
    fontWeight: '800',
  },
  description: {
    marginTop: 8,
    color: '#55616D',
    fontSize: 14,
    lineHeight: 21,
  },
  controlGroup: {
    marginTop: 24,
    gap: 10,
  },
  controlLabel: {
    color: '#26323D',
    fontSize: 14,
    fontWeight: '700',
  },
  controlHint: {
    marginTop: 3,
    color: '#74808B',
    fontSize: 12,
    lineHeight: 17,
  },
  screenGroup: {
    gap: 7,
  },
  screenGroupLabel: {
    color: '#74808B',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  optionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  deviceOptionColumn: {
    alignItems: 'stretch',
    gap: 8,
  },
  dimensionControls: {
    gap: 12,
    marginTop: 4,
    borderTopWidth: 1,
    borderTopColor: '#E6E9EC',
    paddingTop: 14,
  },
  dimensionControl: {
    gap: 4,
  },
  dimensionLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  dimensionLabel: {
    color: '#4E5A65',
    fontSize: 12,
    fontWeight: '700',
  },
  dimensionInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  dimensionValueInput: {
    width: 58,
    borderWidth: 1,
    borderColor: '#C9D0D7',
    borderRadius: 7,
    backgroundColor: '#FFFFFF',
    color: '#23552C',
    fontSize: 12,
    fontVariant: ['tabular-nums'],
    fontWeight: '800',
    paddingHorizontal: 7,
    paddingVertical: 4,
    textAlign: 'right',
  },
  dimensionUnit: {
    color: '#68747F',
    fontSize: 12,
    fontWeight: '700',
  },
  sliderTouchTarget: {
    height: 30,
    justifyContent: 'center',
  },
  sliderTrack: {
    height: 6,
    borderRadius: 999,
    backgroundColor: '#DCE2E6',
  },
  sliderFill: {
    height: 6,
    borderRadius: 999,
    backgroundColor: '#4F8E43',
  },
  sliderThumb: {
    position: 'absolute',
    top: -5,
    width: 16,
    height: 16,
    marginLeft: -8,
    borderWidth: 2,
    borderColor: '#FFFFFF',
    borderRadius: 999,
    backgroundColor: '#A45F00',
    shadowColor: '#16202A',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
  },
  optionButton: {
    minWidth: 88,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#C9D0D7',
    borderRadius: 10,
    backgroundColor: '#F8F9FA',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  optionButtonSelected: {
    borderColor: '#306B3A',
    backgroundColor: '#E8F4E9',
  },
  optionLabel: {
    color: '#596571',
    fontSize: 13,
    fontWeight: '700',
  },
  optionLabelSelected: {
    color: '#23552C',
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 16,
    marginTop: 24,
  },
  switchCopy: {
    flex: 1,
  },
  directLinkHint: {
    marginTop: 24,
    borderRadius: 8,
    backgroundColor: '#F1F3F5',
    color: '#4A5560',
    fontSize: 12,
    padding: 10,
  },
  contractNotice: {
    marginTop: 16,
    borderWidth: 1,
    borderColor: '#E1C48F',
    borderRadius: 10,
    backgroundColor: '#FFF8E8',
    color: '#765513',
    fontSize: 12,
    lineHeight: 18,
    padding: 10,
  },
  stage: {
    marginTop: 24,
  },
  canvasHeading: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  canvasTitle: {
    color: '#26323D',
    fontSize: 14,
    fontWeight: '800',
  },
  canvasLimit: {
    color: '#306B3A',
    fontSize: 11,
    fontWeight: '800',
  },
  canvasSize: {
    color: '#68747F',
    fontSize: 12,
    fontWeight: '700',
  },
  canvas: {
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#AEB7C0',
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
    transformOrigin: 'top left',
  },
  canvasFrame: {
    overflow: 'hidden',
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
  },
  previewAppShell: {
    width: '100%',
    flex: 1,
  },
  previewWebAppShell: {
    alignItems: 'center',
    backgroundColor: '#EEF2E8',
  },
  previewAppContent: {
    width: '100%',
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  previewWebAppContent: {
    maxWidth: WEB_APP_MAX_WIDTH,
  },
});
