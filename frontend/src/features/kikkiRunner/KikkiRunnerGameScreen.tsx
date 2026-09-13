import { useEffect, useRef, useState } from 'react';
import {
  AppState,
  Image,
  type ImageSourcePropType,
  type LayoutChangeEvent,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { imageAssets } from '../../assets';
import { colors, radii, shadows, spacing } from '../../components/theme';
import { BananaGlyph } from '../house/HouseArt';
import {
  IDLE_MINI_GAME_REWARD_STATE,
  miniGameRewardMessage,
  type MiniGameRewardState,
} from '../house/miniGameReward';
import {
  KIKKI_RUNNER_CLIFF_HALF_WIDTH,
  KIKKI_RUNNER_PLAYER_X,
  KIKKI_RUNNER_TICK_MS,
  advanceKikkiRunner,
  createKikkiRunnerState,
  jumpKikkiRunner,
  kikkiRunnerProgress,
  kikkiRunnerSecondsLeft,
  startKikkiRunner,
} from './kikkiRunnerModel';

const GROUND_HEIGHT_PERCENT = 22;
const GROUND_HEIGHT_RATIO = GROUND_HEIGHT_PERCENT / 100;
const GROUND_ASPECT_RATIO = 2172 / 724;
const BROKEN_ROAD_CANVAS_WIDTH = 746;
const BROKEN_ROAD_CANVAS_HEIGHT = 2109;
const BROKEN_ROAD_CONTENT_WIDTH = 719;
const BROKEN_ROAD_CONTENT_TOP = 535;
// At the straight edge, the facade begins 291 px below the visible top. The
// intact road reaches the same seam at 226 / 724 of its height, so a 933 px
// reference height keeps both road surfaces and facades aligned.
const BROKEN_ROAD_SEAM_REFERENCE_HEIGHT = 933;
const GROUND_TILE_OVERLAP = 1;
const PLAYER_SIZE = 86;
const BANANA_VISUAL_CENTER_OFFSET = 23;
const ROCK_GROUND_INSET = 11;
const DEFAULT_ARENA_SIZE = { width: 390, height: 600 } as const;
const CLOUD_REENTRY_GAP = 80;

const runnerClouds: readonly {
  source: ImageSourcePropType;
  width: number;
  height: number;
  top: `${number}%`;
  startRatio: number;
  speedRatio: number;
}[] = [
  {
    source:
      require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/clouds/cloud_05.png') as ImageSourcePropType,
    width: 120,
    height: 27,
    top: '15%',
    startRatio: 0.08,
    speedRatio: 0.13,
  },
  {
    source:
      require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/clouds/cloud_09.png') as ImageSourcePropType,
    width: 98,
    height: 23,
    top: '33%',
    startRatio: 0.66,
    speedRatio: 0.18,
  },
  {
    source:
      require('../../assets/house/moving_temp/campsite_motion_assets_v3_work/clouds/cloud_17.png') as ImageSourcePropType,
    width: 168,
    height: 51,
    top: '21%',
    startRatio: 1.12,
    speedRatio: 0.1,
  },
] as const;

const runnerGroundSource =
  require('../../assets/game_background/kkikki_run/road2.png') as ImageSourcePropType;
const runnerBackgroundSource =
  require('../../assets/game_background/kkikki_run/city_view.png') as ImageSourcePropType;
const runnerBrokenRoadSource =
  require('../../assets/game_background/kkikki_run/broken_road.png') as ImageSourcePropType;

function positiveModulo(value: number, divisor: number): number {
  return ((value % divisor) + divisor) % divisor;
}

/** Wrap only after the complete cloud has crossed the left screen edge. */
export function wrapRunnerCloudLeft(
  unwrappedLeft: number,
  cloudWidth: number,
  arenaWidth: number,
  reentryGap = CLOUD_REENTRY_GAP,
): number {
  const trackWidth = arenaWidth + cloudWidth + reentryGap;
  return positiveModulo(unwrappedLeft + cloudWidth, trackWidth) - cloudWidth;
}

/**
 * The runner sprite bakes transparent padding under the mascot's feet, so the
 * artwork has to be pushed down inside its box to stand on the grass line.
 * The inset is a share of PLAYER_SIZE rather than a raw pixel value, and the
 * grass line itself is a percentage of the arena, so the feet stay planted on
 * every phone size.
 */
const PLAYER_FOOT_INSET = Math.round(PLAYER_SIZE * 0.19) + 6;

export function KikkiRunnerGameScreen({
  onBack,
  onPlayed,
  rewardState = IDLE_MINI_GAME_REWARD_STATE,
}: {
  onBack: () => void;
  /** Fired once when a started round reaches its finished state. */
  onPlayed?: (score: number) => void;
  rewardState?: MiniGameRewardState;
}) {
  const [game, setGame] = useState(createKikkiRunnerState);
  const [paused, setPaused] = useState(false);
  const [arenaSize, setArenaSize] = useState<{
    width: number;
    height: number;
  }>(DEFAULT_ARENA_SIZE);
  const playCounted = useRef(false);

  useEffect(() => {
    if ((game.status !== 'playing' && game.status !== 'falling') || paused)
      return undefined;
    const timer = setInterval(() => {
      setGame((current) =>
        advanceKikkiRunner(current, KIKKI_RUNNER_TICK_MS, Math.random),
      );
    }, KIKKI_RUNNER_TICK_MS);
    return () => clearInterval(timer);
  }, [game.status, paused]);

  useEffect(() => {
    if (game.status !== 'finished' || playCounted.current) return;
    playCounted.current = true;
    onPlayed?.(game.score);
  }, [game.score, game.status, onPlayed]);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      if (nextState !== 'active') setPaused(true);
    });
    return () => subscription.remove();
  }, []);

  const start = () => {
    setPaused(false);
    setGame(startKikkiRunner(Math.random));
  };
  const jump = () => setGame((current) => jumpKikkiRunner(current));
  const progress = kikkiRunnerProgress(game);
  const secondsLeft = kikkiRunnerSecondsLeft(game);
  const groundHeight = arenaSize.height * GROUND_HEIGHT_RATIO;
  const groundTileWidth = groundHeight * GROUND_ASPECT_RATIO;
  const groundTileStride = groundTileWidth - GROUND_TILE_OVERLAP;
  const groundCycleWidth = groundTileStride * 2;
  const groundOffset = -positiveModulo(
    game.worldOffset * arenaSize.width,
    groundCycleWidth,
  );
  const groundTileCount =
    Math.ceil((arenaSize.width + groundCycleWidth) / groundTileStride) + 1;
  const visibleCliffs = game.objects.filter(
    (object) => object.kind === 'cliff',
  );
  const brokenRoadScale = groundHeight / BROKEN_ROAD_SEAM_REFERENCE_HEIGHT;
  const brokenRoadCapWidth = BROKEN_ROAD_CONTENT_WIDTH * brokenRoadScale;
  const brokenRoadImageWidth = BROKEN_ROAD_CANVAS_WIDTH * brokenRoadScale;
  const brokenRoadImageHeight = BROKEN_ROAD_CANVAS_HEIGHT * brokenRoadScale;
  const brokenRoadImageTop = -BROKEN_ROAD_CONTENT_TOP * brokenRoadScale;
  const cliffGapWidth = KIKKI_RUNNER_CLIFF_HALF_WIDTH * 2 * arenaSize.width;
  const cliffVisualWidth = brokenRoadCapWidth * 2 + cliffGapWidth;
  const cliffBackgroundTop = -(arenaSize.height - groundHeight);
  const onArenaLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    if (width > 0 && height > 0) setArenaSize({ width, height });
  };

  return (
    <View style={styles.screen} testID="kikki-runner-screen">
      <Image
        accessible={false}
        fadeDuration={0}
        resizeMode="stretch"
        source={runnerBrokenRoadSource}
        style={[
          styles.assetPreloader,
          { height: brokenRoadImageHeight, width: brokenRoadImageWidth },
        ]}
        testID="kikki-runner-broken-road-preload"
      />

      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.header} testID="kikki-runner-header">
          <Pressable
            accessibilityLabel="끼끼의 집으로 돌아가기"
            accessibilityRole="button"
            onPress={onBack}
            style={styles.headerButton}
          >
            <View style={styles.backChevron} />
          </Pressable>

          <View style={styles.titleBlock}>
            <Text accessibilityRole="header" style={styles.title}>
              끼끼 달리기
            </Text>
          </View>

          <View
            accessibilityLabel={`바나나 ${game.score}개, ${game.distanceM}미터, ${secondsLeft}초 남음`}
            style={styles.scoreBlock}
            testID="kikki-runner-score-card"
          >
            <View style={styles.scoreRow}>
              <BananaGlyph size={18} />
              <Text style={styles.scoreText}>{game.score}</Text>
            </View>
            <Text style={styles.distanceText}>{game.distanceM}m</Text>
            <Text style={styles.timerValue}>{secondsLeft}초</Text>
          </View>
        </View>

        <View style={styles.progressTrack}>
          <View
            style={[styles.progressFill, { width: `${progress * 100}%` }]}
          />
        </View>

        <View
          accessible={game.status === 'playing' && !paused}
          accessibilityHint="달리는 동안 누르면 점프하고, 공중에서 한 번 더 누르면 이단 점프합니다."
          accessibilityLabel="끼끼 달리기 게임 영역"
          accessibilityRole={
            game.status === 'playing' && !paused ? 'button' : undefined
          }
          onResponderGrant={jump}
          onLayout={onArenaLayout}
          onStartShouldSetResponder={() => game.status === 'playing' && !paused}
          style={styles.arena}
          testID="kikki-runner-arena"
        >
          <Image
            accessible={false}
            fadeDuration={0}
            resizeMode="stretch"
            source={runnerBackgroundSource}
            style={styles.cityBackground}
            testID="kikki-runner-city-background"
          />

          {runnerClouds.map((cloud, index) => (
            <Image
              accessible={false}
              fadeDuration={0}
              key={`cloud-${index}`}
              resizeMode="contain"
              source={cloud.source}
              style={[
                styles.cloud,
                {
                  height: cloud.height,
                  left: wrapRunnerCloudLeft(
                    arenaSize.width * cloud.startRatio -
                      game.worldOffset * arenaSize.width * cloud.speedRatio,
                    cloud.width,
                    arenaSize.width,
                  ),
                  top: cloud.top,
                  width: cloud.width,
                },
              ]}
              testID={`kikki-runner-cloud-${index + 1}`}
            />
          ))}
          {game.objects
            .filter((object) => object.kind !== 'cliff')
            .map((object) => (
              <View
                key={object.id}
                pointerEvents="none"
                style={[
                  styles.object,
                  {
                    bottom: `${GROUND_HEIGHT_PERCENT + object.height * 100}%`,
                    left: `${object.x * 100}%`,
                    transform: [
                      {
                        translateY:
                          object.kind === 'banana'
                            ? BANANA_VISUAL_CENTER_OFFSET
                            : ROCK_GROUND_INSET,
                      },
                      { rotate: `${object.rotationDeg}deg` },
                    ],
                  },
                ]}
                testID={`kikki-runner-${object.kind}-${object.id}`}
              >
                {object.kind === 'banana' ? (
                  <BananaGlyph size={34} />
                ) : (
                  <View style={styles.rock}>
                    <View style={styles.rockHighlight} />
                  </View>
                )}
              </View>
            ))}

          <View
            pointerEvents="none"
            style={[
              styles.player,
              {
                bottom: `${GROUND_HEIGHT_PERCENT + game.playerHeight * 100}%`,
                left: `${KIKKI_RUNNER_PLAYER_X * 100}%`,
                opacity:
                  game.invulnerabilityMs > 0 &&
                  Math.floor(game.invulnerabilityMs / 100) % 2 === 0
                    ? 0.35
                    : 1,
                transform: [
                  { translateX: -PLAYER_SIZE / 2 },
                  {
                    rotate:
                      game.status === 'falling'
                        ? '24deg'
                        : game.playerHeight > 0
                          ? '-8deg'
                          : '0deg',
                  },
                ],
              },
            ]}
            testID="kikki-runner-player"
          >
            <Image
              accessibilityLabel="달리는 끼끼"
              resizeMode="contain"
              source={imageAssets.kikkiRunnerMascot}
              style={styles.playerImage}
            />
          </View>

          <View
            pointerEvents="none"
            style={styles.groundLayer}
            testID="kikki-runner-ground-layer"
          >
            <View
              renderToHardwareTextureAndroid
              shouldRasterizeIOS
              style={[
                styles.groundTrack,
                {
                  transform: [{ translateX: groundOffset }],
                  width:
                    (groundTileCount - 1) * groundTileStride + groundTileWidth,
                },
              ]}
              testID="kikki-runner-ground-track"
            >
              {Array.from({ length: groundTileCount }, (_, tileIndex) => (
                <Image
                  accessible={false}
                  fadeDuration={0}
                  key={tileIndex}
                  resizeMode="stretch"
                  source={runnerGroundSource}
                  style={[
                    styles.groundImage,
                    {
                      left: tileIndex * groundTileStride,
                      transform:
                        tileIndex % 2 === 0 ? undefined : [{ scaleX: -1 }],
                      width: groundTileWidth,
                    },
                  ]}
                />
              ))}
            </View>
          </View>

          {visibleCliffs.map((cliff) => {
            const gapStart =
              (cliff.x - KIKKI_RUNNER_CLIFF_HALF_WIDTH) * arenaSize.width;
            const visualLeft = gapStart - brokenRoadCapWidth;
            return (
              <View
                key={cliff.id}
                pointerEvents="none"
                renderToHardwareTextureAndroid
                shouldRasterizeIOS
                style={[
                  styles.cliffVisual,
                  {
                    height: groundHeight,
                    transform: [{ translateX: visualLeft }],
                    width: cliffVisualWidth,
                  },
                ]}
                testID={`kikki-runner-cliff-${cliff.id}`}
              >
                <Image
                  accessible={false}
                  fadeDuration={0}
                  resizeMode="stretch"
                  source={runnerBackgroundSource}
                  style={[
                    styles.cliffBackground,
                    {
                      height: arenaSize.height,
                      top: cliffBackgroundTop,
                      transform: [{ translateX: -visualLeft }],
                      width: arenaSize.width,
                    },
                  ]}
                  testID={`kikki-runner-cliff-background-${cliff.id}`}
                />
                {[
                  { left: 0, mirrored: false, side: 'left' },
                  {
                    left: brokenRoadCapWidth + cliffGapWidth,
                    mirrored: true,
                    side: 'right',
                  },
                ].map((cap) => (
                  <View
                    key={cap.side}
                    style={[
                      styles.brokenRoadCap,
                      {
                        height: groundHeight,
                        left: cap.left,
                        transform: cap.mirrored ? [{ scaleX: -1 }] : undefined,
                        width: brokenRoadCapWidth,
                      },
                    ]}
                    testID={`kikki-runner-cliff-${cap.side}-${cliff.id}`}
                  >
                    <Image
                      accessible={false}
                      fadeDuration={0}
                      resizeMode="stretch"
                      source={runnerBrokenRoadSource}
                      style={[
                        styles.brokenRoadImage,
                        {
                          height: brokenRoadImageHeight,
                          top: brokenRoadImageTop,
                          width: brokenRoadImageWidth,
                        },
                      ]}
                    />
                  </View>
                ))}
              </View>
            );
          })}

          <View
            accessibilityLabel={`남은 기회 ${game.lives}개`}
            pointerEvents="none"
            style={styles.lifeRow}
          >
            {Array.from({ length: 3 }, (_, index) => (
              <Text
                key={index}
                style={[styles.heart, index >= game.lives && styles.heartEmpty]}
              >
                ♥
              </Text>
            ))}
          </View>

          {game.status === 'ready' ? (
            <RunnerCard
              actionLabel="달리기 시작"
              onAction={start}
              title="끼끼와 바나나 도시를 달려요!"
            >
              바나나 도시의 노을을 따라 달리며 바위와 절벽을 뛰어넘고, 바나나를
              모아요. 화면을 두 번 터치하면 2단 점프해요.
            </RunnerCard>
          ) : null}

          {game.status === 'finished' ? (
            <RunnerCard
              actionLabel="확인"
              actionPending={rewardState.status === 'pending'}
              onAction={onBack}
              title={
                game.finishReason === 'cliff'
                  ? `절벽에 빠졌어요! 바나나 ${game.score}개를 모았어요`
                  : `${game.distanceM}m 달리고 바나나 ${game.score}개를 모았어요!`
              }
            >
              {miniGameRewardMessage(rewardState)}
            </RunnerCard>
          ) : null}

          {paused && game.status === 'playing' ? (
            <RunnerCard
              actionLabel="계속 달리기"
              onAction={() => setPaused(false)}
              title="잠시 쉬고 있어요"
            >
              준비되면 끼끼와 이어서 달려요.
            </RunnerCard>
          ) : null}
        </View>
      </SafeAreaView>
    </View>
  );
}

