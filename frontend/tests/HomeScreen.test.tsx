/**
 * The home screen's rendering contract.
 *
 * Home is the entry point, so the invariants that used to live on separate
 * check-in and decision screens are verified here: one final routine, a rest
 * opt-out that survives a safety veto, a serious tone for a stop instruction,
 * and no client-side substitute for anything the server decided.
 */

import { describe, expect, it, jest } from '@jest/globals';
import { fireEvent, render, screen } from '@testing-library/react-native';

import type { DecisionResponse } from '../src/api/types';
import {
  HomeScreen,
  type HomeScreenProps,
} from '../src/features/home/HomeScreen';
import { homePreviewProps } from '../src/features/preview/homePreview';

function props(overrides: Partial<HomeScreenProps> = {}): HomeScreenProps {
  return { ...homePreviewProps('routine'), ...overrides };
}

function decisionFrom(overrides: Partial<DecisionResponse>): DecisionResponse {
  const base = homePreviewProps('routine').decision;
  if (!base) {
    throw new Error('routine preview must carry a decision');
  }
  return { ...base, ...overrides };
}

describe('HomeScreen', () => {
  it('shows one final routine, its rest opt-out, and no plan alternatives', () => {
    render(<HomeScreen {...props()} />);

    expect(screen.getByText('상체 근력 루틴')).toBeOnTheScreen();
    expect(screen.getAllByText('오늘의 운동')).toHaveLength(1);
    expect(screen.getByText('오늘은 쉬기')).toBeOnTheScreen();
    // Internal candidates must never appear as public plan alternatives.
    expect(screen.queryByText(/원래 루틴/)).toBeNull();
    expect(screen.queryByText(/가벼운 루틴/)).toBeNull();
  });

  it('keeps the rest opt-out reachable when safety blocked the plan', () => {
    render(
      <HomeScreen
        {...props({
          decision: decisionFrom({
            safety_status_code: 'BLOCKED',
            action_code: 'REST',
            final_plan: null,
            options: [
              {
                option_id: 'option-rest',
                option_code: 'REST',
                action_code: 'REST',
                plan_id: null,
                selectable: true,
                blocked_reason_code: null,
              },
            ],
            summary: '오늘은 운동을 쉬어주세요.',
          }),
        })}
      />,
    );

    expect(screen.queryByText('운동 시작하기  ›')).toBeNull();
    expect(screen.getByText('오늘은 쉬기')).toBeOnTheScreen();
    expect(screen.getByText('오늘은 운동을 쉬어주세요.')).toBeOnTheScreen();
    expect(
      screen.getByText('오늘은 운동 계획을 제공하지 않아요'),
    ).toBeOnTheScreen();
  });

  it('shows a serious notice and no options for STOP_AND_SEEK_HELP', () => {
    render(
      <HomeScreen
        {...props({
          decision: decisionFrom({
            safety_status_code: 'BLOCKED',
            action_code: 'STOP_AND_SEEK_HELP',
            final_plan: null,
            options: [],
            guidance: {
              code: 'STOP_AND_SEEK_HELP',
              title: '운동을 즉시 중단해주세요.',
              message: '지역 응급의료 도움을 요청하세요.',
              tone_code: 'SERIOUS',
            },
          }),
        })}
      />,
    );

    expect(screen.getByText('운동을 즉시 중단해주세요.')).toBeOnTheScreen();
    expect(screen.queryByText('운동 시작하기  ›')).toBeNull();
    expect(screen.queryByText('오늘은 쉬기')).toBeNull();
  });

  it('disables a start the server marked non-selectable', () => {
    render(
      <HomeScreen
        {...props({
          decision: decisionFrom({
            options: [
              {
                option_id: 'option-routine',
                option_code: 'FINAL_ROUTINE',
                action_code: 'KEEP',
                plan_id: 'plan-1',
                selectable: false,
                blocked_reason_code: 'SAFETY_VETO',
              },
            ],
          }),
        })}
      />,
    );

    const button = screen.getByRole('button', { name: '운동 시작하기  ›' });
    expect(button.props.accessibilityState.disabled).toBe(true);
    expect(
      screen.getByText(/지금은 시작할 수 없는 루틴이에요/),
    ).toBeOnTheScreen();
  });

  it('shows the adjustment as part of the one routine, not as a choice', () => {
    render(<HomeScreen {...homePreviewProps('adjusted')} />);

    expect(
      screen.getByText(/요청한 시간은 그대로 두고 세트와 강도만 조정했어요./),
    ).toBeOnTheScreen();
    expect(screen.getAllByText('오늘의 운동')).toHaveLength(1);
    expect(screen.queryByRole('radio')).toBeNull();
  });

  it('withholds every workout prompt once the user chose rest', () => {
    render(<HomeScreen {...props({ restToday: true })} />);

    expect(screen.getByText('오늘은 휴식하기로 했어요')).toBeOnTheScreen();
    expect(screen.queryByText('오늘 루틴 체크인🍌')).toBeNull();
    expect(screen.queryByText('운동 시작하기  ›')).toBeNull();
    expect(screen.queryByText('오늘은 쉬기')).toBeNull();
  });

  it('collects the safety inputs the decision needs in the check-in sheet', () => {
    const onSubmitCheckin = jest.fn();
    render(
      <HomeScreen
        {...props({ decision: null, context: null, onSubmitCheckin })}
      />,
    );

    fireEvent.press(screen.getByRole('button', { name: '오늘 루틴 체크인' }));
    expect(
      screen.getByRole('header', { name: '오늘 컨디션 체크' }),
    ).toBeOnTheScreen();

    // The adverse-reaction group is what a safety veto is decided from; it must
    // be present on the only check-in surface the product has.
    expect(screen.getByText('이런 증상이 있나요?')).toBeOnTheScreen();
    expect(screen.getByText('가슴 압박감 또는 통증')).toBeOnTheScreen();

    // A discomfort is only recorded once its severity is chosen.
    fireEvent.press(screen.getByRole('button', { name: '무릎' }));
    fireEvent.press(screen.getByRole('button', { name: '심함' }));
    fireEvent.press(screen.getByRole('button', { name: '체크인 !' }));

    expect(onSubmitCheckin).toHaveBeenCalledWith(
      expect.objectContaining({
        fatigueLevelCode: 'MODERATE',
        discomforts: { KNEE: 'SEVERE' },
        adverseReactionCodes: [],
      }),
    );
  });

  it('does not let the edit sheet author exercises', () => {
    const onSubmitUserEdits = jest.fn();
    render(
      <HomeScreen {...props({ previewState: 'editing', onSubmitUserEdits })} />,
    );

    expect(
      screen.getByRole('header', { name: '오늘의 운동 수정' }),
    ).toBeOnTheScreen();
    // Exercise rows are read-only: the contract refuses arbitrary edits.
    expect(screen.queryByLabelText('푸시업 운동명')).toBeNull();

    fireEvent.press(screen.getByRole('button', { name: 'GYM' }));
    fireEvent.press(screen.getByRole('button', { name: '저장하기' }));

    expect(onSubmitUserEdits).toHaveBeenCalledWith({
      routineId: '11111111-1111-4111-8111-111111111111',
      locationCode: 'GYM',
    });
  });

  it('shows the remaining coordinator revisions the server reported', () => {
    render(
      <HomeScreen
        {...props({
          planRevision: {
            revision_id: 'revision-1',
            week_start: '2026-08-10',
            week_end: '2026-08-16',
            revision_sequence: 2,
            ai_revision_count: 1,
            source_code: 'AI',
            source_weekly_report_id: null,
            safety_status_code: 'PASS',
            routine: null,
            selected_location_code: 'HOME',
            finalized: false,
            finalized_at: null,
            revision_reason_codes: [],
            finalization_reason_codes: [],
            created_at: '2026-08-11T09:00:00+09:00',
          },
        })}
      />,
    );

    expect(screen.getByText('↻  다른 루틴 · 1회 남음')).toBeOnTheScreen();
  });
});
