# ТЗ для Claude: полный редизайн и переписывание frontend EventHub

## Роль
Ты работаешь как senior frontend engineer + product designer. Нужно полностью переписать frontend EventHub на базе существующего Angular-проекта, сохранив рабочие бизнес-сценарии, API-контракты и текущую backend-интеграцию.

Главная цель: заменить текущий визуальный стиль полностью. Текущий дизайн не нравится владельцу проекта: он воспринимается как шаблонный, тяжёлый, тёмный, glass/neon, с неудачной визуальной иерархией. Новый frontend должен ощущаться как зрелый, чистый, современный event marketplace, а не как лендинг с декоративными карточками.

## Контекст проекта
Проект: EventHub.

Назначение: платформа для поиска, создания, регистрации, оплаты и проверки билетов на события.

Текущий стек frontend:
- Angular `21`
- Standalone components
- TypeScript `5.9`
- Tailwind CSS
- RxJS
- lucide-angular
- Angular Router
- HTTP interceptors для JWT auth

Backend уже существует. Его переписывать нельзя. Нужно использовать текущие сервисы и API-контракты.

Ключевые frontend-файлы:
- `frontend/src/app/app.routes.ts`
- `frontend/src/app/models/models.ts`
- `frontend/src/app/services/auth.service.ts`
- `frontend/src/app/services/event.service.ts`
- `frontend/src/app/services/payment.service.ts`
- `frontend/src/app/interceptors/auth.interceptor.ts`
- `frontend/src/app/guards/auth.guard.ts`

## Главный принцип
Переписать весь UI и UX, но не ломать бизнес-логику.

Нужно сохранить:
- маршруты
- auth flow
- API-вызовы
- модели данных
- оплату через Stripe
- регистрацию на события
- личный кабинет
- dashboard организатора
- QR/check-in flow

Можно менять:
- структуру компонентов
- HTML/CSS/Tailwind
- visual design system
- layout
- navigation
- interaction patterns
- component composition
- shared UI primitives
- responsive behavior

Нельзя:
- менять backend API без необходимости
- удалять существующие user flows
- делать только красивую главную страницу вместо полноценного приложения
- превращать приложение в маркетинговый лендинг
- оставлять текущий black/glass/neon стиль

## Новое дизайн-направление
Сделать EventHub как современный marketplace для событий: ясный, уверенный, удобный, с хорошей плотностью информации.

Желаемое ощущение:
- premium, но не пафосный
- светлый или нейтральный light-first интерфейс
- чистый marketplace, а не crypto/neon dashboard
- уверенная типографика
- понятная навигация
- события в центре внимания
- рабочие экраны должны быть удобными для повторного использования

Избегать:
- тёмного glassmorphism как основной темы
- neon blue/green glow
- огромных hero-блоков, которые мешают пользоваться сайтом
- декоративных gradient blobs/orbs
- фиолетово-синих градиентов
- перегруженных карточек внутри карточек
- слишком больших border-radius
- generic AI SaaS look
- бессмысленных анимаций

Визуальные ориентиры:
- Eventbrite по ясности сценариев
- Airbnb по аккуратности карточек и фильтров
- Linear/Stripe Dashboard по чистоте рабочих экранов
- modern editorial marketplace по типографике

Не копировать эти продукты, а взять уровень аккуратности.

## Информационная архитектура
Первый экран должен быть не пустым лендингом, а рабочим discovery experience.

Основные зоны приложения:
- public discovery
- event detail
- auth
- attendee account
- organizer workspace
- payment result
- ticket validation

Навигация должна быть простой:
- logo / home
- search/discover
- create event
- my tickets
- organizer dashboard
- profile
- login/logout

Для авторизованных и неавторизованных пользователей навигация должна отличаться.

## Обязательные маршруты
Сохранить и переработать UI для всех текущих routes:

