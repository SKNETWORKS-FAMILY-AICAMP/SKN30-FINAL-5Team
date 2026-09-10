import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useState } from 'react';
import {
  AppState,
  Image,
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
const PLAYER_SIZE = 86;

export function KikkiRunnerGameScreen({ onBack }: { onBack: () => void }) {
  const [game, setGame] = useState(createKikkiRunnerState);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (game.status !== 'playing' || paused) return undefined;
    const timer = setInterval(() => {
      setGame((current) =>
        advanceKikkiRunner(current, KIKKI_RUNNER_TICK_MS, Math.random),
      );
    }, KIKKI_RUNNER_TICK_MS);
    return () => clearInterval(timer);
  }, [game.status, paused]);

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
  const groundShift = game.distanceM % 24;

  return (
    <View style={styles.screen} testID="kikki-runner-screen">
      <LinearGradient
        colors={['#87D9FF', '#DFF6FF', '#FFF0B8']}
        locations={[0, 0.58, 1]}
        pointerEvents="none"
        style={StyleSheet.absoluteFill}
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
            <Text style={styles.subtitle}>바나나 섬 한 바퀴</Text>
          </View>

          <View
            accessibilityLabel={`바나나 ${game.score}개, ${game.distanceM}미터, ${kikkiRunnerSecondsLeft(game)}초 남음`}
            style={styles.scoreBlock}
          >
            <View style={styles.scoreRow}>
              <BananaGlyph size={18} />
              <Text style={styles.scoreText}>{game.score}</Text>
            </View>
            <Text style={styles.distanceText}>{game.distanceM}m</Text>
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
          onStartShouldSetResponder={() => game.status === 'playing' && !paused}
          style={styles.arena}
          testID="kikki-runner-arena"
        >
          <View style={[styles.cloud, styles.cloudOne]} />
          <View style={[styles.cloud, styles.cloudTwo]} />
          <View style={styles.farIsland} />

          {game.objects.map((object) => (
            <View
              key={object.id}
              pointerEvents="none"
              style={[
                styles.object,
                {
                  bottom: `${GROUND_HEIGHT_PERCENT + object.height * 100}%`,
                  left: `${object.x * 100}%`,
                  transform: [{ rotate: `${object.rotationDeg}deg` }],
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
                  { rotate: game.playerHeight > 0 ? '-8deg' : '0deg' },
                ],
              },
            ]}
            testID="kikki-runner-player"
          >
            <Image
              accessibilityLabel="달리는 끼끼"
              resizeMode="contain"
              source={imageAssets.mascotWarmupWalk}
              style={styles.playerImage}
            />
          </View>

          <View pointerEvents="none" style={styles.ground}>
            <View style={styles.grassLine} />
            <View style={styles.groundPath}>
              {Array.from({ length: 7 }, (_, index) => (
                <View
                  key={index}
                  style={[
                    styles.pathMark,
                    { left: `${index * 24 - groundShift}%` },
                  ]}
                />
              ))}
            </View>
          </View>

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
              title="끼끼와 바나나 섬을 달려요!"
            >
              화면을 눌러 점프하고, 한 번 더 눌러 이단 점프해요. 바나나는 모으고
              바위는 가볍게 뛰어넘어 보세요.
            </RunnerCard>
          ) : null}

          {game.status === 'finished' ? (
            <RunnerCard
              actionLabel="한 번 더"
              onAction={start}
              title={`${game.distanceM}m를 달리고 바나나 ${game.score}개를 만났어요!`}
            >
              기록은 이 화면 안에서만 보여요. 편할 때 다시 달려도 좋아요.
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
    <View style={styles.overlay} testID="kikki-runner-dialog">
      <View style={styles.card}>
        <Image
          accessible={false}
          resizeMode="contain"
          source={imageAssets.mascotWarmupWalk}
          style={styles.cardMascot}
        />
        <Text style={styles.cardTitle}>{title}</Text>
        <Text style={styles.cardBody}>{children}</Text>
        <Pressable
          accessibilityRole="button"
          onPress={onAction}
          style={({ pressed }) => [
            styles.startButton,
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
  screen: { flex: 1, overflow: 'hidden', backgroundColor: '#87D9FF' },
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
  title: { color: colors.text, fontSize: 20, fontWeight: '900' },
  subtitle: { color: colors.textSub, fontSize: 11, fontWeight: '700' },
  scoreBlock: {
    minWidth: 72,
    alignItems: 'flex-end',
    borderRadius: 18,
    backgroundColor: 'rgba(255, 255, 255, 0.88)',
    paddingHorizontal: 12,
    paddingVertical: 7,
    ...shadows.card,
  },
  scoreRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  scoreText: { color: colors.text, fontSize: 15, fontWeight: '900' },
  distanceText: { color: colors.textSub, fontSize: 11, fontWeight: '800' },
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
    width: 90,
    height: 26,
    borderRadius: 18,
    backgroundColor: 'rgba(255, 255, 255, 0.72)',
  },
  cloudOne: { top: '15%', right: '8%' },
  cloudTwo: { top: '33%', left: '-8%', transform: [{ scale: 0.7 }] },
  farIsland: {
    position: 'absolute',
    right: '-15%',
    bottom: '18%',
    width: '70%',
    height: '28%',
    borderTopLeftRadius: 180,
    borderTopRightRadius: 90,
    backgroundColor: '#89C978',
    opacity: 0.72,
  },
  object: {
    position: 'absolute',
    zIndex: 4,
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
    zIndex: 5,
    width: PLAYER_SIZE,
    height: PLAYER_SIZE,
  },
  playerImage: { width: '100%', height: '100%' },
  ground: {
    position: 'absolute',
    right: 0,
    bottom: 0,
    left: 0,
    height: `${GROUND_HEIGHT_PERCENT}%`,
    backgroundColor: '#A7D96F',
  },
  grassLine: { height: 9, backgroundColor: '#65AD57' },
  groundPath: {
    flex: 1,
    overflow: 'hidden',
    backgroundColor: '#E9C47A',
  },
  pathMark: {
    position: 'absolute',
    top: '48%',
    width: 36,
    height: 7,
    borderRadius: 4,
    backgroundColor: 'rgba(159, 110, 54, 0.22)',
  },
  lifeRow: {
    position: 'absolute',
    top: spacing.md,
    left: '5%',
    zIndex: 6,
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
  cardMascot: { width: 76, height: 76, marginBottom: spacing.sm },
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
  startButtonPressed: { opacity: 0.76 },
  startButtonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '900' },
});
