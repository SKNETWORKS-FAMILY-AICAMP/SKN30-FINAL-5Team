import type { ReactNode } from 'react';
import {
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type TextStyle,
  type ViewStyle,
} from 'react-native';

import { borderWidths, colors, radii, spacing, typography } from '../theme';

type TextFieldProps = Omit<TextInputProps, 'style'> & {
  containerStyle?: StyleProp<ViewStyle>;
  error?: string;
  inputStyle?: StyleProp<TextStyle>;
  label?: string;
  style?: StyleProp<ViewStyle>;
  trailing?: ReactNode;
};

export function TextField({
  accessibilityState,
  containerStyle,
  editable = true,
  error,
  inputStyle,
  label,
  placeholderTextColor = colors.placeholder,
  style,
  trailing,
  ...inputProps
}: TextFieldProps) {
  return (
    <View style={[styles.group, containerStyle]}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <View
        style={[
          styles.control,
          error ? styles.controlError : null,
          !editable ? styles.controlDisabled : null,
          style,
        ]}
      >
        <TextInput
          {...inputProps}
          accessibilityState={{ ...accessibilityState, disabled: !editable }}
          editable={editable}
          placeholderTextColor={placeholderTextColor}
          style={[styles.input, inputStyle]}
        />
        {trailing}
      </View>
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  group: {
    gap: 5,
  },
  label: {
    ...typography.fieldLabel,
    color: colors.textMuted,
  },
  control: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderWidth: borderWidths.control,
    borderColor: colors.border,
    borderRadius: radii.control,
    backgroundColor: colors.surface,
    paddingHorizontal: 14,
  },
  controlError: {
    borderColor: colors.fieldError,
  },
  controlDisabled: {
    backgroundColor: colors.canvas,
  },
  input: {
    minWidth: 0,
    flex: 1,
    color: colors.text,
    ...typography.fieldInput,
    padding: 0,
  },
  error: {
    color: colors.fieldError,
    ...typography.fieldError,
  },
});
