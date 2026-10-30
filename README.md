# EventHub

Полнофункциональная платформа для организации и продажи билетов на мероприятия. Backend на Django REST Framework, frontend на Angular, PostgreSQL с pgvector для семантического поиска, Redis для realtime-обновлений мест.

Организаторы создают события, настраивают карты мест и типы билетов, принимают оплату через Stripe и проверяют билеты на входе по QR-коду. Посетители ищут события, бронируют места и оплачивают билеты онлайн.

## Возможности

- **Аккаунты и роли** — регистрация, JWT-аутентификация, роли администратора/организатора/посетителя, восстановление пароля и подтверждение email.
- **События** — создание и модерация событий, категории, полнотекстовый и семантический поиск (pgvector + sentence-transformers), SEO-поля.
- **Билеты и брони** — несколько типов билетов, промокоды, донат-опционы, лист ожидания, групповые бронирования.
- **Карта мест** — интерактивный выбор мест с удержанием (hold) и обновлением в реальном времени через WebSocket (Django Channels).
- **Оплата** — Stripe Checkout, вебхуки, возвраты (refunds), партнёрские (affiliate) ссылки.
- **Check-in** — генерация и сканирование QR-билетов, списки check-in, история сканирований.
- **Аналитика и уведомления** — дашборд организатора, экспорт данных, email/websocket-уведомления, отзывы и избранное.
- **Бизнес-правила** — организатор не может купить билет на собственное событие; посетитель не может отменить подтверждённую бронь напрямую; выбор места сохраняется при навигации между страницами.

## Стек

| Слой | Технологии |
| --- | --- |
| Backend | Django 5, Django REST Framework, Simple JWT, Django Channels (WebSocket), Gunicorn + Uvicorn |
| База данных | PostgreSQL 16 + pgvector, Redis 7 |
| Оплата | Stripe (Checkout, Webhooks) |
| Поиск | sentence-transformers, pgvector |
| Frontend | Angular 21 (standalone components), RxJS, Tailwind CSS |
| Инфраструктура | Docker Compose, Nginx, Prometheus + Grafana (опционально) |

## Структура проекта

```text
EventHub/
├── backend/                 # Django REST API
│   ├── accounts/             # пользователи, профили, аутентификация
│   ├── events/                # события, брони, карты мест, поиск, аналитика
│   ├── bookings/               # групповые бронирования
│   ├── payments/               # Stripe-интеграция
│   └── eventhub_backend/        # настройки Django-проекта
├── frontend/                 # Angular SPA
│   └── src/app/
│       ├── components/         # страницы и виджеты
│       ├── services/            # HTTP- и WebSocket-клиенты
│       ├── guards/, interceptors/
│       └── layout/              # сайдбар, топбар, каркас приложения
├── monitoring/                # конфигурация Prometheus и Grafana
├── docs/                      # технические спецификации фич
├── docker-compose.yml
└── postman_collection.json    # коллекция запросов к API
```

## Быстрый старт

Требуется Docker и Docker Compose.

```bash
cd EventHub
cp .env.example .env      # режим разработки: DEBUG, демо-данные, тестовая оплата
docker compose up --build
```

Без `.env` compose не запустится: значения по умолчанию в `docker-compose.yml` рассчитаны на сервер (DEBUG выключен, демо-данных и фиктивной оплаты нет, секреты обязательны).

После запуска:

- Frontend: http://localhost:4200 и https://localhost (self-signed сертификат)
- Backend API: http://localhost:8000/api/ (порт открыт только на localhost)
- Django admin: http://localhost:8000/admin/
- PostgreSQL (для DataGrip/DBeaver): localhost:5433

Тестовые аккаунты (создаются, когда `DJANGO_SEED_DATA=1` и `DJANGO_DEBUG=1`):

```text
organizer / password123
attendee / password123
admin / <пароль из DJANGO_SEED_ADMIN_PASSWORD или из лога backend при первом запуске>
```

`STRIPE_MOCK_MODE=1` (только вместе с `DJANGO_DEBUG=1`) подтверждает оплату без списания денег. Для настоящего Stripe укажите тестовые ключи и `STRIPE_MOCK_MODE=0`.

