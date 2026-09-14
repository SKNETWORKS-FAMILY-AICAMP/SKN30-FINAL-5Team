import { describe, expect, it, jest } from '@jest/globals';
import { act, fireEvent, render, screen } from '@testing-library/react-native';

import type { Api } from '../src/api/endpoints';
import { ApiError } from '../src/api/errors';
import type {
  BananaWalletResponse,
  DailyRewardClaimResponse,
} from '../src/api/types';
import { RewardsScreen } from '../src/features/rewards/RewardsScreen';

const wallet: BananaWalletResponse = {
  balance: 42,
  daily_reward: {
    local_date: '2026-09-07',
    reward_amount: 15,
    is_claimable: true,
    is_claimed: false,
    claimed_at: null,
  },
};

const claimed: DailyRewardClaimResponse = {
  balance: 57,
  daily_reward: {
    ...wallet.daily_reward,
    is_claimable: false,
    is_claimed: true,
    claimed_at: '2026-09-07T14:00:00+09:00',
  },
  transaction: {
    transaction_id: 'transaction-1',
    transaction_type: 'DAILY_REWARD',
    amount: 15,
    balance_after: 57,
    created_at: '2026-09-07T14:00:00+09:00',
  },
};

function rewardsApi(overrides: Partial<Api> = {}): Api {
  return {
    getRewards: jest.fn(async () => wallet),
    claimDailyReward: jest.fn(async () => claimed),
    ...overrides,
  } as unknown as Api;
}

describe('RewardsScreen', () => {
  it('shows loading, then the server wallet', async () => {
    let resolveWallet!: (value: BananaWalletResponse) => void;
    const api = rewardsApi({
      getRewards: jest.fn(
        () =>
          new Promise<BananaWalletResponse>((resolve) => {
            resolveWallet = resolve;
          }),
      ),
    });

    render(<RewardsScreen api={api} onBack={jest.fn()} />);

    expect(screen.getByText('바나나 지갑을 불러오는 중이에요')).toBeTruthy();

    await act(async () => resolveWallet(wallet));

    expect(screen.getByLabelText('보유 바나나 42개')).toBeTruthy();
    expect(screen.getByText('바나나 15개 받기')).toBeTruthy();
    expect(
      screen.getByText(
        '운동 바나나는 목표 시간의 50% 이상 운동했을 때 받을 수 있어요.',
      ),
    ).toBeTruthy();
  });

  it('claims the daily reward through the API and shows the new balance', async () => {
    const claimDailyReward = jest.fn(async () => claimed);
    render(
      <RewardsScreen
        api={rewardsApi({ claimDailyReward })}
        onBack={jest.fn()}
      />,
    );

    await screen.findByLabelText('보유 바나나 42개');
    fireEvent.press(screen.getByTestId('daily-reward-claim'));

    expect(await screen.findByLabelText('보유 바나나 57개')).toBeTruthy();
    expect(claimDailyReward).toHaveBeenCalledTimes(1);
    expect(screen.getByText('오늘 보상 받기 완료')).toBeTruthy();
    expect(screen.getByTestId('banana-transaction-row')).toHaveProp(
      'accessibilityLabel',
      '오늘의 바나나 지급 15개, 거래 후 57개',
    );
    expect(screen.getByText('오늘의 바나나 +15 · 거래 후 57개')).toBeTruthy();
  });

  it('shows the balance error and retries the wallet request', async () => {
    const getRewards = jest
      .fn<Api['getRewards']>()
      .mockRejectedValueOnce(
        new ApiError({
          kind: 'network',
          code: 'NETWORK_UNAVAILABLE',
          status: 0,
          message: '네트워크에 연결하지 못했습니다.',
        }),
      )
      .mockResolvedValueOnce(wallet);

    render(
      <RewardsScreen api={rewardsApi({ getRewards })} onBack={jest.fn()} />,
    );

    expect(
      await screen.findByText('네트워크에 연결하지 못했습니다.'),
    ).toBeTruthy();

    fireEvent.press(screen.getByText('다시 시도'));
    expect(await screen.findByLabelText('보유 바나나 42개')).toBeTruthy();
    expect(getRewards).toHaveBeenCalledTimes(2);
  });

  it('marks HELKKI PASS as a non-purchasable mockup', async () => {
    const onBack = jest.fn();
    render(<RewardsScreen api={rewardsApi()} onBack={onBack} />);

    await screen.findByLabelText('보유 바나나 42개');
    fireEvent.press(screen.getAllByText('HELKKI PASS')[0]);

    expect(screen.getByTestId('kkikki-pass-preview')).toBeTruthy();
    expect(screen.getByTestId('helkki-pass-art')).toBeTruthy();
    expect(screen.getByText('혜택')).toBeTruthy();
    expect(
      screen.getByText(
        '기능 미리보기 · 혜택은 미확정이며 실제 결제는 지원하지 않아요.',
      ),
    ).toBeTruthy();
    expect(screen.queryByText('구매하기')).toBeNull();
    expect(screen.queryByText('결제하기')).toBeNull();

    fireEvent.press(screen.getByLabelText('끼끼의 집으로 돌아가기'));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
