export type MiniGameRewardState =
  | { status: 'idle' | 'pending' | 'claimed_today' | 'unavailable' }
  | { status: 'settled'; amount: number };

export const IDLE_MINI_GAME_REWARD_STATE: MiniGameRewardState = {
  status: 'idle',
};

/** Shared result copy so every mini-game explains the one daily bonus alike. */
export function miniGameRewardMessage(state: MiniGameRewardState): string {
  switch (state.status) {
    case 'pending':
      return '오늘의 바나나 보너스를 확인하고 있어요.';
    case 'settled':
      return `바나나 보너스 ${state.amount}개를 받았어요!`;
    case 'claimed_today':
      return '오늘의 바나나 보너스는 이미 받았어요. 게임은 계속 즐길 수 있어요!';
    case 'unavailable':
      return '바나나 보너스를 확인하지 못했어요. 게임은 계속 즐길 수 있어요!';
    default:
      return '오늘 처음 완료한 게임에서 바나나 보너스를 받을 수 있어요!';
  }
}
