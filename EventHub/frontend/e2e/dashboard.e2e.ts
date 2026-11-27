import { expect, test, type Page } from '@playwright/test';
import {
  bearer,
  buyMockTicket,
  createAttendee,
  createEvent,
  createOrganizer,
  json,
  openSignedIn,
  Schemas,
  Session,
  uid,
} from './support/api';
import { collectErrors } from './support/ui';

/**
 * The organizer dashboard against the real backend: an organizer with more
 * events than one page holds sees every one of them, with the server's tab
 * counts, soonest first, and can copy an event into a draft.
 *
 * The organizer has 22 published events and one that still waits for admin
 * approval, so "Upcoming" holds 23. Only the first is in the next 7 days (for
 * the "soon" callout); the rest are two years out, so they never push the demo
 * events off the Discover page that other specs read (it lists the 12 soonest).
 */
test.describe.configure({ mode: 'serial' });

const PUBLISHED = 22;
/** Days ahead for everything but the one "soon" event: after any demo event. */
const FAR = 730;
const PAGE_SIZE = 20;

let organizer: Session;
let prefix: string;
/** Titles in the order the dashboard must list them: soonest first. */
let expectedTitles: string[];
/** The one event inside the next 7 days (the others are two years out). */
let nearEvent: Schemas['EventList'];

test.beforeAll(async ({ request }) => {
  test.setTimeout(300_000);
  organizer = (await createOrganizer(request)).session;
  prefix = uid('Dash ');
  expectedTitles = [];
  for (let day = 1; day <= PUBLISHED; day++) {
    const title = `${prefix} day ${String(day).padStart(2, '0')}`;
    const created = await createEvent(request, organizer, {
      title,
      daysAhead: day === 1 ? 1 : FAR + day,
    });
    if (day === 1) nearEvent = created;
    expectedTitles.push(title);
  }
  const waiting = `${prefix} waiting`;
  await createEvent(request, organizer, { title: waiting, daysAhead: FAR + 40, publish: false });
  expectedTitles.push(waiting);
});

const cards = (page: Page) => page.getByTestId('dashboard-event');
const titlesOf = async (page: Page) =>
  (await cards(page).locator('h3').allTextContents()).map((title) => title.trim());

test('lists every event across "Show more", soonest first, with the server counts', async ({
  page,
}) => {
  const errors = collectErrors(page);
  await openSignedIn(page, organizer, '/organizer/dashboard');

  // Tab counts and totals cover all events, not just the first page.
  await expect(page.getByRole('tab', { name: /^Upcoming\s*23$/ })).toBeVisible();
  await expect(page.getByRole('tab', { name: /^Past\s*0$/ })).toBeVisible();
  await expect(page.getByRole('tab', { name: /^Drafts\s*0$/ })).toBeVisible();
  await expect(page.getByRole('tab', { name: /^Inactive\s*0$/ })).toBeVisible();
  await expect(page.getByTestId('kpi-events')).toHaveText('23');
  await expect(page.getByTestId('callout-approval')).toHaveText(/1 event awaiting approval/);
  await expect(page.getByTestId('callout-soon')).toBeVisible();

  // First page: 20 events, the soonest first, and the counter says so.
  await expect(cards(page)).toHaveCount(PAGE_SIZE);
  await expect(page.getByTestId('list-counter')).toHaveText('20 of 23');
  await expect(page.getByTestId('live-region')).toHaveText('Upcoming: showing 20 of 23 events');
  expect(await titlesOf(page)).toEqual(expectedTitles.slice(0, PAGE_SIZE));

  // "Show more" appends the rest, none missing, none twice.
  await page.getByTestId('show-more').click();
  await expect(cards(page)).toHaveCount(23);
  await expect(page.getByTestId('list-counter')).toHaveText('23 of 23');
  await expect(page.getByTestId('show-more')).toHaveCount(0);
  expect(await titlesOf(page)).toEqual(expectedTitles);

  // Each card shows its own numbers and a translated status.
  const first = cards(page).first();
  await expect(first.getByTestId('status-badge')).toHaveText('Published');
  await expect(first.getByTestId('tickets-sold')).toHaveText('0');
  await expect(first.getByTestId('capacity-label')).toHaveText('0% sold');
  await expect(cards(page).last().getByTestId('status-badge')).toHaveText('Pending approval');

  expect(errors).toEqual([]);
});

