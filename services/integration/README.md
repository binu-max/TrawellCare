# Integration service

FastAPI service for **travel vendors** (Akbar/Benzy B2B flights, manual fallback) and **notifications** (email via SMTP, SMS OTP). Postgres schema: `integration`. Default port: **8004**.

Parent repo: [TravelCare](../../README.md).

## Layout

| Path | Purpose |
|------|---------|
| `app/main.py` | HTTP API |
| `app/worker.py` | Notification queue + in-flight travel jobs |
| `app/modules/travel/` | Search, price, confirm, cancel |
| `app/modules/notify/` | Templates, enqueue, SMTP adapter |
| `app/modules/vendors/` | Vendor registry and enable/disable |
| `alembic/` | Migrations |
| `tests/` | Unit and API tests |
| [`.env.example`](.env.example) | Integration env vars (merged into repo-root `.env`) |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) from repo root (`uv sync`)
- PostgreSQL with schema `integration` (see [infra/init-db.sql](../../infra/init-db.sql) or Docker Compose)
- Optional: [Mailpit](https://github.com/axllent/mailpit) for local email UI

## Setup

Environment is loaded from **`<repo-root>/.env`**. Copy the integration block from [`.env.example`](.env.example) into that file (or use the combined [`.env.example`](../../.env.example) at the root).

```bash
# from repo root
uv sync
uv run --directory services/integration alembic upgrade head
```

## Run

**API:**

```bash
uv run --directory services/integration uvicorn app.main:app --reload --host 127.0.0.1 --port 8004
```

**Worker** (required for queued email and async travel steps):

```bash
uv run --directory services/integration python -m app.worker
```

**Mailpit (optional):**

```bash
mailpit --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025
# UI: http://127.0.0.1:8025
```

**Docker** (integration + worker + Postgres + Mailpit): see [infra/docker-compose.yml](../../infra/docker-compose.yml).

## Swagger / OpenAPI

| URL | Description |
|-----|-------------|
| http://127.0.0.1:8004/docs | Swagger UI |
| http://127.0.0.1:8004/redoc | ReDoc |

Click **Authorize** and set **X-Api-Key** to `INTEGRATION_API_KEY`. `/health` and `/ready` are public.

**Hello-world email (Mailpit):**

1. Start API, worker, and Mailpit.
2. `POST /v1/notifications/test-hello?to=you@example.com` with header `Idempotency-Key: test-1`.
3. Open Mailpit — subject **Hello**, body **hello world**.

**Travel (Akbar):** `POST /v1/cases/{caseId}/travel-requests` → `POST /v1/travel-requests/{id}/search`. Optional `vendorCode`: `akbar` or `manual`.

## Configuration

Variables are documented in [`.env.example`](.env.example). Summary:

| Area | Key variables |
|------|----------------|
| Core | `DATABASE_URL`, `INTEGRATION_API_KEY` |
| Email | `SMTP_*`, `SENDGRID_API_KEY`, `EMAIL_FROM` |
| Akbar | `VENDOR_AKBAR_*` |

Vendor API code: **`akbar`**. Toggle: `PATCH /v1/vendors/akbar` with `{ "enabled": false }`. Manual vendor: **`manual`**.

Benzy docs: [B2B Revamp Flight](https://wrc.benzyinfotech.com/home/b2b-revamp-flight/flight/) (credentials from Akbar).

## Checklist (integration)

### Local dev

- [ ] Repo-root `.env` includes integration vars from `.env.example`
- [ ] `INTEGRATION_API_KEY` set
- [ ] Migrations applied
- [ ] Mailpit if you want browser email

### Akbar (live inventory)

- [ ] All `VENDOR_AKBAR_*` from Akbar test credentials
- [ ] **IP allowlisting** on Benzy for your public egress IP
- [ ] Optional live smoke: `RUN_LIVE_AKBAR=1 uv run --directory services/integration pytest tests/test_live_akbar.py -q`

### Email (production)

- [ ] SendGrid (or other SMTP): verified sender, TLS settings in `.env.example` comments
- [ ] Worker running

### SMS

- [ ] Twilio row seeded but disabled; dev uses **log** adapter only (DB, not real SMS)

### Not implemented here

- [ ] Resend HTTP adapter (use SMTP/SendGrid)
- [ ] Full Twilio send path

## Tests

```bash
uv run --directory services/integration pytest
```

## Security

- Keep Akbar, SendGrid, and `INTEGRATION_API_KEY` only in repo-root `.env`.
- Travel audit rows redact secrets in `integration.travel_calls`.
- Patient notification templates avoid clinical detail.