- `/` — discovery/home
- `/events/:id` — event detail
- `/create-event` — create event
- `/edit-event/:id` — edit event
- `/login` — sign in
- `/forgot-password` — password reset
- `/register` — registration with email verification
- `/profile` — user profile
- `/my-events` — organizer/user events
- `/my-registrations` — attendee tickets
- `/organizer/dashboard` — organizer dashboard
- `/organizer/events/:id/attendees` — attendee management
- `/validate/:uuid` — ticket validation/check-in
- `/payment/success` — payment success
- `/payment/cancel` — payment cancelled
- `**` — not found

## Экран: Discovery/Home
Цель: пользователь сразу видит события и может искать.

Требования:
- компактный верхний discovery-блок с поиском
- фильтры: category, location, free/paid, online/offline, sort
- список событий сразу на первом экране
- category rail или sidebar filters
- пагинация/load more
- empty state
- loading state
- error state

Не делать огромный hero, который занимает весь экран.

## Экран: Event Card
Карточка события должна быть информативной и аккуратной.

Показать:
- image или fallback
- title
- date/time
- location или online badge
- category
- price/free
- available spots
- organizer mini info
- status, если нужно

Карточка должна хорошо работать в grid/list на desktop и mobile.

## Экран: Event Detail
Цель: быстро понять событие и зарегистрироваться.

Требования:
- сильный visual area для image/event identity
- title, date, location, category, price
- organizer
- description
- capacity/available spots
- CTA registration
- для paid event: корректный переход к checkout flow
- для organizer/admin: edit/manage actions
- states: already registered, full event, own event, unauthenticated

## Auth Screens
Экран login/register/forgot-password должен быть спокойным, понятным и без лишнего визуального шума.

Требования:
- validation errors
- loading states
- password reset flow по шагам
- registration email verification flow
- returnUrl после login
- mobile-friendly forms

## Profile
Требования:
- просмотр и редактирование базовых данных
- nested profile fields
- avatar display/fallback
- save/cancel states
- success/error feedback

## My Registrations
Это экран билетов пользователя.

Требования:
- список регистраций
- event info
- registration status
- QR/ticket UUID, если есть текущий UI для билета
- payment/action states
- cancelled/rejected/confirmed/pending визуально различимы
- понятный empty state

## My Events
Экран событий пользователя/организатора.

Требования:
- список созданных events
- statuses: pending, published, rejected, cancelled, completed
- quick actions: edit, delete, attendees, validate
- visual distinction between public and pending

## Organizer Dashboard
Сделать как рабочую панель, не как лендинг.

Требования:
- overview metrics
- events requiring action
- status overview
- registrations/check-ins summary
- quick links to attendee list
- admin controls, если user is_superuser

## Attendee List
Требования:
- searchable table/list
- participant username
- registration status
- registered_at
- approve/reject actions
- check-in status
- stats: total, checked-in, remaining, check-in rate
- mobile table adaptation

## Validate Ticket
Это должен быть быстрый operational screen.

Требования:
- clear success/used/error states
- attendee name
- event title
- checked-in time
- clear next-ticket action
- no decorative UI that delays scanning workflow

## Payment Screens
Payment success/cancel должны быть clean confirmation screens.

Требования:
- success state
- event title
- amount
- payment status
- link to my tickets
- cancel state with retry/navigation

## Shared UI System
Создать или привести к единой системе:

- buttons
- inputs
- selects
- badges
- cards
- page headers
- empty states
- loading states
- error messages
- modal
- toast
- table/list components
- form sections

Можно реализовать как standalone shared components в:
- `frontend/src/app/components/shared`

Если компонент слишком локальный, держать рядом с feature.

## TypeScript и Angular требования
Соблюдать:
- standalone components
- строгая типизация
- избегать `any`
- не ломать existing services
- использовать существующие models из `models.ts`
- использовать Angular control flow, если уже используется
- не добавлять state management library без необходимости
- не добавлять тяжёлые UI frameworks
- lucide-angular использовать для иконок

Можно улучшить:
- shared layout components
- typed view models
- helper functions для UI formatting
- reusable status mapping
- frontend constants