test('keeps tab and search in the URL, and restores them on reload', async ({ page }) => {
  await openSignedIn(page, organizer, '/organizer/dashboard');
  await expect(cards(page)).toHaveCount(PAGE_SIZE);

  // Another tab: its own list (empty here), URL updated, list reset.
  await page.getByRole('tab', { name: /^Drafts/ }).click();
  await expect(page).toHaveURL(/[?&]tab=drafts\b/);
  await expect(page.getByTestId('list-empty')).toContainText('No drafts');
  await expect(page.getByTestId('empty-create')).toBeVisible();

  // Search is applied by the server, after the typing pauses.
  await page.getByRole('tab', { name: /^Upcoming/ }).click();
  await page.getByTestId('dashboard-search').fill(`${prefix} day 07`);
  await expect(cards(page)).toHaveCount(1);
  await expect(page).toHaveURL(/[?&]search=/);
  await expect(page.getByTestId('list-counter')).toHaveText('1 of 1');

  await page.reload();
  await expect(page.getByTestId('dashboard-search')).toHaveValue(`${prefix} day 07`);
  await expect(cards(page)).toHaveCount(1);
  await expect(cards(page).first().locator('h3')).toHaveText(`${prefix} day 07`);

  // No match: a clear message and a way out.
  await page.getByTestId('dashboard-search').fill(`${prefix} no such event`);
  await expect(page.getByTestId('list-empty')).toContainText('No events match');
  await page.getByTestId('clear-search').click();
  await expect(cards(page)).toHaveCount(PAGE_SIZE);
});

test('sorts by the chosen column, and the tab default is selected', async ({ page }) => {
  await openSignedIn(page, organizer, '/organizer/dashboard');
  const sort = page.getByTestId('dashboard-sort');
  await expect(sort).toHaveValue('date');

  await sort.selectOption('-date');
  await expect(page).toHaveURL(/[?&]ordering=-date\b/);
  await expect(cards(page).first().locator('h3')).toHaveText(`${prefix} waiting`);
});

test('Duplicate makes a draft copy and opens its edit page', async ({ page, request }) => {
  // Its own organizer and event, named for this run: the other tests never see
  // a draft, and a retry of this test copies its own event again instead of
  // depending on (or disturbing) what an earlier attempt left behind.
  const solo = (await createOrganizer(request)).session;
  const title = uid('Dash source ');
  const source = await createEvent(request, solo, { title, daysAhead: FAR + 3 });
  await openSignedIn(page, solo, '/organizer/dashboard');
  await expect(page.locator(`#dashboard-event-title-${source.id}`)).toHaveText(title);

  await page.getByRole('button', { name: `Menu for ${title}`, exact: true }).click();
  await expect(page.getByRole('menu')).toBeVisible();
  const [cloned] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes(`/events/${source.id}/clone/`),
    ),
    page.getByRole('menuitem', { name: 'Duplicate' }).click(),
  ]);
  // The copy is known by the id the server gave it, whatever else exists.
  const copyId = ((await cloned.json()) as { id: number }).id;
  await expect(page).toHaveURL(new RegExp(`/edit-event/${copyId}$`));

  // The copy is a draft with the "(copy)" title, owned by the same organizer.
  const copy = await json<Schemas['EventList']>(
    await request.get(`/api/v1/events/${copyId}/`, { headers: bearer(solo) }),
  );
  expect(copy.id).toBe(copyId);
  expect(copy.title).toBe(`${title} (copy)`);
  expect(copy.status).toBe('draft');

  // And the Drafts tab lists that very copy (found by id and exact title).
  await page.goto(
    `/organizer/dashboard?tab=drafts&search=${encodeURIComponent(`${title} (copy)`)}`,
  );
  await expect(page.locator(`#dashboard-event-title-${copyId}`)).toHaveText(`${title} (copy)`);
  await expect(
    page
      .locator(`article[aria-labelledby="dashboard-event-title-${copyId}"]`)
      .getByTestId('status-badge'),
  ).toHaveText('Draft');
});

