import { jest } from '@jest/globals';
import { AccessibilityInfo } from 'react-native';
import mockSafeAreaContext from 'react-native-safe-area-context/jest/mock';

jest.mock('react-native-safe-area-context', () => mockSafeAreaContext);
jest.mock('expo-font', () => ({
  FontDisplay: { SWAP: 'swap' },
  useFonts: jest.fn(() => [true, null]),
}));

// Component tests must never reach a real Firebase project, and the SDK ships
// ESM that the Expo transform does not process. Stubbing both entry points
// keeps the app's import graph loadable while leaving auth behaviour to the
// `authOverride` seam on SessionProvider.
jest.mock('firebase/app', () => ({
  initializeApp: jest.fn(() => ({ name: 'test-app' })),
}));
jest.mock('firebase/auth', () => ({
  getAuth: jest.fn(() => ({ currentUser: null })),
  onAuthStateChanged: jest.fn(() => () => undefined),
  signInWithEmailAndPassword: jest.fn(),
  createUserWithEmailAndPassword: jest.fn(),
  signOut: jest.fn(),
  validatePassword: jest.fn(),
}));
jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;
