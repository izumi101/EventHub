# EventHub — Buyer Sidebar: UX/Product План (v1, 2026-06-12)

> **Статус: ПЛАН. Ничего из этого документа ещё не имплементировано.**
> Роль: Senior Product Designer + Senior UX Architect. Дизайн-система — **Ember** (Warm Editorial: paper `#FAF7F2` / ink `#1A1714` / ember `#E8552D` / pine `#2B6B5E`, Clash Display + Satoshi + JetBrains Mono, радиус 14px, ticket-stub метафора). Все новые страницы строятся из существующих shell-компонентов (`.sidebar*`, `.topbar*`, `.card`, `.btn*`, skeleton-классы) — без нового визуального языка.

---

## 0. Ключевые решения (зафиксировать до разработки)

| # | Решение | Обоснование |
|---|---------|-------------|
| D1 | Новый сайдбар — **только для роли `attendee`** (signed-in && не organizer && не admin). Секции public/organizer/admin в `nav.config.ts` не трогаем. | Прямое требование владельца. Механика уже есть: `NavSection.roles` — добавляем секции с `roles: ['attendee']` и убираем `attendee` из видимости старой секции `main`. |
| D2 | Навигация берётся из **ручного списка владельца**: EXPLORE (Discover, Categories, Calendar, Nearby), MY EVENTS (Tickets, Bookings, Favorites), ACCOUNT (Payments, Notifications, Settings). | Два списка в постановке расходятся. Ручной — приоритетный. |
| D3 | **Recommended и Trending не отдельные пункты**, а блоки-«полки» внутри Discover. **Rewards — Phase 3** (бэкенда нет вообще). | Меньше пунктов меню = меньше выборов (закон Хика). Recommendations API уже есть; trending — дешёвый новый эндпоинт. |
| D4 | Группы в сайдбаре оформляются **mono-кикерами** (`EXPLORE`, `MY EVENTS`, `ACCOUNT` — JetBrains Mono, 10px, caps, letterspacing .14em, `--muted-foreground`) — фирменный приём Ember. | Уже используется в карточках/инвойсе; узнаваемость. |
| D5 | Нумерация фаз: **Phase 1** — без новых моделей БД (Discover, Categories, Tickets, Bookings, Favorites, Notifications, Settings). **Phase 2** — мелкий бэкенд (Calendar, Payments, Nearby-v1). **Phase 3** — Nearby-geo, Rewards. | Раннее видимое продвижение, риск изолирован. |
| D6 | Мобильная стратегия: сайдбар скрыт за burger (как сейчас), **плюс bottom tab bar** для attendee: Discover · Calendar · Tickets · Account (4 таба, 56px, safe-area). | 2026-паттерн для билетных продуктов; «большой палец» доминирует. |

---

## 1. Архитектура навигации

### 1.1 Сайдбар attendee (desktop ≥1024px)

```
┌──────────────────────────┐
│ ◆ EventHub        [«]    │ ← logo + collapse (существующий topbar/sidebar)
│                          │
│ EXPLORE                  │ ← mono-kicker
│  ◦ Discover              │ route: /            icon: Search
│  ◦ Categories            │ route: /categories  icon: LayoutGrid
│  ◦ Calendar              │ route: /calendar    icon: CalendarDays
│  ◦ Nearby                │ route: /nearby      icon: MapPin
│                          │
│ MY EVENTS                │
│  ◦ Tickets        (•3)   │ route: /my-registrations  icon: Ticket   badge: upcoming
│  ◦ Bookings              │ route: /my-bookings       icon: Armchair
│  ◦ Favorites             │ route: /favorites         icon: Heart
│                          │
│ ACCOUNT                  │
│  ◦ Payments              │ route: /account/payments  icon: CreditCard
│  ◦ Notifications  (•5)   │ route: /notifications     icon: Bell     badge: unread
│  ◦ Settings              │ route: /settings          icon: Settings
│                          │
│ ──────────────────────   │
│ [avatar] name · Sign out │ ← существующий футер сайдбара
└──────────────────────────┘
```

