import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  ActivatedRouteSnapshot,
  Router,
  RouterStateSnapshot,
  UrlTree,
  provideRouter,
} from '@angular/router';
import { roleGuard } from './role.guard';
import { routes } from '../app.routes';

function run(role: 'admin' | 'organizer', user: object | null): boolean | UrlTree {
  localStorage.clear();
  if (user) {
    localStorage.setItem('access_token', 't');
    localStorage.setItem('user', JSON.stringify(user));
  }
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({ providers: [provideRouter([]), provideHttpClient()] });
  return TestBed.runInInjectionContext(() =>
    roleGuard(role)({} as ActivatedRouteSnapshot, { url: '/target' } as RouterStateSnapshot),
  ) as boolean | UrlTree;
}

const asUrl = (r: boolean | UrlTree) => TestBed.inject(Router).serializeUrl(r as UrlTree);

describe('roleGuard', () => {
  const attendee = { is_staff: false, is_superuser: false, profile: { role: 'attendee' } };
  const organizer = { is_staff: false, is_superuser: false, profile: { role: 'organizer' } };
  const admin = { is_staff: true, is_superuser: true, profile: { role: 'attendee' } };

  it('sends anonymous visitors to login with a return URL', () => {
    expect(asUrl(run('organizer', null))).toBe('/login?returnUrl=%2Ftarget');
  });

  it('lets organizers into organizer pages but not attendees', () => {
    expect(run('organizer', organizer)).toBe(true);
    expect(asUrl(run('organizer', attendee))).toBe('/');
  });

  it('keeps admin pages for superusers', () => {
    expect(run('admin', admin)).toBe(true);
    expect(asUrl(run('admin', organizer))).toBe('/');
  });
});

describe('/my-events route', () => {
  const attendee = { is_staff: false, is_superuser: false, profile: { role: 'attendee' } };
  const organizer = { is_staff: false, is_superuser: false, profile: { role: 'organizer' } };

  function runMyEvents(user: object | null): boolean | UrlTree {
    localStorage.clear();
    if (user) {
      localStorage.setItem('access_token', 't');
      localStorage.setItem('user', JSON.stringify(user));
    }
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [provideRouter([]), provideHttpClient()] });
    const route = routes.find((r) => r.path === 'my-events');
    const guard = route?.canActivate?.[0] as ReturnType<typeof roleGuard>;
    return TestBed.runInInjectionContext(() =>
      guard({} as ActivatedRouteSnapshot, { url: '/my-events' } as RouterStateSnapshot),
    ) as boolean | UrlTree;
  }

  it('redirects attendees to Discover and lets organizers in', () => {
    expect(asUrl(runMyEvents(attendee))).toBe('/');
    expect(runMyEvents(organizer)).toBe(true);
  });
});
