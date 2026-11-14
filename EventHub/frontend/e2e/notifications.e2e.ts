import { expect, test } from '@playwright/test';
import {
  bearer,
  buyFreedomPayTicket,
  buyMockTicket,
  createAttendee,
  createEvent,
  createOrganizer,
  json,
  openSignedIn,
  Schemas,
  waitUntilStepUpExpires,
} from './support/api';
import { waitForMail } from './support/mail';
import { freshTotp } from './support/totp';

/**
 * Notifications (docs/NOTIFICATIONS.md): the e-ticket email after a
 * purchase, email preferences that persist, and the cancellation notice to
 * every ticket holder. Emails are read from the worker's console backend.
 */

test('a purchase produces the e-ticket email and the in-app notification', async ({
  page,
  request,
}) => {
  const { session: org } = await createOrganizer(request);
  const event = await createEvent(request, org, { currency: 'USD', price: '12.00' });
  const { account, session: buyer } = await createAttendee(request);
  await buyMockTicket(request, buyer, event.id);

  const mail = await waitForMail(
    account.email,
    (m) => m.subject === `Your ticket for ${event.title}`,
  );
  // HTML + plain text, the ticket QR inline, the preferences link in the footer.
  expect(mail.html).toContain('cid:ticket-qr-');
  expect(mail.inlineIds.some((id) => id.startsWith('ticket-qr-'))).toBe(true);
  expect(mail.text).toContain(event.title);
  expect(mail.text).toContain('/profile/notifications');

  await openSignedIn(page, buyer, '/');
  await page.getByRole('button', { name: /^Notifications/ }).click();
  await expect(page.getByText(event.title).first()).toBeVisible();
});

test('turning an email type off persists across reloads and in the API', async ({
  page,
  request,
}) => {
  const { session } = await createAttendee(request);
  await openSignedIn(page, session, '/profile/notifications');

  const reminder = page.getByRole('checkbox', { name: 'Email: Event reminder' });
  await expect(reminder).toBeChecked();
  const [saved] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/auth/profile/notifications/') && r.request().method() === 'PATCH',
    ),
    reminder.uncheck(),
  ]);
  expect(saved.status()).toBe(200);
  await expect(page.getByText('Event reminder: emails off.')).toBeAttached();

  await page.reload();
  await expect(page.getByRole('checkbox', { name: 'Email: Event reminder' })).not.toBeChecked();
  // Mandatory types cannot be switched off.
  await expect(page.getByRole('checkbox', { name: 'Email: Event cancelled' })).toBeDisabled();

  const prefs = await json<Schemas['NotificationPreferences']>(
    await request.get('/api/v1/auth/profile/notifications/', { headers: bearer(session) }),
  );
  const row = prefs.types.find((t) => t.type === 'event_reminder');
  expect(row?.email_enabled).toBe(false);
  const refused = await request.patch('/api/v1/auth/profile/notifications/', {
    headers: bearer(session),
    data: { email: { event_cancelled: false } },
  });
  expect(refused.status()).toBe(400);
});

test('cancelling an event refunds and notifies every ticket holder', async ({ page, request }) => {
  test.setTimeout(180_000);
  const { account: orgAccount, session: org } = await createOrganizer(request);
  const event = await createEvent(request, org, { currency: 'KZT', price: '5000.00' });
  const holders = [await createAttendee(request), await createAttendee(request)];
  for (const holder of holders) await buyFreedomPayTicket(request, holder.session, event.id);

  // Cancelling is a sensitive action: once the proof is stale, step-up.
  await waitUntilStepUpExpires(org);
  await openSignedIn(page, org, `/organizer/events/${event.id}/settings`);
  await page.getByRole('button', { name: 'Danger', exact: true }).click();
  await page.getByRole('button', { name: /Cancel event & refund attendees/ }).click();
  const since = new Date();
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel event', exact: true }).click();
  const stepUp = page.getByRole('dialog', { name: "Confirm it's you" });
  await stepUp
    .getByLabel('Code', { exact: true })
    .fill(await freshTotp(orgAccount.username, orgAccount.totpSecret ?? ''));
  await stepUp.getByRole('button', { name: 'Confirm' }).click();
  await expect(
    page.getByText(/Event cancelled — 2 attendees notified, 2 refunds issued/),
  ).toBeVisible();

  for (const { account, session: holder } of holders) {
    const mail = await waitForMail(
      account.email,
      (m) => m.subject === `Cancelled: ${event.title}`,
      {
        since,
      },
    );
    expect(mail.text).toMatch(/refund/i);
    const notifications = await json<Schemas['PaginatedNotificationList']>(
      await request.get('/api/v1/notifications/', { headers: bearer(holder) }),
    );
    expect(notifications.results.some((n) => n.title.includes(event.title))).toBe(true);
  }

  // Public page: sales are closed.
  await page.goto(`/events/${event.id}`);
  await expect(page.getByText(/cancelled/i).first()).toBeVisible();
});
