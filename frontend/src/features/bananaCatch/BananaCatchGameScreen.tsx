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
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';

import { imageAssets } from '../../assets';
import { colors, shadows, spacing } from '../../components/theme';
import { BananaGlyph } from '../house/HouseArt';
import {
  BANANA_CATCH_TICK_MS,
  advanceBananaCatch,
  bananaCatchSecondsLeft,
  createBananaCatchState,
  moveBananaCatcher,
  startBananaCatch,
} from './bananaCatchModel';

const PLAYER_SIZE = 92;
const BANANA_SIZE = 30;
const PLAYER_MOVE_STEP = 0.09;

export function BananaCatchGameScreen({ onBack }: { onBack: () => void }) {
  const [game, setGame] = useState(createBananaCatchState);
  const [paused, setPaused] = useState(false);
  const arenaWidth = useRef(1);

  useEffect(() => {
    if (game.status !== 'playing' || paused) return undefined;
    const timer = setInterval(() => {
      setGame((current) => advanceBananaCatch(current, BANANA_CATCH_TICK_MS));
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
    setGame((current) => moveBananaCatcher(current, x));
  };
  const start = () => {
    setPaused(false);
    setGame(startBananaCatch());
  };
  const nudge = (direction: -1 | 1) => {
    setGame((current) =>
      moveBananaCatcher(
        current,
        current.playerX + direction * PLAYER_MOVE_STEP,
      ),
    );
  };

  return (
    <LinearGradient
      colors={['#8DDCFF', '#DFF6FF', '#FFF0B5']}
      end={{ x: 0.5, y: 1 }}
      start={{ x: 0.5, y: 0 }}
      style={styles.screen}
      testID="banana-catch-screen"
    >
      <SafeAreaView edges={['top', 'bottom']} style={styles.safeArea}>
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
            accessibilityLabel={`점수 ${game.score}점`}
            style={styles.score}
          >
            <BananaGlyph size={18} />
            <Text style={styles.scoreText}>{game.score}</Text>
          </View>
        </View>

        <View
          accessibilityLabel="바나나가 떨어지는 게임 공간"
          onLayout={(event) => {
            arenaWidth.current = Math.max(1, event.nativeEvent.layout.width);
          }}
          onMoveShouldSetResponder={() => game.status === 'playing'}
          onResponderGrant={moveFromEvent}
          onResponderMove={moveFromEvent}
          onStartShouldSetResponder={() => game.status === 'playing'}
          style={styles.arena}
          testID="banana-catch-arena"
        >
          <View style={[styles.cloud, styles.cloudLeft]} />
          <View style={[styles.cloud, styles.cloudRight]} />

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
                },
              ]}
              testID={`falling-banana-${banana.id}`}
            >
              <BananaGlyph size={BANANA_SIZE} />
            </View>
          ))}

          <View pointerEvents="none" style={styles.grass} />
          <View
            pointerEvents="none"
            style={[styles.catcher, { left: `${game.playerX * 100}%` }]}
            testID="banana-catcher"
          >
            <View style={styles.basket} />
            <Image
              accessibilityLabel="바나나를 받는 끼끼"
              resizeMode="contain"
              source={imageAssets.houseMascotMonkey01}
              style={styles.mascot}
            />
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

        <View style={styles.controls}>
          <Pressable
            accessibilityLabel="끼끼 왼쪽으로 움직이기"
            accessibilityRole="button"
            accessibilityState={{ disabled: game.status !== 'playing' }}
            disabled={game.status !== 'playing'}
            onPress={() => nudge(-1)}
            style={styles.moveButton}
            testID="banana-catch-left"
          >
            <Text style={styles.moveButtonText}>←</Text>
          </Pressable>
          <View style={styles.timer}>
            <Text style={styles.timerCaption}>남은 시간</Text>
            <Text
              accessibilityLabel={`${bananaCatchSecondsLeft(game)}초 남음`}
              style={styles.timerValue}
            >
              {bananaCatchSecondsLeft(game)}초
            </Text>
          </View>
          <Pressable
            accessibilityLabel="끼끼 오른쪽으로 움직이기"
            accessibilityRole="button"
            accessibilityState={{ disabled: game.status !== 'playing' }}
            disabled={game.status !== 'playing'}
            onPress={() => nudge(1)}
            style={styles.moveButton}
            testID="banana-catch-right"
          >
            <Text style={styles.moveButtonText}>→</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    </LinearGradient>
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
  screen: { flex: 1 },
  safeArea: {
    flex: 1,
    width: '100%',
    maxWidth: 430,
    alignSelf: 'center',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  header: {
    minHeight: 76,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
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
    height: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderRadius: 22,
    backgroundColor: 'rgba(255, 255, 255, 0.86)',
    ...shadows.card,
  },
  scoreText: { color: colors.text, fontSize: 18, fontWeight: '900' },
  arena: {
    flex: 1,
    minHeight: 420,
    overflow: 'hidden',
    borderWidth: 3,
    borderColor: 'rgba(255, 255, 255, 0.9)',
    borderRadius: 28,
    backgroundColor: 'rgba(255, 255, 255, 0.16)',
  },
  cloud: {
    position: 'absolute',
    width: 110,
    height: 36,
    borderRadius: 24,
    backgroundColor: 'rgba(255, 255, 255, 0.66)',
  },
  cloudLeft: { top: 54, left: -24 },
  cloudRight: { top: 132, right: -36, width: 138 },
  fallingBanana: {
    position: 'absolute',
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
    height: '13%',
    backgroundColor: '#92CC67',
  },
  catcher: {
    position: 'absolute',
    bottom: '5%',
    width: PLAYER_SIZE,
    height: PLAYER_SIZE + 16,
    marginLeft: -PLAYER_SIZE / 2,
    alignItems: 'center',
  },
  mascot: { width: PLAYER_SIZE, height: PLAYER_SIZE },
  basket: {
    position: 'absolute',
    top: -4,
    width: 66,
    height: 24,
    zIndex: 2,
    borderWidth: 3,
    borderColor: '#8D5A2B',
    borderRadius: 8,
    backgroundColor: '#D79A4D',
  },
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
  controls: {
    minHeight: 82,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingTop: spacing.md,
  },
  moveButton: {
    width: 68,
    height: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 20,
    backgroundColor: colors.surface,
    ...shadows.card,
  },
  moveButtonText: { color: colors.text, fontSize: 27, fontWeight: '900' },
  timer: { alignItems: 'center' },
  timerCaption: { color: colors.textSub, fontSize: 11, fontWeight: '700' },
  timerValue: { color: colors.text, fontSize: 22, fontWeight: '900' },
});
