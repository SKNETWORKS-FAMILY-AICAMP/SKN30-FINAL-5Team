import { Platform } from 'react-native';

export const colors = {
  canvas: '#FFF8E5',
  surface: '#FFFFFF',
  surfaceAlt: '#FFF4DC',
  primary: '#F6BA50',
  primaryBusy: '#D98B16',
  green: '#F6BA50',
  greenText: '#A45F00',
  greenTint: '#FFF8E5',
  greenBand: '#FFEBC2',
  greenBorder: '#F1D39A',
  text: '#5A4636',
  textSub: '#7B695B',
  textMuted: '#958476',
  textFaint: '#AB9B8E',
  textDisabled: '#C8BBB0',
  placeholder: '#B8AA9E',
  border: '#EEDFCB',
  borderSoft: '#E8D8C2',
  divider: '#F4E9D8',
  successSurface: '#FFF3D4',
  successBorder: '#EDC778',
  warningSurface: '#FFF0E8',
  warningBorder: '#F2C2AC',
  warningText: '#9C4F32',
  dangerSurface: '#FDECE7',
  dangerBorder: '#F1BFAE',
  dangerText: '#A23F2A',
  danger: '#C84E35',
  dangerBg: '#FFF0EB',
  fieldError: '#B64A34',
  disabledFill: '#E8DED2',
  splashBackground: '#F6BA50',
  yellow: '#F6BA50',
  yellowDeep: '#D98B16',
  yellowSoft: '#FFF8E5',
  brandFill: '#F6BA50',
  brandOutline: '#5A4636',
  slogan: '#FFFFFF',
  sloganOutline: '#5A4636',
  errorSurface: '#FFFFFF',
  errorText: '#5A4636',
} as const;

export const shadows = {
  card:
    Platform.select({
      ios: {
        shadowColor: colors.primary,
        shadowOffset: { width: 0, height: 6 },
        shadowOpacity: 0.1,
        shadowRadius: 9,
      },
      android: { elevation: 3 },
      default: {
        shadowColor: colors.primary,
        shadowOffset: { width: 0, height: 6 },
        shadowOpacity: 0.1,
        shadowRadius: 9,
      },
    }) ?? {},
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 18,
} as const;

export const radii = {
  feedback: 12,
  control: 12,
  button: 14,
  card: 16,
} as const;

export const borderWidths = {
  control: 1.5,
} as const;

export const typography = {
  feedback: {
    fontSize: 13,
    lineHeight: 20,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '600',
  },
  fieldInput: {
    fontSize: 15,
  },
  fieldError: {
    fontSize: 12,
    lineHeight: 18,
  },
  buttonLabel: {
    fontSize: 16,
    fontWeight: '700',
  },
} as const;
