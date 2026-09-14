import { Button } from '../components/primitives';
import {
  ErrorState,
  LoadingState,
  ScreenHeading,
  ScreenShell,
} from '../components/states/ScreenState';

export function ProfileLoadingScreen() {
  return (
    <ScreenShell>
      <ScreenHeading title="불러오는 중" />
      <LoadingState label="계정 정보를 확인하고 있어요" />
    </ScreenShell>
  );
}

export function ProfileErrorScreen({
  message,
  onRetry,
  onSignOut,
}: {
  message: string;
  onRetry: () => void;
  onSignOut: () => void;
}) {
  return (
    <ScreenShell>
      <ScreenHeading title="연결하지 못했어요" />
      <ErrorState message={message} onRetry={onRetry} />
      <Button label="로그아웃" tone="secondary" onPress={onSignOut} />
    </ScreenShell>
  );
}
