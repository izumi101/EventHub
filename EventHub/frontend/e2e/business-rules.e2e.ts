import { expect, test } from '@playwright/test';
import {
  bearer,
  buyFreedomPayTicket,
  createAttendee,
  createEvent,
  createOrganizer,
  FPAY_URL,
  json,
  openSignedIn,
  Schemas,
  Session,
} from './support/api';

/**
 * The critical business rules from AGENTS.md, checked in the browser and
 * at the API (the UI hiding a button is not enough):
 *  - seat selection persists across page navigation,
 *  - an organizer cannot buy tickets to their own event,
 *  - clients cannot cancel a confirmed booking directly.
 */

let organizer: Session;

test.beforeAll(async ({ request }) => {
  organizer = (await createOrganizer(request)).session;
});

test('a chosen seat stays held for the buyer across page navigation', async ({ page, request }) => {
  const event = await createEvent(request, organizer, {
    currency: 'KZT',
    price: '6000.00',
    seats: { rows: 3, cols: 5 },
  });
  const { session: buyer } = await createAttendee(request);
  const { session: other } = await createAttendee(request);

  await openSignedIn(page, buyer, `/events/${event.id}`);
  await page.getByRole('button', { name: /Choose a seat/ }).click();
  await page.getByTitle(/^Row 2, Seat 3 /).click();
  const checkout = page.getByRole('dialog', { name: 'Confirm registration' });
  await expect(checkout.getByText('Row 2, Seat 3').first()).toBeVisible();
  await page.getByRole('button', { name: /Proceed to payment/ }).click();
  await expect(page.getByRole('heading', { name: 'Pay for your ticket' })).toBeVisible();
  await page.getByRole('button', { name: 'Close' }).click();

  // Leave the event: home, My Tickets, another page — then come back.
  await page.goto('/');
  await page.goto('/my-registrations');
  await expect(page.getByText(event.title).first()).toBeVisible();
  await expect(page.getByText('Payment pending').first()).toBeVisible();
  await expect(page.getByText('Row 2 · 3').first()).toBeVisible();
  await page.goto(`/events/${event.id}`);
  await expect(page.getByText('Payment incomplete')).toBeVisible();
  await expect(page.getByText('Seat held — complete payment to confirm')).toBeVisible();

  // The server keeps the hold: the seat is taken for everyone else...
  const seatMap = await json<Schemas['SeatMap']>(
    await request.get(`/api/v1/events/${event.id}/seat_map/`, { headers: bearer(other) }),
  );
  const seat = seatMap.seats.find((s) => s.row === 2 && s.col === 3);
  expect(seat?.is_available).toBe(false);
  const steal = await request.post(`/api/v1/events/${event.id}/register/`, {
    headers: bearer(other),
    data: { seat_id: seat?.id },
  });
  expect(steal.status()).toBe(400);

  // ...and "Complete payment" pays for the same seat.
  await page.getByRole('button', { name: 'Complete payment' }).click();
  await expect(page.getByRole('heading', { name: 'Pay for your ticket' })).toBeVisible();
  await page.getByRole('button', { name: 'Pay on this device' }).click();
  await expect(page).toHaveURL(new RegExp(`^${FPAY_URL}`));
  await page.getByRole('button', { name: 'Pay (success)' }).click();
  await expect(page.getByText('Payment confirmed')).toBeVisible();
  const mine = await json<Schemas['PaginatedRegistrationList']>(
    await request.get(`/api/v1/my-registrations/?event=${event.id}`, { headers: bearer(buyer) }),
  );
  expect(mine.results[0].status).toBe('confirmed');
  expect(mine.results[0].seat).toMatchObject({ row: 2, col: 3 });
});

test('an organizer cannot buy a ticket to their own event', async ({ page, request }) => {
  const event = await createEvent(request, organizer, {
    currency: 'KZT',
    price: '2500.00',
    seats: { rows: 2, cols: 2 },
  });

  await openSignedIn(page, organizer, `/events/${event.id}`);
  await expect(page.getByText("You're the organizer of this event")).toBeVisible();
  await expect(page.getByRole('button', { name: /Get tickets|Choose a seat/ })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /Book seats for a group/ })).toHaveCount(0);

  // The API refuses it too: a single ticket and a group booking.
  const ticket = await request.post(`/api/v1/events/${event.id}/register/`, {
    headers: bearer(organizer),
    data: {},
  });
  expect(ticket.status()).toBe(400);
  expect(await ticket.text()).toMatch(/Only attendee accounts can buy tickets|own events/);
  const seats = await json<Schemas['SeatMap']>(
    await request.get(`/api/v1/events/${event.id}/seat_map/`),
  );
  const booking = await request.post('/api/v1/bookings/', {
    headers: bearer(organizer),
    data: { event: event.id, seat_ids: [seats.seats[0].id] },
  });
  expect(booking.status()).toBe(400);
});

test('an attendee cannot cancel a confirmed ticket or group booking directly', async ({
  page,
  request,
}) => {
  const event = await createEvent(request, organizer, {
    currency: 'KZT',
    price: '3500.00',
    seats: { rows: 2, cols: 4 },
  });
  const { session: buyer } = await createAttendee(request);
  await buyFreedomPayTicket(request, buyer, event.id);

  // UI: a confirmed paid ticket offers a refund request, never "release".
  await openSignedIn(page, buyer, `/events/${event.id}`);
  await expect(page.getByText("You're registered!")).toBeVisible();
  await expect(page.getByRole('button', { name: 'Request a refund' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Release seat/i })).toHaveCount(0);

  // API: the cancel endpoint refuses, the ticket stays confirmed.
  const cancel = await request.post(`/api/v1/events/${event.id}/cancel/`, {
    headers: bearer(buyer),
  });
  expect(cancel.status()).toBe(400);
  const mine = await json<Schemas['PaginatedRegistrationList']>(
    await request.get(`/api/v1/my-registrations/?event=${event.id}`, { headers: bearer(buyer) }),
  );
  expect(mine.results[0].status).toBe('confirmed');

  // Group booking: paid → the owner cannot cancel it either (only a refund
  // by the organizer returns the money).
  const { session: groupBuyer } = await createAttendee(request);
  const seats = await json<Schemas['SeatMap']>(
    await request.get(`/api/v1/events/${event.id}/seat_map/`),
  );
  const free = seats.seats.filter((s) => s.is_available).slice(0, 2);
  const booking = await json<Schemas['Booking']>(
    await request.post('/api/v1/bookings/', {
      headers: bearer(groupBuyer),
      data: { event: event.id, seat_ids: free.map((s) => s.id) },
    }),
  );
  const checkout = await json<Schemas['BookingCheckoutResponse']>(
    await request.post(`/api/v1/bookings/${booking.id}/checkout/`, { headers: bearer(groupBuyer) }),
  );
  await request.post(`${FPAY_URL}/_emulator/payments/${checkout.session_id}/complete`, {
    data: {},
  });
  await expect
    .poll(async () => {
      const b = await json<Schemas['Booking']>(
        await request.get(`/api/v1/bookings/${booking.id}/`, { headers: bearer(groupBuyer) }),
      );
      return b.status;
    })
    .toBe('confirmed');
  const cancelBooking = await request.post(`/api/v1/bookings/${booking.id}/cancel/`, {
    headers: bearer(groupBuyer),
  });
  expect(cancelBooking.status()).toBe(400);
  const after = await json<Schemas['Booking']>(
    await request.get(`/api/v1/bookings/${booking.id}/`, { headers: bearer(groupBuyer) }),
  );
  expect(after.status).toBe('confirmed');
});
