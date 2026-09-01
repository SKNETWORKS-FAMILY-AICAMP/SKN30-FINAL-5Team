import { describe, expect, it } from '@jest/globals';

import {
  BASE_H,
  BASE_W,
  getContainedInterfaceScale,
  getInterfaceScale,
  MAX_INTERFACE_SCALE,
  MIN_COMPACT_INTERFACE_SCALE,
} from '../src/components/scale';

describe('responsive interface scale', () => {
  it('shrinks below the reference phone size', () => {
    expect(getInterfaceScale(360, BASE_W)).toBeCloseTo(360 / 390);
    expect(getInterfaceScale(568, BASE_H)).toBeCloseTo(568 / 844);
  });

  it('caps component growth on tablet and web viewports', () => {
    expect(getInterfaceScale(768, BASE_W)).toBe(MAX_INTERFACE_SCALE);
    expect(getInterfaceScale(1440, BASE_W)).toBe(MAX_INTERFACE_SCALE);
    expect(getInterfaceScale(1200, BASE_H)).toBe(MAX_INTERFACE_SCALE);
  });

  it('fits dense controls to the shortest viewport dimension', () => {
    expect(getContainedInterfaceScale(390, 700)).toBeCloseTo(700 / BASE_H);
    expect(getContainedInterfaceScale(350, 844)).toBeCloseTo(350 / BASE_W);
    expect(getContainedInterfaceScale(430, 932)).toBe(1);
    expect(getContainedInterfaceScale(390, 568)).toBe(
      MIN_COMPACT_INTERFACE_SCALE,
    );
  });
});
