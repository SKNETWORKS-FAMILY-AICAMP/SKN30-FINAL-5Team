import { useEffect, useRef, useState } from 'react';

import { createIdempotencyKey } from '../../api/client';
import type { Api } from '../../api/endpoints';
import type {
  WeeklyPlanRevisionResponse,
  WeeklyReportResponse,
  WeekResponse,
} from '../../api/types';
import { useAsyncAction } from '../../api/useAsync';
import { assertReportMatchesWeek } from './weeklyReportModel';

/** Mount once per report, after the selected closed report has loaded. */
export function useWeeklyReportApplication({
  api,
  report,
  week,
  nextWeekStart,
  existingPlan,
  onPlanRevisionChange,
}: {
  api: Api;
  report: WeeklyReportResponse;
  week: WeekResponse;
  nextWeekStart: string | null;
  existingPlan: WeeklyPlanRevisionResponse | null;
  onPlanRevisionChange?: (revision: WeeklyPlanRevisionResponse) => void;
}) {
  const savedReport = useRef(report);
  const [revision, setRevision] = useState(existingPlan);
  const [acknowledged, setAcknowledged] = useState(
    report.status_code === 'ACKNOWLEDGED',
  );
  const intent = useRef<{ key: string; timestamp: string } | null>(null);
  const active = useRef(true);
  const started = useRef(false);

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  const { run, pending, error } = useAsyncAction(async () => {
    if (savedReport.current.status_code !== 'ACKNOWLEDGED') {
      intent.current ??= {
        key: createIdempotencyKey(),
        timestamp: new Date().toISOString(),
      };
      const result = await api.acknowledgeWeeklyReport(
        report.report_id,
        intent.current.timestamp,
        intent.current.key,
      );
      assertReportMatchesWeek(week, result, 'ACKNOWLEDGED');
      if (
        result.report_id !== report.report_id ||
        result.acknowledged_at === null
      ) {
        throw new Error(
          '리포트 확인 응답이 일치하지 않습니다. 다시 시도해주세요.',
        );
      }
      savedReport.current = result;
      if (!active.current) return;
      setAcknowledged(true);
    }

    if (
      !active.current ||
      nextWeekStart === null ||
      onPlanRevisionChange === undefined ||
      existingPlan !== null ||
      revision !== null
    ) {
      return;
    }

    // Report IDs are server UUIDs. One initial-plan intent per report keeps
    // retries/re-entry idempotent even if a successful response was lost.
    const result = await api.createInitialWeeklyPlan(
      nextWeekStart,
      report.report_id,
    );
    if (
      result.week_start !== nextWeekStart ||
      result.source_weekly_report_id !== report.report_id
    ) {
      throw new Error(
        '다음 주 계획 정보가 리포트와 일치하지 않습니다. 다시 시도해주세요.',
      );
    }
    if (!active.current) return;
    setRevision(result);
    onPlanRevisionChange(result);
  });

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void run();
  }, [run]);

  return {
    acknowledged,
    revision: existingPlan ?? revision,
    pending,
    error,
    retry: run,
  };
}
