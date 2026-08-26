import type { ImageSourcePropType } from 'react-native';

export const imageAssets = {
  splashIsland:
    require('./splash/splash-island-v2-hires.png') as ImageSourcePropType,
  questionMark: require('./splash/question-mark.png') as ImageSourcePropType,
  mailbox: require('./map/mailbox.png') as ImageSourcePropType,
  mailboxDone: require('./map/mailbox-done.png') as ImageSourcePropType,
  exclamation: require('./map/exclamation.png') as ImageSourcePropType,
  arrowDown: require('./map/arrow-down.png') as ImageSourcePropType,
  mascotComplete:
    require('./mascot/mascot-complete.png') as ImageSourcePropType,
  progressMascot:
    require('./mascot/progress-mascot.webp') as ImageSourcePropType,
  dayTodo: require('./mascot/day-todo.webp') as ImageSourcePropType,
  profileDefault:
    require('./mascot/monkey/sheet_01/monkey_10.png') as ImageSourcePropType,
  weeklyProgressComplete:
    require('./mascot/monkey/sheet_02/monkey_06.png') as ImageSourcePropType,
  weeklyProgressIncomplete:
    require('./mascot/monkey/sheet_01/monkey_24.png') as ImageSourcePropType,
  mascotWarmupWalk:
    require('./mascot/monkey/sheet_01/monkey_run.gif') as ImageSourcePropType,
  houseCampingMorningBackground:
    require('./house/camping/background/morning_camp.png') as ImageSourcePropType,
  houseCampingDinnerBackground:
    require('./house/camping/background/temp_back_dinner.png') as ImageSourcePropType,
  houseIndoorBackground:
    require('./house/camping/background/kkikki_indoor.png') as ImageSourcePropType,
  houseSnowingOnsenBackground:
    require('./house/camping/background/snowing_onsen.png') as ImageSourcePropType,
  houseCampingMorningBackgroundThumbnail:
    require('./house/camping/background/thumbnails/morning_camp.jpg') as ImageSourcePropType,
  houseCampingDinnerBackgroundThumbnail:
    require('./house/camping/background/thumbnails/temp_back_dinner.jpg') as ImageSourcePropType,
  houseIndoorBackgroundThumbnail:
    require('./house/camping/background/thumbnails/kkikki_indoor.jpg') as ImageSourcePropType,
  houseSnowingOnsenBackgroundThumbnail:
    require('./house/camping/background/thumbnails/snowing_onsen.jpg') as ImageSourcePropType,
  houseMascotMonkey01:
    require('./mascot/monkey/sheet_01/monkey_01.png') as ImageSourcePropType,
  houseMascotBananaSheet01Monkey07:
    require('./mascot/monkey/sheet_01/banana_monkey_07.png') as ImageSourcePropType,
  houseMascotBananaSheet01Monkey08:
    require('./mascot/monkey/sheet_01/banana_monkey_08.png') as ImageSourcePropType,
  houseMascotBananaSheet02Monkey05:
    require('./mascot/monkey/sheet_02/banana_monkey_05.png') as ImageSourcePropType,
  houseMascotBananaSheet02Monkey13:
    require('./mascot/monkey/sheet_02/banana_monkey_13.png') as ImageSourcePropType,
  houseMascotBananaSheet02Monkey20:
    require('./mascot/monkey/sheet_02/banana_monkey_20.png') as ImageSourcePropType,
  houseMascotBananaSheet02Monkey22:
    require('./mascot/monkey/sheet_02/banana_monkey_22.png') as ImageSourcePropType,
} as const;

/**
 * Every selectable non-banana monkey pose under `mascot/monkey`.
 * `unused_` artwork is intentionally not registered here.
 */
export const houseMascotMonkeySources: readonly ImageSourcePropType[] = [
  imageAssets.houseMascotMonkey01,
  require('./mascot/monkey/sheet_01/monkey_02.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_03.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_04.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_05.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_06.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_09.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_10.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_11.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_12.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_13.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_15.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_16.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_17.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_18.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_19.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_20.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_21.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_22.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_01/monkey_23.png') as ImageSourcePropType,
  imageAssets.weeklyProgressIncomplete,
  require('./mascot/monkey/sheet_02/monkey_01.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_02.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_03.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_04.png') as ImageSourcePropType,
  imageAssets.weeklyProgressComplete,
  require('./mascot/monkey/sheet_02/monkey_07.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_08.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_09.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_10.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_11.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_12.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_14.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_15.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_16.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_17.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_18.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_19.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_21.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_23.png') as ImageSourcePropType,
  require('./mascot/monkey/sheet_02/monkey_24.png') as ImageSourcePropType,
];

/**
 * Mascots that can celebrate completed routines on Home. The shared
 * incomplete-slot mascot is excluded, and `unused_` artwork is never
 * registered in the source lists above.
 */
export const weeklyProgressMascotSources: readonly ImageSourcePropType[] = [
  ...houseMascotMonkeySources.filter(
    (source) => source !== imageAssets.weeklyProgressIncomplete,
  ),
  imageAssets.houseMascotBananaSheet01Monkey07,
  imageAssets.houseMascotBananaSheet01Monkey08,
  imageAssets.houseMascotBananaSheet02Monkey05,
  imageAssets.houseMascotBananaSheet02Monkey13,
  imageAssets.houseMascotBananaSheet02Monkey20,
  imageAssets.houseMascotBananaSheet02Monkey22,
];

export type ImageAssetKey = keyof typeof imageAssets;
