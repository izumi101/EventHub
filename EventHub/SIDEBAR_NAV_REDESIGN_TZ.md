# ТЗ: Перестройка навигации EventHub — Grafana-style боковая панель (Sidebar Nav)

> **Статус:** черновик утверждён к исполнению. Готово к старту «с холода» — отдельных объяснений не требуется.
> **Автор контекста:** сессия 2026-06-07. **Цель документа:** завтра开 начать переделку UI/UX без повторных вводных.

---

## 0. TL;DR (на русском)

Сейчас навигация размазана: верхний navbar + кнопочные тулбары внутри страниц (Tickets / Promo codes / Questions / Settings / Check-in lists / Scan — всё это спрятано на странице «Attendees» конкретного события). Чтобы найти функцию — нужно угадать, на какой странице её кнопка. Это и есть боль.

**Решаем:** делаем постоянную сворачиваемую **левую боковую панель** (как в Grafana) — единый навигационный хаб. Все разделы видны и сгруппированы логически, с раскрывающимися подсекциями. Когда заходишь «внутрь события» — в сайдбаре появляется контекстная под-навигация этого события (Attendees, Tickets, Promo, Questions, Check-in, Settings), а не прячется в тулбаре.

**Не трогаем** бизнес-логику, сервисы, API, роуты по сути (только добавляем layout-обёртку). Сохраняем существующую светлую дизайн-систему (indigo `#4f46e5`, токены в `styles.css`). Тёмная тема уже есть — сайдбар обязан её поддерживать.

---

## 1. Текущее состояние (факты для исполнителя)

**Стек:** Angular 21 standalone, Tailwind CSS v3, RxJS, `lucide-angular`. Фронт: `EventHub/frontend/`.

**Корневой layout** — [`app.component.ts`](frontend/src/app/app.component.ts):
```
.app-wrapper (flex column, min-h-100vh)
  <app-navbar/>            ← fixed top, h-16
  <main.main-content>      ← router-outlet
  <app-footer/>
  <app-confirm-modal/> <app-toast-container/>
```

**Текущая навигация** — [`navbar.component.ts`](frontend/src/app/components/navbar/navbar.component.ts):
- Лого → `/`
- Desktop nav: Discover (`/`), My Tickets (`/my-registrations`), [если организатор] Dashboard (`/organizer/dashboard`), Scan (`/scan`)
- Действия справа: theme toggle, Favorites, Notifications (dropdown + badge через `NotificationService`), [организатор] Create Event, Profile (avatar+username), Logout
- Mobile: бургер → выпадающее меню
- Роли: `isOrganizer = is_staff || is_superuser`, `isAdmin = is_superuser` (из `AuthService.currentUser$`)

**Дизайн-токены** — [`styles.css`](frontend/src/styles.css) (CSS custom properties, light + `.dark`):
`--background #fff`, `--foreground #111827`, `--primary #4f46e5`, `--secondary #f3f4f6`, `--muted #f9fafb`, `--muted-foreground #6b7280`, `--border #e5e7eb`, `--card #fff`, `--radius 0.5rem`, `--font-sans Inter`. Тёмная: `--background #0f1117`, `--primary #6366f1`, и т.д.
Готовые классы: `.btn` (+ `-primary/-secondary/-ghost/-danger/-outline/-sm/-lg/-full`), `.card`, `.card-hover`, `.badge` (+статусы), `.input`, `.spinner`, `.container`, `.page-root`, `.page-root-white`, `.focus-ring`, анимации `animate-fade-in`/`animate-slide-up`.

**Все маршруты** — [`app.routes.ts`](frontend/src/app/app.routes.ts). Полный список с категоризацией — см. раздел 3.

**Сервисы, релевантные навигации:** `AuthService` (`currentUser$`, роли), `ThemeService` (`isDark()`, `toggle()`), `NotificationService` (`unreadCount()`, `notifications()`, `load()`, `markRead()`), `EventService` (`getEvent(id)` — для названия события в контекстной навигации), `ModalService` (confirm для logout).

---

## 2. Проблема и цели

