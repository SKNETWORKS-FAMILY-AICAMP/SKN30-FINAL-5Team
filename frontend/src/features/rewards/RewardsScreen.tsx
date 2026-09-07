import { useCallback, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import type { Api } from '../../api/endpoints';
import type {
  BananaTransactionResponse,
  BananaWalletResponse,
} from '../../api/types';
import { useAsyncAction, useAsyncData } from '../../api/useAsync';
import { imageAssets } from '../../assets';
import { Button, Card, InlineFeedback } from '../../components/primitives';
import {
  EmptyState,
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

const TRANSACTION_LABELS: Record<
  BananaTransactionResponse['transaction_type'],
  string
> = {
  DAILY_REWARD: '오늘의 바나나',
  WORKOUT_COMPLETED: '운동 완료 보상',
  WORKOUT_PARTIAL: '운동 참여 보상',
  WORKOUT_SAFETY_STOPPED: '안전 중단 참여 보상',
  WORKOUT_DAILY_QUEST: '오늘의 운동 퀘스트',
  HOUSE_FEED: '끼끼에게 바나나 주기',
  HOUSE_ITEM_PURCHASE: '집 꾸미기 아이템',
};

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
  const [confirmedTransactions, setConfirmedTransactions] = useState<
    BananaTransactionResponse[]
  >([]);
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
    setConfirmedTransactions((current) => {
      if (
        current.some(
          (entry) => entry.transaction_id === result.transaction.transaction_id,
        )
      ) {
        return current;
      }
      return [result.transaction, ...current];
    });
  }, [claim, wallet]);

  return (
    <ScreenShell bands contentStyle={styles.screenContent}>
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
          onBand
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
          label="끼끼패스 미리보기"
          onPress={() => setTab('pass')}
        />
      </View>

      {tab === 'wallet' ? (
        <WalletContent
          claimError={claim.error}
          claimPending={claim.pending}
          confirmedTransactions={confirmedTransactions}
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
  confirmedTransactions,
  onClaim,
  onRetry,
  state,
}: {
  claimError: string | null;
  claimPending: boolean;
  confirmedTransactions: BananaTransactionResponse[];
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
          <Text style={styles.supportingCopy}>
            현재 잔액은 서버 지갑을 기준으로 표시해요.
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

        <Button
          disabled={
            claimPending || dailyReward.is_claimed || !dailyReward.is_claimable
          }
          label={claimPending ? '받는 중…' : claimLabel}
          onPress={onClaim}
          testID="daily-reward-claim"
        />
      </Card>

      <View style={styles.historySection}>
        <Text style={styles.sectionTitle}>이번 화면에서 확인된 내역</Text>
        <Text style={styles.supportingCopy}>
          서버가 이번 화면에 응답한 거래만 보여드려요.
        </Text>
        {confirmedTransactions.length === 0 ? (
          <EmptyState message="이번 화면에서 새로 확인된 거래가 없어요." />
        ) : (
          confirmedTransactions.map((transaction) => (
            <TransactionRow
              key={transaction.transaction_id}
              transaction={transaction}
            />
          ))
        )}
      </View>
    </View>
  );
}

function TransactionRow({
  transaction,
}: {
  transaction: BananaTransactionResponse;
}) {
  const isCredit = transaction.amount >= 0;
  return (
    <Card style={styles.transactionRow} testID="banana-transaction-row">
      <View style={styles.transactionCopy}>
        <Text style={styles.transactionTitle}>
          {TRANSACTION_LABELS[transaction.transaction_type]}
        </Text>
        <Text style={styles.transactionMeta}>
          거래 후 {transaction.balance_after.toLocaleString('ko-KR')}개
        </Text>
      </View>
      <Text
        style={[styles.transactionAmount, !isCredit && styles.transactionDebit]}
      >
        {isCredit ? '+' : ''}
        {transaction.amount.toLocaleString('ko-KR')}
      </Text>
    </Card>
  );
}

function KkikkiPassPreview() {
  return (
    <View style={styles.passSections} testID="kkikki-pass-preview">
      <Card style={styles.passHero}>
        <View style={styles.previewBadge}>
          <Text style={styles.previewBadgeText}>기능 미리보기</Text>
        </View>
        <Text style={styles.passTitle}>끼끼패스</Text>
        <Text style={styles.passDescription}>
          끼끼와 운동을 더 즐겁게 이어가는 모습을 살펴보는 목업이에요. 실제
          구독이나 결제는 아직 제공하지 않아요.
        </Text>
      </Card>

      <Card style={styles.benefitsCard}>
        <Text style={styles.sectionTitle}>혜택 표현 예시</Text>
        <Text style={styles.supportingCopy}>
          아래 내용은 화면 검토용이며 실제 혜택으로 확정되지 않았어요.
        </Text>
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
        message="이 화면에서는 결제 수단을 입력받거나 구매를 시도하지 않아요."
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
    borderRadius: radii.button,
    backgroundColor: colors.surfaceAlt,
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
    backgroundColor: colors.successSurface,
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
    backgroundColor: colors.surface,
  },
  bananaArt: {
    width: 70,
    height: 70,
  },
  dailyCard: {
    gap: spacing.lg,
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
    borderRadius: 999,
    backgroundColor: colors.successSurface,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  rewardAmountText: {
    color: colors.greenText,
    fontSize: 15,
    fontWeight: '800',
  },
  historySection: {
    gap: spacing.sm,
  },
  transactionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
  },
  transactionCopy: {
    flex: 1,
    gap: 2,
  },
  transactionTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  transactionMeta: {
    color: colors.textSub,
    fontSize: 12,
  },
  transactionAmount: {
    color: colors.greenText,
    fontSize: 16,
    fontWeight: '800',
  },
  transactionDebit: {
    color: colors.warningText,
  },
  passSections: {
    gap: spacing.lg,
  },
  passHero: {
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.successBorder,
    backgroundColor: colors.successSurface,
    ...shadows.card,
  },
  previewBadge: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  previewBadgeText: {
    color: colors.greenText,
    fontSize: 12,
    fontWeight: '800',
  },
  passTitle: {
    color: colors.text,
    fontSize: 28,
    fontWeight: '800',
  },
  passDescription: {
    color: colors.textSub,
    fontSize: 15,
    lineHeight: 23,
  },
  benefitsCard: {
    gap: spacing.sm,
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
