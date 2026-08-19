import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';

import { ScaleViewportProvider } from '../../components/scale';
import { LoginScreen } from '../auth/LoginScreen';
import {
  LOGIN_PREVIEW_OPTIONS,
  type LoginPreviewState,
  SIGN_UP_PREVIEW_OPTIONS,
  type SignUpPreviewState,
} from '../auth/previewStates';
import { SignUpScreen } from '../auth/SignUpScreen';
import { CalendarReportScreen } from '../home/CalendarReportScreen';
import { HOME_PREVIEW_OPTIONS, type HomePreviewState } from '../home/homeModel';
import { HomeScreen } from '../home/HomeScreen';
import {
  CALENDAR_REPORT_PREVIEW_OPTIONS,
  type CalendarReportPreviewState,
  MAP_HOME_PREVIEW_OPTIONS,
  type MapHomePreviewState,
  MY_PAGE_PREVIEW_OPTIONS,
  type MyPagePreviewState,
} from '../home/homeSecondaryModel';
import { MapHomeScreen } from '../home/MapHomeScreen';
import { MyPageScreen } from '../home/MyPageScreen';
import { PreviousHomeScreen } from '../home/PreviousHomeScreen';
import { MascotHouseScreen } from '../house/MascotHouseScreen';
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
import { SessionScreen } from '../workout/SessionScreen';
import { WorkoutScreen } from '../workout/WorkoutScreen';
import {
  WORKOUT_PREVIEW_OPTIONS,
  type WorkoutPreviewState,
} from '../workout/workoutModel';
import { homePreviewProps } from './homePreview';
import { onboardingPreviewApi } from './onboardingPreview';
import {
  accountPreviewApi,
  createHousePreviewApi,
  createSessionPreviewApi,
  createWeeklyReportPreviewApi,
  HOUSE_PREVIEW_OPTIONS,
  type HousePreviewState,
  PREVIEW_PLAN,
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
] as const;
export const SPLASH_DEVICE_PREVIEWS = DEVICE_PREVIEWS;
const PREVIEW_SCREENS = [
  { id: 'splash', label: 'Splash' },
  { id: 'login', label: 'Login (API)' },
  { id: 'signup', label: 'SignUp (API)' },
  { id: 'profile', label: 'Profile' },
  { id: 'onboarding', label: 'Onboarding (API)' },
  { id: 'today', label: 'Home previous (API)' },
  { id: 'session', label: 'Workout session (API)' },
  { id: 'session-result', label: 'Workout result (API)' },
  { id: 'mascot-house', label: 'Mascot house (API)' },
  { id: 'weekly-report', label: 'Weekly report (API)' },
  { id: 'account', label: 'Account (API)' },
  { id: 'home', label: 'Home (API)' },
  { id: 'home-map', label: 'Home map' },
  { id: 'calendar-report', label: 'Calendar/report(API)' },
  { id: 'my-page', label: 'My page' },
  { id: 'workout', label: 'Workout(API)' },
] as const;

export type PreviewScreenId = (typeof PREVIEW_SCREENS)[number]['id'];
type SplashPreviewState = 'pending' | 'error';
type DevicePreviewId = (typeof DEVICE_PREVIEWS)[number]['id'];