### Проблема
1. Управление событием раздроблено: страницы `attendees / ticket-types / promo-codes / questions / checkin-lists / settings` доступны только через кнопки-тулбар внутри страницы Attendees. Нет единого места «вот всё про это событие».
2. Глобальные разделы (Dashboard, My Events, Scan, Create, Favorites, Profile) разбросаны между nav и иконками справа.
3. Нет визуальной иерархии и ощущения «полноты» продукта.

### Цели (UX)
- **Discoverability < 3 c:** любую ключевую функцию видно в сайдбаре или его раскрытой группе без перехода по страницам.
- **Снижение трения:** контекст события — в сайдбаре, не в тулбаре страницы.
- **Профессиональный, насыщенный, но не захламлённый** вид. Информативность через иерархию, а не через свалку ссылок.
- **Sidebar = главный навигационный хаб.** Tулбары внутри страниц убираем/минимизируем (дублирование уходит в сайдбар).

### Референс
Grafana: постоянный левый сайдбар (иконки+лейблы, сворачивание), раскрывающиеся секции, контекстные под-разделы, верхний бар с хлебными крошками/поиском/профилем.

---

## 3. Информационная архитектура (полное дерево навигации)

> Источник истины — сделать **data-driven**: массив-конфиг (раздел 5.4), а не хардкод в шаблоне.

### 3.1 Глобальный сайдбар

```
┌─ HEADER ──────────────────────────────
│  [logo] EventHub            [«collapse]
├─ (секция) MAIN ───────────────────────
│  ◷ Discover            → /                       (icon: Search)      [все]
│  🎟 My Tickets          → /my-registrations       (icon: Ticket)      [auth]
│  ♥ Favorites           → /favorites              (icon: Heart)       [auth]
├─ (секция, group) ORGANIZE ────────────  [только isOrganizer]
│  ▦ Dashboard           → /organizer/dashboard    (LayoutDashboard)
│  🗓 My Events           → /my-events              (CalendarDays)
│  ＋ Create Event        → /create-event           (Plus)
│  ⎘ Scan Tickets        → /scan                   (ScanLine)
├─ (секция, контекст) CURRENT EVENT ────  [только когда выбран event :id, см. 5.3]
│  «{{eventTitle}}»  — заголовок группы, раскрыт по умолчанию
│  👤 Attendees          → /organizer/events/:id/attendees      (Users)
│  🎟 Tickets            → /organizer/events/:id/ticket-types    (Ticket)
│  🏷 Promo Codes        → /organizer/events/:id/promo-codes     (Tag)
│  💬 Questions          → /organizer/events/:id/questions       (MessageSquare)
│  📋 Check-in Lists     → /organizer/events/:id/checkin-lists   (ClipboardList)
│  ⚙ Settings           → /organizer/events/:id/settings        (Settings)
│  ✎ Edit Event         → /edit-event/:id                       (Edit)
│  ↩ All events         → /organizer/dashboard  (выход из контекста)
├─ (секция) ADMIN ──────────────────────  [только isAdmin]
│  🛡 Admin Panel        → /organizer/dashboard (admin-режим)   (Shield)
│     (платформенная статистика; backend уже есть: /api/admin-dashboard/)
└─ FOOTER (низ сайдбара) ───────────────
   ☀/☾ Theme toggle        (ThemeService.toggle)
   🔔 Notifications (badge) → открывает панель уведомлений
   [avatar] {{username}}   → /profile   (+ выпадашка: Profile / Sign out)
```

### 3.2 Маршруты вне сайдбара (доступны, но не пункты меню)
`/events/:id` (публичная карточка), `/events/:id/group`, `/booking/:token`, `/login`, `/register`, `/forgot-password`, `/payment/success`, `/payment/cancel`, `/validate/:uuid`, `**` (404). Эти страницы **рендерятся внутри shell** (или без него — см. 5.5 «auth-страницы без сайдбара»).

