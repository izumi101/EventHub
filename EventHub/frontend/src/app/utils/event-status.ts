import type { components } from '../api/openapi';

/** An event's lifecycle status, as the API sends it. */
export type EventStatus = components['schemas']['EventStatusEnum'];

/** Translation key of each event status (the badge text everywhere an event is listed). */
export const EVENT_STATUS_LABEL: Readonly<Record<EventStatus, string>> = {
  draft: 'dashboard.draft',
  pending: 'dashboard.pendingApproval',
  published: 'dashboard.published',
  completed: 'dashboard.completed',
  rejected: 'common.rejected',
  cancelled: 'common.cancelled',
};

/** Badge colour class of each event status. */
export const EVENT_STATUS_BADGE: Readonly<Record<EventStatus, string>> = {
  draft: 'badge-pending',
  pending: 'badge-pending',
  published: 'badge-published',
  completed: 'badge-completed',
  rejected: 'badge-rejected',
  cancelled: 'badge-rejected',
};

const isEventStatus = (status: string): status is EventStatus =>
  Object.prototype.hasOwnProperty.call(EVENT_STATUS_LABEL, status);

/**
 * Translation key for a status. A status this client does not know yet (a
 * newer server) comes back unchanged, so the badge shows it rather than nothing.
 */
export function eventStatusLabel(status: string): string {
  return isEventStatus(status) ? EVENT_STATUS_LABEL[status] : status;
}

/** Badge class for a status; an unknown one gets the neutral "pending" look. */
export function eventStatusBadge(status: string): string {
  return isEventStatus(status) ? EVENT_STATUS_BADGE[status] : 'badge-pending';
}
