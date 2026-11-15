# "Concept A" redesign: implementation plan

## Agent Entry

- Purpose: file-level implementation plan for the editorial redesign of the Discover page and the Event page ("Concept A"), with the bugs folded into it.
- Read when: starting or continuing any redesign phase, or changing the shell, home page, event card or event page.
- Skip when: working on backend-only or organizer-only features.
- Canonical: Yes, until the redesign is merged; then fold the outcome into `HANDOFF.md`.
- Read next: `design-mockups/` (repository root), `I18N.md`, `TEST_REPORT.md`.

Date: 2026-11-14. Read on `integration/phase-2-4` @ `975a923`. `FE/` = `EventHub/frontend/src/app/`, `BE/` = `EventHub/backend/`. Anything that was not read in the code is marked UNVERIFIED.

## 0. Findings that change the brief

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| 1 | One registration is one ticket; there is no quantity. | `RegisterRequestRequest` has `ticket_type_id`, `seat_id`, promo, donation, answers, notes only (`FE/api/openapi.ts:3312`) | No steppers and no "Total for 2 tickets". Several seats means the group flow. |
| 2 | The "₸0" bug is the card printing `event.price`, not `price_from`. | `event-card.component.ts:138-142`; `is_free` is tier-aware (`BE/events/models.py:157-168`) | Fix by using `price_from`; zero means Free. |
| 3 | The `is_free=true` filter is `price=0` on the base price. | `BE/events/views/events.py:173-174` | Paid tiered events with base price 0 leak into "Free". Backend fix B1. |
| 4 | There is no event time zone. | `Event` fields (`models.py:70-112`); `localDate` formats in the browser zone (`FE/i18n/locale.pipes.ts:19`) | "Almaty time" label is not supported. |
| 5 | `page_size` is not supported on `/events/`; page size is fixed at 12. | `settings.py:208-209`, no `page_size_query_param` on the viewset | The mosaic and the hero take slices of a 12-item page. |
| 6 | Recommendations are empty without embeddings. | `recommendations.py:25-50` filters `embedding__isnull=False` | The rail is hidden on the slim QA/e2e image; the hero rule cannot depend on it. |
| 7 | No seed creates an event image. | no `image` in `seed_data.py`, `seed_demo_kz.py`, `seed_showcase.py` | The demo and e2e stacks always show the fallback hero unless images are seeded (Q1). |
| 8 | Seat persistence is server-side: a pending registration holding the seat. | no client storage of seats; `e2e/business-rules.e2e.ts:39-55` | The "Payment incomplete / Complete payment / Release seat" state must survive the redesign as is. |
| 9 | "City" is a substring of the free-text venue field. | `location__icontains` (`events.py:177-178`); seeds have `'KBTU, Almaty'` and `'Astana Hub'` | A city select cannot be reliable; "Tonight" has no date filter behind it. |
| 10 | Home always sends `upcoming=true`. | `home.component.ts:472` | The mockup's "Upcoming" chip has no off state (Q3). |
| 11 | Dark text `#1A120D` on `#E8643A` is about 5.6:1 by hand calculation, not ~7:1; white is 3.3:1. | computed, not tool-checked | Still passes AA, so the rule stands. Re-check with a tool in phase 1. |
| 12 | There are 7 e2e spec files with 23 tests, run at Desktop Chrome 1280×720. | `e2e/*.e2e.ts`, `playwright.config.ts:28` | E2e runs exactly at the desktop breakpoint. |
| 13 | `GET /favorites/` is paginated at 12 and the client reads only page 1. | `engagement.py:23-30`, `event.service.ts:152-154` | Card hearts need an ids source (B2). |
| 14 | CSP is `font-src 'self'; img-src 'self' data: blob:`. | `nginx-security-headers.conf:11` | Fonts must be self-hosted; no map iframes or remote images. |
| 15 | Theme toggle, profile link and sign-out exist only in the sidebar footer; the topbar search is a stub. | `sidebar.component.ts:148-208`, `topbar.component.ts:91-99` | The top nav must take these over. |
| 16 | The capacity bar has a typo class `'bg-[color:var(--pine-50)]0'`. | `event-detail.component.ts:527` | The bar is invisible under 50%. Fix in phase 0. |
| 17 | No backend test covers a non-organizer creating an event. | only `test_create_event` as organizer (`BE/events/tests.py:76`) | Add in phase 0. |