### 3.3 Видимость по ролям
| Секция | Гость | Attendee (auth) | Organizer (is_staff) | Admin (is_superuser) |
|---|---|---|---|---|
| MAIN: Discover | ✓ | ✓ | ✓ | ✓ |
| MAIN: My Tickets / Favorites | — | ✓ | ✓ | ✓ |
| ORGANIZE | — | — | ✓ | ✓ |
| CURRENT EVENT | — | — | ✓ (на своих) | ✓ |
| ADMIN | — | — | — | ✓ |
| FOOTER: theme | ✓ | ✓ | ✓ | ✓ |
| FOOTER: notif/profile | — | ✓ | ✓ | ✓ |

Гость видит сжатый сайдбар (Discover + theme) и в футере кнопки **Sign In / Get Started**.

---

## 4. Визуальный дизайн

### 4.1 Размеры
- Sidebar expanded: **width 248px**; collapsed: **64px**. Плавный transition `width .2s ease`.
- Topbar height: **56px** (slim). Sidebar — full height `100vh`, `sticky`/`fixed` слева.
- Контент (`main`) смещается на ширину сайдбара (`margin-left`/grid column), под topbar.
- Иконки пунктов 18–20px (`w-4.5 h-4.5` ~ используем `w-5 h-5`), gap до лейбла 12px.
- Пункт: высота 36–40px, паддинг `px-3`, `rounded-md`.

### 4.2 Цвета/состояния (через существующие токены)
- Фон сайдбара: `--card` (light `#fff`, dark `#1a1d27`); правый бордер `--border`.
- Пункт по умолчанию: текст `--muted-foreground`; hover: фон `--muted`, текст `--foreground`.
- **Активный пункт:** фон `--primary` @ 10% (`bg-primary/10`), текст `--primary`, левый акцент-бар 3px `--primary` (`border-l-2`/псевдоэлемент).
- Заголовки секций: `text-[11px] uppercase tracking-wider text-muted-foreground`, паддинг сверху.
- Badge уведомлений: красный кружок (как сейчас в navbar).
- Контекстная группа «CURRENT EVENT»: заголовок = название события (truncate), маленький цветной маркер.

### 4.3 Collapsed-режим
- Только иконки по центру; лейблы скрыты; заголовки секций → тонкий разделитель.
- При hover на пункт — **tooltip** с лейблом справа (нативный `title` минимум; в идеале кастомный поповер).
- Группы в collapsed: клик по иконке группы — раскрывает flyout-поповер со списком под-пунктов (Grafana-стиль). MVP: в collapsed клик по иконке группы переводит на её корневой роут и авто-разворачивает сайдбар.

### 4.4 Иконки (lucide-angular, все уже доступны в проекте)
`Search, Ticket, Heart, LayoutDashboard, CalendarDays, Plus, ScanLine, Users, Tag, MessageSquare, ClipboardList, Settings, Edit, Shield, Bell, Sun, Moon, LogOut, User, ChevronLeft, ChevronRight, ChevronDown, PanelLeftClose, PanelLeftOpen`.

---

## 5. Техническая реализация

### 5.1 Новые файлы
```
frontend/src/app/layout/
  app-shell.component.ts     ← обёртка: sidebar + topbar + <router-outlet/> + footer
  sidebar.component.ts       ← сама панель (data-driven по nav.config)
  topbar.component.ts        ← хлебные крошки/тайтл + поиск(опц.) + bell + theme + profile-menu
  nav.config.ts             ← декларативное дерево навигации (типы + массив)
frontend/src/app/services/
  layout.service.ts          ← signals: collapsed, mobileOpen, eventContext{id,title}, groupState; persistence
```

### 5.2 Изменения существующих файлов
- [`app.component.ts`](frontend/src/app/app.component.ts): заменить `<app-navbar/> + <main> + <app-footer/>` на `<app-shell/>` (shell сам решает, где footer). `confirm-modal` и `toast-container` оставить в корне.
- [`navbar.component.ts`](frontend/src/app/components/navbar/navbar.component.ts): **логику переиспользовать** (theme, notif, logout, роли) — перенести в `topbar` + `sidebar`. Старый navbar удалить **после** переноса (не раньше).
- Страницы управления событием (`attendee-list`, `ticket-types`, `promo-codes`, `event-questions`, `event-settings`, `checkin-lists`): из шапок **убрать дублирующий кнопочный тулбар** перехода между разделами события (он переезжает в сайдбар). Оставить только действия, специфичные для страницы (Export, Message, Scan tickets, New list и т.п.). Хлебные крошки оставить/упростить (их дублирует topbar).
- `app.config.ts`: ничего обязательного; `SeoService` уже инициализируется.

