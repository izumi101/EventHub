/** The server names the two tier-less rows in English; everything else is the organizer's own text. */
const GROUP_ROW = 'Group booking';
const GENERAL_ROW = 'General';

/**
 * Translation key for a ticket-type row of the analytics API when it is one of
 * the server's own rows (group bookings, tickets without a tier: both have
 * no capacity), otherwise null: a tier the organizer named shows as typed.
 */
export function ticketTypeLabelKey(row: { name: string; quantity: number | null }): string | null {
  if (row.quantity !== null) return null;
  if (row.name === GROUP_ROW) return 'dashboard.ticketTypes.group';
  if (row.name === GENERAL_ROW) return 'dashboard.ticketTypes.general';
  return null;
}
