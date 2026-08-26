/**
 * The house's artwork, declared as slots rather than as image imports.
 *
 * The room and the temporary house mascot are connected. Extra pose artwork
 * and every decoration are still being drawn. Declaring each one as a slot
 * fixes its id, label and footprint now, so dropping finished art in later is
 * a one-line change to `source` with no edit to the screen.
 *
 * Only reviewed assets are wired up. A slot with `source: null` renders as a
 * labelled placeholder, which is honest about being unfinished — an
 * unreviewed stand-in shipped as if it were final is not.
 */

import type { ImageSourcePropType } from 'react-native';

import { houseMascotMonkeySources, imageAssets } from '../../assets';
import { colors } from '../../components/theme';
import {
  DEFAULT_HOUSE_BACKGROUND_ID,
  type HouseBackgroundId,
  type HouseItemId,
  type HousePose,
} from './houseModel';

export type HouseArtSlot = {
  id: string;
  /** Used for the accessibility label and for the placeholder caption. */
  label: string;
  source: ImageSourcePropType | null;
  /** Placeholder fill while the art is missing. */
  fill: string;
  /** Placeholder outline while the art is missing. */
  outline: string;
  /**
   * How the image fills its frame. The room is a full-bleed backdrop, so it
   * covers and crops; everything else keeps its whole shape.
   */
  fit?: 'cover' | 'contain';
};

function slot(
  id: string,
  label: string,
  source: ImageSourcePropType | null,
  fill: string,
  outline: string,
  fit: 'cover' | 'contain' = 'contain',
): HouseArtSlot {
  return { id, label, source, fill, outline, fit };
}

/**
 * The scene the mascot lives in — a full-bleed backdrop, not a framed picture.
 * `MascotHouseContent` sizes this at half of its former cover dimensions,
 * fixes it to the top and keeps its horizontal centre aligned.
 */
export const houseBackgroundLabels: Record<HouseBackgroundId, string> = {
  morning_camp: '아침 캠핑장',
  dinner_camp: '저녁 캠핑장',
  indoor_treehouse: '햇살 나무집',
  snowing_onsen: '눈 내리는 온천',
};

export const houseBackgroundArt: Record<HouseBackgroundId, HouseArtSlot> = {
  morning_camp: slot(
    'background-morning-camp',
    '끼끼의 캠핑장 아침 배경',
    imageAssets.houseCampingMorningBackground,
    '#F3E3C6',
    '#D8BE93',
    'cover',
  ),
  dinner_camp: slot(
    'background-dinner-camp',
    '끼끼의 캠핑장 저녁 배경',
    imageAssets.houseCampingDinnerBackground,
    '#493A28',
    '#241C14',
    'cover',
  ),
  indoor_treehouse: slot(
    'background-indoor-treehouse',
    '끼끼의 실내 나무집 배경',
    imageAssets.houseIndoorBackground,
    '#F4E2BC',
    '#C9A66F',
    'cover',
  ),
  snowing_onsen: slot(
    'background-snowing-onsen',
    '끼끼의 눈 내리는 온천 배경',
    imageAssets.houseSnowingOnsenBackground,
    '#F4EEE2',
    '#C7C5C3',
    'cover',
  ),
};

/**
 * Small background previews for the decorate grid. The full-size PNG artwork
 * above remains the scene source; these JPGs avoid decoding four large images
 * just to render phone-width selection cards.
 */
export const houseBackgroundThumbnailArt: Record<
  HouseBackgroundId,
  HouseArtSlot
> = {
  morning_camp: {
    ...houseBackgroundArt.morning_camp,
    source: imageAssets.houseCampingMorningBackgroundThumbnail,
  },
  dinner_camp: {
    ...houseBackgroundArt.dinner_camp,
    source: imageAssets.houseCampingDinnerBackgroundThumbnail,
  },
  indoor_treehouse: {
    ...houseBackgroundArt.indoor_treehouse,
    source: imageAssets.houseIndoorBackgroundThumbnail,
  },
  snowing_onsen: {
    ...houseBackgroundArt.snowing_onsen,
    source: imageAssets.houseSnowingOnsenBackgroundThumbnail,
  },
};

/** Default room art retained for previews that do not own house state. */
export const houseRoomArt = houseBackgroundArt[DEFAULT_HOUSE_BACKGROUND_ID];

/**
 * The gradient standing in for the backdrop until the illustration arrives.
 * Sky, tree line, meadow, path — top to bottom.
 */
export const HOUSE_BACKDROP_FALLBACK = [
  '#BFE3F5',
  '#D3EAD9',
  '#DDEBC4',
  '#EFE3C0',
] as const;

