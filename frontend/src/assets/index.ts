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
  mascotWarmupWalk:
    require('./mascot/mascot-warmup-walk.gif') as ImageSourcePropType,
  houseCampingDinnerBackground:
    require('./house/camping/background/temp_back_dinner.png') as ImageSourcePropType,
  houseMascotMonkey01:
    require('./mascot/monkey/sheet_01/monkey_01.png') as ImageSourcePropType,
} as const;

export type ImageAssetKey = keyof typeof imageAssets;
