import {
  NavigationContainer,
  createNavigationContainerRef,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { LoginScreen } from '../features/auth/LoginScreen';
import { SignUpScreen } from '../features/auth/SignUpScreen';
import { CalendarReportScreen } from '../features/home/CalendarReportScreen';
import { HomeScreen } from '../features/home/HomeScreen';
import { MapHomeScreen } from '../features/home/MapHomeScreen';
import { MyPageScreen } from '../features/home/MyPageScreen';
import { homePreviewProps } from '../features/preview/homePreview';
import { PreviewGallery } from '../features/preview/PreviewGallery';
import { ProfileScreen } from '../features/profile/ProfileScreen';
import { SplashScreen } from '../features/splash/SplashScreen';
import { WorkoutScreen } from '../features/workout/WorkoutScreen';
import {
  type BootDestination,
  type BootDestinationResolver,
  resolveBootDestination,
} from './bootstrap';
import { DemoApp } from './DemoApp';
import { getPreviewMode, type PreviewMode } from './preview';
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
  splashPreview,
  ...navigatorProps
}: AppProps) {
  const activePreview =
    previewMode !== undefined
      ? previewMode
      : splashPreview !== undefined
        ? splashPreview
          ? 'splash'
          : null
        : getPreviewMode();

  return (
    <SafeAreaProvider>
      {activePreview === 'gallery' ? (
        <PreviewGallery />
      ) : activePreview === 'today' ? (
        <PreviewGallery initialScreenId="today" />
      ) : activePreview === 'workout' ? (
        <WorkoutScreen />
      ) : activePreview === 'calendar-report' ? (
        <CalendarReportScreen />
      ) : activePreview === 'home' ? (
        <HomeScreen {...homePreviewProps('pre-checkin')} />
      ) : activePreview === 'home-map' ? (
        <MapHomeScreen />
      ) : activePreview === 'login' ? (
        <LoginScreen />
      ) : activePreview === 'my-page' ? (
        <MyPageScreen />
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
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  placeholder: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
  },
  placeholderText: {
    color: '#2F5233',
    fontSize: 20,
    fontWeight: '700',
  },
});
