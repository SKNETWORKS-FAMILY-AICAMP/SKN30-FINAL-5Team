import { localDateString, weekStartString } from '../src/api/useAsync';

describe('timezone-aware API dates', () => {
  const instant = new Date('2026-08-17T15:30:00.000Z');

  it('uses the profile timezone for daily resource keys', () => {
    expect(localDateString(instant, 'Asia/Seoul')).toBe('2026-08-18');
    expect(localDateString(instant, 'America/Los_Angeles')).toBe('2026-08-17');
  });

  it('calculates Monday from the date in the profile timezone', () => {
    expect(weekStartString(instant, 'Asia/Seoul')).toBe('2026-08-17');
    expect(weekStartString(instant, 'America/Los_Angeles')).toBe('2026-08-17');
  });
});
