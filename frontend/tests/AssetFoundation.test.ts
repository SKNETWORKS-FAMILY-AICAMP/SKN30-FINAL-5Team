import { afterEach, describe, expect, it } from '@jest/globals';
import { renderHook } from '@testing-library/react-native';
import { Dimensions, type ScaledSize } from 'react-native';

import {
  houseMascotMonkeySources,
  imageAssets,
  weeklyProgressMascotSources,
} from '../src/assets';
import { BASE_H, BASE_W, useScale } from '../src/components/scale';

const originalWindow = Dimensions.get('window');
const originalScreen = Dimensions.get('screen');

function setDimensions(window: ScaledSize, screen: ScaledSize = window) {
  Dimensions.set({ window, screen });
}

afterEach(() => {
  setDimensions(originalWindow, originalScreen);
});

describe('fidelity foundation', () => {
  it('uses the 390 by 844 reference and caps all interface growth', () => {
    setDimensions({ width: 780, height: 1688, scale: 2, fontScale: 1 });

    const { result } = renderHook(() => useScale());

    expect(BASE_W).toBe(390);
    expect(BASE_H).toBe(844);
    expect(result.current.width).toBe(780);
    expect(result.current.height).toBe(1688);
    expect(result.current.s(10)).toBe(12);
    expect(result.current.sv(10)).toBe(12);
    expect(result.current.f(10)).toBe(12);
  });

  it('keeps every decoded and density-aware image in one registry', () => {
    expect(Object.keys(imageAssets)).toEqual([
      'splashIsland',
      'questionMark',
      'mailbox',
      'mailboxDone',
      'exclamation',
      'arrowDown',
      'mascotComplete',
      'progressMascot',
      'dayTodo',
      'banana',
      'bananaCatchBackground',
      'bananaCatchGrass',
      'profileDefault',
      'weeklyProgressComplete',
      'weeklyProgressIncomplete',
      'weeklyProgressCompletedWorkout',
      'mascotWarmupWalk',
      'houseCampingMorningBackground',
      'houseCampingDinnerBackground',
      'houseIndoorBackground',
      'houseSnowingOnsenBackground',
      'houseCampingMorningBackgroundThumbnail',
      'houseCampingDinnerBackgroundThumbnail',
      'houseIndoorBackgroundThumbnail',
      'houseSnowingOnsenBackgroundThumbnail',
      'houseMascotMonkey01',
      'houseMascotCollectingBananasEmpty',
      'houseMascotCollectingBananasMedium',
      'houseMascotCollectingBananasFull',
      'houseMascotBananaSheet01Monkey07',
      'houseMascotBananaSheet01Monkey08',
      'houseMascotBananaSheet02Monkey05',
      'houseMascotBananaSheet02Monkey13',
      'houseMascotBananaSheet02Monkey20',
      'houseMascotBananaSheet02Monkey22',
    ]);
    expect(Object.values(imageAssets).every(Boolean)).toBe(true);
    expect(houseMascotMonkeySources).toHaveLength(41);
    expect(houseMascotMonkeySources.every(Boolean)).toBe(true);
    expect(weeklyProgressMascotSources).toHaveLength(46);
    expect(weeklyProgressMascotSources.every(Boolean)).toBe(true);
    expect(weeklyProgressMascotSources).not.toContain(
      imageAssets.weeklyProgressIncomplete,
    );
  });
});