test('"Today & this week" shows the event starting soon, with working links', async ({ page }) => {
  const errors = collectErrors(page);
  await openSignedIn(page, organizer, '/organizer/dashboard');

  // The block holds the one event inside the next 7 days, and none of the far ones.
  const today = page.getByTestId('today');
  await expect(today).toBeVisible();
  await expect(today.getByRole('heading', { name: 'Today & this week' })).toBeVisible();
  const row = today.getByTestId('today-event').filter({ hasText: expectedTitles[0] });
  await expect(row).toHaveCount(1);
  await expect(today.getByText(expectedTitles[1])).toHaveCount(0);
  await expect(row.getByTestId('today-countdown')).toHaveText(/^Starts in \d+ (d|h|min)/);
  await expect(row.getByTestId('today-sold')).toHaveText('0 of 50 tickets sold');
  await expect(row.getByTestId('today-checked-in')).toHaveText('0 checked in');
  await expect(row.getByTestId('today-title')).toHaveAttribute('href', `/events/${nearEvent.id}`);

  // Nothing is beyond the ten the block shows.
  await expect(today.getByTestId('today-more')).toHaveCount(0);

  // Attendees and check-in lists open the event's own pages.
  await expect(row.getByTestId('today-checkin-lists')).toHaveAttribute(
    'href',
    `/organizer/events/${nearEvent.id}/checkin-lists`,
  );
  await row.getByTestId('today-attendees').click();
  await expect(page).toHaveURL(new RegExp(`/organizer/events/${nearEvent.id}/attendees$`));

  // Scan opens the scanner.
  await page.goBack();
  await expect(page.getByTestId('today')).toBeVisible();
  await page
    .getByTestId('today')
    .getByTestId('today-event')
    .filter({ hasText: expectedTitles[0] })
    .getByTestId('today-scan')
    .click();
  await expect(page).toHaveURL(/\/scan$/);
  expect(errors.filter((e) => !/camera|getUserMedia|NotAllowed|NotFound/i.test(e))).toEqual([]);
});

