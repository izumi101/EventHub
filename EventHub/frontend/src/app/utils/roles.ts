import type { User } from '../models/models';

/**
 * Single source for the client-side role rule (UX only — the API enforces
 * permissions). Self-registered organizers carry `profile.role ===
 * 'organizer'`; staff/superuser flags come from Django admin.
 */
export function isOrganizer(user: User | null | undefined): boolean {
  return user?.is_staff || user?.is_superuser || user?.profile.role === 'organizer';
}

export function isAdmin(user: User | null | undefined): boolean {
  return !!user?.is_superuser;
}