export function PreviewGallery({
  initialScreenId = 'splash',
}: {
  initialScreenId?: PreviewScreenId;
}) {
  const { width } = useWindowDimensions();
  const [screenId, setScreenId] = useState<PreviewScreenId>(initialScreenId);
  const [splashState, setSplashState] = useState<SplashPreviewState>('pending');
  const [devicePreviewId, setDevicePreviewId] =
    useState<DevicePreviewId>('reference');
  const [loginState, setLoginState] = useState<LoginPreviewState>('idle');
  const [signUpState, setSignUpState] = useState<SignUpPreviewState>('idle');
  const [profileStep, setProfileStep] = useState(1);
  const [profileState, setProfileState] =
    useState<ProfilePreviewState>('editing');
  const [onboardingStep, setOnboardingStep] = useState(1);
  const [homeState, setHomeState] = useState<HomePreviewState>('pre-checkin');
  const homeTransitionTimer = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const [todayState, setTodayState] =
    useState<TodayPreviewState>('pre-checkin');
  const [sessionState, setSessionState] =
    useState<SessionPreviewState>('active');
  const [sessionResultState, setSessionResultState] =
    useState<SessionResultPreviewState>('completed');
  const [houseState, setHouseState] = useState<HousePreviewState>('loaded');
  const [weeklyReportState, setWeeklyReportState] =
    useState<WeeklyReportPreviewState>('closed');
  const [mapHomeState, setMapHomeState] = useState<MapHomePreviewState>('map');
  const [calendarReportState, setCalendarReportState] =
    useState<CalendarReportPreviewState>('calendar');
  const [myPageState, setMyPageState] = useState<MyPagePreviewState>('profile');
  const [workoutState, setWorkoutState] =
    useState<WorkoutPreviewState>('active');
  const [reducedMotion, setReducedMotion] = useState(false);
  const useWideLayout = width >= 920;
  const canvasViewport =
    DEVICE_PREVIEWS.find((preview) => preview.id === devicePreviewId) ??
    APP_CANVAS;
  const sessionApi = useMemo(
    () => createSessionPreviewApi(sessionState),
    [sessionState],
  );
  const houseApi = useMemo(
    () => createHousePreviewApi(houseState),
    [houseState],
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
    setHomeState(next);
  }, []);
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

        <ControlGroup label="화면">
          <View style={styles.optionRow}>
            {PREVIEW_SCREENS.map((screen) => (
              <OptionButton
                key={screen.id}
                label={screen.label}
                selected={screenId === screen.id}
                onPress={() => setScreenId(screen.id)}
              />
            ))}
          </View>
        </ControlGroup>

        <ControlGroup label="기기 비율">
          <View style={styles.deviceOptionColumn}>
            {DEVICE_PREVIEWS.map((preview) => (
              <OptionButton
                key={preview.id}
                label={preview.label}
                selected={devicePreviewId === preview.id}
                onPress={() => setDevicePreviewId(preview.id)}
              />
            ))}
          </View>
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

        {screenId === 'login' ? (
          <PreviewStateOptions
            label="Login mock 상태"
            options={LOGIN_PREVIEW_OPTIONS}
            selected={loginState}
            onSelect={setLoginState}
          />
        ) : null}

        {screenId === 'signup' ? (
          <>
            <PreviewStateOptions
              label="SignUp mock 상태"
              options={SIGN_UP_PREVIEW_OPTIONS}
              selected={signUpState}
              onSelect={setSignUpState}
            />
            <Text style={styles.contractNotice}>
              시각 참고 전용: 로컬 계정 유지 여부와 Firebase 인증 계약은
              미확정입니다.
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
              label="Workout session API 응답 상태"
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

        {screenId === 'session-result' ? (
          <>
            <PreviewStateOptions
              label="Workout result 서버 결과"
              options={SESSION_RESULT_PREVIEW_OPTIONS}
              selected={sessionResultState}
              onSelect={setSessionResultState}
            />
            <Text style={styles.contractNotice}>
              서버가 확정한 완료·일부 완료·미수행·안전 중단 결과와 피드백 저장
              화면을 표시합니다.
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
              현재 루틴과 주간 목표를 백엔드 응답 형태의 fixture에서 읽습니다.
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
              onSelect={setCalendarReportState}
            />
            <Text style={styles.contractNotice}>
              시각 참고 전용: 날짜별 수행 상태와 주간 집계는 fixture이며 리포트
              생성·확인은 저장하지 않습니다.
            </Text>
          </>
        ) : null}

        {screenId === 'my-page' ? (
          <>
            <PreviewStateOptions
              label="My page mock 상태"
              options={MY_PAGE_PREVIEW_OPTIONS}
              selected={myPageState}
              onSelect={setMyPageState}
            />
            <Text style={styles.contractNotice}>
              시각 참고 전용: 프로필·기록·연동·알림·계정 값은 저장되지 않는
              fixture입니다.
            </Text>
          </>
        ) : null}

        {screenId === 'workout' ? (
          <>
            <PreviewStateOptions
              label="Workout mock 상태"
              options={WORKOUT_PREVIEW_OPTIONS}
              selected={workoutState}
              onSelect={setWorkoutState}
            />
            <Text style={styles.contractNotice}>
              시각 참고 전용: 타이머와 블록 체크는 공식 완료를 결정하지 않으며,
              안전 안내와 결과는 서버 응답 fixture로 분리했습니다.
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
          <Text style={styles.canvasSize}>
            {canvasViewport.width} × {canvasViewport.height}
          </Text>
        </View>
        <View
          testID="preview-app-canvas"
          style={[
            styles.canvas,
            {
              width: canvasViewport.width,
              height: canvasViewport.height,
            },
          ]}
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
                onChooseRest={() => selectHomeState('rest')}
                onNavigateTab={(tab) => {
                  if (tab === 'house') {
                    setScreenId('mascot-house');
                  } else if (tab === 'report') {
                    setScreenId('weekly-report');
                  } else if (tab === 'my') {
                    setScreenId('account');
                  }
                }}
                onOpenCalendar={() => setScreenId('calendar-report')}
                onProfile={() => setScreenId('account')}
                onRequestAiRevision={() => runHomeTransition('adjusted')}
                onStartWorkout={() => setScreenId('session')}
                onSubmitCheckin={() => runHomeTransition('routine')}
                onSubmitUserEdits={() => runHomeTransition('adjusted')}
              />
            ) : null}
            {screenId === 'today' ? (
              <PreviousHomeScreen {...previousHomePreviewProps(todayState)} />
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
            {screenId === 'session-result' ? (
              <SessionResultScreen
                key={sessionResultState}
                api={sessionResultPreviewApi}
                sessionId="session-preview"
                outcome={sessionResultPreviewOutcome(sessionResultState)}
                onDone={() => undefined}
              />
            ) : null}
            {screenId === 'mascot-house' ? (
              <MascotHouseScreen
                key={houseState}
                api={houseApi}
                nickname={PREVIEW_ME.profile?.nickname ?? '미리보기'}
                onNavigate={() => undefined}
              />
            ) : null}
            {screenId === 'weekly-report' ? (
              <WeeklyReportScreen
                key={weeklyReportState}
                api={weeklyReportApi}
                onBack={() => undefined}
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
              <MapHomeScreen previewState={mapHomeState} />
            ) : null}
            {screenId === 'calendar-report' ? (
              <CalendarReportScreen previewState={calendarReportState} />
            ) : null}
            {screenId === 'my-page' ? (
              <MyPageScreen previewState={myPageState} />
            ) : null}
            {screenId === 'workout' ? (
              <WorkoutScreen previewState={workoutState} />
            ) : null}
          </ScaleViewportProvider>
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
  optionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  deviceOptionColumn: {
    alignItems: 'stretch',
    gap: 8,
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
  },
});