### 5.3 Определение «контекста события» (`layout.service`)
- Подписка на `Router.events` (`NavigationEnd`). Регуляркой вытащить `:id` из URL для паттернов:
  `/organizer/events/:id/...` и `/edit-event/:id`.
- Если `id` найден → `eventContext.id = id`; подтянуть `eventTitle` через `EventService.getEvent(id)` с кэшем (не дёргать на каждый переход внутри того же id).
- Если ушли с event-маршрутов → `eventContext = null` (секция CURRENT EVENT скрывается).
- Хранить в `signal`, чтобы sidebar реактивно показывал/прятал секцию.

### 5.4 `nav.config.ts` — форма данных (ориентир, не догма)
```ts
export type Role = 'public' | 'auth' | 'organizer' | 'admin';
export interface NavItem {
  label: string; icon: any; route?: string;            // route может быть фабрикой для :id
  routeFn?: (eventId: string) => string;
  exact?: boolean; roles: Role[]; badge?: () => number; // напр. для notif
}
export interface NavSection {
  id: string; title?: string; roles: Role[];
  collapsible?: boolean; defaultOpen?: boolean;
  context?: 'event';                                    // секция видна только при eventContext
  items: NavItem[];
}
export const NAV: NavSection[] = [ /* MAIN, ORGANIZE, EVENT(context), ADMIN */ ];
```
Sidebar рендерит `NAV`, фильтруя секции/пункты по текущей роли и (для context-секции) по наличию `eventContext`.

### 5.5 Состояние и персистентность (`layout.service`, signals)
- `collapsed = signal<boolean>` ← `localStorage['sidebar_collapsed']` (default: false на desktop).
- `mobileOpen = signal<boolean>` (off-canvas на мобиле; default false).
- `groupOpen = signal<Record<string,boolean>>` ← `localStorage['sidebar_groups']` (какие группы раскрыты).
- `eventContext = signal<{id:string,title:string}|null>`.
- Все сеттеры пишут в localStorage. Ключи: `sidebar_collapsed`, `sidebar_groups`.

### 5.6 Auth-страницы без сайдбара
`/login`, `/register`, `/forgot-password`, `/payment/*` — рендерить **без** сайдбара/topbar (чистый центрированный layout). Реализация: либо отдельный layout-роут, либо `app-shell` скрывает sidebar/topbar для списка «bare»-маршрутов (проверка по URL). Выбрать: shell с флагом `bareRoutes` (проще, без рефакторинга роутера).

---

## 6. Адаптивность

| Брейкпоинт | Поведение |
|---|---|
| ≥1024px (desktop) | Sidebar постоянный (expanded/collapsed по выбору пользователя). Контент со смещением. |
| 640–1023px (tablet) | Sidebar по умолчанию collapsed (иконки). Можно развернуть оверлеем. |
| <640px (mobile) | Sidebar скрыт; **off-canvas drawer** по бургеру в topbar; затемнение-оверлей; закрытие по выбору пункта/Esc/клику вне. |

Topbar на мобиле: бургер (открывает drawer) + лого + bell + avatar.

---

## 7. Доступность (a11y)
- `<nav aria-label="Main">`, активный пункт `aria-current="page"`.
- Кнопка collapse: `aria-expanded`, понятный `aria-label` («Collapse sidebar»).
- Группы: `aria-expanded` на заголовке-кнопке; управление с клавиатуры (Enter/Space).
- Полная клавиатурная навигация, видимый `focus-ring` (класс уже есть).
- Esc закрывает мобильный drawer и поповеры. Фокус-трап внутри открытого drawer.
- Контраст текста пунктов ≥ AA (проверить `muted-foreground` на `card` в обеих темах).

---

## 8. Пошаговый план внедрения (порядок работ на завтра)

