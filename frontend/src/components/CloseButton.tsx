import { Pressable, StyleSheet, Text } from 'react-native';

/** The check-in sheet's unboxed close control, shared by dismissible panels. */
export function CloseButton({
  onPress,
  accessibilityLabel = '닫기',
  disabled = false,
  testID,
}: {
  onPress: () => void;
  accessibilityLabel?: string;
  disabled?: boolean;
  testID?: string;
}) {
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={styles.button}
      testID={testID}
    >
      <Text style={styles.icon}>×</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    width: 44,
    height: 44,
    flexShrink: 0,
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'center',
    marginTop: -10,
    marginBottom: -10,
    marginRight: -12,
  },
  icon: { color: '#958476', fontSize: 22 },
});
