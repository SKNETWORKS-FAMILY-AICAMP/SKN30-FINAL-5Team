import { createContext, type ReactNode, useContext } from 'react';

export type OverlayViewportBounds = {
  bottom: number;
  left: number;
  right: number;
  top: number;
};

export type MeasureOverlayViewport = (
  onMeasure: (bounds: OverlayViewportBounds) => void,
) => void;

const OverlayViewportContext = createContext<MeasureOverlayViewport | null>(
  null,
);

/**
 * Supplies the visible app boundary to overlays rendered through a Modal.
 *
 * Production screens use the native window by default. The preview gallery
 * provides its simulated device frame because a Modal is otherwise positioned
 * against the browser window and can escape the preview canvas.
 */
export function OverlayViewportProvider({
  children,
  measure,
}: {
  children?: ReactNode;
  measure: MeasureOverlayViewport;
}) {
  return (
    <OverlayViewportContext.Provider value={measure}>
      {children}
    </OverlayViewportContext.Provider>
  );
}

export function useOverlayViewportMeasure() {
  return useContext(OverlayViewportContext);
}
