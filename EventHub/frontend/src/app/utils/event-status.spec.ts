import {
  EVENT_STATUS_BADGE,
  EVENT_STATUS_LABEL,
  eventStatusBadge,
  eventStatusLabel,
} from './event-status';
import en from '../../assets/i18n/en.json';

const lookup = (key: string): unknown =>
  key
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        typeof node === 'object' && node !== null
          ? (node as Record<string, unknown>)[part]
          : undefined,
      en,
    );

describe('event status', () => {
  it('has a translation that exists for every status', () => {
    for (const key of Object.values(EVENT_STATUS_LABEL)) {
      expect(typeof lookup(key), key).toBe('string');
    }
  });

  it('covers the same statuses for label and badge', () => {
    expect(Object.keys(EVENT_STATUS_BADGE).sort()).toEqual(Object.keys(EVENT_STATUS_LABEL).sort());
  });

  it('maps known statuses and passes unknown ones through', () => {
    expect(eventStatusLabel('published')).toBe('dashboard.published');
    expect(eventStatusBadge('cancelled')).toBe('badge-rejected');
    expect(eventStatusLabel('archived')).toBe('archived');
    expect(eventStatusBadge('archived')).toBe('badge-pending');
    // Inherited object keys are not statuses.
    expect(eventStatusLabel('toString')).toBe('toString');
  });
});
