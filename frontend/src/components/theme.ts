import { Platform } from 'react-native';

export const colors = {
  canvas: '#FAF7F1',
  surface: '#FFFFFF',
  surfaceAlt: '#F7F5EF',
  primary: '#2F5233',
  primaryBusy: '#5B7C5F',
  green: '#4E8B3A',
  greenText: '#3E7A32',
  greenTint: '#EFF4E6',
  greenBand: '#DCEBC4',
  greenBorder: '#CBDDB4',
  text: '#2A2A26',
  textSub: '#6F6B63',
  textMuted: '#8B8780',
  textFaint: '#A8A49C',
  textDisabled: '#C0BBB1',
  placeholder: '#B5B0A6',
  border: '#E7E3DB',
  borderSoft: '#E2DED4',
  divider: '#F0EDE5',
  successSurface: '#EAF3E4',
  successBorder: '#C6DEB8',
  warningSurface: '#FBF0E8',
  warningBorder: '#E6C7B2',
  warningText: '#9A5B2E',
  dangerSurface: '#FBECE8',
  dangerBorder: '#E8C3B8',
  dangerText: '#B04A2C',
  danger: '#C2402F',
  dangerBg: '#FDECE9',
  fieldError: '#C2603F',
  disabledFill: '#E7E3DB',
  splashBackground: '#8ECB4E',
  yellow: '#FBD24E',
  yellowDeep: '#E0AF25',
  yellowSoft: '#FBF6DF',
  brandFill: '#EEDA30',
  brandOutline: '#6B4A2B',
  slogan: '#FFFFFF',
  sloganOutline: '#2F5233',
  errorSurface: '#FFFFFF',
  errorText: '#243525',
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
