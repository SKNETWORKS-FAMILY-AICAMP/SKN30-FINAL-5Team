import { decisionReasonLabel } from '../../api/labels';
import type {
  DailyContextResponse,
  DecisionResponse,
  PainAreaInput,
} from '../../api/types';
import {
  HOME_DEFAULT_CHECKIN,
  checkinFromContext,
  type HomeAvailabilitySlot,
  type HomeCheckin,
  type HomePreviewState,
} from './homeModel';
import { uniqueText } from './homeRevisionNotice';

export type TimePickerTarget = {
  field: keyof HomeAvailabilitySlot;
  index: number;
};

export function buildInitialCheckin(
  apiMode: boolean,
  context: DailyContextResponse | null,
  persistentPains: readonly PainAreaInput[],
  locationCodes: readonly string[],
  initialState: HomePreviewState,
): HomeCheckin {
  if (apiMode) {
    return checkinFromContext(context, persistentPains, locationCodes);
  }
  if (initialState === 'adjusted') {
    return {
      ...HOME_DEFAULT_CHECKIN,
      pains: { KNEE: 3 },
      redFlagPresent: false,
      workoutMinutes: '40',
    };
  }
  if (initialState === 'pre-checkin' || initialState === 'checkin') {
    return { ...HOME_DEFAULT_CHECKIN, pains: {} };
  }
  return {
    ...HOME_DEFAULT_CHECKIN,
    pains: {},
    redFlagPresent: false,
    workoutMinutes: '40',
  };
}

export function routineNotesFromDecision(
  decision: DecisionResponse | null,
): string[] | undefined {
  return decision === null
    ? undefined
    : [decision.summary, decision.guidance?.message].filter(
        (note): note is string => Boolean(note),
      );
}

export function recommendationReasonsFromDecision(
  decision: DecisionResponse | null,
): string[] {
  return decision === null
    ? []
    : uniqueText([
        ...decision.reason_codes.map(decisionReasonLabel),
        ...(decision.adjustment_reason_codes ?? []).map(decisionReasonLabel),
        ...(decision.safety_summary?.reason_codes ?? []).map(
          decisionReasonLabel,
        ),
      ]);
}
