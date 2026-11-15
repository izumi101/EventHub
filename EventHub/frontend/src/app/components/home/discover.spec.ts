import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { Router, convertToParamMap, provideRouter } from '@angular/router';
import { Observable, of, throwError } from 'rxjs';
import { I18nTestingModule } from '../../i18n/testing';
import type { Event } from '../../models/models';
import { EventService } from '../../services/event.service';
import { FavoritesStore } from '../../services/favorites.store';
import { ToastService } from '../../services/toast.service';
import { AuthService } from '../../services/auth.service';
import { EventCardComponent } from '../event-card/event-card.component';
import { DiscoverHeroComponent, pickHeroEvents } from './discover-hero.component';
import { EventRailComponent } from './event-rail.component';
import { FilterBarComponent } from './filter-bar.component';
import {
  EMPTY_FILTERS,
  filtersFromParams,
  filtersToApi,
  filtersToParams,
  hasActiveFilters,
  sheetFilterCount,
} from './discover-filters';

let nextId = 1;
function ev(overrides: Partial<Event> = {}): Event {
  return {
    id: nextId++,
    title: 'Event',
    location: 'Hall, Almaty',
    date: '2026-12-11T19:00:00Z',
    category: { id: 3, name: 'Music', description: '', icon: 'music' },
    image: null,
    price: '5000.00',
    price_from: '5000.00',
    currency: 'KZT',
    is_free: false,
    is_online: false,
    has_ticket_types: false,
    available_spots: 50,
    max_participants: 100,
    ...overrides,
  } as Event;
}

describe('discover filters ↔ URL ↔ API', () => {
  it('reads every filter from the query string', () => {
    const f = filtersFromParams(
      convertToParamMap({
        q: ' jazz ',
        ai: '1',
        city: 'Almaty',
        category: '4',
        free: '1',
        online: '1',
        sort: '-price',
      }),
    );
    expect(f).toEqual({
      q: 'jazz',
      ai: true,
      city: 'Almaty',
      category: 4,
      free: true,
      online: true,
      sort: '-price',
    });
  });

  it('falls back to defaults and to the remembered city', () => {
    const f = filtersFromParams(convertToParamMap({ category: 'x', sort: 'drop' }), 'Astana');
    expect(f).toEqual({ ...EMPTY_FILTERS, city: 'Astana' });
    // An explicit empty city in the URL beats the remembered one.
    expect(filtersFromParams(convertToParamMap({ city: '' }), 'Astana').city).toBe('');
  });

  it('writes only non-default values (nulls clear on merge)', () => {
    expect(filtersToParams({ ...EMPTY_FILTERS, free: true, category: 2 })).toEqual({
      q: null,
      ai: null,
      city: null,
      category: 2,
      free: 1,
      online: null,
      sort: null,
    });
  });

  it('sends the same API params as the old Discover page', () => {
    expect(filtersToApi(EMPTY_FILTERS)).toEqual({ page: 1, upcoming: true, ordering: 'date' });
    expect(
      filtersToApi(
        { ...EMPTY_FILTERS, q: 'jazz', city: 'Almaty', category: 2, free: true, online: true },
        3,
      ),
    ).toEqual({
      page: 3,
      upcoming: true,
      search: 'jazz',
      location: 'Almaty',
      category: 2,
      ordering: 'date',
      is_free: true,
      is_online: true,
    });
    expect(filtersToApi({ ...EMPTY_FILTERS, q: 'jazz', ai: true })).toMatchObject({ q: 'jazz' });
    expect(filtersToApi({ ...EMPTY_FILTERS, ai: true })).not.toHaveProperty('q');
  });

  it('keeps the rails for a city alone, hides them for real filters', () => {
    expect(hasActiveFilters({ ...EMPTY_FILTERS, city: 'Almaty' })).toBe(false);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, free: true })).toBe(true);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, sort: '-price' })).toBe(true);
    expect(sheetFilterCount({ ...EMPTY_FILTERS, city: 'A', online: true })).toBe(2);
  });
});

