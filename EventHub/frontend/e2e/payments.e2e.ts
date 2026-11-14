import { expect, Page, test } from '@playwright/test';
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
  waitUntilStepUpExpires,
} from './support/api';
import { waitForMail } from './support/mail';
import { freshTotp } from './support/totp';
import { collectErrors, payWithTestCard } from './support/ui';

/**
 * Payments end to end: KZT through the Freedom Pay emulator (QR dialog,
 * hosted page, signed callback, status polling), USD through mock Stripe,
 * group bookings, and an organizer refund behind the step-up dialog.
 */

const SUCCESS_CARD = '4111111111111111';
const DECLINED_CARD = '5548398681700148'; // 10009, insufficient funds

let organizer: Session;

test.beforeAll(async ({ request }) => {
  organizer = (await createOrganizer(request)).session;
});

async function registrationOf(page: Page, buyer: Session, eventId: number) {
  const mine = await json<Schemas['PaginatedRegistrationList']>(
    await page.request.get(`/api/v1/my-registrations/?event=${eventId}`, {
      headers: bearer(buyer),
    }),
  );
  return mine.results.find((r) => r.event.id === eventId);
}

test('KZT ticket: QR dialog, pay on this device with a test card, ticket confirmed', async ({
  page,
  request,
}) => {
  const errors = collectErrors(page);
  const event = await createEvent(request, organizer, { currency: 'KZT', price: '7500.00' });
  const { account, session: buyer } = await createAttendee(request);

  await openSignedIn(page, buyer, `/events/${event.id}`);
  await page.getByRole('button', { name: /Get tickets/ }).click();
  await page.getByRole('button', { name: /Proceed to payment/ }).click();

  // The Freedom Pay QR dialog: amount and a QR code of the payment page.
  await expect(page.getByRole('heading', { name: 'Pay for your ticket' })).toBeVisible();
  await expect(page.getByTestId('qr-amount')).toHaveText(/\d/);
  await expect(
    page.getByRole('img', { name: /QR code that opens the payment page/ }),
  ).toBeVisible();
  await expect(page.getByTestId('qr-status')).toHaveText('Waiting for the payment…');

  await page.getByRole('button', { name: 'Pay on this device' }).click();
  await expect(page).toHaveURL(new RegExp(`^${FPAY_URL}`));
  await payWithTestCard(page, SUCCESS_CARD);

  // Back in the SPA: confirmed by the signed callback + get_status3.
  await expect(page).toHaveURL(/\/payment\/success/);
  await expect(page.getByText('Payment confirmed')).toBeVisible();
  expect((await registrationOf(page, buyer, event.id))?.status).toBe('confirmed');

  await page.goto('/my-registrations');
  await expect(page.getByText(event.title).first()).toBeVisible();

  // The e-ticket email (ticket QR attached inline) left through the worker.
  const mail = await waitForMail(account.email, (m) => m.text.includes(event.title));
  expect(mail.inlineIds.some((id) => id.startsWith('ticket-qr'))).toBe(true);
  expect(errors).toEqual([]);
});

