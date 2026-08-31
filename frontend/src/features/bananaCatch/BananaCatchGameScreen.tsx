import { useEffect, useRef, useState } from 'react';
import {
  AppState,
  Image,
  Pressable,
  StyleSheet,
  Text,
  View,
  type GestureResponderEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { imageAssets } from '../../assets';
import { colors, shadows, spacing } from '../../components/theme';
import { BananaGlyph } from '../house/HouseArt';
import {
  BANANA_HALF_WIDTH,
  BANANA_CATCH_TICK_MS,
  PLAYER_HALF_WIDTH,
  advanceBananaCatch,
  bananaBasketStage,
  bananaCatchSecondsLeft,
  createBananaCatchState,
  moveBananaCatcher,
  startBananaCatch,
} from './bananaCatchModel';

const PLAYER_SIZE = 92;
const BANANA_SIZE = 33;
const CATCHER_HEIGHT = PLAYER_SIZE + 16;
const CATCHER_BOTTOM_RATIO = 0.05;
const BASKET_LIP_RATIO_IN_ASSET = 0.56;
const BASKET_WIDTH_RATIO_IN_ASSET = 0.42;
const DEFAULT_CATCH_LINE_Y = 0.75;

export function bananaCatchLayoutMetrics(width: number, height: number) {
  const safeWidth = Math.max(1, width);
  const safeHeight = Math.max(1, height);
  const bananaHalfWidthX = BANANA_SIZE / 2 / safeWidth;
  const playerHalfWidthX = PLAYER_SIZE / 2 / safeWidth;
  const basketLipY =
    1 -
    CATCHER_BOTTOM_RATIO -
    (CATCHER_HEIGHT - PLAYER_SIZE * BASKET_LIP_RATIO_IN_ASSET) / safeHeight;

  return {
    bananaHalfWidthX,
    playerHalfWidthX,
    catchHalfWidthX:
      (PLAYER_SIZE * BASKET_WIDTH_RATIO_IN_ASSET) / 2 / safeWidth +
      bananaHalfWidthX,
    catchLineY: Math.min(
      1,
      Math.max(0, basketLipY - BANANA_SIZE / 2 / safeHeight),
    ),
  };
}

const COLLECTING_MASCOT_ASSETS = [
  {
    stage: 'empty' as const,
    source: imageAssets.houseMascotCollectingBananasEmpty,
  },
  {
    stage: 'medium' as const,
    source: imageAssets.houseMascotCollectingBananasMedium,
  },
  {
    stage: 'full' as const,
    source: imageAssets.houseMascotCollectingBananasFull,
  },
];

export function BananaCatchGameScreen({ onBack }: { onBack: () => void }) {
  const [game, setGame] = useState(createBananaCatchState);
  const [paused, setPaused] = useState(false);
  const arenaWidth = useRef(1);
  const catchLineY = useRef(DEFAULT_CATCH_LINE_Y);
  const catchHalfWidthX = useRef(PLAYER_HALF_WIDTH);
  const bananaHalfWidthX = useRef(BANANA_HALF_WIDTH);
  const playerHalfWidthX = useRef(PLAYER_HALF_WIDTH);
  const catcherStage = bananaBasketStage(game.score);

  useEffect(() => {
    if (game.status !== 'playing' || paused) return undefined;
    const timer = setInterval(() => {
      setGame((current) =>
        advanceBananaCatch(
          current,
          BANANA_CATCH_TICK_MS,
          Math.random,
          catchLineY.current,
          catchHalfWidthX.current,
          bananaHalfWidthX.current,
        ),
      );
    }, BANANA_CATCH_TICK_MS);
    return () => clearInterval(timer);
  }, [game.status, paused]);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      if (nextState !== 'active') setPaused(true);
    });
    return () => subscription.remove();
  }, []);

  const moveFromEvent = (event: GestureResponderEvent) => {
    const x = event.nativeEvent.locationX / arenaWidth.current;
    setGame((current) =>
      moveBananaCatcher(current, x, playerHalfWidthX.current),
    );
  };
  const start = () => {
    setPaused(false);
    setGame(startBananaCatch(Math.random, bananaHalfWidthX.current));
  };

  return (
    <View style={styles.screen} testID="banana-catch-screen">
      <View
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, styles.backgroundFrame]}
        testID="banana-catch-background-frame"
      >
        <Image
          blurRadius={3}
          resizeMode="cover"
          source={imageAssets.bananaCatchBackground}
          style={styles.background}
          testID="banana-catch-background"
        />
      </View>
      <SafeAreaView
        edges={['top']}
        style={styles.safeArea}
        testID="banana-catch-safe-area"
      >
        <View style={styles.header}>
          <Pressable
            accessibilityLabel="끼끼의 집으로 돌아가기"
            accessibilityRole="button"
            onPress={onBack}
            style={styles.headerButton}
          >
            <Text style={styles.headerButtonText}>‹</Text>
          </Pressable>

          <View style={styles.titleBlock}>
            <Text accessibilityRole="header" style={styles.title}>
              바나나 받아라!
            </Text>
            <Text style={styles.subtitle}>하늘에서 오는 바나나를 잡아봐요</Text>
          </View>

          <View
            accessibilityLabel={`점수 ${game.score}점, ${bananaCatchSecondsLeft(game)}초 남음`}
            style={styles.score}
          >
            <View style={styles.scoreRow}>
              <BananaGlyph size={18} />
              <Text style={styles.scoreText}>{game.score}</Text>
            </View>
            <Text style={styles.timerValue}>
              {bananaCatchSecondsLeft(game)}초
            </Text>
          </View>
        </View>

        <View
          accessibilityLabel="바나나가 떨어지는 게임 공간"
          onLayout={(event) => {
            const { height, width } = event.nativeEvent.layout;
            const metrics = bananaCatchLayoutMetrics(width, height);
            arenaWidth.current = Math.max(1, width);
            catchLineY.current = metrics.catchLineY;
            catchHalfWidthX.current = metrics.catchHalfWidthX;
            bananaHalfWidthX.current = metrics.bananaHalfWidthX;
            playerHalfWidthX.current = metrics.playerHalfWidthX;
          }}
          onMoveShouldSetResponder={() => game.status === 'playing'}
          onResponderGrant={moveFromEvent}
          onResponderMove={moveFromEvent}
          onStartShouldSetResponder={() => game.status === 'playing'}
          style={styles.arena}
          testID="banana-catch-arena"
        >
          {game.bananas.map((banana) => (
            <View
              accessible={false}
              key={banana.id}
              pointerEvents="none"
              style={[
                styles.fallingBanana,
                {
                  left: `${banana.x * 100}%`,
                  top: `${banana.y * 100}%`,
                  transform: [{ rotate: `${banana.rotationDeg}deg` }],
                },
              ]}
              testID={`falling-banana-${banana.id}`}
            >
              <BananaGlyph size={BANANA_SIZE} />
            </View>
          ))}

          <View
            pointerEvents="none"
            style={styles.grass}
            testID="banana-catch-grass-frame"
          >
            <Image
              accessible={false}
              resizeMode="stretch"
              source={imageAssets.bananaCatchGrass}
              style={styles.grassImage}
              testID="banana-catch-grass"
            />
          </View>
          <View
            pointerEvents="none"
            style={[styles.catcher, { left: `${game.playerX * 100}%` }]}
            testID="banana-catcher"
          >
            {COLLECTING_MASCOT_ASSETS.map(({ source, stage }) => {
              const active = stage === catcherStage;
              return (
                <Image
                  accessibilityLabel={active ? '바나나를 받는 끼끼' : undefined}
                  accessible={active}
                  key={stage}
                  resizeMode="contain"
                  source={source}
                  style={[styles.mascot, !active && styles.hiddenMascot]}
                  testID={`banana-catcher-mascot-${stage}`}
                />
              );
            })}
          </View>

          {game.status === 'ready' ? (
            <GameCard
              actionLabel="게임 시작"
              onAction={start}
              title="30초 동안 바나나를 받아요!"
            >
              화면을 누르거나 드래그해서 끼끼를 움직여요. 놓쳐도 점수는 줄지
              않아요.
            </GameCard>
          ) : null}

          {game.status === 'finished' ? (
            <GameCard
              actionLabel="한 번 더"
              onAction={start}
              title={`바나나 ${game.score}개를 받았어요!`}
            >
              원하는 만큼 다시 놀 수 있어요.
            </GameCard>
          ) : null}

          {paused && game.status === 'playing' ? (
            <GameCard
              actionLabel="계속하기"
              onAction={() => setPaused(false)}
              title="잠시 멈췄어요"
            >
              준비되면 이어서 받아요.
            </GameCard>
          ) : null}
        </View>
      </SafeAreaView>
    </View>
  );
}