describe('hero rule', () => {
  it('shows the brand hero (no picks) when there are no events', () => {
    expect(pickHeroEvents([])).toEqual([]);
  });

  it('shows one event without thumbnails rules', () => {
    const only = ev();
    expect(pickHeroEvents([only])).toEqual([only]);
  });

  it('prefers events with a photo and takes three', () => {
    const plain = ev();
    const photos = [1, 2, 3, 4].map(() => ev({ image: '/media/a.jpg' }));
    expect(pickHeroEvents([plain, ...photos])).toEqual(photos.slice(0, 3));
  });

  it('falls back to category covers when nothing has a photo', () => {
    const list = [ev(), ev(), ev(), ev()];
    expect(pickHeroEvents(list)).toEqual(list.slice(0, 3));
  });

  it('skips sold-out events and duplicates (recommendations + upcoming)', () => {
    const sold = ev({ available_spots: 0 });
    const open = ev();
    const unlimited = ev({ max_participants: 0, available_spots: 0 });
    expect(pickHeroEvents([sold, open, open, unlimited])).toEqual([open, unlimited]);
  });

  it('switches to the category cover when the photo fails to load', () => {
    TestBed.configureTestingModule({
      imports: [I18nTestingModule],
      providers: [provideRouter([])],
    });
    const fixture = TestBed.createComponent(DiscoverHeroComponent);
    const e = ev({ image: '/media/broken.jpg' });
    fixture.componentInstance.events = [e];
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    el.querySelector('img.hero-img')!.dispatchEvent(new window.Event('error'));
    fixture.detectChanges();
    expect(el.querySelector('img.hero-img')).toBeNull();
    expect(el.querySelector('.hero-cover-icon')).not.toBeNull();
    expect(el.querySelector('h1')?.textContent).toContain(e.title);
  });
});

describe('Discover card', () => {
  const favorites = { has: signal(false), toggle: vi.fn() };

  function render(event: Event): HTMLElement {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [I18nTestingModule, EventCardComponent],
      providers: [
        provideRouter([]),
        {
          provide: FavoritesStore,
          useValue: { has: () => favorites.has(), toggle: favorites.toggle },
        },
      ],
    });
    const fixture = TestBed.createComponent(EventCardComponent);
    fixture.componentInstance.event = event;
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }
  const pills = (el: HTMLElement) =>
    Array.from(el.querySelectorAll('.card-pill')).map((p) => p.textContent.trim());

  it('says "N spots left" at 20 or fewer, not above', () => {
    expect(pills(render(ev({ available_spots: 12 })))).toEqual(['12 spots left']);
    expect(pills(render(ev({ available_spots: 21 })))).toEqual([]);
  });

  it('marks sold-out, free and online events', () => {
    const sold = render(ev({ available_spots: 0 }));
    expect(pills(sold)).toEqual(['Sold out']);
    expect(sold.querySelector('[data-testid="card-price"]')?.textContent.trim()).toBe('Sold out');
    expect(pills(render(ev({ is_free: true, price_from: '0.00', is_online: true })))).toEqual([
      'Free',
      'Online',
    ]);
  });

  it('links the title to the event and keeps the heart a separate button', () => {
    const el = render(ev({ id: 77, title: 'Jazz Night' }));
    const link = el.querySelector('a')!;
    expect(link.getAttribute('href')).toBe('/events/77');
    expect(link.textContent.trim()).toBe('Jazz Night');
    const heart = el.querySelector<HTMLButtonElement>('.event-card-heart')!;
    expect(heart.getAttribute('aria-pressed')).toBe('false');
    heart.click();
    expect(favorites.toggle).toHaveBeenCalledWith(77);
  });

  it('keeps a long venue from widening the card', () => {
    const venue = render(ev({ location: 'A'.repeat(300) })).querySelector('.event-card-venue')!;
    expect(venue.getAttribute('title')).toHaveLength(300);
    expect(venue.className).toContain('event-card-venue');
  });
});