## 1. Audit summary

### Frontend today

| Piece | Today | Where |
|---|---|---|
| Shell | One `<router-outlet>` that must stay single; sidebar + topbar + footer unless a bare route | `layout/app-shell.component.ts:11-47` |
| Nav config | Sections `main`, `organize`, `event-context`, `admin` with roles | `layout/nav.config.ts:51-157` |
| Roles | organizer = `is_staff` or `is_superuser` or `profile.role === 'organizer'`; admin = `is_superuser` | `sidebar.component.ts:267-269`, `guards/role.guard.ts:23-26` |
| Routes | `/my-events` has `authGuard` only. Event-scoped organizer pages are `authGuard` on purpose (co-organizers are attendee accounts). | `app.routes.ts:91-95`, `role.guard.ts:7-12` |
| Home | Text hero, search + AI toggle, location input, sort select, Free/Online chips, sticky category chips, recommended row, grid with fake featured first card, load more | `home.component.ts:43-303`, `:281-283`, `:468-483` |
| Card | Used only by Home. 16:9 image, letter placeholder, perforation, date block, no favorite button | `event-card.component.ts:23-157` |
| Event page | Banners, 16:7 hero, info grid, organizer, description, reviews, sticky price card with an 11-branch state chain, modals | `event-detail.component.ts:98-170`, `:535-825`, `:858-881` |
| Checkout modal | Owns tier, seat (`app-seat-selector`), promo, donation, questions, notes; emits the payload | `event-checkout-modal.component.ts:278-283`, `:648-684` |
| Group booking | Separate page `/events/:id/group`; link shown only when `!is_free && !has_ticket_types` | `app.routes.ts:20-28`, `event-detail.component.ts:816-824` |
| Footer | Organizer column for everyone; "Discover" links are keyword searches for hard-coded English words | `footer.component.ts:108-142`, `:369-375` |
| Tokens | CSS variables in `:root` and `.dark`, bridged to Tailwind. Light primary is `#c2410c` with white text. | `styles.css:62-186`, `tailwind.config.js:7-36` |
| Fonts | Self-hosted Clash Display, Satoshi, JetBrains Mono. Cyrillic coverage is UNVERIFIED (no font tooling was available). | `styles.css:9-57`, `index.html:49-69`, `tailwind.config.js:38-42` |
| Logo | `symbol.svg` and `favicon.svg` are mask-based; `.ember-mark` is a CSS background | `assets/brand/symbol.svg`, `styles.css:412-418`, `sidebar.component.ts:46,57` |
| Theme | `dark` class on `<html>`, `eh-theme`, defaults to the OS preference | `services/theme.service.ts` |

### API (verified)

`GET /api/v1/events/` (`BE/events/views/events.py:116-192`):

| Param | Behaviour |
|---|---|
| `upcoming=true` | `date >= now` |
| `category=<id>` | exact category |
| `is_free=true` | base `price = 0` (see finding 3) |
| `is_online=true` | online only; ANDed with the other filters |
| `location=<text>` | `location__icontains`; does not search `address` |
| `search=<text>` | DRF SearchFilter over `title`, `description`, `location` |
| `q=<text>` | semantic search, limit 40, falls back to keyword on error |
| `ordering` | `date`, `price`, `created_at`, each with `-`; default is `-date` |
| `page` | page number, 12 per page |
| `status` | defaults to published |

Not available: date range, featured or popularity, city field, `page_size`.

Other endpoints the redesign uses:

- **Recommendations:** `GET /api/v1/recommendations/` (`urls.py:15`, `events.py:675-693`). Signed-in only, up to 10 upcoming published events, excludes events the user is registered for, `EventList` shape.
- **Categories:** `GET /categories/`, unpaginated, with `icon` and `event_count` (`openapi.ts:2110-2117`). Seeded icons: `music`, `laptop`, `briefcase`, `book`, `trophy`, `theater`.
- **Seat map and pricing:** `GET /events/:id/seat_map/` (404 means general admission) returns `zone_prices`; `GET /events/:id/pricing/` returns the real dynamic price and `demand_level`.
- **Favorites:** `GET/POST /favorites/:id/` and the paginated `GET /favorites/`.
- **Other event-page flows:** waitlist, queue, `request-refund`, reviews and questions already have service methods (`event.service.ts:115-342`).

