import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

export type AppRole = 'admin' | 'organizer';

/**
 * UX guard only — the API enforces permissions on every request. It keeps
 * attendees from landing on organizer/admin screens that would just fail.
 * Event-scoped organizer pages are not guarded by role: co-organizers and
 * check-in staff are attendee accounts with rights on a single event.
 */
export const roleGuard = (role: AppRole): CanActivateFn => (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isLoggedIn) {
    return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  }
  const user = auth.currentUser;
  const allowed = role === 'admin'
    ? !!user?.is_superuser
    : !!(user?.is_staff || user?.is_superuser || user?.profile?.role === 'organizer');
  return allowed ? true : router.createUrlTree(['/']);
};