test('KZT ticket: a declined card leaves the ticket unpaid and the spot held', async ({
  page,
  request,
}) => {
  const event = await createEvent(request, organizer, { currency: 'KZT', price: '3000.00' });
  const { session: buyer } = await createAttendee(request);

  await openSignedIn(page, buyer, `/events/${event.id}`);
  await page.getByRole('button', { name: /Get tickets/ }).click();
  await page.getByRole('button', { name: /Proceed to payment/ }).click();
  await page.getByRole('button', { name: 'Pay on this device' }).click();
  await payWithTestCard(page, DECLINED_CARD);

  await expect(page).toHaveURL(/\/payment\/(cancel|success)/);
  await expect(page.getByText(/Payment did not go through|Payment cancelled/)).toBeVisible();
  expect((await registrationOf(page, buyer, event.id))?.status).toBe('pending');

  // The event page offers to finish the payment for the held spot.
  await page.goto(`/events/${event.id}`);
  await expect(page.getByText('Payment incomplete')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Complete payment' })).toBeVisible();
});

test('USD ticket: the mock provider confirms at once', async ({ page, request }) => {
  const errors = collectErrors(page);
  const event = await createEvent(request, organizer, { currency: 'USD', price: '25.00' });
  const { session: buyer } = await createAttendee(request);

  await openSignedIn(page, buyer, `/events/${event.id}`);
  await page.getByRole('button', { name: /Get tickets/ }).click();
  await page.getByRole('button', { name: /Proceed to payment/ }).click();

  await expect(page.getByText('Payment confirmed')).toBeVisible();
  expect((await registrationOf(page, buyer, event.id))?.status).toBe('confirmed');
  expect(errors).toEqual([]);
});

test('KZT group booking: hold seats, pay the whole booking by QR', async ({ page, request }) => {
  const event = await createEvent(request, organizer, {
    currency: 'KZT',
    price: '4000.00',
    seats: { rows: 3, cols: 4 },
  });
  const { session: buyer } = await createAttendee(request);

  await openSignedIn(page, buyer, `/events/${event.id}/group`);
  await page.getByRole('checkbox', { name: /^Row 1, seat 1,/ }).click();
  await page.getByRole('checkbox', { name: /^Row 1, seat 2,/ }).click();
  await expect(page.getByText('2 seat(s)')).toBeVisible();
  await page.getByRole('button', { name: /Hold seats/ }).click();
  await expect(page.getByText('Seats held')).toBeVisible();
  await page.getByRole('button', { name: /Pay for group/ }).click();

  await expect(page.getByRole('heading', { name: 'Pay for your group booking' })).toBeVisible();
  await page.getByRole('button', { name: 'Pay on this device' }).click();
  await payWithTestCard(page, SUCCESS_CARD);

  await expect(page.getByText('Your group booking is confirmed')).toBeVisible();
  const mine = await json<Schemas['Booking'][] | { results: Schemas['Booking'][] }>(
    await page.request.get('/api/v1/bookings/mine/', { headers: bearer(buyer) }),
  );
  const booking = (Array.isArray(mine) ? mine : mine.results).find((b) => b.event_id === event.id);
  expect(booking?.status).toBe('confirmed');
  expect(booking?.seats).toHaveLength(2);
});

test('organizer refunds a Freedom Pay ticket through the step-up dialog; the attendee sees it', async ({
  page,
  request,
}) => {
  test.setTimeout(180_000);
  const { account: orgAccount, session: org } = await createOrganizer(request);
  const event = await createEvent(request, org, { currency: 'KZT', price: '9000.00' });
  const { account: buyerAccount, session: buyer } = await createAttendee(request);
  const { registration, paymentId } = await buyFreedomPayTicket(request, buyer, event.id);

  // The organizer's proof is older than MFA_STEP_UP_MAX_AGE_SECONDS on the
  // test stack (45 s), so the refund asks for a fresh second factor.
  await waitUntilStepUpExpires(org);
  await openSignedIn(page, org, `/organizer/events/${event.id}/attendees`);
  await page.getByRole('button', { name: 'Refund', exact: true }).filter({ visible: true }).click();
  const since = new Date();
  await page.getByRole('button', { name: /^Refund \d/ }).click();

  const stepUp = page.getByRole('dialog', { name: "Confirm it's you" });
  await expect(stepUp).toBeVisible();
  await stepUp
    .getByLabel('Code', { exact: true })
    .fill(await freshTotp(orgAccount.username, orgAccount.totpSecret ?? ''));
  await stepUp.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('Refund issued.')).toBeVisible();

  // The money went back through the gateway and the ticket is void.
  const status = await json<Schemas['PaymentStatusResponse']>(
    await request.get(`/api/v1/payments/status/${paymentId}/`, { headers: bearer(buyer) }),
  );
  expect(status.status).toBe('refunded');
  expect(status.registration_id).toBe(registration.id);
  expect(status.registration_status).toBe('cancelled');
  const mail = await waitForMail(buyerAccount.email, (m) => /refund/i.test(m.subject), { since });
  expect(mail.text).toContain(event.title);

  // The attendee: the refund notification under the bell, and the ticket is
  // gone from My Tickets (cancelled registrations are not listed there).
  await openSignedIn(page, buyer, '/my-registrations');
  await expect(page.getByText('No tickets yet')).toBeVisible();
  await page.getByRole('button', { name: /^Notifications/ }).click();
  await expect(page.getByText(/refund/i).first()).toBeVisible();
});
