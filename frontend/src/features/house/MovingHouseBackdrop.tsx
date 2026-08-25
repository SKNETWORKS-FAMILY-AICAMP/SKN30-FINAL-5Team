import { useEffect, useState } from 'react';
import {
  Animated,
  Easing,
  Image,
  type ImageSourcePropType,
  StyleSheet,
  View,
} from 'react-native';

export const movingHouseBackgroundSource =
  require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/background/background_static.png') as ImageSourcePropType;

const movingAssets = {
  bulb: require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/bulbs/bulb_generic.png') as ImageSourcePropType,
  cable:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/bulbs/string_light_cable.png') as ImageSourcePropType,
  canopyLeft:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/leaves/canopy_left.png') as ImageSourcePropType,
  canopyRight:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/leaves/canopy_right.png') as ImageSourcePropType,
  cloud05:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/clouds/cloud_05.png') as ImageSourcePropType,
  cloud09:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/clouds/cloud_09.png') as ImageSourcePropType,
  cloud17:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/clouds/cloud_17.png') as ImageSourcePropType,
  flowerOrange:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/flowers/flower_orange_03.png') as ImageSourcePropType,
  flowerPink:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/flowers/flower_pink_14.png') as ImageSourcePropType,
  flowerPurple:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/flowers/flower_purple_spike_04.png') as ImageSourcePropType,
  flowerWhite:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/flowers/flower_white_17.png') as ImageSourcePropType,
  grassLeft:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/grass/grass_patch_01.png') as ImageSourcePropType,
  grassRight:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/grass/grass_patch_04.png') as ImageSourcePropType,
  lantern:
    require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/lanterns/lantern_hanging_body.png') as ImageSourcePropType,
} as const;

const SCENE_SIZE = { width: 1672, height: 941 } as const;

type SceneRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

const bulbs: SceneRect[] = [
  { x: 638, y: 420, width: 42, height: 48 },
  { x: 804, y: 442, width: 42, height: 48 },
  { x: 965, y: 438, width: 42, height: 48 },
  { x: 1130, y: 407, width: 42, height: 48 },
  { x: 1283, y: 348, width: 42, height: 48 },
];

const flowers = [
  {
    source: movingAssets.flowerPurple,
    rect: { x: 1130, y: 565, width: 42, height: 88 },
  },
  {
    source: movingAssets.flowerPink,
    rect: { x: 1240, y: 555, width: 58, height: 82 },
  },
  {
    source: movingAssets.flowerWhite,
    rect: { x: 1340, y: 595, width: 48, height: 42 },
  },
  {
    source: movingAssets.flowerOrange,
    rect: { x: 1435, y: 585, width: 48, height: 52 },
  },
] as const;

/**
 * A deliberately separate motion experiment for the preview gallery.
 *
 * `moving_temp` is a sprite package rather than a video. The layers below use
 * only transform and opacity animations so the experiment works on native and
 * web without adding a media dependency or changing the production backdrop.
 */