Поведение: активный пункт — ember-маркер слева (3px вертикальная полоска) + ink-текст; hover — `--surface-sunken`; collapsed-режим — только иконки + tooltip; badge — мини-каунтер (ember на paper). Все статусы уже покрыты текущим `.sidebar*` CSS.

### 1.2 Изменения в `nav.config.ts` (план)

- Секция `main` → `roles: ['public', 'organizer', 'admin']` (исключаем attendee; для public остаётся Discover; для organizer/admin — всё как сейчас, **ноль визуальных изменений**).
- +3 секции `explore` / `my-events` / `account` с `roles: ['attendee']`, `title` → кикер.
- Бэйджи: `NavItem.badge?: () => Signal<number>` — счётчики из `NotificationService.unreadCount` и нового `TicketsBadgeService` (upcoming confirmed regs). Опрос — переиспользуем существующий polling нотификаций, без новых таймеров.

### 1.3 Карта маршрутов

| Пункт | Route | Состояние |
|---|---|---|
| Discover | `/` | есть (HomeComponent) — доработка полками |
| Categories | `/categories`, `/categories/:id` | **новый** (фильтр `?category=` уже есть в API) |
| Calendar | `/calendar` | **новый** + параметры `date_from/date_to` в API |
| Nearby | `/nearby` | **новый** (v1 — по городу; v2 — геолокация) |
| Tickets | `/my-registrations` | есть — мелкие улучшения |
| Bookings | `/my-bookings` | есть — мелкие улучшения |
| Favorites | `/favorites` | есть — мелкие улучшения |
| Payments | `/account/payments` | **новый** + новый эндпоинт истории |
| Notifications | `/notifications` | **новый** (API готов целиком) |
| Settings | `/settings` | **новый** (обёртка над /profile API + темы) |

---

## 2. Маршруты детально

### 2.1 `/` — Discover

**Цель:** главная точка входа покупателя; за ≤10 секунд показать «что интересного происходит» и довести до карточки события.

**Сценарии:** (a) «пришёл без цели» → листает полки → кликает карточку; (b) «ищу конкретное» → поиск (semantic `?q=` уже есть) → результаты; (c) «вернулся» → полка Recommended наверху уже персонализирована.