function RunnerCard({
  actionLabel,
  actionPending = false,
  children,
  onAction,
  title,
}: {
  actionLabel: string;
  actionPending?: boolean;
  children: string;
  onAction: () => void;
  title: string;
}) {
  return (
    <View style={styles.overlay} testID="kikki-runner-dialog">
      <View style={styles.card}>
        <Image
          accessible={false}
          resizeMode="contain"
          source={imageAssets.kikkiRunnerMascot}
          style={styles.cardMascot}
        />
        <Text style={styles.cardTitle}>{title}</Text>
        <Text style={styles.cardBody}>{children}</Text>
        <Pressable
          accessibilityRole="button"
          disabled={actionPending}
          onPress={onAction}
          style={({ pressed }) => [
            styles.startButton,
            actionPending && styles.startButtonPending,
            pressed && styles.startButtonPressed,
          ]}
        >
          <Text style={styles.startButtonText}>{actionLabel}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, overflow: 'hidden', backgroundColor: '#51407D' },
  cityBackground: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    width: '100%',
    height: '100%',
  },
  safeArea: { flex: 1, width: '100%' },
  header: {
    zIndex: 8,
    flexDirection: 'row',
    alignItems: 'center',
    width: '100%',
    paddingHorizontal: '4%',
    paddingVertical: spacing.sm,
  },
  headerButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 22,
    backgroundColor: 'rgba(255, 255, 255, 0.86)',
    ...shadows.card,
  },
  backChevron: {
    width: 12,
    height: 12,
    borderBottomWidth: 2.5,
    borderLeftWidth: 2.5,
    borderColor: colors.text,
    transform: [{ rotate: '45deg' }],
  },
  titleBlock: { flex: 1, alignItems: 'center' },
  title: {
    color: '#FFF8FF',
    fontSize: 20,
    fontWeight: '900',
    textShadowColor: 'rgba(30, 18, 57, 0.72)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  scoreBlock: {
    minWidth: 72,
    minHeight: 64,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 18,
    backgroundColor: 'rgba(255, 255, 255, 0.88)',
    paddingHorizontal: 12,
    paddingVertical: 7,
    ...shadows.card,
  },
  scoreRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  scoreText: { color: colors.text, fontSize: 15, fontWeight: '900' },
  distanceText: { color: colors.textSub, fontSize: 11, fontWeight: '800' },
  timerValue: { color: colors.textSub, fontSize: 12, fontWeight: '800' },
  progressTrack: {
    zIndex: 7,
    height: 6,
    marginHorizontal: '5%',
    overflow: 'hidden',
    borderRadius: 3,
    backgroundColor: 'rgba(255, 255, 255, 0.65)',
  },
  progressFill: {
    height: '100%',
    borderRadius: 3,
    backgroundColor: '#FF9D47',
  },
  arena: { flex: 1, overflow: 'hidden' },
  cloud: {
    position: 'absolute',
    opacity: 0.86,
  },
  assetPreloader: {
    position: 'absolute',
    top: 0,
    left: -10_000,
    opacity: 0,
  },
  object: {
    position: 'absolute',
    zIndex: 5,
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'flex-end',
    marginLeft: -22,
  },
  rock: {
    width: 42,
    height: 34,
    overflow: 'hidden',
    borderTopLeftRadius: 19,
    borderTopRightRadius: 14,
    borderBottomLeftRadius: 8,
    borderBottomRightRadius: 10,
    borderWidth: 2,
    borderColor: '#765746',
    backgroundColor: '#9A735C',
  },
  rockHighlight: {
    width: 16,
    height: 7,
    marginLeft: 7,
    marginTop: 7,
    borderRadius: 6,
    backgroundColor: '#C69B7C',
    transform: [{ rotate: '-12deg' }],
  },
  player: {
    position: 'absolute',
    zIndex: 6,
    width: PLAYER_SIZE,
    height: PLAYER_SIZE,
  },
  playerImage: {
    width: '100%',
    height: '100%',
    transform: [{ translateY: PLAYER_FOOT_INSET }, { scaleX: -1 }],
  },
  groundLayer: {
    position: 'absolute',
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 3,
    height: `${GROUND_HEIGHT_PERCENT}%`,
    overflow: 'hidden',
  },
  groundTrack: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
  },
  groundImage: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    height: '100%',
  },
  brokenRoadCap: {
    position: 'absolute',
    bottom: 0,
    zIndex: 1,
    overflow: 'hidden',
  },
  cliffVisual: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    zIndex: 4,
    overflow: 'hidden',
  },
  cliffBackground: {
    position: 'absolute',
    left: 0,
  },
  brokenRoadImage: {
    position: 'absolute',
    left: 0,
  },
  lifeRow: {
    position: 'absolute',
    top: spacing.md,
    left: '5%',
    zIndex: 7,
    flexDirection: 'row',
    gap: 4,
    borderRadius: 16,
    backgroundColor: 'rgba(255, 255, 255, 0.82)',
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  heart: { color: '#FF705B', fontSize: 18 },
  heartEmpty: { color: 'rgba(111, 89, 74, 0.2)' },
  overlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 10,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(74, 59, 46, 0.2)',
    padding: spacing.xl,
  },
  card: {
    width: '100%',
    maxWidth: 330,
    alignItems: 'center',
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    backgroundColor: 'rgba(255, 255, 255, 0.96)',
    padding: spacing.xl,
    ...shadows.card,
  },
  cardMascot: {
    width: 76,
    height: 76,
    marginBottom: spacing.sm,
    transform: [{ scaleX: -1 }],
  },
  cardTitle: {
    color: colors.text,
    fontSize: 20,
    fontWeight: '900',
    textAlign: 'center',
  },
  cardBody: {
    marginTop: spacing.sm,
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 21,
    textAlign: 'center',
  },
  startButton: {
    minWidth: 160,
    minHeight: 48,
    marginTop: spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 24,
    backgroundColor: '#FF9D47',
    paddingHorizontal: spacing.xl,
    ...shadows.card,
  },
  startButtonPending: { opacity: 0.56 },
  startButtonPressed: { opacity: 0.76 },
  startButtonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '900' },
});
