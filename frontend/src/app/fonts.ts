import { FontDisplay, type FontSource, useFonts } from 'expo-font';
import { Platform } from 'react-native';

const juaSource = require('../assets/fonts/Jua-Regular.ttf') as number;
const baloo2Source = require('../assets/fonts/Baloo2-Variable.ttf') as number;
const neoDunggeunmoSource =
  require('../assets/fonts/NeoDunggeunmo.ttf') as number;

export const fontFamilies = {
  brand: 'Helkki-Baloo2',
  loginHeading: 'Helkki-NeoDunggeunmo',
  slogan: 'Helkki-Jua',
} as const;

function withWebDisplay(source: number): FontSource {
  if (Platform.OS !== 'web') {
    return source;
  }

  return {
    uri: source,
    display: FontDisplay.SWAP,
  };
}

export function useBrandFonts() {
  const [loaded, error] = useFonts({
    [fontFamilies.brand]: withWebDisplay(baloo2Source),
    [fontFamilies.slogan]: withWebDisplay(juaSource),
  });

  return {
    loaded,
    failed: error !== null,
  };
}

export function useAuthFonts() {
  const [loaded, error] = useFonts({
    [fontFamilies.loginHeading]: withWebDisplay(neoDunggeunmoSource),
  });

  return {
    loaded,
    failed: error !== null,
  };
}
