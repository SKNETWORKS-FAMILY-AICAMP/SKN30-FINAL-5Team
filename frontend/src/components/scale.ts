import { useWindowDimensions } from 'react-native';

export const BASE_W = 390;
export const BASE_H = 844;

export function useScale() {
  const { width, height } = useWindowDimensions();
  return {
    s: (n: number) => (n * width) / BASE_W,
    sv: (n: number) => (n * height) / BASE_H,
    f: (n: number) => n * Math.min(width / BASE_W, 1.2),
    width,
    height,
  };
}
