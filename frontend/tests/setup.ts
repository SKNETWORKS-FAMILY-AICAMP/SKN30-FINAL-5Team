import { jest } from '@jest/globals';
import { AccessibilityInfo } from 'react-native';
import mockSafeAreaContext from 'react-native-safe-area-context/jest/mock';

jest.mock('react-native-safe-area-context', () => mockSafeAreaContext);
jest.mock('expo-font', () => ({
  FontDisplay: { SWAP: 'swap' },
  useFonts: jest.fn(() => [true, null]),
}));
jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;