## 2. Data mapping

| Mockup element | Source | Status |
|---|---|---|
| Hero event, thumbnails | `/events/?upcoming=true&ordering=date`, recommendations first when present | Supported (rule in phase 3) |
| Kicker "Theatre · Opera" | `category.name` | One category only; no subcategory |
| Kicker "Soon" | `date` within 7 days | Derived |
| Hero date, venue | `date`, `location` | Supported, viewer's zone |
| "from 9 000 ₸" | `price_from`, `currency`, `money: 'short'` | Supported; "from" wording is Q6 |
| "Buy ticket", "Details" | link to `/events/:id` | Supported; no checkout from Home |
| CITY | `location=` free text | Text input, not a select (Q2) |
| Free, Online chips | `is_free`, `is_online` | Supported |
| "Upcoming" chip | always on | Replace with the sort control (Q3) |
| Category chips, "+N more" | `/categories/`, `category=<id>` | Supported |
| Search + AI | `search=` or `q=` | Supported |
| "Recommended for you" | `/recommendations/` | Supported; hidden when empty |
| "Tonight in Almaty" | none | "Tonight" not supported; becomes "In <city>" using `location=` |
| "Free & online" | two requests merged by id | Supported as a union |
| Category rails | `category=<id>` for the top categories by `event_count` | Supported |
| Card date pill, title, venue | `date`, `title`, `location` | Supported |
| "12 seats left", "Sold out" | `available_spots` | Supported |
| Card heart | favorites | Needs B2 for correct state beyond 12 |
| Cover fallback | `category.icon` | Supported, client-side |
| Thumbnail gallery | none | Not supported; single `image` |
| "Almaty time" | none | Not supported; show the viewer's GMT offset |
| Time range | `date`, `end_date` | Supported |
| Seating row | `seat_map.zone_prices` | Supported when a seat map exists |
| "Refund until start" | `refundable` boolean only | Show Refundable or Non-refundable |
| Tabs About / Location / Reviews | `description`; `location` + `address`; reviews component | Supported; no map embed (CSP) |
| Organizer "KazOpera Events" | `organizer.first_name`, `last_name`, `username` | No brand name, avatar or profile page |
| Zone rows with prices | `zone_prices` | Supported, read-only |
| Quantity steppers, total | none | Not supported |
| Ticket / Group switch | existing group page link | Supported where the link shows today |
| "Choose seats on the map" | existing checkout modal with the seat selector | Supported; single seat, so keep "Choose a seat" |
| "Freedom Pay · QR or card" | provider is chosen by currency server-side | Show only for KZT events; UNVERIFIED how the client learns the provider before checkout |

## 3. Phases

### Phase 0: bugs (1.5 days)

- **Role-aware footer.** In `footer.component.ts`, show the Organizer column only to organizers and admins, and replace the four hard-coded Discover links with real categories from `/categories/`.
- **Guard.** `/my-events` gets `roleGuard('organizer')` in `app.routes.ts`. Leave event-scoped pages and `/scan` as they are.
- **Backend tests** in `BE/events/tests.py`: attendee `POST /events/` returns 403; attendee `GET /events/:id/stats/` returns 403; attendee `GET /admin-dashboard/` returns 403 (UNVERIFIED whether that last one already exists). `GET /my-events/` stays 200 with an empty list.
- **Zero price.** Card and event page use `price_from`; zero shows Free.
- **Fake featured.** Remove `[featured]="$first"` and the col-span classes (`home.component.ts:281-283`), the `featured` input and the `event.featured` key in all three catalogs.
- **Venue overflow.** Add `min-w-0` to the location flex row (`event-card.component.ts:108-115`); the full fix lands with the new card.
- **Logo.** Redraw `symbol.svg` and `favicon.svg` as plain paths with `fill-rule="evenodd"`, replace `.ember-mark` with `<img>`, add `?v=2` to icon URLs in `index.html` and `site.webmanifest`, regenerate the PNGs and `favicon.ico`. Remove the duplicate `theme-color` meta (`index.html:19,46`).
- **Capacity bar typo** (finding 16).
- **Tests:** a new `footer.component.spec.ts` (guest, attendee, organizer), a route test for `/my-events`, a card spec for the price label.
- **Risk:** low. E2e is unaffected.
- **Done when:** an attendee sees no organizer links anywhere and `/my-events` redirects to `/`.

