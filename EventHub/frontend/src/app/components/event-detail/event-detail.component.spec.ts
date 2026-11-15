import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import en from '../../../assets/i18n/en.json';
import { I18nTestingModule } from '../../i18n/testing';
import type { Event, Registration } from '../../models/models';
import { AuthService } from '../../services/auth.service';
import { EventService } from '../../services/event.service';
import { FavoritesStore } from '../../services/favorites.store';
import { PaymentService } from '../../services/payment.service';
import { SeoService } from '../../services/seo.service';
import { EventDetailComponent, PrimaryAction } from './event-detail.component';

/** English text of a translation key (params stripped), to find it on the page. */
function t(key: string): string {
  let node: unknown = en;
  for (const part of key.split('.')) node = (node as Record<string, unknown>)[part];
  return String(node).split('{{')[0].trim();
}

const attendee = {
  id: 7,
  username: 'aliya',
  is_staff: false,
  is_superuser: false,
  profile: { role: 'attendee' },
};
const organizerUser = { ...attendee, id: 8, username: 'org', profile: { role: 'organizer' } };

function event(overrides: Partial<Event> = {}): Event {
  return {
    id: 5,
    title: 'Jazz Night',
    description: 'Live jazz.',
    location: 'Hall, Almaty',
    address: '',
    date: '2026-12-11T19:00:00Z',
    end_date: null,
    status: 'published',
    category: { id: 3, name: 'Music', description: '', icon: 'music' },
    organizer: { id: 99, username: 'host', first_name: 'Ann', last_name: 'Lee' },
    image: null,
    price: '5000.00',
    price_from: '5000.00',
    currency: 'KZT',
    is_free: false,
    is_online: false,
    online_link: '',
    has_ticket_types: false,
    ticket_types: [],
    available_spots: 40,
    max_participants: 100,
    registered_count: 60,
    refundable: true,
    ...overrides,
  } as Event;
}

interface State {
  user?: object | null;
  event?: Partial<Event>;
  status?: string | null;
  registration?: Partial<Registration>;
  waitlist?: object | null;
  queued?: boolean;
  zones?: { zone: string; price: string; multiplier: number }[];
}

async function render(state: State) {
  const user = state.user === undefined ? attendee : state.user;
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, EventDetailComponent],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      { provide: AuthService, useValue: { isLoggedIn: !!user, currentUser: user } },
      { provide: EventService, useValue: {} },
      { provide: PaymentService, useValue: {} },
      { provide: SeoService, useValue: { setEvent: () => undefined } },
      { provide: FavoritesStore, useValue: { has: () => false, toggle: () => undefined } },
    ],
  });
  await TestBed.compileComponents(); // @defer blocks need async compilation
  const fixture = TestBed.createComponent(EventDetailComponent);
  const cmp = fixture.componentInstance;
  fixture.detectChanges(); // ngOnInit: no :id in the test route, nothing is fetched
  cmp.event = event(state.event);
  cmp.registrationStatus = state.status ?? null;
  cmp.myRegistration = (state.registration ?? null) as Registration | null;
  cmp.waitlist = (state.waitlist ?? null) as never;
  cmp.queueInfo = state.queued ? ({ status: 'queued', position: 2, total: 9 } as never) : null;
  cmp.seatZones = (state.zones ?? []) as never;
  cmp.seatPriceFrom = state.zones?.length ? state.zones[0].price : null;
  fixture.detectChanges();
  const panel = (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>(
    '.purchase-panel',
  )!;
  return { cmp, panel, fixture };
}

const has = (panel: HTMLElement, key: string) => panel.textContent.includes(t(key));
const buttons = (panel: HTMLElement) =>
  Array.from(panel.querySelectorAll('button, a')).map((b) =>
    b.textContent.replace(/\s+/g, ' ').trim(),
  );