**Wireframe (сверху вниз):**
1. Hero-строка: display-заголовок («What's on in Almaty») + большой search-input (`?q=`, debounce 300ms, semantic).
2. Чипы-фильтры: категории (горизонтальный скролл) + Free / Online / This week.
3. Полка **Recommended for you** (если auth, ≥3 итемов) — горизонтальная, 4 карточки.
4. Полка **Trending** — топ по регистрациям за 7 дней, бейдж «🔥 N going».
5. Featured-сетка (асимметричная, Ember-сигнатура): 1 крупная + 4 обычных.
6. Бесконечный список «All upcoming» (existing pagination `{count,next,results}`).

**Состояния:** loading — skeleton-полки (существующие skeleton-классы); empty поиска — «Nothing for "X"» + кнопка сброса + 4 популярных; error — retry-карточка; в полках ошибки **тихие** (полка просто скрывается — деградация, не алерт).

**CTA:** карточка целиком кликабельна; быстрый ♥ на карточке (optimistic, `POST /api/events/favorites/{id}/toggle/`).

**API:** `GET /api/events/?status=published&upcoming=true&page=` · `GET /api/events/recommendations/` (есть) · **новый** `GET /api/events/trending/` (annotate Count(registrations) за 7д, top-8, cache 15 мин) · `GET /api/categories/`.

**Mobile:** поиск сворачивается в иконку topbar; полки — нативный horizontal scroll со snap; featured-сетка → одна колонка; фильтры — bottom-sheet.

**UX-улучшения:** skeleton → плавный fade (без CLS); pull-to-refresh на мобиле; сохранение позиции скролла при возврате с карточки (router scroll restoration).

---

### 2.2 `/categories` и `/categories/:id` — Categories

**Цель:** браузинг по интересам — «я хочу на концерт», а не «я ищу конкретное».

**`/categories` wireframe:** kicker `BROWSE` + заголовок → сетка категорий-карточек (иконка/эмодзи категории, имя, счётчик «N upcoming», ember-underline на hover). 12–20 категорий, без пагинации.

**`/categories/:id` wireframe:** breadcrumb (Categories → Music) → заголовок + счётчик → панель: сортировка (Date soonest ▾ | Price | Popularity) + фильтры (Free, Online, дата-диапазон, город) → сетка карточек 3×N с пагинацией «Load more».

**Состояния:** skeleton-сетка; пустая категория — «No upcoming events in Music» + CTA «Explore all» + 4 события других категорий; error — retry.

**API:** `GET /api/categories/` (есть; **доработка** — annotate счётчик upcoming) · `GET /api/events/?category={id}&ordering=date|price` (есть, `ordering` уже поддержан OrderingFilter).

**Mobile:** сетка категорий 2 колонки; фильтры/сортировка — bottom-sheet с кнопкой-итогом («Show 23 events»); applied-фильтры — чипы с ×.

**UX:** URL-синхронизация фильтров (`?free=true&sort=price`) — шарябельные ссылки; счётчики в карточках категорий предотвращают «пустые клики».

---

### 2.3 `/calendar` — Calendar

**Цель:** ответ на «что происходит в эти даты» — планирование выходных/поездки.

**Wireframe:** заголовок месяца + ‹ › + кнопка Today + переключатель Month/List → **месячная сетка**: в ячейке дня до 3 точек-событий (цвет = категория) + «+N»; сегодня — ember-кольцо → клик по дню раскрывает под сеткой список событий дня (карточки-строки: время, название, площадка, цена, ♥).

**Сценарии:** (a) листает месяцы → видит плотность; (b) кликает дату → список дня → карточка; (c) mobile — list-view по умолчанию.

**Состояния:** loading — сетка сразу, события подгружаются (skeleton-точки); пустой месяц — «Quiet month» + CTA на Discover; error — retry-баннер над сеткой.

**API (доработка):** `GET /api/events/?date_from=2026-07-01&date_to=2026-07-31` — **новые** два query-параметра в существующем `EventViewSet.get_queryset()` (`date__gte/date__lte`, ~5 строк). Префетч соседних месяцев.

**Mobile:** month-grid сжимается до компактной с точками; список дня — снизу, infinite; **list-view по умолчанию** (сгруппированный по дням скролл «Jul 30 — Wed» с sticky-датами); горизонтальный week-strip наверху.

**UX:** deep-link `?month=2026-07`; долгое нажатие на событие — quick-preview (bottom-sheet с CTA «View event»); ics-экспорт дня — Phase 3.

---

### 2.4 `/nearby` — Nearby

**Цель:** «что рядом со мной» — спонтанные походы.

**Phase 2 (v1, без геоданных в БД):** селектор города (из distinct location-значений) + список офлайн-событий города, сортировка по дате. Wireframe: заголовок «Events in Almaty ▾» (city-switcher) → чипы районов/площадок (если парсятся из location) → лента карточек с указанием площадки.

**Phase 3 (v2, полноценный):** поля `Event.lat/lng` (+ заполнение при создании через geocoding), `GET /api/events/nearby/?lat=&lng=&radius_km=10`; на странице — карта (MapLibre GL, self-hosted тайлы) + синхронизированный список; «Near me» через `navigator.geolocation` (graceful: отказ → city-selector); пины — ember-капли, кластеризация.

**Состояния:** запрос геолокации — мягкий pre-prompt («Show events near you?» → кнопка), не авто-запрос; отказ — city-selector; пусто в радиусе — расширение радиуса «Nothing within 10 km — try 25 km?»; error карты — список остаётся (карта — прогрессивное улучшение).

**Mobile:** карта-«шапка» 40vh + bottom-sheet список (драг вверх на fullscreen) — паттерн Airbnb/Я.Афиши.

---

### 2.5 `/my-registrations` — Tickets (существующая, доработки)

**Цель:** все билеты пользователя; быстрый доступ к QR в день события.

**Что уже есть:** список, QR, статусы, refund-flow (после сегодняшнего фикса кнопка скрыта после чек-ина), complete-payment, invoice.

**Доработки плана:**
1. Сегментация **Upcoming / Past** (tabs) вместо общего списка; в Upcoming — ближайший билет первым с крупным QR-CTA «Today! Show QR».
2. «Day-of mode»: если событие сегодня — карточка билета подсвечена ember-рамкой, QR раскрыт сразу (главный сценарий у входа = ноль кликов).
3. Empty: «No tickets yet» + полка Recommended (конверсия из мёртвой зоны).
4. Бейдж в сайдбаре = upcoming confirmed.

**API:** всё есть (`GET /api/events/registrations/my/`, `?event=` фильтр). Доп. запросов не нужно.

**Mobile:** QR fullscreen по тапу с max-яркостью экрана (Screen Wake Lock API); свайп между билетами одного события.

---

### 2.6 `/my-bookings` — Bookings (существующая, доработки)

**Цель:** групповые брони: статус, оплата, раздача мест.

**Доработки:** статус-таймлайн на карточке (Created → Paid → Seats claimed N/M → Checked in); прогресс-бар клейма мест; кнопка «Copy invite link» с быстрым share (Web Share API на мобиле); empty-состояние объясняет ценность групповой брони + CTA «Find an event».

**API:** есть (`GET /api/bookings/mine/`, detail, checkout, cancel, shared/claim).

---

### 2.7 `/favorites` — Favorites (существующая, доработки)

**Цель:** вишлист; возврат к отложенным событиям.

**Доработки:** бейдж-уведомление на карточке «Selling out — N spots left» (данные `available_spots` уже приходят); сортировка Date added / Event date; прошедшие события — секция «Past» с приглушением и кнопкой очистки; empty — «Tap ♥ on any event» + полка Trending.

**API:** есть (`GET /api/events/favorites/`, toggle). Уведомление «favorite скоро начнётся» — Phase 3 (бэкенд-таска).

---

### 2.8 `/account/payments` — Payments (новая)

**Цель:** финансовая история: «за что я платил, где квитанция, где возврат».

**Wireframe:** заголовок + summary-строка (Total spent YTD · Refunded · мини-«spending» спарклайн) → фильтры (All / Completed / Refunded / Pending, период) → **таблица-список** (mono-цифры, tabular-nums): дата · событие (ссылка) · метод · сумма · статус-пилюля (pine paid / amber pending / red refunded) · ⋮ (Invoice ↗, Request refund если доступен, View event) → пагинация.

**Состояния:** skeleton-строки 8шт; empty — «No payments yet» + CTA Discover; error — retry; частичный возврат — две строки (платёж + связанный возврат со стрелкой-связью).

**API (новое):** `GET /api/payments/history/` — список Payment текущего юзера: `{id, event:{id,title}, amount, currency, status, method, refunded_amount, created_at, registration_id}`, пагинация, фильтр `?status=`. Бэкенд — один ListAPIView (~30 строк), модель готова. Invoice — существующий `GET /api/payments/invoice/{registration_id}/` (теперь в Ember-стиле).

**Mobile:** таблица → карточки-строки (двухэтажные: событие+дата / сумма+статус); фильтры — чипы.

---

### 2.9 `/notifications` — Notifications (новая страница)

**Цель:** полная история уведомлений (а не только dropdown в topbar); центр «что изменилось по моим событиям».

**Wireframe:** заголовок + «Mark all as read» → фильтр-чипы (All / Tickets / Events / Payments — маппинг существующих `type`) → лента, сгруппированная по дням (Today / Yesterday / Earlier): иконка типа в цветном бабле · заголовок · тело · время · точка-непрочитанность; непрочитанные — фон `--surface-sunken`; клик = mark-read + переход к событию (`event` приходит в payload).

**Состояния:** skeleton 6 строк; empty — «You're all caught up 🎉»; error — retry; realtime-добавление новых сверху (WebSocket-канал уведомлений уже есть — `events/consumers.py`).

**API:** всё есть: `GET /api/events/notifications/` (последние 50), `POST /api/events/notifications/read/` и `/read/{id}/`. **Доработка** — пагинация вместо среза 50 (заменить `[:50]` на стандартный пагинатор, ~3 строки).

**Mobile:** свайп строки = mark read; pull-to-refresh.

---

### 2.10 `/settings` — Settings (новая, поглощает /profile)

**Цель:** один дом для профиля, безопасности и предпочтений; `/profile` остаётся редиректом.

**Wireframe (секции-карточки, якорная под-навигация слева на desktop):**
1. **Profile** — avatar (upload есть), имя, email (read-only + verified-чип), телефон. Сохранение по секции, не глобальной кнопкой.
2. **Security** — change password (flow есть), активная сессия, «Sign out everywhere» (Phase 3).
3. **Appearance** — Light / Dark / System (тёмная Ember-тема уже в styles.css; переключатель сейчас в topbar — дублируем сюда как первоисточник).
4. **Notifications prefs** — toggles email/in-app по типам (Phase 2: нужны поля `Profile.notify_*` + учёт в `notify()`).
5. **Danger zone** — Delete account (Phase 3: soft-delete + анонимизация, отдельное продуктовое решение).

**Состояния:** per-секция: idle → saving (spinner в кнопке) → saved (галочка 2с) → error (inline под полем); никаких глобальных тостов на каждое поле.

**API:** `GET/PATCH /api/auth/profile/`, `POST /api/auth/profile/avatar/`, `POST /api/auth/change-password/` — всё есть. Prefs — Phase 2.

**Mobile:** секции — аккордеон; sticky-кнопка Save внутри открытой секции.

---

## 3. Сквозные состояния и паттерны (все страницы)

- **Loading:** только skeleton (никаких полноэкранных спиннеров); shimmer уже в styles.css; резервирование высоты — CLS < 0.1.
- **Empty:** иллюстрация-глиф + одна строка человеческим языком + один CTA + (где уместно) полка-альтернатива. Никогда не «No data».
- **Error:** inline retry-карточка с человеческим текстом; сетевые ошибки списков не выбрасывают на error-page.
- **Success:** существующие тосты; для money-операций — подтверждение в самой карточке (статус-пилюля), не только тост.
- **Пагинация:** все списки терпят оба формата (`Array | {results}` — уже принятый паттерн в сервисах).
- **A11y:** фокус-кольца ember, aria-live на тостах/бейджах, полная клавиатурная навигация сайдбара, WCAG AA (пары уже проверены в Ember ТЗ).

## 4. Сводка бэкенд-доработок

| Эндпоинт/изменение | Размер | Фаза |
|---|---|---|
| `GET /api/events/trending/` | ~20 строк (annotate+cache) | 1 |
| `?date_from/date_to` в EventViewSet | ~5 строк | 2 |
| `GET /api/payments/history/` | ~30 строк | 2 |
| Пагинация notifications (вместо [:50]) | ~3 строки | 1 |
| Счётчик upcoming в categories | ~5 строк | 1 |
| `Profile.notify_*` prefs + учёт в notify() | ~40 строк + миграция | 2 |
| `Event.lat/lng` + `/nearby/` geo + geocoding | модель+миграция+вью | 3 |
| Rewards (модель, начисление, траты) | новое приложение | 3 |

## 5. Порядок имплементации

- **Phase 1 (нав + быстрые победы):** nav.config + сайдбар-секции с кикерами и бэйджами → Discover-полки (recommendations есть, trending новый) → Categories (две страницы) → Notifications-страница → Settings v1 (profile+security+appearance) → доработки Tickets/Bookings/Favorites (tabs, day-of mode, empty-states) → bottom tab bar (mobile).
- **Phase 2:** Calendar (+date-параметры) → Payments (+history) → Nearby v1 (города) → notification prefs.
- **Phase 3:** Nearby v2 (карта/гео), Rewards, ics-экспорт, «favorite напоминания», delete account.

Каждый шаг — отдельно собираемый и деплоимый (`ng build` зелёный после каждого), бизнес-логика и API существующих флоу не ломаются, organizer/admin-навигация не меняется ни на пиксель.

## 6. Метрики успеха

- Discover → Event detail CTR; полка Recommended CTR vs общая лента.
- % покупателей, открывших QR без поиска по списку в день события (day-of mode).
- Время до первого билета у нового пользователя (signup → purchase).
- Возвраты в Favorites → покупка (конверсия вишлиста).
- Notifications: unread@7d ↓ после запуска страницы.