### HTTPS и камера на телефоне

Сканер QR использует камеру, а браузеры дают к ней доступ только по HTTPS. Положите сертификат в `EventHub/frontend/certs/server.crt` и `server.key` (например, `mkcert localhost 192.168.0.10`). Если папка пустая, контейнер сам создаст self-signed сертификат для `localhost`. Ключи монтируются в контейнер, в образ они не попадают. Чтобы открыть приложение с телефона, добавьте IP компьютера в `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS` и `DJANGO_CSRF_TRUSTED_ORIGINS` в `.env`.

### Фоновые задачи

Сервис `worker` (`python manage.py run_worker`) выполняет очередь задач и раз в минуту — обслуживание: освобождает места с истёкшим удержанием, закрывает просроченные групповые брони, двигает лист ожидания и переводит прошедшие события в `completed`. GET-запросы в базу не пишут.

Письма, вебхуки и индексация для семантического поиска не выполняются внутри запроса: они записываются в таблицу `jobs_job` в той же транзакции, что и бизнес-изменение (transactional outbox). Если транзакция откатилась, письма не будет; если SMTP или сервер вебхука недоступен, задача повторится с растущей паузой (30 с … 1 ч, 3–6 попыток в зависимости от типа). Задачи, которые так и не выполнились, видны в Django admin → Jobs, оттуда их можно перезапустить действием «Retry». Несколько воркеров можно запускать параллельно: задачи забираются через `SELECT … FOR UPDATE SKIP LOCKED`.

Без воркера (например, при локальном запуске) задайте `JOBS_RUN_INLINE=1`: задачи будут выполняться сразу после коммита запроса.

### Облегчённый образ без семантического поиска

Образ ставит CPU-сборку PyTorch (без CUDA) и заранее скачивает модель, поэтому семантический поиск работает без доступа в интернет. Если он не нужен, поиск работает по ключевым словам, а образ собирается заметно быстрее — задайте в `.env`:

```bash
INSTALL_SEMANTIC_SEARCH=0
docker compose build backend worker
```

Остановить контейнеры:

```bash
docker compose down
```

Остановить и удалить том с базой данных (чистый старт):

```bash
docker compose down -v
```

## Локальная разработка без Docker

Нужны PostgreSQL 16 с расширением pgvector и Redis.

```bash
# Backend
cd EventHub/backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.lock                 # + requirements-search.lock для семантического поиска
export DJANGO_DEBUG=1 STRIPE_MOCK_MODE=1
python manage.py migrate
python manage.py seed_data --noinput
uvicorn eventhub_backend.asgi:application --reload --port 8000   # HTTP + WebSocket, перезапуск при изменениях
python manage.py run_worker                      # в отдельном терминале (или JOBS_RUN_INLINE=1)

# Frontend (dev-сервер проксирует /api, /ws и /media на backend)
cd EventHub/frontend
npm ci
npm start
```

## Тесты и проверки

```bash
cd EventHub/backend
python manage.py test        # нужен PostgreSQL: часть тестов проверяет настоящие транзакции и гонки
ruff check --select F,E9 --exclude "*/migrations/*" .

cd EventHub/frontend
npm test                     # unit-тесты (Vitest)
npm run build                # сборка в strict-режиме TypeScript с проверкой шаблонов и бюджетов бандла
npm audit                    # и runtime-, и dev-зависимости

# End-to-end тесты (Playwright) против запущенного стека: docker compose up
npx playwright install chromium
E2E_BASE_URL=http://localhost:4200 npx playwright test
```

E2E-тесты проверяют покупку билета (с mock-оплатой), CSP на реальной сборке, WebSocket карты мест через nginx и то, что письмо с кодом уходит через очередь, а не из запроса. Для них нужны демо-данные и mock-оплата из `.env.example`.

Те же проверки запускает GitHub Actions (`.github/workflows/ci.yml`) на каждый push и pull request; задача `e2e` поднимает весь `docker compose` и прогоняет Playwright, `search-image` собирает полный образ с PyTorch и проверяет модель без сети.

Зависимости Python зафиксированы в `requirements.lock` и `requirements-search.lock`. Диапазоны версий задаются в `requirements*.txt`, lock-файлы пересобираются командой из их заголовка (`uv pip compile …`).

