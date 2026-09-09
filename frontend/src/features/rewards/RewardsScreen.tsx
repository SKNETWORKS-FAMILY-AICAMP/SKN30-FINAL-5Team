import { useCallback, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import type {
  BananaTransactionResponse,
  BananaWalletResponse,
} from '../../api/types';
import { useAsyncAction, useAsyncData } from '../../api/useAsync';
import { imageAssets } from '../../assets';
import {
  Card,
  GradientActionButton,
  InlineFeedback,
} from '../../components/primitives';
import {
  ErrorState,
  LoadingState,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { colors, radii, shadows, spacing } from '../../components/theme';

type RewardsTab = 'wallet' | 'pass';

const PASS_PREVIEW_BENEFITS = [
  '끼끼의 집 전용 테마 예시',
  '주간 리포트 꾸미기 예시',
  '추가 끼끼 반응 예시',
] as const;

export function RewardsScreen({
  api,
  backAccessibilityLabel = '끼끼의 집으로 돌아가기',
  onBack,
}: {
  api: Api;
  backAccessibilityLabel?: string;
  onBack: () => void;
}) {
  const [tab, setTab] = useState<RewardsTab>('wallet');
  const [confirmedTransaction, setConfirmedTransaction] =
    useState<BananaTransactionResponse | null>(null);
  const wallet = useAsyncData<BananaWalletResponse>(
    (signal) => api.getRewards(signal),
    [api],
  );
  const claimRequest = useCallback(() => api.claimDailyReward(), [api]);
  const claim = useAsyncAction(claimRequest);

  const handleClaim = useCallback(async () => {
    const result = await claim.run();
    if (!result) return;
    wallet.setData(result);
    setConfirmedTransaction(result.transaction);
  }, [claim, wallet]);

  return (
    <ScreenShell contentStyle={styles.screenContent}>
      <View style={styles.topRow}>
        <Pressable
          accessibilityLabel={backAccessibilityLabel}
          accessibilityRole="button"
          hitSlop={10}
          onPress={onBack}
          style={({ pressed }) => [styles.back, pressed && styles.pressed]}
          testID="rewards-back"
        >
          <Text style={styles.backText}>‹</Text>
        </Pressable>
        <ScreenHeading
          subtitle="서버에 저장된 바나나와 준비 중인 혜택을 확인해요."
          title="바나나 지갑"
        />
      </View>

      <View accessibilityRole="tablist" style={styles.tabs}>
        <RewardsTabButton
          active={tab === 'wallet'}
          label="바나나 지갑"
          onPress={() => setTab('wallet')}
        />
        <RewardsTabButton
          active={tab === 'pass'}
          label="HELKKI PASS"
          onPress={() => setTab('pass')}
        />
      </View>

      {tab === 'wallet' ? (
        <WalletContent
          claimError={claim.error}
          claimPending={claim.pending}
          confirmedTransaction={confirmedTransaction}
          onClaim={handleClaim}
          onRetry={wallet.reload}
          state={wallet.state}
        />
      ) : (
        <KkikkiPassPreview />
      )}
    </ScreenShell>
  );
}

function RewardsTabButton({
  active,
  label,
  onPress,
}: {
  active: boolean;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={({ pressed }) => [
        styles.tab,
        active && styles.tabActive,
        pressed && styles.pressed,
      ]}
    >
      <Text style={[styles.tabText, active && styles.tabTextActive]}>
        {label}
      </Text>
    </Pressable>
  );
}

function WalletContent({
  claimError,
  claimPending,
  confirmedTransaction,
  onClaim,
  onRetry,
  state,
}: {
  claimError: string | null;
  claimPending: boolean;
  confirmedTransaction: BananaTransactionResponse | null;
  onClaim: () => void;
  onRetry: () => void;
  state:
    | { status: 'loading' }
    | { status: 'error'; message: string; error: unknown }
    | { status: 'ready'; data: BananaWalletResponse };
}) {
  if (state.status === 'loading') {
    return <LoadingState label="바나나 지갑을 불러오는 중이에요" />;
  }

  if (state.status === 'error') {
    return (
      <ErrorState
        message={state.message || '바나나 지갑을 불러오지 못했어요.'}
        onRetry={onRetry}
      />
    );
  }

  const { balance, daily_reward: dailyReward } = state.data;
  const claimLabel = dailyReward.is_claimed
    ? '오늘 보상 받기 완료'
    : dailyReward.is_claimable
      ? `바나나 ${dailyReward.reward_amount}개 받기`
      : '오늘은 받을 수 없어요';

  return (
    <View style={styles.walletSections}>
      <Card style={styles.balanceCard} testID="banana-wallet-balance">
        <View style={styles.balanceCopy}>
          <Text style={styles.eyebrow}>보유 바나나</Text>
          <Text
            accessibilityLabel={`보유 바나나 ${balance}개`}
            style={styles.balance}
          >
            {balance.toLocaleString('ko-KR')}개
          </Text>
        </View>
        <View style={styles.bananaArtFrame}>
          <Image
            accessibilityLabel="바나나"
            resizeMode="contain"
            source={imageAssets.banana}
            style={styles.bananaArt}
          />
        </View>
      </Card>

      <Card style={styles.dailyCard} testID="daily-reward-card">
        <View style={styles.sectionHeadingRow}>
          <View style={styles.sectionHeadingCopy}>
            <Text style={styles.sectionTitle}>오늘의 바나나</Text>
            <Text style={styles.supportingCopy}>
              {dailyReward.is_claimed
                ? '오늘 보상은 이미 지갑에 담겼어요.'
                : dailyReward.is_claimable
                  ? '오늘 한 번 받을 수 있는 보상이에요.'
                  : '받을 수 있는 상태가 되면 여기에 알려드려요.'}
            </Text>
          </View>
          <View
            accessibilityLabel={`오늘의 보상 바나나 ${dailyReward.reward_amount}개`}
            style={styles.rewardAmount}
          >
            <Text style={styles.rewardAmountText}>
              +{dailyReward.reward_amount}
            </Text>
          </View>
        </View>

        {claimError ? (
          <InlineFeedback message={claimError} tone="error" />
        ) : null}

        {confirmedTransaction ? (
          <View
            accessibilityLabel={`오늘의 바나나 ${confirmedTransaction.amount >= 0 ? '지급' : '차감'} ${Math.abs(confirmedTransaction.amount)}개, 거래 후 ${confirmedTransaction.balance_after}개`}
            style={styles.confirmedTransaction}
            testID="banana-transaction-row"
          >
            <Text style={styles.confirmedTransactionText}>
              오늘의 바나나 {confirmedTransaction.amount >= 0 ? '+' : ''}
              {confirmedTransaction.amount.toLocaleString('ko-KR')} · 거래 후{' '}
              {confirmedTransaction.balance_after.toLocaleString('ko-KR')}개
            </Text>
          </View>
        ) : null}

        <GradientActionButton
          disabled={
            claimPending || dailyReward.is_claimed || !dailyReward.is_claimable
          }
          label={claimPending ? '받는 중…' : claimLabel}
          labelStyle={styles.claimLabel}
          onPress={onClaim}
          style={styles.claimButton}
          testID="daily-reward-claim"
        />
      </Card>
    </View>
  );
}

function KkikkiPassPreview() {
  return (
    <View style={styles.passSections} testID="kkikki-pass-preview">
      <Card style={styles.passHero}>
        <Text style={styles.passTitle}>HELKKI PASS</Text>
        <Image
          accessibilityLabel="HELKKI PASS 끼끼"
          resizeMode="contain"
          source={imageAssets.helkkiPass}
          style={styles.passArt}
          testID="helkki-pass-art"
        />
      </Card>

      <Card style={styles.benefitsCard}>
        <Text style={styles.sectionTitle}>혜택</Text>
        <View style={styles.benefitList}>
          {PASS_PREVIEW_BENEFITS.map((benefit) => (
            <View key={benefit} style={styles.benefitRow}>
              <View style={styles.benefitDot} />
              <Text style={styles.benefitText}>{benefit}</Text>
            </View>
          ))}
        </View>
      </Card>

      <InlineFeedback
        message="기능 미리보기 · 혜택은 미확정이며 실제 결제는 지원하지 않아요."
        tone="warning"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screenContent: {
    gap: spacing.lg,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
  },
  back: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 22,
    backgroundColor: colors.surface,
    ...shadows.card,
  },
  backText: {
    marginTop: -3,
    color: colors.text,
    fontSize: 34,
    lineHeight: 38,
  },
  pressed: {
    opacity: 0.76,
  },
  tabs: {
    flexDirection: 'row',
    gap: spacing.sm,
    padding: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.button,
    backgroundColor: colors.canvas,
  },
  tab: {
    minHeight: 44,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.control,
    paddingHorizontal: spacing.sm,
  },
  tabActive: {
    backgroundColor: colors.surface,
    ...shadows.card,
  },
  tabText: {
    color: colors.textSub,
    fontSize: 14,
    fontWeight: '700',
    textAlign: 'center',
  },
  tabTextActive: {
    color: colors.greenText,
  },
  walletSections: {
    gap: spacing.lg,
  },
  balanceCard: {
    minHeight: 166,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    ...shadows.card,
  },
  balanceCopy: {
    flex: 1,
    gap: spacing.sm,
  },
  eyebrow: {
    color: colors.greenText,
    fontSize: 13,
    fontWeight: '700',
  },
  balance: {
    color: colors.text,
    fontSize: 34,
    fontWeight: '800',
    letterSpacing: -1,
  },
  supportingCopy: {
    color: colors.textSub,
    fontSize: 13,
    lineHeight: 19,
  },
  bananaArtFrame: {
    width: 94,
    height: 94,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 47,
    backgroundColor: colors.canvas,
  },
  bananaArt: {
    width: 70,
    height: 70,
  },
  dailyCard: {
    gap: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.card,
  },
  sectionHeadingRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
  },
  sectionHeadingCopy: {
    flex: 1,
    gap: spacing.xs,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '800',
  },
  rewardAmount: {
    minWidth: 54,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    backgroundColor: colors.canvas,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  rewardAmountText: {
    color: colors.greenText,
    fontSize: 15,
    fontWeight: '800',
  },
  claimButton: {
    height: 52,
  },
  claimLabel: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '800',
  },
  confirmedTransaction: {
    borderRadius: radii.control,
    backgroundColor: colors.successSurface,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  confirmedTransactionText: {
    color: colors.greenText,
    fontSize: 13,
    fontWeight: '700',
  },
  passSections: {
    gap: spacing.lg,
  },
  passHero: {
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    ...shadows.card,
  },
  passTitle: {
    color: colors.text,
    fontSize: 28,
    fontWeight: '800',
  },
  /**
   * A fixed height rather than the source's aspect ratio: at full card width
   * the artwork alone ran past 270px and left the card looking empty. `contain`
   * keeps the whole drawing inside this box on every screen width.
   */
  passArt: {
    width: '100%',
    height: 176,
  },
  benefitsCard: {
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  benefitList: {
    gap: spacing.md,
    marginTop: spacing.sm,
  },
  benefitRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  benefitDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.primary,
  },
  benefitText: {
    flex: 1,
    color: colors.text,
    fontSize: 14,
    lineHeight: 20,
  },
});