test('the sales chart, ticket types and reviews show what this organizer sold', async ({
  page,
  request,
}) => {
  test.setTimeout(180_000);
  // Its own organizer and a USD event, so the totals are exactly what this run sold
  // (mock payments confirm the ticket at once) and a retry starts from nothing.
  const solo = (await createOrganizer(request)).session;
  const title = uid('Dash sales ');
  const event = await createEvent(request, solo, {
    title,
    currency: 'USD',
    price: '25.00',
    daysAhead: FAR + 5,
  });
  for (let i = 0; i < 2; i++) {
    await buyMockTicket(request, (await createAttendee(request)).session, event.id);
  }

  const analytics: string[] = [];
  page.on('request', (r) => {
    if (r.url().includes(`/events/${event.id}/analytics/`)) analytics.push(r.url());
  });
  const todayAnswer = page.waitForResponse((r) => r.url().includes('/api/v1/organizer/today/'));
  const errors = collectErrors(page);
  await openSignedIn(page, solo, '/organizer/dashboard');
  await todayAnswer;

  // Chart: the 30-day totals are this run's two tickets and their $50.00.
  await expect(page.getByTestId('chart')).toBeVisible();
  await expect(page.getByTestId('chart-total-tickets')).toHaveText('2');
  await expect(page.getByTestId('chart-total-revenue')).toHaveText('$50.00');
  await expect(page.getByTestId('chart-ticket-bar')).toHaveCount(1);
  await expect(page.getByTestId('chart-revenue-bar')).toHaveCount(1);
  await expect(page).toHaveURL(/\/organizer\/dashboard$/);
  await expect(page.getByRole('radio', { name: '30 days' })).toHaveAttribute(
    'aria-checked',
    'true',
  );

  // The keyboard reads a day out: the latest one is where the sales are.
  await page.getByTestId('chart-scroll').focus();
  await expect(page.getByTestId('chart-readout')).toContainText('2 tickets');
  await expect(page.getByTestId('chart-readout')).toContainText('$50.00 net revenue');

  // The same numbers as a table, with the totals row.
  await page.getByTestId('chart-table-toggle').click();
  const footer = page.getByTestId('chart-table').locator('tfoot');
  await expect(footer).toContainText('Total');
  await expect(footer).toContainText('2');
  await expect(footer).toContainText('$50.00');
  await expect(page.getByTestId('chart-table-row')).toHaveCount(30);

  // The range toggle: arrow keys move it, the URL follows, the totals are the same.
  const thirty = page.getByRole('radio', { name: '30 days' });
  await thirty.focus();
  await page.keyboard.press('ArrowLeft');
  await expect(page).toHaveURL(/[?&]range=7d\b/);
  await expect(page.getByRole('radio', { name: '7 days' })).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByTestId('chart-table-row')).toHaveCount(7);
  await expect(page.getByTestId('chart-total-tickets')).toHaveText('2');
  await page.reload();
  await expect(page.getByRole('radio', { name: '7 days' })).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByTestId('chart-total-revenue')).toHaveText('$50.00');
  await page.getByRole('radio', { name: '30 days' }).click();
  await expect(page).not.toHaveURL(/range=/);

  // Reviews: nobody has reviewed this organizer's events yet.
  await expect(page.getByTestId('reviews-empty')).toContainText('No reviews yet');

  // Nothing starts within a week, so there is no "Today & this week" block.
  await expect(page.getByTestId('today')).toHaveCount(0);

  // Ticket types are fetched when the section is opened, once.
  const card = page.locator(`article[aria-labelledby="dashboard-event-title-${event.id}"]`);
  await expect(card).toBeVisible();
  expect(analytics).toHaveLength(0);
  const toggle = card.getByTestId('ticket-types-toggle');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  const row = card.getByTestId('ticket-types-row');
  await expect(row).toHaveCount(1);
  await expect(row.locator('th')).toHaveText('General');
  await expect(row.getByTestId('ticket-types-sold')).toHaveText('2');
  await expect(row.getByTestId('ticket-types-left')).toHaveText('Unlimited');
  await expect(row.getByTestId('ticket-types-revenue')).toHaveText('$50.00');
  await toggle.click();
  await toggle.click();
  await expect(row).toHaveCount(1);
  expect(analytics).toHaveLength(1);

  // A narrow phone: the chart scrolls inside its box, the page does not.
  await page.setViewportSize({ width: 375, height: 800 });
  const overflow = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    chart: (() => {
      const box = document.querySelector('[data-testid="chart-scroll"]');
      return box ? box.scrollWidth - box.clientWidth : -1;
    })(),
  }));
  expect(overflow.page).toBeLessThanOrEqual(0);
  expect(overflow.chart).toBeGreaterThan(0);

  expect(errors).toEqual([]);
});

test('an organizer with no sales sees an empty chart, and a card whose tiers are still empty', async ({
  page,
  request,
}) => {
  const fresh = (await createOrganizer(request)).session;
  const title = uid('Dash quiet ');
  const event = await createEvent(request, fresh, { title, daysAhead: FAR + 6 });
  await openSignedIn(page, fresh, '/organizer/dashboard?range=90d');

  await expect(page.getByTestId('chart-empty')).toHaveText('No sales in the last 90 days');
  await expect(page.getByRole('radio', { name: '90 days' })).toHaveAttribute(
    'aria-checked',
    'true',
  );
  await expect(page.getByTestId('chart')).toHaveCount(0);
  await expect(page.getByTestId('reviews-empty')).toBeVisible();
  await expect(page.getByTestId('today')).toHaveCount(0);

  const card = page.locator(`article[aria-labelledby="dashboard-event-title-${event.id}"]`);
  await card.getByTestId('ticket-types-toggle').click();
  await expect(card.getByTestId('ticket-types-empty')).toHaveText('No tickets sold yet.');
});