## Переменные окружения

Скопируйте `EventHub/.env.example` в `EventHub/.env` и при необходимости отредактируйте:

```bash
cp EventHub/.env.example EventHub/.env
```

| Переменная | Назначение |
| --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | параметры PostgreSQL |
| `POSTGRES_HOST_PORT` | локальный порт для подключения к БД, по умолчанию `5433` |
| `DJANGO_SECRET_KEY` | секретный ключ Django — обязательно заменить перед реальным деплоем |
| `DJANGO_DEBUG` | `1` для разработки, `0` для продакшена |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | списки доверенных хостов/источников |
| `DJANGO_SEED_DATA` | `1` — демо-данные при старте (работает только с `DJANGO_DEBUG=1`) |
| `DJANGO_SEED_ADMIN_PASSWORD` | пароль демо-админа; если пусто, генерируется и печатается в лог |
| `FRONTEND_URL` | используется для редиректов после оплаты |
| `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` | ключи Stripe; при `DJANGO_DEBUG=0` обязательны |
| `STRIPE_MOCK_MODE` | `1` — оплата без Stripe (только для разработки, только с `DJANGO_DEBUG=1`) |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | SMTP для кодов подтверждения; при `DJANGO_DEBUG=0` обязательны |
| `JOBS_RUN_INLINE` | `1` — выполнять фоновые задачи сразу после запроса, без воркера (только для локальной разработки) |
| `WEB_CONCURRENCY` | число процессов backend (gunicorn + uvicorn) в контейнере, по умолчанию `2` |
| `INSTALL_SEMANTIC_SEARCH` | `0` — собрать backend без PyTorch и семантического поиска (по умолчанию `1`) |
| `DJANGO_NUM_PROXIES` | сколько прокси стоит перед Django (по умолчанию `1` — nginx); нужно для корректного rate limiting |
| `GRAFANA_ADMIN_PASSWORD` | пароль Grafana для `docker-compose.monitoring.yml` (обязателен) |

## API

Полное описание эндпоинтов и готовые запросы — в [`EventHub/postman_collection.json`](EventHub/postman_collection.json). Основные группы:

- `/api/auth/` — регистрация, логин, профиль, обновление токена.
- `/api/events/` — CRUD событий, категории, поиск, регистрации.
- `/api/payments/` — Stripe checkout, вебхуки, проверка статуса оплаты.
- `/api/bookings/` — групповые брони; организатор видит брони события (`/api/bookings/event/<id>/`) и может вернуть деньги за бронь (`POST /api/bookings/<id>/refund/`).
- `/ws/seats/<id>/` — обновления карты мест. JWT передаётся не в URL, а в подпротоколе: `new WebSocket(url, ['eventhub.jwt', accessToken])`.

Ошибки бизнес-правил приходят как `{"error": "<текст для человека>"}`; там, где клиенту нужно ветвиться, добавлен стабильный `code` (например, `QUEUE_REQUIRED` — сначала встаньте в очередь ожидания).

Технические спецификации отдельных фич — в [`EventHub/docs/`](EventHub/docs/).

## Перед продакшн-деплоем

При `DJANGO_DEBUG=0` backend сам откажется стартовать без ключей Stripe, SMTP и явного `DJANGO_ALLOWED_HOSTS`. Кроме этого:

- Сгенерировать новый `DJANGO_SECRET_KEY`.
- Задать точные списки `DJANGO_ALLOWED_HOSTS`, CORS и CSRF origins под реальный домен.
- Не публиковать порт 8000: снаружи должен быть доступен только nginx.
- Поставить настоящий TLS-сертификат и включить HSTS (строка закомментирована в `frontend/nginx-security-headers.conf`).
- Использовать managed PostgreSQL или защищённый Docker-инстанс.
- Хранить продовые ключи Stripe в секретах деплоя, не в Git.
- Миграция `accounts.0006` создаёт уникальный индекс по `lower(email)`. Если в базе уже есть аккаунты с одинаковым email, она остановится и выведет их список — объедините или переименуйте эти аккаунты и запустите `migrate` снова.