## API/Business Flow
Сохранить интеграции:

Auth:
- register
- send registration code
- verify registration code
- login
- logout
- refresh token
- get/update profile
- password reset request/verify/confirm

Events:
- get categories
- get events
- get event
- create/update/delete event
- register/cancel
- approve/reject event
- my events
- my registrations
- attendee list
- stats
- check-in
- approve/reject registration

Payments:
- create checkout session
- verify payment

## UX States
Каждый экран должен иметь:
- loading state
- empty state
- error state
- success feedback where relevant
- disabled states for pending actions
- mobile layout

Нельзя оставлять пользователю пустой экран без объяснения.

## Responsive
Обязательно проверить:
- mobile 360px
- mobile 390px
- tablet 768px
- desktop 1280px
- wide desktop 1440px+

На mobile:
- navigation не должна ломаться
- filters должны быть usable
- tables должны превращаться в list/card layout
- buttons and labels must not overflow

## Accessibility
Требования:
- semantic HTML
- labels for inputs
- focus states
- keyboard accessible controls
- sufficient contrast
- no text overlap
- no important action hidden behind hover-only behavior
- aria-label для icon-only buttons

## Performance
Требования:
- не добавлять тяжёлые зависимости без причины
- lazy loading сохранить там, где он уже есть
- images должны иметь fallback
- не делать чрезмерных animations
- build должен проходить

## Качество кода
После переписывания:
- `npm run build` должен проходить
- TypeScript errors должны быть исправлены
- не оставлять dead code
- не оставлять console.log/debug
- не оставлять старый неиспользуемый UI/CSS
- компоненты должны быть читаемыми
- повторяющиеся UI-паттерны вынести в shared

## Предлагаемая структура
Можно оставить текущую структуру, но лучше привести к более понятной:

- `components/shared`
- `components/layout`
- `components/home`
- `components/events`
- `components/auth`
- `components/profile`
- `components/organizer`
- `components/payments`
- `components/tickets`
- `services`
- `models`
- `guards`
- `interceptors`

Не обязательно делать миграцию структуры ради структуры. Делать только если это реально упрощает проект.

## Acceptance Criteria
Работа считается принятой, если:

1. Все существующие routes открываются.
2. Пользователь может искать события.
3. Пользователь может зарегистрироваться и войти.
4. Пользователь может просмотреть event detail.
5. Авторизованный пользователь может зарегистрироваться на event.
6. Организатор может создать/редактировать event.
7. Организатор может видеть attendee list.
8. Организатор может approve/reject registrations.
9. Check-in screen показывает success/used/error.
10. Payment success/cancel screens работают.
11. Mobile layout не разваливается.
12. `npm run build` проходит.
13. Старый visual direction полностью заменён.
14. UI выглядит как цельная система, а не набор отдельных страниц.

## Особые пожелания владельца проекта
Владелец проекта прямо недоволен текущим дизайном. Нужен не лёгкий facelift, а полноценная замена frontend-впечатления.

Главное:
- не оставлять старый dark neon glass стиль
- не делать шаблонный AI дизайн
- сделать продуктовым, чистым, удобным
- уделить внимание реальным сценариям, не только красоте
- EventHub должен ощущаться как нормальная event platform, которую не стыдно показывать

## Порядок работы
Рекомендуемый порядок:

1. Проанализировать текущие routes, services, models.
2. Создать новую visual system: colors, type scale, spacing, components.
3. Переписать layout/navigation.
4. Переписать discovery/home.
5. Переписать event card/detail.
6. Переписать auth screens.
7. Переписать account/tickets/profile.
8. Переписать organizer dashboard/attendees.
9. Переписать payment/check-in/not-found.
10. Удалить мёртвый CSS/старые паттерны.
11. Прогнать build.
12. Проверить mobile/desktop.

## Финальный отчёт
В конце работы дать краткий отчёт:
- какие компоненты переписаны
- какие shared components добавлены
- какие flows проверены
- какие команды запускались
- есть ли остаточные риски

