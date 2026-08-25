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

import { imageAssets } from '../../assets';
import { colors } from '../../components/theme';
import type { HouseItemId, HousePose } from './houseModel';

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
export const houseRoomArt: HouseArtSlot = slot(
  'room',
  '끼끼의 캠핑장 저녁 배경',
  imageAssets.houseCampingDinnerBackground,
  '#F3E3C6',
  '#D8BE93',
  'cover',
);

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
 * Until pose-specific house artwork is selected, every house pose deliberately
 * reuses the same transparent monkey asset so interactions do not fall back to
 * placeholders or to a different mascot design.
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
