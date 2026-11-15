import { Type, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { shellLayout } from './app-shell.component';
import { AccountMenuComponent } from './account-menu.component';
import { TopNavComponent } from './top-nav.component';
import { I18nTestingModule } from '../i18n/testing';
import { ThemeService } from '../services/theme.service';

/** jsdom has no matchMedia, which the real ThemeService reads. */
const themeStub = { isDark: signal(false), toggle: () => undefined };

const attendee = {
  username: 'aliya',
  email: 'aliya@example.com',
  is_staff: false,
  is_superuser: false,
  profile: { role: 'attendee' },
};
const organizer = { ...attendee, username: 'org', profile: { role: 'organizer' } };
const admin = { ...attendee, username: 'root', is_staff: true, is_superuser: true };

function signIn(user: object | null): void {
  localStorage.clear();
  if (user) {
    localStorage.setItem('access_token', 't');
    localStorage.setItem('user', JSON.stringify(user));
  }
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      { provide: ThemeService, useValue: themeStub },
    ],
  });
}

function render(component: Type<unknown>): HTMLElement {
  const fixture = TestBed.createComponent(component);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const hrefs = (el: HTMLElement) =>
  Array.from(el.querySelectorAll('a')).map((a) => a.getAttribute('href'));

describe('shellLayout', () => {
  it.each([
    ['/', 'consumer'],
    ['/?category=3', 'consumer'],
    ['/events/12', 'consumer'],
    ['/my-registrations', 'consumer'],
    ['/profile/security', 'consumer'],
    ['/organizer/dashboard', 'workspace'],
    ['/organizer/events/4/attendees', 'workspace'],
    ['/my-events', 'workspace'],
    ['/create-event', 'workspace'],
    ['/edit-event/4', 'workspace'],
    ['/scan', 'workspace'],
    ['/validate/abc', 'workspace'],
    ['/admin/moderation', 'workspace'],
    ['/login?returnUrl=%2F', 'bare'],
    ['/payment/success', 'bare'],
  ])('%s → %s', (url, layout) => {
    expect(shellLayout(url)).toBe(layout);
  });
});

describe('AccountMenuComponent', () => {
  afterEach(() => localStorage.clear());

  it('offers sign-in and a theme toggle to guests', () => {
    signIn(null);
    const el = render(AccountMenuComponent);
    expect(hrefs(el)).toEqual(['/login']);
    expect(el.querySelector('[aria-haspopup]')).toBeNull();
  });

  it('names the trigger after the user and starts closed', () => {
    signIn(attendee);
    const trigger = render(AccountMenuComponent).querySelector('button')!;
    expect(trigger.getAttribute('aria-label')).toContain('aliya');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });

  function openMenu(user: object): { el: HTMLElement; trigger: HTMLButtonElement } {
    signIn(user);
    const fixture = TestBed.createComponent(AccountMenuComponent);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const trigger = el.querySelector('button')!;
    trigger.click();
    fixture.detectChanges();
    return { el, trigger };
  }

  it('shows account pages but no organizer or admin area to attendees', () => {
    const { el } = openMenu(attendee);
    const links = hrefs(el);
    expect(links).toEqual([
      '/profile',
      '/my-bookings',
      '/profile/security',
      '/profile/notifications',
    ]);
    const signOut = Array.from(el.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Sign Out'),
    );
    expect(signOut).toBeDefined();
  });

  it('adds the organizer area for organizers and the admin area for admins', () => {
    expect(hrefs(openMenu(organizer).el)).toContain('/organizer/dashboard');
    expect(hrefs(openMenu(organizer).el)).not.toContain('/admin/moderation');
    expect(hrefs(openMenu(admin).el)).toEqual(
      expect.arrayContaining(['/organizer/dashboard', '/admin/moderation']),
    );
  });

  it('closes on Escape and gives focus back to the trigger', () => {
    signIn(attendee);
    const fixture = TestBed.createComponent(AccountMenuComponent);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    document.body.appendChild(el);
    const trigger = el.querySelector('button')!;
    trigger.click();
    fixture.detectChanges();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    fixture.detectChanges();
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(trigger);
    el.remove();
  });

  it('moves focus between entries with the arrow keys', () => {
    signIn(attendee);
    const fixture = TestBed.createComponent(AccountMenuComponent);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    document.body.appendChild(el);
    el.querySelector('button')!.click();
    fixture.detectChanges();
    const items = Array.from(el.querySelectorAll<HTMLElement>('.account-item'));
    items[0].focus();
    items[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    expect(document.activeElement).toBe(items[1]);
    items[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true }));
    expect(document.activeElement).toBe(items[items.length - 1]);
    el.remove();
  });
});

describe('TopNavComponent', () => {
  afterEach(() => localStorage.clear());

  it('shows only Discover to guests', () => {
    signIn(null);
    const nav = render(TopNavComponent).querySelector<HTMLElement>('header nav')!;
    expect(hrefs(nav)).toEqual(['/']);
  });

  it('adds My Tickets and Favorites once signed in, with a bell', () => {
    signIn(attendee);
    const el = render(TopNavComponent);
    expect(hrefs(el.querySelector<HTMLElement>('header nav')!)).toEqual([
      '/',
      '/my-registrations',
      '/favorites',
    ]);
    const bell = el.querySelector('app-notification-bell button');
    expect(bell?.getAttribute('aria-label')).toMatch(/^Notifications/);
  });
});
