import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  AppState,
  Image,
  Pressable,
  StyleSheet,
  Text,
  View,
  type LayoutChangeEvent,
  type NativeSyntheticEvent,
  type NativeTouchEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { kikkiMergeStageSources } from '../../assets';
import { colors, radii, shadows, spacing } from '../../components/theme';
import {
  IDLE_MINI_GAME_REWARD_STATE,
  miniGameRewardMessage,
  type MiniGameRewardState,
} from '../house/miniGameReward';
import {
  KIKKI_MERGE_DANGER_Y,
  KIKKI_MERGE_DROP_COOLDOWN_MS,
  KIKKI_MERGE_TICK_MS,
  KIKKI_MERGE_TIERS,
  KIKKI_MERGE_WORLD_HEIGHT,
  KIKKI_MERGE_WORLD_WIDTH,
  addKikkiMergeScore,
  clampKikkiDropX,
  createKikkiMergeRound,
  finishKikkiMergeFromOverflow,
  getKikkiMergeCreatedStageCount,
  nextKikkiMergeTier,
  startKikkiMergeRound,
} from './kikkiMergeModel';
import { KikkiMergePhysics, type KikkiMergeOrb } from './kikkiMergePhysics';

type BoardLayout = { width: number; height: number };

export function KikkiMergeGameScreen({
  onBack,
  onPlayed,
  rewardState = IDLE_MINI_GAME_REWARD_STATE,
}: {
  onBack: () => void;
  /** Fired once when a started round reaches its finished state. */
  onPlayed?: (score: number) => void;
  rewardState?: MiniGameRewardState;
}) {
  const [round, setRound] = useState(createKikkiMergeRound);
  const [orbs, setOrbs] = useState<KikkiMergeOrb[]>([]);
  const [currentTier, setCurrentTier] = useState(() => nextKikkiMergeTier());
  const [nextTier, setNextTier] = useState(() => nextKikkiMergeTier());
  const [previewX, setPreviewX] = useState(KIKKI_MERGE_WORLD_WIDTH / 2);
  const [dropReady, setDropReady] = useState(true);
  const [dangerProgress, setDangerProgress] = useState(0);
  const [paused, setPaused] = useState(false);
  const [boardLayout, setBoardLayout] = useState<BoardLayout>({
    width: KIKKI_MERGE_WORLD_WIDTH,
    height: KIKKI_MERGE_WORLD_HEIGHT,
  });
  const physics = useRef<KikkiMergePhysics | null>(null);
  const cooldownTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const playCounted = useRef(false);

  const boardScale = useMemo(
    () =>
      Math.max(
        0.1,
        Math.min(
          boardLayout.width / KIKKI_MERGE_WORLD_WIDTH,
          boardLayout.height / KIKKI_MERGE_WORLD_HEIGHT,
        ),
      ),
    [boardLayout],
  );
  const boardWidth = KIKKI_MERGE_WORLD_WIDTH * boardScale;
  const boardHeight = KIKKI_MERGE_WORLD_HEIGHT * boardScale;

  useEffect(() => {
    if (round.status !== 'playing' || paused) return undefined;
    const timer = setInterval(() => {
      physics.current?.step(KIKKI_MERGE_TICK_MS);
      setOrbs(physics.current?.snapshot() ?? []);
      setDangerProgress(physics.current?.dangerProgress() ?? 0);
    }, KIKKI_MERGE_TICK_MS);
    return () => clearInterval(timer);
  }, [paused, round.status]);

  useEffect(() => {
    if (round.status !== 'finished') return;
    physics.current?.stop();
    physics.current = null;
    if (playCounted.current) return;
    playCounted.current = true;
    onPlayed?.(round.score);
  }, [onPlayed, round.score, round.status]);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextState) => {
      if (nextState !== 'active') setPaused(true);
    });
    return () => subscription.remove();
  }, []);

  useEffect(
    () => () => {
      physics.current?.stop();
      if (cooldownTimer.current !== null) clearTimeout(cooldownTimer.current);
    },
    [],
  );

  const start = () => {
    physics.current?.stop();
    playCounted.current = false;
    setRound(startKikkiMergeRound());
    setOrbs([]);
    setDangerProgress(0);
    setPaused(false);
    setDropReady(true);
    const first = nextKikkiMergeTier();
    const second = nextKikkiMergeTier();
    setCurrentTier(first);
    setNextTier(second);
    setPreviewX(clampKikkiDropX(KIKKI_MERGE_WORLD_WIDTH / 2, first));
    physics.current = new KikkiMergePhysics(
      (resultTier) =>
        setRound((value) => addKikkiMergeScore(value, resultTier)),
      () => setRound((value) => finishKikkiMergeFromOverflow(value)),
    );
  };

  const setAimFromEvent = (event: NativeSyntheticEvent<NativeTouchEvent>) => {
    const nextX = event.nativeEvent.locationX / boardScale;
    setPreviewX(clampKikkiDropX(nextX, currentTier));
  };

  const drop = (requestedX: number = previewX) => {
    if (
      round.status !== 'playing' ||
      paused ||
      !dropReady ||
      !physics.current?.drop(currentTier, requestedX)
    ) {
      return;
    }
    setOrbs(physics.current.snapshot());
    setDropReady(false);
    setCurrentTier(nextTier);
    const queued = nextKikkiMergeTier();
    setNextTier(queued);
    setPreviewX((x) => clampKikkiDropX(x, nextTier));
    cooldownTimer.current = setTimeout(
      () => setDropReady(true),
      KIKKI_MERGE_DROP_COOLDOWN_MS,
    );
  };

  const onBoardLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    if (width > 0 && height > 0) setBoardLayout({ width, height });
  };

  const current = KIKKI_MERGE_TIERS[currentTier] ?? KIKKI_MERGE_TIERS[0];
  const queued = KIKKI_MERGE_TIERS[nextTier] ?? KIKKI_MERGE_TIERS[0];
  const stage9Count = getKikkiMergeCreatedStageCount(round, 9);
  const stage10Count = getKikkiMergeCreatedStageCount(round, 10);
  const stage11Count = getKikkiMergeCreatedStageCount(round, 11);

  return (
    <View style={styles.screen} testID="kikki-merge-screen">
      <LinearGradient
        colors={['#FFF6D7', '#DFF4CB', '#A8D8C3']}
        locations={[0, 0.58, 1]}
        pointerEvents="none"
        style={StyleSheet.absoluteFill}
      />
      <SafeAreaView edges={['top']} style={styles.safeArea}>
        <View style={styles.header}>
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
              끼끼 합치기
            </Text>
            <StageMilestones
              stage9Count={stage9Count}
              stage10Count={stage10Count}
              stage11Count={stage11Count}
            />
          </View>
          <View
            accessibilityLabel={`점수 ${round.score}점`}
            style={styles.scoreChip}
          >
            <Text style={styles.scoreLabel}>점수</Text>
            <Text style={styles.score}>{round.score}</Text>
          </View>
        </View>

        <View onLayout={onBoardLayout} style={styles.boardShell}>
          <View
            accessible={round.status === 'playing' && !paused}
            accessibilityHint="원하는 위치를 누르면 끼끼가 떨어집니다."
            accessibilityLabel={`${current.name} 떨어뜨리기`}
            accessibilityRole={
              round.status === 'playing' && !paused ? 'button' : undefined
            }
            onResponderGrant={setAimFromEvent}
            onResponderMove={setAimFromEvent}
            onResponderRelease={(event) => {
              const nextX = clampKikkiDropX(
                event.nativeEvent.locationX / boardScale,
                currentTier,
              );
              setPreviewX(nextX);
              drop(nextX);
            }}
            onStartShouldSetResponder={() =>
              round.status === 'playing' && !paused
            }
            style={[styles.board, { width: boardWidth, height: boardHeight }]}
            testID="kikki-merge-board"
          >
            <LinearGradient
              colors={['#FFFDF3', '#F4F2D8']}
              pointerEvents="none"
              style={StyleSheet.absoluteFill}
            />
            <View
              pointerEvents="none"
              style={[
                styles.dangerLine,
                {
                  top: KIKKI_MERGE_DANGER_Y * boardScale,
                  borderColor:
                    dangerProgress > 0 ? '#E9684A' : 'rgba(143, 103, 72, 0.3)',
                },
              ]}
            >
              <Text style={styles.dangerLabel}>
                {dangerProgress > 0 ? '위험!' : '여기까지 쌓이면 끝'}
              </Text>
            </View>

            {round.status === 'playing' && !paused ? (
              <>
                <View
                  pointerEvents="none"
                  style={[
                    styles.guide,
                    {
                      left: previewX * boardScale,
                      top: current.radius * 2.4 * boardScale,
                      height:
                        (KIKKI_MERGE_DANGER_Y - current.radius * 2.2) *
                        boardScale,
                    },
                  ]}
                />
                <KikkiOrb
                  preview
                  scale={boardScale}
                  tier={currentTier}
                  x={previewX}
                  y={44}
                />
              </>
            ) : null}

            {orbs.map((orb) => (
              <KikkiOrb
                angle={orb.angle}
                key={orb.id}
                scale={boardScale}
                tier={orb.tier}
                x={orb.x}
                y={orb.y}
              />
            ))}

            {round.status === 'ready' ? (
              <GameCard
                actionLabel="합치기 시작"
                endMascotTier={KIKKI_MERGE_TIERS.length - 1}
                mascotTier={0}
                onAction={start}
                title="아기 끼끼를 챔피언 끼끼로!"
              >
                같은 끼끼가 만나면 성장해요! 잘 조준해서 떨어뜨려 보세요
              </GameCard>
            ) : null}

            {round.status === 'finished' ? (
              <GameCard
                actionLabel="확인"
                actionPending={rewardState.status === 'pending'}
                mascotTier={Math.min(
                  KIKKI_MERGE_TIERS.length - 1,
                  Math.max(0, Math.floor(round.score / 20)),
                )}
                onAction={onBack}
                title={`${round.score}점 달성!`}
                detail={
                  <View style={styles.resultDetail}>
                    <Text style={styles.resultMergeCount}>
                      총 합치기 {round.mergeCount}회
                    </Text>
                    <StageMilestones
                      large
                      stage9Count={stage9Count}
                      stage10Count={stage10Count}
                      stage11Count={stage11Count}
                    />
                  </View>
                }
              >
                {miniGameRewardMessage(rewardState)}
              </GameCard>
            ) : null}

            {paused && round.status === 'playing' ? (
              <GameCard
                actionLabel="계속 합치기"
                mascotTier={currentTier}
                onAction={() => setPaused(false)}
                title="잠시 쉬고 있어요"
              >
                준비되면 이어서 끼끼를 합쳐봐요.
              </GameCard>
            ) : null}
          </View>
        </View>

        <View style={styles.queueBar}>
          <View style={styles.queueCopy}>
            <Text style={styles.queueLabel}>다음 끼끼</Text>
            <Text style={styles.queueName}>{queued.name}</Text>
          </View>
          <View style={[styles.nextBubble, { backgroundColor: queued.color }]}>
            <Image
              accessible={false}
              resizeMode="contain"
              source={stageSource(nextTier)}
              style={styles.nextImage}
            />
          </View>
          <Pressable
            accessibilityRole="button"
            disabled={round.status !== 'playing' || paused || !dropReady}
            onPress={() => drop()}
            style={({ pressed }) => [
              styles.dropButton,
              (round.status !== 'playing' || paused || !dropReady) &&
                styles.dropButtonDisabled,
              pressed && styles.dropButtonPressed,
            ]}
          >
            <Text style={styles.dropButtonText}>
              {dropReady ? '떨어뜨리기' : '합치는 중'}
            </Text>
          </Pressable>
        </View>
      </SafeAreaView>
    </View>
  );
}