### Phase 1: tokens, fonts, both themes (2 days)

- **Tokens.** Keep the existing variable names so Tailwind classes keep working; change values.

| Token | Dark | Light (proposed) |
|---|---|---|
| `--background` | `#121110` | `#FAF7F2` |
| `--surface-sunken` | `#171513` | `#F2ECE3` |
| `--surface`, `--card`, `--popover`, `--input` | `#1E1B18` | `#FFFFFF` |
| `--surface-elevated` (new), `--muted`, `--secondary` | `#26221E` | `#F2ECE3` |
| `--border` | `#2F2A25` | `#ECE6DD` |
| `--foreground` | `#F5F1EA` | `#1A1714` |
| `--text-secondary` (new) | `#A8A29A` | `#5F574E` |
| `--muted-foreground` | `#969088` (was `#7D776F`, see below) | `#6B6259` |
| `--primary`, `--accent` | `#E8643A` | `#E8643A` |
| `--primary-hover` (new) | `#F07A53` | `#D95A32` |
| `--primary-foreground` | `#1A120D` | `#1A120D` |
| `--accent-text` (new, for links and kickers) | `#F07A53` | `#B93D0B` (was `#C2410C`, see below) |

- **Contrast (done 2026-11-15, computed and enforced by `src/app/design-tokens.spec.ts`).** `#7D776F` measured 3.56–3.87:1 on dark cards, and `--muted-foreground` is used for body-size text everywhere, so it became `#969088` (≥ 5:1) instead of sweeping every use. `#C2410C` measured 4.41:1 on the light muted surface, so `--accent-text` became `#B93D0B` (≥ 4.8:1). `text-primary`, `text-ember` and `text-accent` map to `--accent-text` in `tailwind.config.js` (fills keep `#E8643A`). `--warning-foreground` is dark in both themes (white on `#B8761F` is 3.7:1). `text-white` on ember fixed in `home.component.ts:91`; status pills and badges use the `*-foreground` tokens.
- **Fonts.** Self-host Onest as a variable woff2 for headings and body, keep JetBrains Mono for codes only, remove Clash Display and Satoshi and their preloads. Before committing, verify the file covers Latin, Cyrillic, `ә ғ қ ң ө ұ ү һ і` and `₸`.
- **Motion.** Keep the existing reduced-motion block (`styles.css:348`); new animations must respect it.
- **Files:** `styles.css`, `tailwind.config.js`, `index.html`, `assets/fonts/`.
- **Tests:** a small spec that both theme blocks define every token; manual screenshots of five pages in both themes.
- **Risk:** every page changes colour at once. Phase 5 is the clean-up.

### Phase 2: shell and navigation (3 days)

- **Layouts.** `AppShellComponent` keeps the single outlet and computes `layout` from the URL:
  - `workspace` (sidebar + topbar, as today): `/organizer/*`, `/my-events`, `/create-event`, `/edit-event/*`, `/scan`, `/validate/*`, `/admin/*`.
  - `bare`: unchanged list.
  - `consumer` (new top nav): everything else.
