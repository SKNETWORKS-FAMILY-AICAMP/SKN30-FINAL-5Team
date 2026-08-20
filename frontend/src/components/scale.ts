import {
  createContext,
  createElement,
  type ReactNode,
  useContext,
} from 'react';
import { useWindowDimensions } from 'react-native';

export const BASE_W = 390;
export const BASE_H = 844;
export const MAX_INTERFACE_SCALE = 1.2;
export const WEB_APP_MAX_WIDTH = 640;

export function getInterfaceScale(size: number, baseSize: number) {
  return Math.min(size / baseSize, MAX_INTERFACE_SCALE);
}

export type ScaleViewport = {
  width: number;
  height: number;
};

const ScaleViewportContext = createContext<ScaleViewport | null>(null);

export function ScaleViewportProvider({
  children,
  viewport,
}: {
  children: ReactNode;
  viewport: ScaleViewport;
}) {
  return createElement(
    ScaleViewportContext.Provider,
    { value: viewport },
    children,
  );
}

export function useScale() {
  const windowViewport = useWindowDimensions();
  const previewViewport = useContext(ScaleViewportContext);
  const { width, height } = previewViewport ?? windowViewport;
  const horizontalScale = getInterfaceScale(width, BASE_W);
  const verticalScale = getInterfaceScale(height, BASE_H);
  return {
    s: (n: number) => n * horizontalScale,
    sv: (n: number) => n * verticalScale,
    f: (n: number) => n * horizontalScale,
    width,
    height,
  };
}
