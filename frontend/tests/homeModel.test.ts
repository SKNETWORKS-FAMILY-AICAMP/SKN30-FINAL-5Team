import {
  availabilitySlotsForRequest,
  validateAvailabilitySlots,
} from '../src/features/home/homeModel';

describe('Home check-in availability', () => {
  it('validates complete, ordered, non-overlapping ranges', () => {
    expect(
      validateAvailabilitySlots([
        { startTime: '09:00', endTime: '12:00' },
        { startTime: '13:00', endTime: '15:00' },
      ]),
    ).toBeNull();
    expect(
      validateAvailabilitySlots([
        { startTime: '09:00', endTime: '12:00' },
        { startTime: '12:00', endTime: '15:00' },
      ]),
    ).toBe('가능한 시간대끼리는 겹치거나 맞닿을 수 없어요.');
    expect(
      validateAvailabilitySlots([{ startTime: '15:00', endTime: '13:00' }]),
    ).toBe('종료 시간은 시작 시간보다 뒤여야 해요.');
  });

  it('uses the profile timezone when creating API datetimes', () => {
    expect(
      availabilitySlotsForRequest(
        [
          { startTime: '09:00', endTime: '12:00' },
          { startTime: '13:00', endTime: '15:00' },
        ],
        '2026-08-20',
        'Asia/Seoul',
      ),
    ).toEqual([
      {
        start_at: '2026-08-20T09:00:00+09:00',
        end_at: '2026-08-20T12:00:00+09:00',
      },
      {
        start_at: '2026-08-20T13:00:00+09:00',
        end_at: '2026-08-20T15:00:00+09:00',
      },
    ]);
  });

  it('preserves unanswered and explicitly empty availability values', () => {
    expect(
      availabilitySlotsForRequest(null, '2026-08-20', 'Asia/Seoul'),
    ).toBeNull();
    expect(availabilitySlotsForRequest([], '2026-08-20', 'Asia/Seoul')).toEqual(
      [],
    );
  });

  it('treats an end time of midnight as the next-day boundary', () => {
    expect(
      availabilitySlotsForRequest(
        [{ startTime: '22:00', endTime: '00:00' }],
        '2026-08-20',
        'Asia/Seoul',
      ),
    ).toEqual([
      {
        start_at: '2026-08-20T22:00:00+09:00',
        end_at: '2026-08-21T00:00:00+09:00',
      },
    ]);
  });
});