describe('Event page purchase panel — one case per state, in the panel order', () => {
  const cases: [string, State, string, PrimaryAction][] = [
    ['cancelled', { event: { status: 'cancelled' } }, 'eventDetail.thisEventWasCancelled', null],
    ['completed', { event: { status: 'completed' } }, 'eventDetail.thisEventHasEnded', null],
    ['guest', { user: null }, 'eventDetail.signInToRegister', 'login'],
    [
      'owner',
      { event: { organizer: { id: 7, username: 'aliya', first_name: '', last_name: '' } } },
      'eventDetail.youReTheOrganizer',
      null,
    ],
    [
      'confirmed',
      { status: 'confirmed', registration: { is_checked_in: false } },
      'eventDetail.youReRegistered',
      'ticket',
    ],
    ['pending', { status: 'pending' }, 'eventDetail.paymentIncomplete', 'pay'],
    ['rejected', { status: 'rejected' }, 'eventDetail.registrationDeclined', null],
    ['non-attendee account', { user: organizerUser }, 'eventDetail.onlyAttendeeAccountsCan', null],
    ['waitlist offer', { waitlist: { status: 'offered' } }, 'eventDetail.aSpotOpenedUp', 'claim'],
    ['queued', { queued: true }, 'eventDetail.youReInThe', null],
    [
      'sold out',
      { event: { available_spots: 0, registered_count: 100 } },
      'eventDetail.joinTheWaitlist',
      'waitlist',
    ],
    ['buy', {}, 'eventDetail.getTicketsPrice', 'buy'],
  ];

  it.each(cases)('%s', async (_name, state, key, action) => {
    const { cmp, panel } = await render(state);
    expect(has(panel, key)).toBe(true);
    expect(cmp.primaryAction).toBe(action);
  });

  it('never offers to cancel a confirmed ticket; paid + refundable gets a refund request', async () => {
    const { panel } = await render({
      status: 'confirmed',
      registration: { is_checked_in: false, payment: { amount: '5000.00' } } as never,
    });
    expect(has(panel, 'eventDetail.releaseSeat2')).toBe(false);
    expect(buttons(panel)).toContain(t('eventDetail.requestARefund'));
  });

  it('keeps the held-seat block for a pending payment: complete or release', async () => {
    const { panel } = await render({ status: 'pending' });
    expect(has(panel, 'eventDetail.seatHeldCompletePayment')).toBe(true);
    expect(buttons(panel)).toEqual(
      expect.arrayContaining([t('eventDetail.completePayment'), t('eventDetail.releaseSeat2')]),
    );
  });

  it('lets the organizer of the event buy nothing', async () => {
    const { panel } = await render({
      event: { organizer: { id: 7, username: 'aliya', first_name: '', last_name: '' } },
    });
    expect(buttons(panel).some((b) => /Get tickets|Choose a seat/.test(b))).toBe(false);
    expect(buttons(panel).some((b) => b.includes(t('eventDetail.bookSeatsForA')))).toBe(false);
  });
});

describe('Event page purchase panel — buy state details', () => {
  it('lists seat-map zones with prices and asks to choose a seat', async () => {
    const { panel } = await render({
      zones: [
        { zone: 'standard', price: '9000.00', multiplier: 1 },
        { zone: 'vip', price: '18000.00', multiplier: 2 },
      ],
    });
    const rows = Array.from(panel.querySelectorAll('.purchase-row-name')).map((r) =>
      r.textContent.trim(),
    );
    expect(rows).toEqual(['Standard', 'VIP']);
    expect(buttons(panel).some((b) => b.startsWith('Choose a seat'))).toBe(true);
  });

  it('shows ticket tiers as rows that open checkout on that tier', async () => {
    const tiers = [
      {
        id: 11,
        name: 'Early bird',
        kind: 'paid',
        price: '3000.00',
        sale_state: 'on_sale',
        available: 50,
      },
      { id: 12, name: 'VIP', kind: 'paid', price: '9000.00', sale_state: 'sold_out', available: 0 },
    ];
    const { cmp, panel } = await render({
      event: { has_ticket_types: true, ticket_types: tiers as never, price_from: '3000.00' },
    });
    const rows = Array.from(panel.querySelectorAll<HTMLButtonElement>('button.purchase-row'));
    expect(rows.map((r) => r.disabled)).toEqual([false, true]);
    rows[0].click();
    expect(cmp.showCheckout).toBe(true);
    expect(cmp.preselectTicketTypeId).toBe(11);
    expect(buttons(panel)).toContain(t('eventDetail.chooseTickets'));
  });

  it('offers the group booking only for flat-priced paid events', async () => {
    const { cmp, panel, fixture } = await render({});
    const group = Array.from(panel.querySelectorAll<HTMLButtonElement>('[role="radio"]'))[1];
    group.click();
    fixture.detectChanges();
    expect(cmp.bookingMode).toBe('group');
    const link = Array.from(panel.querySelectorAll('a')).find((a) =>
      a.textContent.includes(t('eventDetail.bookSeatsForA')),
    );
    expect(link?.getAttribute('href')).toBe('/events/5/group');

    const free = (await render({ event: { is_free: true, price: '0.00', price_from: '0.00' } }))
      .panel;
    expect(free.querySelector('[role="radiogroup"]')).toBeNull();
    const tiered = (await render({ event: { has_ticket_types: true } })).panel;
    expect(tiered.querySelector('[role="radiogroup"]')).toBeNull();
  });

  it('says Free (never 0 ₸) and shows the KZT payment note only for paid KZT events', async () => {
    const free = (await render({ event: { is_free: true, price: '0.00', price_from: '0.00' } }))
      .panel;
    expect(free.querySelector('.purchase-price')?.textContent.trim()).toBe('Free');
    expect(free.querySelector('.purchase-pay-note')).toBeNull();
    const paid = (await render({})).panel;
    expect(paid.querySelector('.purchase-pay-note')).not.toBeNull();
  });
});
