const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;

const formatters = new Map<string, Intl.RelativeTimeFormat>();

function formatter(locale: string): Intl.RelativeTimeFormat {
  let rtf = formatters.get(locale);
  if (!rtf) {
    try {
      rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto', style: 'short' });
    } catch {
      // A malformed language tag must not break the page: fall back to English.
      rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto', style: 'short' });
    }
    formatters.set(locale, rtf);
  }
  return rtf;
}

/**
 * "5 min. ago", "3 hr. ago", "yesterday" in the given locale. Past moments
 * only: a timestamp slightly ahead of this device's clock reads as "now".
 * The caller shows the exact time next to it (`title`, `<time datetime>`).
 * An unparseable timestamp gives '' (the exact time is still shown by the caller).
 */
export function relativeTime(iso: string, locale: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then) || Number.isNaN(now)) return '';
  const seconds = Math.min(0, Math.round((then - now) / 1000));
  const age = -seconds;
  const rtf = formatter(locale);
  if (age < 45) return rtf.format(0, 'second');
  if (age < HOUR) return rtf.format(-Math.max(1, Math.floor(age / MINUTE)), 'minute');
  if (age < DAY) return rtf.format(-Math.floor(age / HOUR), 'hour');
  if (age < WEEK) return rtf.format(-Math.floor(age / DAY), 'day');
  return rtf.format(-Math.floor(age / WEEK), 'week');
}
