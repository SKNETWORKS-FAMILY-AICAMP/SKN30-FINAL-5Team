import {
  placePainScaleBubble,
  placePainScaleBubbleHorizontally,
} from '../src/components/profile/PainScaleInfo';

describe('placePainScaleBubble', () => {
  it('opens below the icon when the full bubble fits', () => {
    expect(
      placePainScaleBubble({
        anchor: { x: 100, y: 100, width: 22, height: 22 },
        bubbleHeight: 150,
        viewportBottom: 800,
      }),
    ).toEqual({ maxHeight: 768, side: 'below', top: 126 });
  });

  it('opens above the icon when the lower edge would be clipped', () => {
    expect(
      placePainScaleBubble({
        anchor: { x: 100, y: 700, width: 22, height: 22 },
        bubbleHeight: 150,
        viewportBottom: 800,
      }),
    ).toEqual({ maxHeight: 768, side: 'above', top: 546 });
  });

  it('clamps an oversized bubble inside the safe area', () => {
    expect(
      placePainScaleBubble({
        anchor: { x: 100, y: 700, width: 22, height: 22 },
        bubbleHeight: 900,
        viewportBottom: 776,
        viewportTop: 44,
      }),
    ).toEqual({ maxHeight: 700, side: 'above', top: 60 });
  });
});

describe('placePainScaleBubbleHorizontally', () => {
  it('keeps the bubble inside a preview frame offset from the browser edge', () => {
    const placement = placePainScaleBubbleHorizontally({
      anchor: { x: 176, y: 100, width: 22, height: 22 },
      viewportLeft: 85,
      viewportRight: 655,
    });

    expect(placement).toEqual({ left: 101, pointerLeft: 81, width: 320 });
    expect(placement.left + placement.pointerLeft + 5).toBe(187);
  });

  it('uses the full device window when no preview offset is supplied', () => {
    expect(
      placePainScaleBubbleHorizontally({
        anchor: { x: 176, y: 100, width: 22, height: 22 },
        viewportRight: 390,
      }),
    ).toEqual({ left: 27, pointerLeft: 155, width: 320 });
  });
});