describe('FavoritesStore', () => {
  const toastError = vi.fn();
  function setup(toggle: () => unknown, user: { id: number } | null = { id: 1 }) {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [I18nTestingModule],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        { provide: AuthService, useValue: { currentUser$: of(user), isLoggedIn: !!user } },
        {
          provide: EventService,
          useValue: { getFavoriteIds: () => of([5]), toggleFavorite: toggle },
        },
        { provide: ToastService, useValue: { error: toastError } },
      ],
    });
    return TestBed.inject(FavoritesStore);
  }
  afterEach(() => localStorage.clear());

  it('loads the ids for a signed-in user', () => {
    const store = setup(() => of({ favorited: true }));
    expect(store.has(5)).toBe(true);
    expect(store.has(6)).toBe(false);
  });

  it('flips at once and keeps the server answer', () => {
    const store = setup(() => of({ favorited: true }));
    store.toggle(6);
    expect(store.has(6)).toBe(true);
  });

  it('rolls back and reports when the API refuses', () => {
    const store = setup(() => throwError(() => new Error('nope')));
    store.toggle(5);
    expect(store.has(5)).toBe(true);
    expect(toastError).toHaveBeenCalled();
  });

  it('sends guests to sign in with a return URL', () => {
    const toggle = vi.fn();
    const store = setup(toggle, null);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    store.toggle(5);
    expect(toggle).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith(['/login'], { queryParams: { returnUrl: '/' } });
  });
});

describe('EventRailComponent', () => {
  function rail(source: () => Observable<Event[]>) {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [I18nTestingModule],
      providers: [provideRouter([])],
    });
    const fixture = TestBed.createComponent(EventRailComponent);
    fixture.componentInstance.title = 'Rail';
    fixture.componentInstance.source = source;
    fixture.componentInstance.load();
    fixture.detectChanges();
    return fixture;
  }

  it('hides itself when empty', () => {
    const fixture = rail(() => of([]));
    expect(fixture.componentInstance.hidden()).toBe(true);
    expect((fixture.nativeElement as HTMLElement).querySelector('section')).toBeNull();
  });

  it('hides itself when the request fails', () => {
    const fixture = rail(() => throwError(() => new Error('down')));
    expect(fixture.componentInstance.hidden()).toBe(true);
  });

  it('shows its cards when loaded', () => {
    const fixture = rail(() => of([ev(), ev()]));
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('h2')?.textContent).toContain('Rail');
    expect(el.querySelectorAll('app-event-card')).toHaveLength(2);
  });
});

describe('FilterBarComponent', () => {
  async function bar() {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ imports: [I18nTestingModule, FilterBarComponent] });
    await TestBed.compileComponents(); // @defer (filter sheet) needs async compilation
    const fixture = TestBed.createComponent(FilterBarComponent);
    fixture.componentInstance.filters = EMPTY_FILTERS;
    fixture.componentInstance.categories = [1, 2, 3, 4, 5, 6].map((id) => ({
      id,
      name: `Cat ${id}`,
      description: '',
      icon: '',
      event_count: 10 - id,
    }));
    fixture.componentInstance.ngOnChanges();
    fixture.detectChanges();
    const changes: unknown[] = [];
    fixture.componentInstance.filtersChange.subscribe((c) => changes.push(c));
    return { el: fixture.nativeElement as HTMLElement, changes };
  }
  const button = (el: HTMLElement, text: string) =>
    Array.from(el.querySelectorAll('button')).find((b) => b.textContent.trim().startsWith(text))!;

  it('emits each chip as a filter change', async () => {
    const { el, changes } = await bar();
    button(el, 'Free only').click();
    button(el, 'Online').click();
    button(el, 'Cat 2').click();
    expect(changes).toEqual([{ free: true }, { online: true }, { category: 2 }]);
  });

  it('offers the categories past the first four behind "+N more"', async () => {
    const { el } = await bar();
    expect(button(el, '2 more')).toBeDefined();
  });

  it('applies the typed search on Enter', async () => {
    const { el, changes } = await bar();
    const input = el.querySelector<HTMLInputElement>('#discover-search')!;
    input.value = ' opera ';
    input.dispatchEvent(new window.Event('input'));
    input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter' }));
    expect(changes).toEqual([{ q: 'opera' }]);
  });
});
