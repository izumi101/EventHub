import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { FooterComponent } from './footer.component';
import { EventService } from '../../services/event.service';
import { I18nTestingModule } from '../../i18n/testing';

const categories = [
  { id: 1, name: 'Music', icon: 'music', event_count: 3 },
  { id: 2, name: 'Tech', icon: 'laptop', event_count: 9 },
  { id: 3, name: 'Sport', icon: 'trophy', event_count: 1 },
  { id: 4, name: 'Theatre', icon: 'theater', event_count: 5 },
  { id: 5, name: 'Business', icon: 'briefcase', event_count: 7 },
];

function render(user: object | null): HTMLElement {
  localStorage.clear();
  if (user) {
    localStorage.setItem('access_token', 't');
    localStorage.setItem('user', JSON.stringify(user));
  }
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, FooterComponent],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      { provide: EventService, useValue: { getCategories: () => of(categories) } },
    ],
  });
  const fixture = TestBed.createComponent(FooterComponent);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const hrefs = (el: HTMLElement) =>
  Array.from(el.querySelectorAll('a')).map((a) => a.getAttribute('href'));

describe('FooterComponent', () => {
  const attendee = {
    username: 'a',
    is_staff: false,
    is_superuser: false,
    profile: { role: 'attendee' },
  };
  const organizer = {
    username: 'o',
    is_staff: false,
    is_superuser: false,
    profile: { role: 'organizer' },
  };

  afterEach(() => localStorage.clear());

  it('hides organizer links from guests', () => {
    const el = render(null);
    expect(el.querySelector('[data-testid="footer-organizer"]')).toBeNull();
    expect(hrefs(el)).not.toContain('/my-events');
  });

  it('hides organizer links from attendees', () => {
    const el = render(attendee);
    expect(el.querySelector('[data-testid="footer-organizer"]')).toBeNull();
    expect(hrefs(el)).not.toContain('/create-event');
  });

  it('shows organizer links to organizers', () => {
    const el = render(organizer);
    expect(el.querySelector('[data-testid="footer-organizer"]')).not.toBeNull();
    expect(hrefs(el)).toEqual(
      expect.arrayContaining(['/organizer/dashboard', '/create-event', '/my-events']),
    );
  });

  it('links the four busiest real categories to the Discover filter', () => {
    const links = hrefs(render(null)).filter((h) => h?.startsWith('/?category='));
    expect(links).toEqual(['/?category=2', '/?category=5', '/?category=4', '/?category=1']);
  });
});