export function MovingHouseBackdrop({
  size,
}: {
  size: { width: number; height: number };
}) {
  const [wind] = useState(() => new Animated.Value(0));
  const [drift] = useState(() => new Animated.Value(0));
  const [glow] = useState(() => new Animated.Value(0));

  useEffect(() => {
    const animations = [
      Animated.loop(
        Animated.sequence([
          Animated.timing(wind, {
            duration: 2800,
            easing: Easing.inOut(Easing.sin),
            toValue: 1,
            useNativeDriver: true,
          }),
          Animated.timing(wind, {
            duration: 2800,
            easing: Easing.inOut(Easing.sin),
            toValue: 0,
            useNativeDriver: true,
          }),
        ]),
      ),
      Animated.loop(
        Animated.timing(drift, {
          duration: 24000,
          easing: Easing.linear,
          toValue: 1,
          useNativeDriver: true,
        }),
      ),
      Animated.loop(
        Animated.sequence([
          Animated.timing(glow, {
            duration: 900,
            easing: Easing.inOut(Easing.quad),
            toValue: 1,
            useNativeDriver: true,
          }),
          Animated.timing(glow, {
            duration: 1250,
            easing: Easing.inOut(Easing.quad),
            toValue: 0,
            useNativeDriver: true,
          }),
        ]),
      ),
    ];

    animations.forEach((animation) => animation.start());
    return () => animations.forEach((animation) => animation.stop());
  }, [drift, glow, wind]);

  const scaleX = size.width / SCENE_SIZE.width;
  const scaleY = size.height / SCENE_SIZE.height;
  const windRotation = wind.interpolate({
    inputRange: [0, 1],
    outputRange: ['-0.8deg', '0.8deg'],
  });
  const flowerRotation = wind.interpolate({
    inputRange: [0, 1],
    outputRange: ['-1.8deg', '1.8deg'],
  });
  const cloudTranslate = drift.interpolate({
    inputRange: [0, 1],
    outputRange: [-24 * scaleX, 54 * scaleX],
  });
  const cloudTranslateReverse = drift.interpolate({
    inputRange: [0, 1],
    outputRange: [42 * scaleX, -28 * scaleX],
  });
  const bulbOpacity = glow.interpolate({
    inputRange: [0, 1],
    outputRange: [0.72, 1],
  });

  return (
    <View style={[styles.scene, size]} testID="moving-house-backdrop">
      <Image
        resizeMode="stretch"
        source={movingHouseBackgroundSource}
        style={StyleSheet.absoluteFill}
        testID="moving-house-background"
      />

      <Animated.Image
        resizeMode="contain"
        source={movingAssets.cloud05}
        style={[
          scaledRect({ x: 96, y: 49, width: 382, height: 84 }, scaleX, scaleY),
          { transform: [{ translateX: cloudTranslate }] },
        ]}
        testID="moving-house-cloud-1"
      />
      <Animated.Image
        resizeMode="contain"
        source={movingAssets.cloud09}
        style={[
          scaledRect(
            { x: 562, y: 114, width: 315, height: 73 },
            scaleX,
            scaleY,
          ),
          { transform: [{ translateX: cloudTranslateReverse }] },
        ]}
      />
      <Animated.Image
        resizeMode="contain"
        source={movingAssets.cloud17}
        style={[
          scaledRect(
            { x: 897, y: 45, width: 758, height: 231 },
            scaleX,
            scaleY,
          ),
          { transform: [{ translateX: cloudTranslate }] },
        ]}
      />

      <Image
        resizeMode="stretch"
        source={movingAssets.cable}
        style={scaledRect(
          { x: 535, y: 251, width: 816, height: 48 },
          scaleX,
          scaleY,
        )}
      />
      {bulbs.map((rect, index) => (
        <Animated.Image
          key={`${rect.x}-${rect.y}`}
          resizeMode="contain"
          source={movingAssets.bulb}
          style={[
            scaledRect(rect, scaleX, scaleY),
            {
              opacity: bulbOpacity,
              transform: [
                { rotate: index % 2 === 0 ? windRotation : flowerRotation },
              ],
            },
          ]}
        />
      ))}

      <Animated.Image
        resizeMode="contain"
        source={movingAssets.lantern}
        style={[
          scaledRect(
            { x: 455, y: 205, width: 82, height: 154 },
            scaleX,
            scaleY,
          ),
          {
            opacity: bulbOpacity,
            transform: [{ rotate: windRotation }],
          },
        ]}
        testID="moving-house-lantern"
      />

      <Animated.Image
        resizeMode="contain"
        source={movingAssets.grassLeft}
        style={[
          scaledRect(
            { x: 30, y: 655, width: 350, height: 274 },
            scaleX,
            scaleY,
          ),
          { transform: [{ rotate: windRotation }] },
        ]}
      />
      <Animated.Image
        resizeMode="contain"
        source={movingAssets.grassRight}
        style={[
          scaledRect(
            { x: 1280, y: 640, width: 362, height: 297 },
            scaleX,
            scaleY,
          ),
          { transform: [{ rotate: flowerRotation }] },
        ]}
      />
      {flowers.map(({ rect, source }) => (
        <Animated.Image
          key={`${rect.x}-${rect.y}`}
          resizeMode="contain"
          source={source}
          style={[
            scaledRect(rect, scaleX, scaleY),
            { transform: [{ rotate: flowerRotation }] },
          ]}
        />
      ))}

      <Animated.Image
        resizeMode="contain"
        source={movingAssets.canopyLeft}
        style={[
          scaledRect({ x: 0, y: 0, width: 757, height: 336 }, scaleX, scaleY),
          { transform: [{ rotate: windRotation }] },
        ]}
        testID="moving-house-canopy-left"
      />
      <Animated.Image
        resizeMode="contain"
        source={movingAssets.canopyRight}
        style={[
          scaledRect(
            { x: 1145, y: 0, width: 527, height: 353 },
            scaleX,
            scaleY,
          ),
          { transform: [{ rotate: flowerRotation }] },
        ]}
      />
    </View>
  );
}

function scaledRect(rect: SceneRect, scaleX: number, scaleY: number) {
  return {
    position: 'absolute' as const,
    left: rect.x * scaleX,
    top: rect.y * scaleY,
    width: rect.width * scaleX,
    height: rect.height * scaleY,
  };
}

const styles = StyleSheet.create({
  scene: {
    overflow: 'hidden',
  },
});