1. **`layout.service.ts`** — signals + persistence + детект event-контекста (роутер + кэш getEvent). Юнит-проверка вручную.
2. **`nav.config.ts`** — описать всё дерево из раздела 3 (с ролями и context).
3. **`sidebar.component.ts`** — рендер по конфигу: секции, группы (раскрытие), активные состояния, collapsed-режим, футер (theme/notif/profile/logout — перенести из navbar).
4. **`topbar.component.ts`** — хлебные крошки/тайтл (из `eventContext` + route title), bell-dropdown (перенести из navbar), avatar-menu, бургер для мобилы. Глобальный поиск — опционально (заглушка-кнопка `⌘K`, реальный command-palette — вне MVP).
5. **`app-shell.component.ts`** — собрать grid: `[sidebar][ (topbar)/(content)/(footer) ]`; обработать `bareRoutes`; mobile drawer + overlay.
6. **`app.component.ts`** — переключить на `<app-shell/>`.
7. **Подчистить страницы события** — убрать дублирующие тулбары перехода (attendees/ticket-types/promo-codes/questions/checkin-lists/settings), оставить page-specific действия.
8. **Удалить старый `navbar.component.ts`** (и его импорты) после полного переноса.
9. **Темы/адаптив/QA** — light+dark, три брейкпоинта, клавиатура.
10. **Сборка** `npm run build` (должна проходить чисто), визуальная проверка через preview на `:4200` (Docker) или локальный `ng serve`.

> Примечание для исполнителя: проект гоняется в Docker (`docker compose up -d --build frontend` пересобирает nginx-образ). Для быстрой итерации по UI удобнее локальный `ng serve` с `proxy.conf.json` → backend на `localhost:8000` (НЕ `backend:8000`, тот хостнейм только внутри Docker). Не плодить дубль ng-serve на занятом порту 4200.

---

## 9. Критерии приёмки (чек-лист)
- [ ] Постоянный левый сайдбар на всех страницах приложения (кроме bare: login/register/forgot/payment).
- [ ] Сайдбар сворачивается/разворачивается; состояние сохраняется между перезагрузками.
- [ ] Все ключевые разделы достижимы из сайдбара ≤ 1 клик (или 1 раскрытие группы).
- [ ] При входе в событие в сайдбаре появляется его контекстная под-навигация (6 разделов + Edit + «All events») с названием события.
- [ ] Роли учитываются: гость/attendee/organizer/admin видят корректный набор.
- [ ] Активный пункт подсвечен; хлебные крошки/тайтл в topbar корректны.
- [ ] Дублирующие тулбары переходов внутри страниц события убраны.
- [ ] Уведомления (badge+dropdown), theme toggle, профиль, logout доступны из shell.
- [ ] Адаптив: desktop постоянный, mobile — drawer по бургеру с оверлеем и закрытием.
- [ ] Light + dark темы консистентны; контраст AA; полная клавиатурная навигация + focus-ring.
- [ ] `npm run build` без ошибок; нет ошибок в консоли браузера на ключевых маршрутах.
- [ ] Старый `navbar.component.ts` удалён, мёртвых импортов нет.

---

## 10. Вне области (MVP) / на будущее
- Полноценный command-palette (`⌘K`) с фаззи-поиском по событиям/действиям — позже (в topbar пока только визуальная кнопка-заглушка).
- Flyout-поповеры под-пунктов в collapsed-режиме (MVP: авто-разворот сайдбара).
- Drag-to-resize ширины сайдбара.
- Пер-юзерные «закреплённые» пункты/недавние события.

## 11. Открытые вопросы (с дефолтными решениями — менять только если возразят)
1. **Topbar + Sidebar или только Sidebar?** → **Оба** (Grafana-стиль): sidebar = навигация, topbar = крошки + notif/theme/profile. *(дефолт принят)*
2. **My Events vs Dashboard** — оба остаются отдельными пунктами в ORGANIZE. *(дефолт)*
3. **Admin** — переиспользуем `/organizer/dashboard` в admin-режиме (отдельного фронт-роута нет). *(дефолт)*
4. **Глобальный поиск в topbar** — в MVP кнопка-заглушка `⌘K`, без логики. *(дефолт)*