function GameCard({
  actionLabel,
  children,
  onAction,
  title,
}: {
  actionLabel: string;
  children: string;
  onAction: () => void;
  title: string;
}) {
  return (
    <View style={styles.overlay} testID="banana-catch-dialog">
      <View style={styles.card}>
        <BananaGlyph size={36} />
        <Text style={styles.cardTitle}>{title}</Text>
        <Text style={styles.cardBody}>{children}</Text>
        <Pressable
          accessibilityRole="button"
          onPress={onAction}
          style={styles.startButton}
        >
          <Text style={styles.startButtonText}>{actionLabel}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, overflow: 'hidden', backgroundColor: '#8DDCFF' },
  backgroundFrame: {
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  background: {
    width: '100%',
    height: '100%',
  },
  safeArea: {
    flex: 1,
    width: '100%',
  },
  header: {
    zIndex: 6,
    width: '100%',
    maxWidth: 430,
    minHeight: 76,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
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
  headerButtonText: {
    marginTop: -3,
    color: colors.text,
    fontSize: 36,
    lineHeight: 38,
  },
  titleBlock: { flex: 1 },
  title: { color: colors.text, fontSize: 21, fontWeight: '900' },
  subtitle: { color: colors.textSub, fontSize: 11, fontWeight: '600' },
  score: {
    minWidth: 64,
    minHeight: 58,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.86)',
    paddingHorizontal: 10,
    ...shadows.card,
  },
  scoreRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  scoreText: { color: colors.text, fontSize: 18, fontWeight: '900' },
  arena: {
    flex: 1,
    minHeight: 420,
    overflow: 'hidden',
    borderWidth: 0,
    backgroundColor: 'transparent',
  },
  fallingBanana: {
    position: 'absolute',
    zIndex: 5,
    width: BANANA_SIZE,
    height: BANANA_SIZE,
    marginLeft: -BANANA_SIZE / 2,
    marginTop: -BANANA_SIZE / 2,
  },
  grass: {
    position: 'absolute',
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 1,
    height: '13%',
  },
  grassImage: {
    width: '100%',
    height: '100%',
  },
  catcher: {
    position: 'absolute',
    bottom: '5%',
    zIndex: 3,
    width: PLAYER_SIZE,
    height: CATCHER_HEIGHT,
    marginLeft: -PLAYER_SIZE / 2,
    alignItems: 'center',
  },
  mascot: {
    position: 'absolute',
    top: 0,
    width: PLAYER_SIZE,
    height: PLAYER_SIZE,
    opacity: 1,
  },
  hiddenMascot: { opacity: 0 },
  overlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 10,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: 'rgba(63, 84, 73, 0.24)',
  },
  card: {
    width: '100%',
    maxWidth: 360,
    alignItems: 'center',
    gap: spacing.md,
    borderRadius: 24,
    backgroundColor: colors.surface,
    padding: 24,
    ...shadows.card,
  },
  cardTitle: {
    color: colors.text,
    fontSize: 21,
    fontWeight: '900',
    textAlign: 'center',
  },
  cardBody: {
    color: colors.textSub,
    fontSize: 14,
    lineHeight: 21,
    textAlign: 'center',
  },
  startButton: {
    minWidth: 160,
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 24,
    backgroundColor: colors.primary,
    paddingHorizontal: 24,
  },
  startButtonText: { color: colors.text, fontSize: 16, fontWeight: '900' },
  timerValue: { color: colors.textSub, fontSize: 12, fontWeight: '800' },
});
