# EventHub

EventHub is a full-stack event management application with Angular, Django REST Framework, and PostgreSQL. The project is wired so a developer can clone it and start the frontend, backend, database, migrations, and seed data with one command.

## Architecture

- `frontend`: Angular SPA. API URLs come from Angular environment files instead of hardcoded service strings.
- `backend`: Django REST Framework API with JWT auth, events, registrations, profiles, and Stripe payment hooks.
- `db`: PostgreSQL running in Docker with a persistent Docker volume.
- `postman_collection.json`: API collection for auth, categories, event CRUD, registrations, and payments.

Startup flow with Docker Compose:

1. PostgreSQL starts and waits until it is healthy.
2. Django starts after PostgreSQL healthcheck passes.
3. Django runs migrations automatically.
4. Django runs `python manage.py seed_data --noinput` automatically when `DJANGO_SEED_DATA=1`.
5. Gunicorn serves the Django API on `http://localhost:8000`.
6. Angular dev server serves the frontend on `http://localhost:4200`.

## Folder Structure

```text
EventHub/
|-- docker-compose.yml
|-- .env.example
|-- postman_collection.json
|-- backend/
|   |-- Dockerfile
|   |-- entrypoint.sh
|   |-- requirements.txt
|   |-- manage.py
|   |-- eventhub_backend/
|   |   |-- settings.py
|   |   `-- urls.py
|   |-- accounts/
|   |-- events/
|   |   |-- views/       # API views split by concern (events, registrations,
|   |   |   |            #   engagement, organizer, checkin, admin_dashboard)
|   |   |-- services/    # domain services (registration, lifecycle, refunds,
|   |   |   |            #   holds, realtime) — import from events.services
|   |   `-- management/commands/seed_data.py
|   `-- payments/
`-- frontend/
    |-- Dockerfile
    |-- angular.json
    |-- package.json
    `-- src/
        |-- environments/
        |   |-- environment.ts
        |   `-- environment.prod.ts
        `-- app/
            |-- services/
            |-- components/
            |-- guards/
            `-- interceptors/
```

## One Command Setup

```bash
cd "EventHub"
docker compose up --build
```

Open:

- Frontend: `http://localhost:4200`
- Backend API: `http://localhost:8000/api/`
- Django admin: `http://localhost:8000/admin/`
- PostgreSQL for DataGrip: `localhost:5433`; inside Docker: `db:5432`

Seeded demo accounts:

```text
admin / admin123
organizer / password123
attendee / password123
```

To stop containers:

```bash
docker compose down
```

To remove the PostgreSQL volume and start with a fresh database:

```bash
docker compose down -v
```

## Environment Variables

Docker Compose works with safe development defaults. For local overrides, copy `.env.example` to `.env` and edit it:

```bash
cp .env.example .env
```

Important variables:

| Variable | Purpose |
| --- | --- |
| `POSTGRES_DB` | PostgreSQL database name |
| `POSTGRES_USER` | PostgreSQL username |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `POSTGRES_HOST_PORT` | Local host port for DataGrip, defaults to `5433` |
| `DJANGO_SECRET_KEY` | Django secret key; replace for real deployments |
| `DJANGO_DEBUG` | `1` for development, `0` for production-like runs |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated Django allowed hosts |
| `DJANGO_CORS_ALLOWED_ORIGINS` | Comma-separated Angular/browser origins |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated CSRF trusted origins |
| `DJANGO_SEED_DATA` | `1` to seed automatically, `0` to skip |
| `DJANGO_COLLECTSTATIC` | `1` to collect static files at container start |
| `FRONTEND_URL` | Used by backend payment redirects |
| `STRIPE_SECRET_KEY` | Stripe secret key for checkout |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |

## Docker Services

`docker-compose.yml` defines three isolated services:

- `db`: `postgres:16-alpine`, persistent volume `postgres_data`, healthcheck with `pg_isready`. It is reachable by the backend as `db:5432`; use `docker compose exec db psql -U eventhub_user -d eventhub` when you need a SQL shell.
- `backend`: Django API image from `backend/Dockerfile`, runs migrations and seed data in `backend/entrypoint.sh`, then starts Gunicorn.
- `frontend`: Angular production build served by nginx on `localhost:4200`, with `/api/` proxied to the Django backend.

