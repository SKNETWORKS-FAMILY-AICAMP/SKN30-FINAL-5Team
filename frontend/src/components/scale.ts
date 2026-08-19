import {
  createContext,
  createElement,
  type ReactNode,
  useContext,
} from 'react';
import { useWindowDimensions } from 'react-native';

export const BASE_W = 390;
export const BASE_H = 844;

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
  return {
    s: (n: number) => (n * width) / BASE_W,
    sv: (n: number) => (n * height) / BASE_H,
    f: (n: number) => n * Math.min(width / BASE_W, 1.2),
    width,
    height,
  };
}
