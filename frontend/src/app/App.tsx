import {
  NavigationContainer,
  createNavigationContainerRef,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { WEB_APP_MAX_WIDTH } from '../components/scale';
import { LoginScreen } from '../features/auth/LoginScreen';
import { SignUpScreen } from '../features/auth/SignUpScreen';
import { CalendarReportScreen } from '../features/home/CalendarReportScreen';
import { HomeScreen } from '../features/home/HomeScreen';
import { MapHomeScreen } from '../features/home/MapHomeScreen';
import { OnboardingScreen } from '../features/onboarding/OnboardingScreen';
import {
  PREVIEW_OPEN_WEEK,
  PREVIEW_ROUTINE,
} from '../features/preview/backendPreview';
import { homePreviewProps } from '../features/preview/homePreview';
import { onboardingPreviewApi } from '../features/preview/onboardingPreview';
import { PreviewGallery } from '../features/preview/PreviewGallery';
import { ProfileScreen } from '../features/profile/ProfileScreen';
import { SceneEditor } from '../features/sceneEditor/SceneEditor';
import { isSceneEditorRoute } from '../features/sceneEditor/sceneEditorRoute';
import { SplashScreen } from '../features/splash/SplashScreen';
import {
  type BootDestination,
  type BootDestinationResolver,
  resolveBootDestination,
} from './bootstrap';
import { DemoApp } from './DemoApp';
import {
  getPreviewMode,
  getPreviewViewportMode,
  type PreviewMode,
  type PreviewViewportMode,
} from './preview';
import { SessionProvider } from './SessionProvider';

export type RootStackParamList = {
  Splash: undefined;
  Auth: undefined;
  Main: undefined;
};

type BootState =
  | { status: 'pending' }
  | { status: 'ready'; destination: BootDestination }
  | { status: 'error' };

type AppProps = {
  bootResolver?: BootDestinationResolver;
  onNavigationTransition?: (destination: BootDestination) => void;
  previewMode?: PreviewMode;
  previewViewport?: PreviewViewportMode;
  splashPreview?: boolean;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const navigationRef = createNavigationContainerRef<RootStackParamList>();

function PlaceholderScreen({ label }: { label: string }) {
  return (
    <View style={styles.placeholder}>
      <Text accessibilityRole="header" style={styles.placeholderText}>
        {label}
      </Text>
    </View>
  );
}

function AppNavigator({
  bootResolver = resolveBootDestination,
  onNavigationTransition,
}: AppProps) {
  const requestId = useRef(0);
  const didNavigate = useRef(false);
  const [isNavigationReady, setNavigationReady] = useState(false);
  const [bootState, setBootState] = useState<BootState>({ status: 'pending' });

  const executeBoot = useCallback(() => {
    const currentRequest = ++requestId.current;

    void bootResolver().then(
      (destination) => {
        if (requestId.current === currentRequest) {
          setBootState({ status: 'ready', destination });
        }
      },
      () => {
        if (requestId.current === currentRequest) {
          setBootState({ status: 'error' });
        }
      },
    );
  }, [bootResolver]);

  const beginBoot = useCallback(() => {
    setBootState({ status: 'pending' });
    executeBoot();
  }, [executeBoot]);

  useEffect(() => {
    executeBoot();
    return () => {
      requestId.current += 1;
    };
  }, [executeBoot]);

  useEffect(() => {
    if (
      bootState.status !== 'ready' ||
      !isNavigationReady ||
      didNavigate.current ||
      !navigationRef.isReady()
    ) {
      return;
    }

    didNavigate.current = true;
    navigationRef.resetRoot({
      index: 0,
      routes: [{ name: bootState.destination }],
    });
    onNavigationTransition?.(bootState.destination);
  }, [bootState, isNavigationReady, onNavigationTransition]);

  return (
    <NavigationContainer
      ref={navigationRef}
      onReady={() => setNavigationReady(true)}
    >
      <Stack.Navigator
        initialRouteName="Splash"
        screenOptions={{ headerShown: false, animation: 'none' }}
      >
        <Stack.Screen name="Splash">
          {() => (
            <SplashScreen bootStatus={bootState.status} onRetry={beginBoot} />
          )}
        </Stack.Screen>
        <Stack.Screen name="Auth">
          {() => <PlaceholderScreen label="로그인 준비 중" />}
        </Stack.Screen>
        <Stack.Screen name="Main">
          {() => <PlaceholderScreen label="앱 준비 중" />}
        </Stack.Screen>
      </Stack.Navigator>
    </NavigationContainer>
  );
}

export function App({
  previewMode,
  previewViewport,
  splashPreview,
  ...navigatorProps
}: AppProps) {
  if (isSceneEditorRoute()) {
    return <SceneEditor />;
  }

  const activePreview =
    previewMode !== undefined
      ? previewMode
      : splashPreview !== undefined
        ? splashPreview
          ? 'splash'
          : null
        : getPreviewMode();
  const activePreviewViewport =
    previewViewport !== undefined ? previewViewport : getPreviewViewportMode();

  const usesPreviewGallery =
    activePreview === 'gallery' ||
    activePreview === 'account' ||
    activePreview === 'auth' ||
    activePreview === 'background_test' ||
    activePreview === 'exercise-catalog' ||
    activePreview === 'loading' ||
    activePreview === 'mascot-house' ||
    activePreview === 'session' ||
    activePreview === 'session-result' ||
    activePreview === 'today' ||
    activePreview === 'weekly-report' ||
    activePreview === 'workout' ||
    activePreview === 'my-page';

  return (
    <SafeAreaProvider>
      <View style={styles.appShell} testID="app-shell">
        <View
          style={[
            styles.appViewport,
            Platform.OS === 'web' && !usesPreviewGallery
              ? styles.webAppViewport
              : undefined,
          ]}
          testID="app-viewport"
        >
          {activePreview === 'gallery' ? (
            <PreviewGallery />
          ) : activePreview === 'account' ? (
            <PreviewGallery initialScreenId="account" />
          ) : activePreview === 'auth' ? (
            <PreviewGallery initialScreenId="auth" />
          ) : activePreview === 'background_test' ? (
            <PreviewGallery initialScreenId="background_test" />
          ) : activePreview === 'exercise-catalog' ? (
            <PreviewGallery initialScreenId="exercise-catalog" />
          ) : activePreview === 'loading' ? (
            <PreviewGallery initialScreenId="loading" />
          ) : activePreview === 'mascot-house' ? (
            <PreviewGallery
              deviceViewport={activePreviewViewport === 'device'}
              initialScreenId="mascot-house"
            />
          ) : activePreview === 'session' ? (
            <PreviewGallery initialScreenId="session" />
          ) : activePreview === 'session-result' ? (
            <PreviewGallery initialScreenId="session-result" />
          ) : activePreview === 'today' ? (
            <PreviewGallery initialScreenId="today" />
          ) : activePreview === 'weekly-report' ? (
            <PreviewGallery initialScreenId="weekly-report" />
          ) : activePreview === 'workout' ? (
            <PreviewGallery initialScreenId="workout" />
          ) : activePreview === 'calendar-report' ? (
            <CalendarReportScreen />
          ) : activePreview === 'home' ? (
            <HomeScreen {...homePreviewProps('pre-checkin')} />
          ) : activePreview === 'home-map' ? (
            <MapHomeScreen routine={PREVIEW_ROUTINE} week={PREVIEW_OPEN_WEEK} />
          ) : activePreview === 'login' ? (
            <LoginScreen />
          ) : activePreview === 'my-page' ? (
            <PreviewGallery initialScreenId="my-page" />
          ) : activePreview === 'onboarding' ? (
            <OnboardingScreen
              api={onboardingPreviewApi}
              onCompleted={() => undefined}
              onSignOut={() => undefined}
            />
          ) : activePreview === 'profile' ? (
            <ProfileScreen />
          ) : activePreview === 'signup' ? (
            <SignUpScreen />
          ) : activePreview === 'splash' ? (
            <SplashScreen />
          ) : navigatorProps.bootResolver !== undefined ||
            navigatorProps.onNavigationTransition !== undefined ? (
            // The boot-resolver navigator is retained for the existing boot tests.
            <AppNavigator {...navigatorProps} />
          ) : (
            // Default entry is the real user flow, not the preview gallery.
            <SessionProvider>
              <DemoApp />
            </SessionProvider>
          )}
        </View>
      </View>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  appShell: {
    width: '100%',
    flex: 1,
    alignItems: 'center',
    backgroundColor: '#FFF4DC',
  },
  appViewport: {
    width: '100%',
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  webAppViewport: {
    maxWidth: WEB_APP_MAX_WIDTH,
  },
  placeholder: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
  },
  placeholderText: {
    color: '#5A4636',
    fontSize: 20,
    fontWeight: '700',
  },
});
