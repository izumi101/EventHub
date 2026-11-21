import { relativeTime } from './relative-time';

const NOW = Date.parse('2026-11-21T12:00:00Z');
const ago = (seconds: number) => new Date(NOW - seconds * 1000).toISOString();

describe('relativeTime', () => {
  it('says "now" for the last moments and for a clock slightly ahead', () => {
    expect(relativeTime(ago(10), 'en', NOW)).toBe('now');
    expect(relativeTime(ago(-120), 'en', NOW)).toBe('now');
  });

  it('counts minutes, hours, days and weeks', () => {
    expect(relativeTime(ago(5 * 60), 'en', NOW)).toMatch(/^5 min/);
    expect(relativeTime(ago(3 * 3600), 'en', NOW)).toMatch(/^3 hr/);
    expect(relativeTime(ago(2 * 86400), 'en', NOW)).toMatch(/^2 days/);
    expect(relativeTime(ago(21 * 86400), 'en', NOW)).toMatch(/^3 wk/);
  });

  it('never rounds up to the next unit', () => {
    expect(relativeTime(ago(3599), 'en', NOW)).toMatch(/^59 min/);
  });

  it('follows the language', () => {
    expect(relativeTime(ago(5 * 60), 'ru', NOW)).toContain('назад');
    expect(relativeTime(ago(5 * 60), 'kk', NOW)).not.toBe(relativeTime(ago(5 * 60), 'en', NOW));
  });

  it.each(['', 'not a date', '2026-13-45T99:00:00Z'])(
    'gives an empty string, not a RangeError, for the invalid timestamp %j',
    (value) => {
      expect(() => relativeTime(value, 'en', NOW)).not.toThrow();
      expect(relativeTime(value, 'en', NOW)).toBe('');
    },
  );

  it('survives a malformed language tag by falling back to English', () => {
    expect(relativeTime(ago(5 * 60), 'not_a_locale!!', NOW)).toMatch(/^5 min/);
  });
});
