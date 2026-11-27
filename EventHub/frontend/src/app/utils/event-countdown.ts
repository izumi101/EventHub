export interface CountdownParts {
  days: number;
  hours: number;
  minutes: number;
}

export type CountdownUnit = 'day' | 'hour' | 'minute';

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

/**
 * Whole days, hours and minutes from `now` until `startIso`; the minutes are
 * rounded down, so "0 min" means less than a minute is left. Null when the
 * moment is not in the future (or is unparseable): there is nothing to count.
 */
export function countdownParts(startIso: string, now: number = Date.now()): CountdownParts | null {
  const left = new Date(startIso).getTime() - now;
  if (Number.isNaN(left) || left <= 0) return null;
  return {
    days: Math.floor(left / DAY_MS),
    hours: Math.floor((left % DAY_MS) / HOUR_MS),
    minutes: Math.floor((left % HOUR_MS) / MINUTE_MS),
  };
}

/**
 * The two largest units that matter, as [unit, amount] pairs: "2 d 3 h",
 * "3 h 5 min", "12 min". Empty when under a minute is left. A unit that is 0
 * is left out ("2 d" for exactly two days).
 */
export function countdownUnits(parts: CountdownParts): [CountdownUnit, number][] {
  const all: [CountdownUnit, number][] = [
    ['day', parts.days],
    ['hour', parts.hours],
    ['minute', parts.minutes],
  ];
  const first = all.findIndex(([, amount]) => amount > 0);
  if (first < 0) return [];
  return all.slice(first, first + 2).filter(([, amount]) => amount > 0);
}
