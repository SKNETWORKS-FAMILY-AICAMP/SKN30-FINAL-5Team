import { useState } from 'react';
import {
  Image,
  StyleSheet,
  type ImageStyle,
  type StyleProp,
} from 'react-native';

import { imageAssets } from '../../assets';

type ProfileAvatarProps = {
  accessibilityLabel?: string;
  profileImageUrl?: string | null;
  size: number;
  style?: StyleProp<ImageStyle>;
  testID?: string;
};

/**
 * Shared profile image used by Home and My Page.
 *
 * A missing or unreachable remote image always falls back to the bundled
 * mascot so profile chrome never renders as an empty circle.
 */
export function ProfileAvatar({
  accessibilityLabel = '프로필 이미지',
  profileImageUrl,
  size,
  style,
  testID = 'profile-avatar',
}: ProfileAvatarProps) {
  const [failedRemoteUrl, setFailedRemoteUrl] = useState<string | null>(null);
  const usesRemoteImage =
    Boolean(profileImageUrl) && profileImageUrl !== failedRemoteUrl;

  return (
    <Image
      accessibilityLabel={accessibilityLabel}
      onError={
        usesRemoteImage
          ? () => setFailedRemoteUrl(profileImageUrl ?? null)
          : undefined
      }
      resizeMode="cover"
      source={
        usesRemoteImage
          ? { uri: profileImageUrl as string }
          : imageAssets.profileDefault
      }
      style={[
        styles.image,
        { width: size, height: size, borderRadius: size / 2 },
        style,
      ]}
      testID={testID}
    />
  );
}

const styles = StyleSheet.create({
  image: {
    backgroundColor: '#FFF8E5',
  },
});
