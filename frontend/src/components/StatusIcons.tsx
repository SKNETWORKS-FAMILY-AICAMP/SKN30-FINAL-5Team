import Svg, { Circle, G, Path } from 'react-native-svg';

/**
 * Report status marks, traced from the shared `design-assets/status` vectors.
 * The calendar and the weekly report both draw them, so they live here rather
 * than inside either feature.
 *
 * Their palette belongs to the asset, so callers pass a box size only. Both
 * view boxes are cropped to the artwork, which lets a mark fill the same circle
 * a completed or safety-stopped day gets instead of sitting shrunken beside it.
 */
export function PartialStatusIcon({
  size = 20,
  testID,
}: {
  size?: number;
  testID?: string;
}) {
  return (
    <Svg
      accessible={false}
      width={size}
      height={size}
      testID={testID}
      viewBox="3 3 26 26"
      fill="none"
    >
      <Circle cx={16} cy={16} r={13} fill="#EFEBE3" />
      <Circle
        cx={16}
        cy={16}
        r={11.6}
        stroke="#776E62"
        strokeDasharray="2.8 2.6"
        strokeLinecap="round"
        strokeWidth={1.9}
      />
      <G
        stroke="#4E463B"
        strokeDasharray="1.6 2.6"
        strokeLinecap="round"
        strokeWidth={2.6}
      >
        <Path d="M15.13 20.17 11.03 16.07" />
        <Path d="M15.13 20.17 21.1 11.65" />
      </G>
    </Svg>
  );
}

export function RestStatusIcon({
  size = 20,
  testID,
}: {
  size?: number;
  testID?: string;
}) {
  return (
    <Svg
      accessible={false}
      width={size}
      height={size}
      testID={testID}
      viewBox="4.9 2.5 25 25"
      fill="none"
    >
      <Path
        d="M18.8 4.3C11.6 3.1 5.5 8.4 5.5 15.1c0 6.6 5.3 11.9 11.9 11.9 4.9 0 9.2-3 10.8-7.3-2.1 1.2-4.3 1.6-6.7 1.1-5.5-1.1-9.1-6.3-8-11.8.4-1.9 1.4-3.7 2.7-5.1"
        fill="#F2C76C"
      />
      <Path
        d="m24 3 1.65 3.35 3.7.54-2.67 2.6.63 3.69L24 11.44l-3.31 1.74.63-3.69-2.67-2.6 3.7-.54L24 3Z"
        fill="#C68A35"
      />
    </Svg>
  );
}