- **New `layout/top-nav.component.ts`.** Logo, Discover, My Tickets and Favorites (signed in), language switcher, search button (focuses the Discover search field, navigating to `/` first if needed), bell (move the dropdown out of the topbar into a shared `notification-bell.component.ts`), avatar menu.
- **Avatar menu** (shared `account-menu.component.ts`, also used by the workspace topbar): Profile, My Bookings, Security, Notification settings, Organizer area (organizers), Admin (admins), theme toggle, Sign out. Guests get a "Sign in" button and a theme toggle. Add a `roles.ts` helper so the role rule stops being copied in three places.
- **No duplicates.** In `workspace`, the sidebar keeps Organize, Event and Admin plus one "Back to Discover" item; profile and sign-out move to the avatar menu.
- **Transparent state** only on `/` while the hero is in view (IntersectionObserver sets a `LayoutService` signal); solid elsewhere and after scrolling.
- **Mobile (<768).** Top bar with logo, bell and menu button; bottom tab bar with Discover, Tickets, Favorites, Profile. The tab bar is hidden on `/events/:id`, where the purchase bar takes that slot. The menu sheet uses the existing `appDialog` directive.
- **i18n keys:** `nav.accountMenu` ("Account menu, {{ name }}"), `nav.organizerArea`, `nav.adminArea`, `nav.security`, `nav.notificationSettings`, `nav.backToDiscover`, `nav.openMenu`, `nav.tabTickets`, `nav.tabProfile`. The mockup uses "Афиша" for Discover in Russian; changing `nav.discover` means updating `i18n.e2e.ts:15`.
- **Accessibility:** a skip link, `<nav aria-label>`, menu with `aria-expanded`, Escape and arrow keys, focus returned to the trigger, 44px touch targets.
- **E2e updates:**
  - `i18n.e2e.ts:34` looks for `role=complementary`; change it to the banner's navigation.
  - `support/ui.ts:39-41` signs out through a button named by username; keep the username in the avatar button's label.
  - The bell must keep a name starting with "Notifications" (`payments.e2e.ts:187`, `notifications.e2e.ts:43`).
- **Risk:** the post-login navigation bug the single outlet protects against (`app-shell.component.ts:17`). Do not add a second outlet.
- **Done 2026-11-15.** Files: `layout/top-nav`, `tab-bar`, `account-menu`, `notification-bell`, `account-links.ts` (links + `SignOutService`), `app-shell` (`shellLayout()`), slimmed `sidebar`/`topbar`, `nav.config` (one "Back to Discover" item). Notes:
  - The account menu is a disclosure (button with `aria-expanded` + links/buttons), not `role="menu"`: `support/ui.ts` finds the trigger by username and "Sign Out" as a button, so it works unchanged. Arrow keys, Home/End and Escape (focus back to the trigger) are implemented.
  - The transparent-over-hero state moves to phase 3, where the hero exists.
  - ⌘K / Ctrl+K and the search button focus `#discover-search`, going to `/` first.
  - Q8 applied: Russian `nav.discover` is "Афиша"; `i18n.e2e.ts` now reads the banner's navigation.
  - Not covered by e2e yet: the e2e suite was not run after this phase.

### Phase 3: Discover (5–6 days)

- **New files under `components/home/`:** `discover-hero.component.ts`, `filter-bar.component.ts`, `filter-sheet.component.ts`, `event-rail.component.ts`, `category-cover.ts`; plus `services/favorites.store.ts`. `home.component.ts` keeps `buildParams` and the load-more logic.
- **Filter state in the URL** (`?q=&ai=1&city=&category=&free=1&online=1&sort=`), additive to the `/` route, so filters survive back navigation and "All" links work. `SearchService` stays as the bridge for the footer and the nav search.
- **Hero rule.**
  1. Pool = recommendations (signed in, if any) followed by page 1 of `upcoming=true&ordering=date`, de-duplicated.
  2. Keep events with `image` and `available_spots > 0`; take the first four: one hero and three thumbnails.
  3. If none has an image, show a category-styled hero for the first upcoming event.
  4. If there are no events, show a brand hero with the existing headline keys and no call to action.
  5. An image load error switches that event to its category cover.