The backend uses these PostgreSQL settings from environment variables in `backend/eventhub_backend/settings.py`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'eventhub'),
        'USER': os.environ.get('POSTGRES_USER', 'eventhub_user'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'eventhub_password'),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}
```

## Seed Data

Seed data is implemented as an idempotent Django management command:

```bash
python manage.py seed_data --noinput
```

It creates:

- `admin`, `organizer`, and `attendee` users.
- Demo profiles.
- Event categories: Technology, Business, Education, Music, Sports.
- Demo published events.
- Demo registrations and one pending payment record.

Docker runs this command automatically from `backend/entrypoint.sh` after migrations when `DJANGO_SEED_DATA=1`.

## API Endpoints

Authentication:

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/auth/register/` | Register a new user |
| `POST` | `/api/auth/login/` | Login and receive JWT tokens |
| `POST` | `/api/auth/logout/` | Logout and blacklist refresh token |
| `GET` | `/api/auth/profile/` | Get current user profile |
| `PUT` | `/api/auth/profile/` | Update current user profile |
| `POST` | `/api/auth/token/refresh/` | Refresh access token |

Events and categories:

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/categories/` | List categories |
| `POST` | `/api/categories/` | Create a category |
| `GET` | `/api/events/` | List events with search, filtering, ordering, pagination |
| `POST` | `/api/events/` | Create an event |
| `GET` | `/api/events/{id}/` | Get event detail |
| `PUT` | `/api/events/{id}/` | Update an event |
| `DELETE` | `/api/events/{id}/` | Delete an event |
| `GET` | `/api/events/{id}/registrations/` | List event registrations |

Registrations:

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/events/{id}/register/` | Register for event |
| `POST` | `/api/events/{id}/cancel/` | Cancel registration |
| `GET` | `/api/my-events/` | Events organized by current user |
| `GET` | `/api/my-registrations/` | Registrations for current user |

Payments:

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/payments/create-checkout/{registration_id}/` | Create Stripe Checkout session |
| `POST` | `/api/payments/webhook/` | Stripe webhook |
| `GET` | `/api/payments/verify/?session_id=...` | Verify payment status |

## Angular API Configuration

Angular services use `environment.apiUrl`:

```ts
import { environment } from '../../environments/environment';

private apiUrl = environment.apiUrl;
```

Development config lives in `frontend/src/environments/environment.ts`:

```ts
export const environment = {
  production: false,
  apiUrl: '/api',
};
```

Production builds use `frontend/src/environments/environment.prod.ts` through the file replacement in `frontend/angular.json`.

## Postman Collection

Import `postman_collection.json` into Postman. The collection uses these variables:

- `baseUrl`: `http://localhost:8000/api`
- `accessToken`, `refreshToken`: updated automatically by login/register test scripts.
- `organizerAccessToken`, `attendeeAccessToken`: used for role-specific requests.
- `categoryId`, `createdEventId`, `registrationId`: updated by list/create/register requests.

Recommended Postman flow:

1. Run `Auth / Login Organizer`.
2. Run `Categories / List Categories` or `Create Category`.
3. Run `Events / Create Event`.
4. Run `Events / Get Created Event` and `Update Created Event`.
5. Run `Auth / Login Attendee`.
6. Run `Registrations / Register For Created Event`.
7. Run `Registrations / Cancel Created Event Registration` if needed.
8. Run `Events / Delete Created Event` when finished.

To maintain the collection:

1. Update requests whenever an endpoint, body shape, auth rule, or variable name changes.
2. Keep secrets out of the collection; use variables only.
3. Export as Postman Collection v2.1.
4. Replace `postman_collection.json` in the repository.
5. Run the collection against `docker compose up --build` before sharing.

## Production Notes

Before a real deployment:

- Set `DJANGO_DEBUG=0`.
- Replace `DJANGO_SECRET_KEY` and database passwords.
- Set a strict `DJANGO_ALLOWED_HOSTS` list.
- Set exact CORS and CSRF origins for the frontend domain.
- Set `DJANGO_COLLECTSTATIC=1` or collect static assets during image build/release.
- Use a managed PostgreSQL instance or secure the Docker PostgreSQL service properly.
- Put Stripe live/test keys in deployment secrets, not in Git.
