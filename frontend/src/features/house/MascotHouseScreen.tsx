/**
 * 끼끼의 집 — the mascot's home, showing the user's real standing.
 *
 * This API container fills the map-style house screen from the server: the
 * active routine and the current week's target and status.
 *
 * The mascot reacts to progress but never to a shortfall. A missed or
 * unfinished week is a learning signal, so the copy stays level and no
 * disappointed state exists here.
 */

import type { Api } from '../../api/endpoints';
import { isApiError } from '../../api/errors';
import type { RoutineResponse, WeekResponse } from '../../api/types';
import {
  localDateString,
  useAsyncData,
  weekStartString,
} from '../../api/useAsync';
import type { TabId } from '../../components/brand/BrandChrome';
import {
  ErrorState,
  LoadingState,
  ScreenHeading,
  ScreenShell,
} from '../../components/states/ScreenState';
import { HomeBottomNavigation } from '../home/HomeScreen';
import { MapHomeScreen } from '../home/MapHomeScreen';

type HouseData = {
  routine: RoutineResponse | null;
  week: WeekResponse | null;
};

export function MascotHouseScreen({
  api,
  onNavigate,
  timeZone,
}: {
  api: Api;
  nickname: string;
  onNavigate: (tab: TabId) => void;
  timeZone?: string;
}) {
  const now = new Date();
  const localDate = localDateString(now, timeZone);
  const weekStart = weekStartString(now, timeZone);

  const { state, reload } = useAsyncData<HouseData>(
    async (signal) => {
      const routine = await api
        .getCurrentRoutine(localDate, signal)
        .catch((error: unknown) => {
          if (isApiError(error) && error.kind === 'notFound') {
            return null;
          }
          throw error;
        });
      const week = await api.getWeek(weekStart, signal).catch(() => null);
      return { routine, week };
    },
    [api, localDate, weekStart],
  );

  const tabBar = (
    <HomeBottomNavigation activeTab="house" onNavigate={onNavigate} />
  );

  if (state.status === 'loading') {
    return (
      <ScreenShell bands tallBands footer={tabBar}>
        <ScreenHeading title="끼끼의 집" onBand />
        <LoadingState />
      </ScreenShell>
    );
  }

  if (state.status === 'error') {
    return (
      <ScreenShell bands tallBands footer={tabBar}>
        <ScreenHeading title="끼끼의 집" onBand />
        <ErrorState message={state.message} onRetry={reload} />
      </ScreenShell>
    );
  }

  const { routine, week } = state.data;

  return (
    <MapHomeScreen
      onNavigateTab={onNavigate}
      previewState="routine"
      routine={routine}
      week={week}
    />
  );
}