- **Hero behaviour:** no autoplay; thumbnails are buttons with `aria-pressed`, arrow keys move between them, and the title sits in an `aria-live="polite"` region.
- **Filter bar.** City text input, Free and Online chips, sort select, category chips with a "+N more" popover, search with the AI toggle, search button. One row at ≥1280, two rows at 768–1279, a single "Filters" button with a count that opens the sheet below 768 while category chips scroll horizontally.
- **Rails,** shown only when no filter is active (same rule as today's recommended row, `home.component.ts:214`); each hides itself when empty and loads when it scrolls near the viewport:
  - Recommended: horizontal scroll with arrow buttons and scroll-snap.
  - City: mosaic of the first five results, only when a city is set.
  - Free & online: union of two requests.
  - Up to two category rails.
  - "All events" grid with load more, always present, with `id="all-events"`; this is where filtered results appear.
- **Card contract.** `event` (required), `variant: 'portrait' | 'wide'`, `favorited: boolean`, output `favoriteToggle`.
  - Structure: an `<article>` with a stretched link whose label is the existing `event.viewDetailsFor`, and a sibling favorite `<button aria-pressed>`.
  - Favorite click as a guest goes to `/login` with a return URL.
  - Pills: "N seats left" at `0 < available_spots ≤ 20`, Sold out at 0, Free, Online.
  - Layout: `min-width: 0` on every flex and grid child; fixed 3:4 ratio.
- **States:** skeletons for hero, rails and grid; the existing empty state and error toast; a rail that fails is simply hidden.
- **i18n keys:** `home.hero.soon`, `home.hero.buyTicket`, `home.hero.register`, `home.hero.details`, `home.hero.showEvent`, `home.filters.city`, `.formatPrice`, `.category`, `.search`, `.more` (plural), `.open`, `.apply`, `.activeCount`, `home.rails.inCity`, `.freeOnline`, `.allEvents`, `.seeAll`, `.scrollLeft`, `.scrollRight`, `event.seatsLeft` (plural), `event.priceFrom`, `event.addFavorite`, `event.removeFavorite`. Remove the keys the old hero and card no longer use.
- **Tests:** specs for the hero rule (five cases above), filter bar to query params, rail hiding, card pills and price label, favorites store rollback. Update `purchase.e2e.ts:17,31` to click the card link by role; `getByText(...).first()` could hit a hero thumbnail.
- **Risks:**
  - Home issues six or seven list requests; anonymous throttle rates are UNVERIFIED, hence the lazy loading.
  - The initial bundle is at 816 kB against a 900 kB warning (`angular.json:39-41`), so lazy-load the filter sheet.
- **Done 2026-11-15.** Backend B1 (tier-aware `is_free`) and B2 (`GET /favorites/ids/`) shipped with tests; `openapi.yaml` and `openapi.ts` regenerated. Frontend: `components/home/` (`discover-hero`, `filter-bar`, `filter-sheet` via `@defer`, `event-rail`, `discover-filters.ts`, `category-cover.ts`), `services/favorites.store.ts`, new `event-card`; `SearchService` removed (only the old Home used it). Notes:
  - Hero: when no event has a photo, up to three upcoming events show with category covers (not just one), so the thumbnails still work on the demo data.
  - The city is a standing preference: it narrows the grid and the rails but does not hide them, and it adds the "In <city>" mosaic.
  - Filter changes navigate to `#filters` (router `anchorScrolling` on, `ViewportScroller` offset 80px) so the page does not jump to the top.
  - IntersectionObserver callbacks run outside Angular's zone; the hero and the rails re-enter it with `NgZone.run`.
  - Initial bundle is now 875 kB (900 kB warning). Phase 4 should lazy-load its modals or the page will cross it.

### Phase 4: Event page (4–5 days)

- **Approach.** Keep every flow method in `EventDetailComponent` untouched (`event-detail.component.ts:1021-1473`) and split only the template into presentational components under `components/event-detail/`: `event-media`, `event-facts`, `event-tabs`, `organizer-card`, `purchase-panel`, `purchase-bar`.
- **Layout.** Three columns at ≥1280 (image, content, sticky panel); two at 768–1279 (image and content stacked beside the panel); one below 768 with a sticky bottom bar and bottom padding equal to its height.
- **Purchase panel** renders the existing chain in the same order (`:535-825`): cancelled or completed, guest, owner, confirmed with its refund sub-states, pending, rejected, non-attendee account, waitlist offer, queued, sold out with waitlist, buy. The buy state shows:
  - Ticket types as read-only rows (name, price, availability from `sale_state`) with "Choose tickets". Add an optional `preselectTicketTypeId` input to the checkout modal.
  - Seat-map events: zone rows from `zone_prices` (store the full list instead of only the cheapest, `:1049-1057`) with "Choose a seat — from X".
  - General admission: the current price and the real demand badge.
  - Ticket / Group segmented control only where the group link shows today; Group shows a short explanation and links to `/events/:id/group`.
- **Banners** (pending, draft, cancelled) and owner/admin actions stay, restyled.
- **Checkout, QR and refund modals:** restyle only. The checkout dialog keeps the name "Confirm registration" and widens on desktop when a seat map is present.
- **Mobile bar** shows the price and the same primary action as the panel for the current state.
- **Business rules:**
  - Owner and non-attendee branches stay first.
  - No cancel control for confirmed tickets.
  - The pending-seat block stays.
- **i18n keys:** `eventDetail.tabs.about`, `.location`, `.reviews`, `eventDetail.seating`, `eventDetail.zonesSummary`, `eventDetail.refundable`, `eventDetail.nonRefundable`, `eventDetail.openInMaps`, `eventDetail.timeZoneNote`, `eventDetail.modeTicket`, `eventDetail.modeGroup`, `eventDetail.groupHint`, `eventDetail.total`.
- **Accessibility:** tabs with `role="tablist"` and arrow keys, the panel as a labelled region, live region for queue and waitlist changes.
- **Tests:** a panel spec with one case per state; the existing checkout modal spec must pass unchanged. E2e selectors to keep or update together:
  - Buttons `Get tickets`, `Choose a seat`, `Complete payment`, `Request a refund`, `Release seat`.
  - Link `Book seats for a group`.
  - Texts `You're the organizer of this event`, `Payment incomplete`, `Seat held — complete payment to confirm`, `You're registered!` (`business-rules.e2e.ts:39-128`, `payments.e2e.ts:52-101`).
- **Risk:** regressions in payment flows. Mitigate by not touching class logic and running the full e2e suite after each sub-step.
- **Done 2026-11-15.** New `event-media`, `event-facts`, `event-tabs` (ARIA tabs; reviews `@defer`red), `organizer-card`; the panel, its 11-state chain and the mobile bar stay in `event-detail.component.ts` because they bind straight to the unchanged flow methods (moving them would mean ~20 inputs/outputs). Notes:
  - Added only: `seatZones` (full zone list), `bookingMode` (Ticket / Group, where the group link showed before), `preselectTicketTypeId` (tier row → checkout opens on it; new optional input on the checkout modal), `primaryAction` (mobile bar), and the heart now uses `FavoritesStore`.
  - Checkout, QR and refund dialogs load via `@defer`: the initial bundle went from 875 kB to 844 kB.
  - "Almaty time" is shown as the viewer's own offset (`your time, GMT+5`); donation tiers read "Donation" or "from X".
  - Spec: `event-detail.component.spec.ts`, one case per panel state plus zones, tiers, group switch and the Free price.

### Phase 5: remaining pages (3 days)

- Most pages re-skin through the tokens. Sweep for hard-coded colours and fix them: `#15803d` and the placeholder gradient in event detail (`:114`, `:204`), `bg-red-400` / `bg-amber-400` (`:524-526`), `.badge-soldout` and `.note-*` hexes (`styles.css:436-449`, `:1007`), footer social hovers, the bell's `bg-red-500 text-white`. The full count is UNVERIFIED; run a grep for hex values and Tailwind palette classes first.
- Pages to check in both themes: favorites, my tickets, my bookings, profile, security, notification settings, group booking, booking claim, auth pages, payment success and cancel, organizer and admin pages, 404.
- Remove dead CSS: `.card-ticket`, `.ticket-perf`, `.date-block` (`styles.css:1045-1095`).
- Add a short design-tokens page to `docs/` and update the `HANDOFF.md` entry.
- **Done 2026-11-15.** The grep found 56 hard-coded colours in 12 files; all now use tokens. Notes:
  - New tokens `--zone-vip(-50)` and `--zone-premium(-50)` in both themes (standard zone uses Pine); both text colours are in the AA contrast spec. The seat map SVG binds `[style.fill]` / `[style.stroke]` to them, so dark mode no longer shows pale light-theme seats; a selected seat is Ember with dark text.
  - My Tickets placeholders reuse the Discover category cover instead of five fixed gradients; the PDF export paints the ticket's own surface colour (it was always white, unreadable in dark mode).
  - Pills over photos (ticket type, favourite heart) are dark glass with white text in both themes; toasts use `--popover`; the approve button, waitlist badges, review stars and footer social hovers use the feedback tokens.
  - Dead CSS removed (114 lines): `.sidebar-footer`, `.sidebar-avatar`, `.notif-badge`, `.profile-dropdown*`, `.btn-accent`, `.card-hover`, `.kicker-hot`, `.font-mono-ui`, `.no-scrollbar` and unused badge aliases. `.card-ticket` / `.ticket-perf` / `.date-block` were already gone.
  - Rules and the grep check: [`DESIGN_TOKENS.md`](DESIGN_TOKENS.md).

### Phase 6: QA (2 days)

- Full suites on a fresh `ehqa` stack as in `TEST_REPORT.md`; second run for idempotency.
- Manual matrix: 2 themes × 3 widths (1440, 1024, 390) × 3 languages for Discover, Event (each panel state), My Tickets, checkout, QR dialog.
- Safari check for the logo and sticky elements; keyboard-only pass; reduced-motion pass; contrast check with a tool.
- Before and after screenshots; update `TEST_REPORT.md` counts.

- **Done 2026-11-15.** Results in `TEST_REPORT.md` §5.1: backend 582 OK, frontend 265, e2e 23/23 on three runs, 108-state matrix clean. One fix came out of it: a global focus ring (the `button` reset had hidden it on the filter chips). Not done: Safari (no WebKit here) and before/after screenshots.

**Total: about 21–23 engineer-days.**

## 4. What does not change, and backend changes

**Unchanged:**

- All API contracts and `openapi.yaml`, except the additive items below.
- Payment providers, callbacks and status polling.
- Booking and refund rules.
- All route paths; only query params on `/` and one guard are added.
- The single router outlet.
- Transloco setup.
- The notification service.

**Backend changes, each backward-compatible:**

| ID | Change | Why | Needed? |
|---|---|---|---|
| B1 | `is_free=true` filters tier-aware (no paid active tier), matching the serializer | The Free rail and chip otherwise show paid events | Recommended |
| B2 | `GET /favorites/ids/` returning the user's favorite event ids | Correct hearts beyond 12 favorites | Recommended. Fallback: page-1 ids plus the toggle response |
| B3 | Tests from phase 0 | Close the coverage gap | Yes |
| B4 | Seed images for the demo seeds | Otherwise the hero never shows a photo in demos | Depends on Q1 |

Out of scope, listed for later: image gallery model, event `timezone` and `city` fields, date-range filter, zone-aware `price_from` on the list (whether the base price equals the cheapest zone is UNVERIFIED; `seat_pricing.py` was not read).

## 5. Acceptance criteria

**Every phase:** `npm run lint`, `npm run format:check`, `npm test` (translation parity included), `npm run build` with no new budget warning, `manage.py test`, and the Playwright suite green on a Docker stack with no test skipped or deleted.

**Per phase:**

- **0:** role-aware footer and guard verified by tests; no "₸0"; no "Featured"; logo crisp in Safari.
- **1:** both themes complete; Kazakh and Russian render in Onest, not a fallback; contrast checked.
- **2:** every destination reachable exactly once per layout; keyboard-operable menus; e2e helpers updated.
- **3:** every filter produces the same API params as today; rails hide when empty; a long venue name never widens a card; hero works with zero, one and four candidates.
- **4:** all eleven panel states reachable; all payment and business-rule specs green; mobile bar never covers content.
- **5:** no hard-coded colours left outside tokens.
- **6:** the test matrix and before/after screenshots attached.

**Whole redesign:** all of the above on one commit, both themes, three breakpoints, three languages.

## 6. Open questions

| # | Question | Recommended default |
|---|---|---|
| Q1 | Where do demo photos come from? | Add a few licensed images to `seed_demo_kz` and `seed_showcase` (B4); until then the category hero shows. |
| Q2 | City: select or free text? | Free-text input, remembered per visitor; the city rail appears only once a city is set. |
| Q3 | What replaces the "Upcoming" chip? | The existing sort select ("Soonest first" by default); Discover never shows past events. |
| Q4 | Default theme? | Keep the OS preference; the hero is dark over the photo in both themes. |
| Q5 | Light-theme buttons: orange with dark text, or keep `#C2410C` with white? | Orange with dark text, for one brand colour. |
| Q6 | When does a card say "from"? | Only when the event has ticket types; plain price otherwise. |
| Q7 | Low-stock threshold for "N seats left"? | 20 on cards; the event page always shows the count. |
| Q8 | Russian label for Discover: "Обзор" (today) or "Афиша" (mockup)? | "Афиша", with the e2e case updated. |
| Q9 | Body font: Onest for everything, or Manrope for body? | Onest for both, one file to verify and load. |