function KikkiOrb({
  angle = 0,
  preview = false,
  scale,
  tier,
  x,
  y,
}: {
  angle?: number;
  preview?: boolean;
  scale: number;
  tier: number;
  x: number;
  y: number;
}) {
  const value = KIKKI_MERGE_TIERS[tier] ?? KIKKI_MERGE_TIERS[0];
  const diameter = value.radius * 2 * scale;
  return (
    <View
      pointerEvents="none"
      style={[
        styles.orb,
        {
          width: diameter,
          height: diameter,
          left: x * scale - diameter / 2,
          top: y * scale - diameter / 2,
          borderRadius: diameter / 2,
          borderWidth: Math.max(1, 2 * scale),
          backgroundColor: value.color,
          opacity: preview ? 0.82 : 1,
          transform: [{ rotate: `${angle}rad` }],
        },
      ]}
      testID={preview ? 'kikki-merge-preview' : undefined}
    >
      <Image
        accessible={false}
        resizeMode="contain"
        source={stageSource(tier)}
        style={{ width: diameter * 1.42, height: diameter * 1.42 }}
      />
    </View>
  );
}

function StageMilestones({
  large = false,
  stage9Count,
  stage10Count,
  stage11Count,
}: {
  large?: boolean;
  stage9Count: number;
  stage10Count: number;
  stage11Count: number;
}) {
  return (
    <View
      accessibilityLabel={`9단계 ${stage9Count}개, 10단계 ${stage10Count}개, 11단계 ${stage11Count}개`}
      style={[styles.milestoneRow, large && styles.milestoneRowLarge]}
    >
      {[
        { count: stage9Count, stage: 9, tier: 8 },
        { count: stage10Count, stage: 10, tier: 9 },
        { count: stage11Count, stage: 11, tier: 10 },
      ].map(({ count, stage, tier }) => (
        <View
          key={stage}
          style={[styles.milestoneItem, large && styles.milestoneItemLarge]}
        >
          <Image
            accessible={false}
            resizeMode="contain"
            source={stageSource(tier)}
            style={[styles.milestoneImage, large && styles.milestoneImageLarge]}
            testID={`kikki-merge-stage-${stage}-stat-icon`}
          />
          <Text
            style={[styles.milestoneCount, large && styles.milestoneCountLarge]}
          >
            × {count}
          </Text>
        </View>
      ))}
    </View>
  );
}

