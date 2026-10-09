# Platform service

FastAPI service for **identity** (customer phone OTP, staff login + TOTP), **cases**, **catalogue**, **clinical** matching, **quotes**, and **engagement** (reviews, chatbot handoff). Postgres schema: `platform`. Default port: **8001**.

Calls the [integration service](../integration/README.md) for SMS OTP when `OTP_DELIVERY=integration`.

Parent repo: [TravelCare](../../README.md).

## Layout

| Path | Purpose |
|------|---------|
| `app/main.py` | HTTP API |
| `app/worker.py` | Background jobs (follow-ups, async work) |
| `app/modules/identity/` | Auth, customers, staff |
| `app/modules/cases/` | Case lifecycle |
| `app/modules/catalogue/` | Providers and offerings |
| `app/modules/clinical/` | Care plans and matching |
| `app/modules/quotes/` | Quote requests and responses |
| `app/modules/engagement/` | Reviews, enquiries / chatbot handoff |
| `alembic/` | Migrations |
| `tests/` | API and route coverage |
| [`.env.example`](.env.example) | Platform env vars (merged into repo-root `.env`) |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) from repo root (`uv sync`)
- PostgreSQL with schema `platform` ([infra/init-db.sql](../../infra/init-db.sql))
- Integration API on **8004** if using real SMS OTP (`OTP_DELIVERY=integration`)

## Setup

Environment is loaded from **`<repo-root>/.env`**. Copy the platform block from [`.env.example`](.env.example) into that file (or use the combined [`.env.example`](../../.env.example) at the root).

```bash
# from repo root
uv sync
uv run --directory services/platform alembic upgrade head
```

Startup seeds catalogue data and staff users (see **Seeded staff** below).

## Run

**API:**

```bash
uv run --directory services/platform uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

**Worker:**

```bash
uv run --directory services/platform python -m app.worker
```

**Docker:** platform + worker are defined in [infra/docker-compose.yml](../../infra/docker-compose.yml).

## Swagger / OpenAPI

| URL | Description |
|-----|-------------|
| http://127.0.0.1:8001/docs | Swagger UI |
| http://127.0.0.1:8001/redoc | ReDoc |

**Customer and staff routes:** `Authorization: Bearer` (access token from phone OTP or staff login + TOTP).

**Chatbot / service handoff:** `POST /v1/enquiries` (and related engagement routes) use header **X-Api-Key** = `PLATFORM_SERVICE_API_KEY`.

## Configuration

See [`.env.example`](.env.example).

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Same DB as integration; schema `platform` |
| `PLATFORM_SERVICE_API_KEY` | Service-to-service and chatbot handoff |
| `INTEGRATION_BASE_URL` | e.g. `http://127.0.0.1:8004` |
| `INTEGRATION_API_KEY` | Must match integration service |
| `OTP_DELIVERY` | `integration` (call integration SMS) or `log` (dev, no SMS) |
| `STAFF_SEED_PASSWORD` | Password for seeded staff accounts |
| `STAFF_TOTP_SECRET` | Shared TOTP secret for seeded staff MFA |
| `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` | Optional PEM; auto-generated if empty (dev only) |

## Seeded staff (local dev)

Replace passwords and TOTP before any shared environment.

| Email | Role (seed) |
|-------|-------------|
| `ops@trawellcare.local` | Operations |
| `cm@trawellcare.local` | Case manager |
| `curator@trawellcare.local` | Curator |
| `doctor@trawellcare.local` | Clinical |
| `auditor@trawellcare.local` | Auditor |

Login flow: `POST /v1/auth/staff/login` → `POST /v1/auth/staff/totp` with code from authenticator app configured with `STAFF_TOTP_SECRET`.

Customer flow: `POST /v1/auth/phone/start` → `POST /v1/auth/phone/verify` (OTP via integration or log mode).

## Checklist (platform)

- [ ] Repo-root `.env` includes platform vars from `.env.example`
- [ ] `PLATFORM_SERVICE_API_KEY` and `INTEGRATION_API_KEY` aligned with integration service
- [ ] Migrations applied
- [ ] Integration running on 8004 if `OTP_DELIVERY=integration`
- [ ] Change `STAFF_SEED_PASSWORD` and `STAFF_TOTP_SECRET` outside local-only use
- [ ] Set stable `JWT_*` keys for staging/production

## Tests

```bash
uv run --directory services/platform pytest
```

Route smoke (broader coverage):

```bash
uv run --directory services/platform pytest tests/test_all_routes.py
```

Uses `trawellcare_test` by default (`TEST_DATABASE_URL` override optional).

## Security

- Do not commit repo-root `.env`.
- `PLATFORM_SERVICE_API_KEY` and `INTEGRATION_API_KEY` are shared secrets between services; rotate together.
- Auto-generated JWT keys are for local dev only; provision real keys for deployed environments.