/**
 * Poses.
 *
 * The shared defaults use one transparent monkey asset. Feeding replaces the
 * `eating` default with one of `houseBananaPoseArt` for the reaction duration.
 */
export const housePoseArt: Record<HousePose, HouseArtSlot> = {
  greeting: slot(
    'pose-greeting',
    '인사하는 끼끼',
    imageAssets.houseMascotMonkey01,
    colors.brandFill,
    colors.brandOutline,
  ),
  happy: slot(
    'pose-happy',
    '신난 끼끼',
    imageAssets.houseMascotMonkey01,
    colors.brandFill,
    colors.brandOutline,
  ),
  eating: slot(
    'pose-eating',
    '바나나를 먹는 끼끼',
    imageAssets.houseMascotMonkey01,
    colors.yellowSoft,
    colors.yellowDeep,
  ),
  petted: slot(
    'pose-petted',
    '쓰다듬어 주는 중',
    imageAssets.houseMascotMonkey01,
    colors.yellowSoft,
    colors.yellowDeep,
  ),
  resting: slot(
    'pose-resting',
    '쉬고 있는 끼끼',
    imageAssets.houseMascotMonkey01,
    colors.surfaceAlt,
    colors.borderSoft,
  ),
};

/** Every reviewed `banana_` mascot image under the monkey asset folders. */
export const houseBananaPoseArt: readonly HouseArtSlot[] = [
  imageAssets.houseMascotBananaSheet01Monkey07,
  imageAssets.houseMascotBananaSheet01Monkey08,
  imageAssets.houseMascotBananaSheet02Monkey05,
  imageAssets.houseMascotBananaSheet02Monkey13,
  imageAssets.houseMascotBananaSheet02Monkey20,
  imageAssets.houseMascotBananaSheet02Monkey22,
].map((source) =>
  slot(
    'pose-eating',
    '바나나를 먹는 끼끼',
    source,
    colors.yellowSoft,
    colors.yellowDeep,
  ),
);

/** All normal monkey poses; `banana_` and `unused_` files are not registered. */
export const houseRegularPoseArt: readonly HouseArtSlot[] =
  houseMascotMonkeySources.map((source) =>
    slot(
      'pose-random',
      '다른 모습의 끼끼',
      source,
      colors.brandFill,
      colors.brandOutline,
    ),
  );

function randomNonRepeatingArt(
  artwork: readonly HouseArtSlot[],
  previousSource: ImageSourcePropType | null,
  random: () => number,
): HouseArtSlot {
  const fallback = artwork[0];
  if (fallback === undefined) {
    throw new Error('No mascot artwork is registered.');
  }
  const candidates = artwork.filter(
    (candidate) => candidate.source !== previousSource,
  );
  const randomIndex = Math.min(
    Math.floor(Math.max(0, random()) * candidates.length),
    candidates.length - 1,
  );
  return candidates[randomIndex] ?? fallback;
}

/**
 * Picks a banana pose and avoids immediately repeating the visible artwork
 * when the user feeds the mascot again during the same visit.
 */
export function randomHouseBananaPoseArt(
  previousSource: ImageSourcePropType | null = null,
  random: () => number = Math.random,
): HouseArtSlot {
  return randomNonRepeatingArt(houseBananaPoseArt, previousSource, random);
}

/** Picks a normal pose, excluding an immediately repeated source. */
export function randomHouseRegularPoseArt(
  previousSource: ImageSourcePropType | null = null,
  random: () => number = Math.random,
): HouseArtSlot {
  return randomNonRepeatingArt(houseRegularPoseArt, previousSource, random);
}

/** Decorations. All pending, each with its own colour so the room reads. */
export const houseItemArt: Record<HouseItemId, HouseArtSlot> = {
  yoga_mat: slot('item-yoga_mat', '요가 매트', null, '#DCD3F2', '#9E8FD0'),
  dumbbell: slot('item-dumbbell', '아령', null, '#D6E7CB', '#7FA46B'),
  plant: slot('item-plant', '화분', null, '#D9EBC9', '#78A45C'),
  cushion: slot('item-cushion', '쿠션', null, '#E3E9CC', '#93A268'),
  lamp: slot('item-lamp', '스탠드', null, '#FBEFD1', '#D8AE55'),
  star_frame: slot('item-star_frame', '별 액자', null, '#EFE3C8', '#B4915A'),
  window: slot('item-window', '창문 커튼', null, '#DCEAD3', '#8FAE7C'),
};