function GameCard({
  actionLabel,
  actionPending = false,
  children,
  detail,
  endMascotTier,
  mascotTier,
  onAction,
  title,
}: {
  actionLabel: string;
  actionPending?: boolean;
  children: string;
  detail?: ReactNode;
  endMascotTier?: number;
  mascotTier: number;
  onAction: () => void;
  title: string;
}) {
  const mascotName = KIKKI_MERGE_TIERS[mascotTier]?.name ?? '끼끼';
  const endMascotName =
    endMascotTier === undefined
      ? undefined
      : (KIKKI_MERGE_TIERS[endMascotTier]?.name ?? '끼끼');

  return (
    <View style={styles.overlay} testID="kikki-merge-dialog">
      <View style={styles.card}>
        <View
          accessibilityLabel={
            endMascotName
              ? `${mascotName}에서 ${endMascotName}로 성장`
              : mascotName
          }
          accessibilityRole="image"
          style={styles.cardEvolution}
        >
          <View
            style={[
              styles.cardMascotBubble,
              endMascotName ? styles.cardMascotBubbleSmall : undefined,
              { backgroundColor: KIKKI_MERGE_TIERS[mascotTier]?.color },
            ]}
          >
            <Image
              accessible={false}
              resizeMode="contain"
              source={stageSource(mascotTier)}
              style={[
                styles.cardMascot,
                endMascotName ? styles.cardMascotSmall : undefined,
              ]}
              testID={endMascotName ? 'kikki-merge-intro-baby' : undefined}
            />
          </View>
          {endMascotTier !== undefined ? (
            <>
              <Text accessible={false} style={styles.cardEvolutionArrow}>
                →
              </Text>
              <View
                style={[
                  styles.cardMascotBubble,
                  {
                    backgroundColor: KIKKI_MERGE_TIERS[endMascotTier]?.color,
                  },
                ]}
              >
                <Image
                  accessible={false}
                  resizeMode="contain"
                  source={stageSource(endMascotTier)}
                  style={styles.cardMascot}
                  testID="kikki-merge-intro-champion"
                />
              </View>
            </>
          ) : null}
        </View>
        <Text style={styles.cardTitle}>{title}</Text>
        {detail}
        <Text style={styles.cardBody}>{children}</Text>
        <Pressable
          accessibilityRole="button"
          disabled={actionPending}
          onPress={onAction}
          style={({ pressed }) => [
            styles.cardButton,
            actionPending && styles.cardButtonPending,
            pressed && styles.dropButtonPressed,
          ]}
        >
          <Text style={styles.cardButtonText}>{actionLabel}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function stageSource(tier: number) {
  return kikkiMergeStageSources[tier] ?? kikkiMergeStageSources[0];
}

const styles = StyleSheet.create({
  screen: { flex: 1, overflow: 'hidden', backgroundColor: '#DFF4CB' },
  safeArea: { flex: 1 },
  header: {
    zIndex: 5,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  headerButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 22,
    backgroundColor: 'rgba(255, 255, 255, 0.9)',
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
  milestoneRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: 1,
  },
  milestoneRowLarge: { gap: spacing.sm, marginTop: spacing.xs },
  milestoneItem: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 15,
    backgroundColor: 'rgba(255, 255, 255, 0.58)',
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  milestoneItemLarge: {
    borderRadius: 16,
    backgroundColor: '#FFF7E8',
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  milestoneImage: { width: 30, height: 30 },
  milestoneImageLarge: { width: 52, height: 52 },
  milestoneCount: {
    color: '#6B7B56',
    fontSize: 10,
    fontWeight: '900',
  },
  milestoneCountLarge: { color: colors.text, fontSize: 14 },
  scoreChip: {
    minWidth: 58,
    alignItems: 'center',
    borderRadius: 18,
    backgroundColor: 'rgba(255, 255, 255, 0.9)',
    paddingHorizontal: 10,
    paddingVertical: 5,
    ...shadows.card,
  },
  scoreLabel: { color: colors.textSub, fontSize: 10, fontWeight: '800' },
  score: { color: '#E0783D', fontSize: 18, fontWeight: '900' },
  boardShell: {
    flex: 1,
    minHeight: 0,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
  },
  board: {
    overflow: 'hidden',
    borderRadius: 22,
    borderWidth: 3,
    borderColor: 'rgba(101, 124, 83, 0.45)',
    backgroundColor: '#FFFDF3',
  },
  dangerLine: {
    position: 'absolute',
    right: 0,
    left: 0,
    zIndex: 2,
    borderTopWidth: 2,
    borderStyle: 'dashed',
  },
  dangerLabel: {
    position: 'absolute',
    top: 4,
    right: 8,
    color: '#A15F48',
    fontSize: 10,
    fontWeight: '800',
  },
  guide: {
    position: 'absolute',
    zIndex: 2,
    width: 1,
    borderLeftWidth: 1,
    borderColor: 'rgba(119, 104, 74, 0.28)',
    borderStyle: 'dashed',
  },
  orb: {
    position: 'absolute',
    zIndex: 3,
    alignItems: 'center',
    justifyContent: 'center',
    borderColor: 'rgba(111, 83, 53, 0.24)',
    ...shadows.card,
  },
  queueBar: {
    minHeight: 76,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  queueCopy: { flex: 1 },
  queueLabel: { color: colors.textSub, fontSize: 11, fontWeight: '800' },
  queueName: {
    marginTop: 2,
    color: colors.text,
    fontSize: 14,
    fontWeight: '900',
  },
  nextBubble: {
    width: 48,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    borderRadius: 24,
    borderWidth: 1,
    borderColor: 'rgba(111, 83, 53, 0.2)',
  },
  nextImage: { width: 68, height: 68 },
  dropButton: {
    minWidth: 118,
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 24,
    backgroundColor: '#FF9D47',
    paddingHorizontal: spacing.md,
    ...shadows.card,
  },
  dropButtonDisabled: { backgroundColor: '#CDBFAF', opacity: 0.74 },
  dropButtonPressed: { opacity: 0.75 },
  dropButtonText: { color: '#FFFFFF', fontSize: 15, fontWeight: '900' },
  overlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 10,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(72, 64, 45, 0.22)',
    padding: spacing.xl,
  },
  card: {
    width: '100%',
    maxWidth: 310,
    alignItems: 'center',
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    backgroundColor: 'rgba(255, 255, 255, 0.97)',
    padding: spacing.xl,
    ...shadows.card,
  },
  cardEvolution: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  cardMascotBubble: {
    width: 78,
    height: 78,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    borderRadius: 39,
  },
  cardMascotBubbleSmall: {
    width: 60,
    height: 60,
    borderRadius: 30,
  },
  cardMascot: { width: 108, height: 108 },
  cardMascotSmall: { width: 84, height: 84 },
  cardEvolutionArrow: {
    color: '#E0783D',
    fontSize: 28,
    fontWeight: '900',
  },
  cardTitle: {
    marginTop: spacing.sm,
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
  resultDetail: {
    marginTop: spacing.sm,
    alignItems: 'center',
  },
  resultMergeCount: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '900',
  },
  cardButton: {
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
  cardButtonPending: { opacity: 0.56 },
  cardButtonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '900' },
});
