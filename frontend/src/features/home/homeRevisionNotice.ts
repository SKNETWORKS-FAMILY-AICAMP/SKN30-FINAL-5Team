import { planRevisionReasonLabel } from '../../api/labels';
import type { WeeklyPlanRevisionResponse } from '../../api/types';

type RevisionNotice = {
  serious: boolean;
  text: string;
  title: string;
};

export function uniqueText(
  values: readonly (string | null | undefined)[],
): string[] {
  return Array.from(
    new Set(values.filter((value): value is string => Boolean(value))),
  );
}

export function revisionNotice(
  revision: WeeklyPlanRevisionResponse | null,
): RevisionNotice | null {
  if (revision === null) {
    return null;
  }
  const reasons = uniqueText([
    ...revision.revision_reason_codes.map(planRevisionReasonLabel),
    ...revision.finalization_reason_codes.map(planRevisionReasonLabel),
  ]);
  const text = reasons.join(' ') || '서버가 루틴 조정 결과를 확인했어요.';
  switch (revision.safety_status_code) {
    case 'NEEDS_INPUT':
      return {
        serious: false,
        text:
          reasons.join(' ') ||
          '루틴을 조정하려면 상태를 조금 더 확인해야 해요.',
        title: '추가 확인이 필요해요',
      };
    case 'BLOCKED':
      return {
        serious: true,
        text:
          reasons.join(' ') || '안전 기준에 따라 이 루틴을 진행하지 않아요.',
        title: '안전하게 진행할 수 없어요',
      };
    case 'FAILED':
      return {
        serious: true,
        text:
          reasons.join(' ') ||
          '안전 확인을 완료하지 못해 루틴을 적용하지 않았어요.',
        title: '루틴을 적용하지 않았어요',
      };
    case 'REVISE':
      return {
        serious: false,
        text,
        title: '안전 기준에 맞춰 조정했어요',
      };
    case 'PASS':
    default:
      return revision.source_code === 'INITIAL'
        ? null
        : { serious: false, text, title: '루틴 조정을 반영했어요' };
  }
}
