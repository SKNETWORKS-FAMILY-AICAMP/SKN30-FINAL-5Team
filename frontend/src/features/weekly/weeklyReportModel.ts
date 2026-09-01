import { ApiError } from '../../api/errors';
import type { WeeklyReportResponse, WeekResponse } from '../../api/types';

export type WeeklyReportAvailability =
  | 'IN_PROGRESS'
  | 'AVAILABLE_TO_CREATE'
  | 'GENERATED'
  | 'ACKNOWLEDGED'
  | 'FAILED';

function contractError(): ApiError {
  return new ApiError({
    kind: 'server',
    code: 'WEEKLY_REPORT_RESPONSE_MISMATCH',
    status: 0,
    message: '선택한 주의 리포트 정보가 일치하지 않습니다. 다시 불러와주세요.',
  });
}

function addDays(localDate: string, amount: number): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(localDate);
  if (match === null) return null;
  const date = new Date(
    Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])),
  );
  date.setUTCDate(date.getUTCDate() + amount);
  return [
    date.getUTCFullYear(),
    String(date.getUTCMonth() + 1).padStart(2, '0'),
    String(date.getUTCDate()).padStart(2, '0'),
  ].join('-');
}

export function assertWeekMatchesSelection(
  selectedWeekStart: string,
  week: WeekResponse,
): void {
  if (
    week.week_start !== selectedWeekStart ||
    addDays(week.week_start, 6) !== week.week_end
  ) {
    throw contractError();
  }
  weeklyReportAvailability(week);
}

export function weeklyReportAvailability(
  week: WeekResponse,
): WeeklyReportAvailability {
  const hasReportId = week.report_id !== null;
  const hasReportStatus = week.report_status_code !== null;

  if (hasReportId !== hasReportStatus) {
    throw contractError();
  }

  if (week.status_code === 'OPEN') {
    if (hasReportId || hasReportStatus) {
      throw contractError();
    }
    return 'IN_PROGRESS';
  }

  if (!hasReportId) return 'AVAILABLE_TO_CREATE';
  if (week.report_status_code === 'GENERATED') return 'GENERATED';
  if (week.report_status_code === 'ACKNOWLEDGED') return 'ACKNOWLEDGED';
  if (week.report_status_code === 'FAILED') return 'FAILED';
  throw contractError();
}

export function assertReportMatchesWeek(
  week: WeekResponse,
  report: WeeklyReportResponse,
  expectedStatus?: WeeklyReportResponse['status_code'],
): void {
  if (
    report.week_start !== week.week_start ||
    report.week_end !== week.week_end ||
    (expectedStatus !== undefined && report.status_code !== expectedStatus)
  ) {
    throw contractError();
  }
}
