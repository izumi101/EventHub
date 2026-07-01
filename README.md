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
| Backend | Django 5, Django REST Framework, Simple JWT, Django Channels (WebSocket), Daphne |
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
docker compose up --build
```

После запуска:

- Frontend: http://localhost:4200
- Backend API: http://localhost:8000/api/
- Django admin: http://localhost:8000/admin/
- PostgreSQL (для DataGrip/DBeaver): localhost:5433

Тестовые аккаунты (создаются автосидом при первом запуске):

```text
admin / admin123
organizer / password123
attendee / password123
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

```bash
# Backend
cd EventHub/backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data --noinput
python manage.py runserver

# Frontend
cd EventHub/frontend
npm install
npm start
```

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
| `DJANGO_SEED_DATA` | `1` — автозаполнение демо-данными при старте |
| `FRONTEND_URL` | используется для редиректов после оплаты |
| `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` | ключи Stripe |

## API

Полное описание эндпоинтов и готовые запросы — в [`EventHub/postman_collection.json`](EventHub/postman_collection.json). Основные группы:

- `/api/auth/` — регистрация, логин, профиль, обновление токена.
- `/api/events/` — CRUD событий, категории, поиск, регистрации.
- `/api/payments/` — Stripe checkout, вебхуки, проверка статуса оплаты.

Технические спецификации отдельных фич — в [`EventHub/docs/`](EventHub/docs/).

## Перед продакшн-деплоем

- Установить `DJANGO_DEBUG=0` и сгенерировать новый `DJANGO_SECRET_KEY`.
- Задать точные списки `DJANGO_ALLOWED_HOSTS`, CORS и CSRF origins под реальный домен.
- Использовать managed PostgreSQL или защищённый Docker-инстанс.
- Хранить продовые ключи Stripe в секретах деплоя, не в Git.
