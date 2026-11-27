import { countdownParts, countdownUnits } from './event-countdown';
import { ticketTypeLabelKey } from './ticket-type-label';

const NOW = Date.parse('2026-11-21T10:00:00Z');
const at = (ms: number) => new Date(NOW + ms).toISOString();
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

describe('countdownParts', () => {
  it('splits what is left into whole days, hours and minutes, rounding down', () => {
    expect(countdownParts(at(2 * DAY + 3 * HOUR + 4 * MINUTE + 59_000), NOW)).toEqual({
      days: 2,
      hours: 3,
      minutes: 4,
    });
    expect(countdownParts(at(59 * MINUTE + 59_999), NOW)).toEqual({
      days: 0,
      hours: 0,
      minutes: 59,
    });
  });

  it('is 0 minutes for under a minute', () => {
    expect(countdownParts(at(1), NOW)).toEqual({ days: 0, hours: 0, minutes: 0 });
  });

  it('is null at the start, after it, and for an unreadable time', () => {
    expect(countdownParts(at(0), NOW)).toBeNull();
    expect(countdownParts(at(-HOUR), NOW)).toBeNull();
    expect(countdownParts('soon', NOW)).toBeNull();
  });
});

describe('countdownUnits', () => {
  it.each([
    [
      { days: 2, hours: 3, minutes: 4 },
      [
        ['day', 2],
        ['hour', 3],
      ],
    ],
    [{ days: 2, hours: 0, minutes: 4 }, [['day', 2]]],
    [
      { days: 0, hours: 3, minutes: 5 },
      [
        ['hour', 3],
        ['minute', 5],
      ],
    ],
    [{ days: 0, hours: 3, minutes: 0 }, [['hour', 3]]],
    [{ days: 0, hours: 0, minutes: 12 }, [['minute', 12]]],
    [{ days: 0, hours: 0, minutes: 0 }, []],
  ])('%j gives %j', (parts, expected) => {
    expect(countdownUnits(parts)).toEqual(expected);
  });
});

describe('ticketTypeLabelKey', () => {
  it("translates the server's two rows without a capacity", () => {
    expect(ticketTypeLabelKey({ name: 'Group booking', quantity: null })).toBe(
      'dashboard.ticketTypes.group',
    );
    expect(ticketTypeLabelKey({ name: 'General', quantity: null })).toBe(
      'dashboard.ticketTypes.general',
    );
  });

  it('leaves a tier the organizer named, or any tier with a capacity, as typed', () => {
    expect(ticketTypeLabelKey({ name: 'VIP', quantity: null })).toBeNull();
    expect(ticketTypeLabelKey({ name: 'General', quantity: 50 })).toBeNull();
    expect(ticketTypeLabelKey({ name: 'Group booking', quantity: 10 })).toBeNull();
  });
});
