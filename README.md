# TravelCare (trawellcare)

Health-travel platform MVP. This repository ships the **integration** service (travel vendors and notifications) and the **platform** service (identity, cases, care plans, and quotes).

Broader architecture and journey design live under [`docs/`](docs/) (see [`docs/trawellCareArch_v1.md`](docs/trawellCareArch_v1.md) and [`docs/lld.md`](docs/lld.md)). Platform, admin, and front-end services are planned; not in this repo yet.

## Repository layout

| Path | Purpose |
|------|---------|
| [`services/integration`](services/integration) | FastAPI app (port **8004**), schema `integration` |
| [`services/platform`](services/platform) | FastAPI app (port **8001**), schema `platform` — identity, cases, quotes |
| [`libs/tc_common`](libs/tc_common) | Shared errors and problem JSON |
| [`infra/docker-compose.yml`](infra/docker-compose.yml) | Postgres, Mailpit, integration API + worker |
| [`docs/`](docs/) | Architecture and LLD |
| [`.env.example`](.env.example) | Environment template (copy to `.env`) |

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** (Python package manager)
- **PostgreSQL 14+** (local install or Docker via Compose)
- Optional: **Docker** for Postgres + Mailpit + containerized API
- Optional: **Mailpit** (`brew install mailpit`) for viewing email in the browser

Python **3.12** is pinned via [`.python-version`](.python-version).

## First-time setup

### 1. Environment file

```bash
cp .env.example .env
```

Edit `.env` with your secrets. **Never commit `.env`** (it is gitignored).

Generate a strong API key for local use:

```bash
# example
INTEGRATION_API_KEY=local-dev-integration-key
```

### 2. Install dependencies (uv)

From the repo root:

```bash
uv sync
```

This creates `.venv`, installs workspace packages (`tc-common`, `integration`), and dev tools (pytest, etc.).

### 3. Database

**Option A — Docker Compose (Postgres only)**

```bash
docker compose -f infra/docker-compose.yml up -d postgres
```

**Option B — Local Postgres**

Create role and database (adjust superuser if needed):

```sql
CREATE ROLE integration_user LOGIN PASSWORD 'integration';
CREATE DATABASE trawellcare OWNER integration_user;
CREATE DATABASE trawellcare_test OWNER integration_user;
\c trawellcare
CREATE SCHEMA IF NOT EXISTS integration AUTHORIZATION integration_user;
```

Set `DATABASE_URL` in `.env` to match (see `.env.example`).

### 4. Migrations

```bash
uv run --directory services/integration alembic upgrade head
```

Startup also runs seed data (vendors `akbar` + `manual`, notification providers, templates).

### 5. Run the integration API

```bash
uv run --directory services/integration uvicorn app.main:app --reload --host 127.0.0.1 --port 8004
```

### 6. Run the platform API

```bash
uv run --directory services/platform alembic upgrade head
uv run --directory services/platform uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Swagger: **http://127.0.0.1:8001/docs**. Customer and staff routes use `Authorization: Bearer`. The chatbot handoff `POST /v1/enquiries` uses `X-Api-Key` = `PLATFORM_SERVICE_API_KEY`. Phone OTP calls integration `POST /v1/sms/otp` unless `OTP_DELIVERY=log`.

Seeded staff (password `STAFF_SEED_PASSWORD`, authenticator secret `STAFF_TOTP_SECRET`): `ops@trawellcare.local`, `cm@trawellcare.local`, `curator@trawellcare.local`, `doctor@trawellcare.local`, `auditor@trawellcare.local`. Replace those secrets before any shared environment.

### 7. Run the notification / travel worker

Notifications and in-flight booking polls are **async**. In another terminal:

```bash
uv run --directory services/integration python -m app.worker
```

### 8. (Optional) Mailpit — email in the browser

For local email (no real inbox):

```bash
mailpit --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025
# or: docker compose -f infra/docker-compose.yml up -d mailpit
```

Open **http://127.0.0.1:8025**. Keep `.env` on `SMTP_HOST=localhost`, `SMTP_PORT=1025`, `SMTP_USE_TLS=false`.

### Full stack in Docker

```bash
docker compose -f infra/docker-compose.yml up --build
```

API: **http://localhost:8004** · Mailpit UI: **http://localhost:8025**

---

## Try the API (Swagger / OpenAPI)

| URL | Description |
|-----|-------------|
| http://127.0.0.1:8004/docs | Swagger UI |
| http://127.0.0.1:8004/redoc | ReDoc |
| http://127.0.0.1:8004/openapi.json | OpenAPI spec (Postman import) |

**Authentication:** Click **Authorize** in Swagger and set **X-Api-Key** to the value of `INTEGRATION_API_KEY` from your `.env`.  
`/health` and `/ready` do not require a key.

**Quick hello-world email (local + Mailpit):**

1. Start API, worker, and Mailpit.
2. `POST /v1/notifications/test-hello?to=you@example.com` with header `Idempotency-Key: test-1`.
3. Refresh Mailpit — subject **Hello**, body **hello world**.

**Travel (Akbar):** `POST /v1/cases/{caseId}/travel-requests` → `POST /v1/travel-requests/{id}/search`. Use a UUID for `caseId`. Optional body field `vendorCode` (`akbar` or `manual`).

---

## Configuration reference

All variables below are defined in [`.env.example`](.env.example).

### Core

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Async Postgres URL, e.g. `postgresql+asyncpg://integration_user:integration@localhost:5432/trawellcare` |
| `INTEGRATION_API_KEY` | Yes | Shared secret; sent as header `X-Api-Key` on protected routes |

### Email (SMTP)

| Variable | Required | Description |
|----------|----------|-------------|
| `SMTP_HOST` | Yes | `localhost` (Mailpit) or `smtp.sendgrid.net` |
| `SMTP_PORT` | Yes | `1025` (Mailpit) or `587` (SendGrid) |
| `SMTP_USE_TLS` | Yes | `false` for Mailpit; `true` for SendGrid |
| `SMTP_USER` | SendGrid | SendGrid: `apikey` |
| `SMTP_PASSWORD` | Optional | SMTP password if not using `SENDGRID_API_KEY` |
| `SENDGRID_API_KEY` | SendGrid | API key (used as SMTP password when `SMTP_USER=apikey`) |
| `EMAIL_FROM` | Yes | From address; must be verified with SendGrid for production |

Provider rows in the DB: `smtp` (enabled by default), `resend` (disabled, not implemented yet). Toggle via `PATCH /v1/notification-providers/{code}`.

### Akbar Travels (Benzy B2B flight)

| Variable | Required | Description |
|----------|----------|-------------|
| `VENDOR_AKBAR_FLIGHT_BASE_URL` | Yes | Test: `https://b2bapiflights.benzyinfotech.com` |
| `VENDOR_AKBAR_UTILS_BASE_URL` | Yes | Test: `https://b2bapiutils.benzyinfotech.com` |
| `VENDOR_AKBAR_MERCHANT_ID` | Yes | Merchant / AUI (from Akbar) |
| `VENDOR_AKBAR_CLIENT_ID` | Yes | Client ID for Signature + API |
| `VENDOR_AKBAR_API_KEY` | Yes | ApiKey in Signature payload |
| `VENDOR_AKBAR_PASSWORD` | Yes | Password in Signature payload |
| `VENDOR_AKBAR_BROWSER_KEY` | Yes | BrowserKey in Signature / StartPay |
| `VENDOR_AKBAR_KEY` | Often | Extra `Key` field when provided by Akbar |
| `VENDOR_AKBAR_AGENT_CODE` | Optional | Agent code if supplied |
| `VENDOR_AKBAR_CHANNEL_ID` | Optional | e.g. `b2bsaudideals` (sent on search when set) |

Vendor `code` in API: **`akbar`**. Disable without redeploy: `PATCH /v1/vendors/akbar` with `{ "enabled": false }`. Manual fallback vendor: **`manual`**.

API docs (Postman): [Benzy Web Connect – B2B Revamp Flight](https://wrc.benzyinfotech.com/home/b2b-revamp-flight/flight/) (login credentials from Akbar).

---

## Setup checklist — what is still pending

Use this before pilot or production.

### Must have for local development

- [ ] `.env` created from `.env.example`
- [ ] `INTEGRATION_API_KEY` set
- [ ] Postgres running; `alembic upgrade head` applied
- [ ] Mailpit (or Docker Mailpit) if you want to see email in the browser

### Akbar / flight search (live inventory)

- [ ] All `VENDOR_AKBAR_*` values filled from Akbar test credentials
- [ ] **IP allowlisting** — Akbar/Benzy must whitelist your **public egress IP** (office VPN or server). Without this, Signature/search may **timeout** even with correct keys
- [ ] Confirm test airline (e.g. Indigo) enabled on your Akbar test account
- [ ] Optional: run live smoke test — `RUN_LIVE_AKBAR=1 uv run --directory services/integration pytest tests/test_live_akbar.py -q`

### Email — real delivery (not Mailpit)

- [ ] **SendGrid** account and **verified sender** domain or single sender
- [ ] `SENDGRID_API_KEY` (or `SMTP_PASSWORD`) in `.env`
- [ ] Switch SMTP settings to SendGrid block in `.env.example` (`smtp.sendgrid.net`, port 587, TLS on)
- [ ] `EMAIL_FROM` matches verified sender
- [ ] Worker running so queued messages are sent

### SMS (OTP / notifications)

- [ ] **Twilio** (or other) — provider `twilio` is seeded **disabled**; only **`log`** SMS adapter is implemented for dev (messages stored in DB, not sent to phones)
- [ ] Production: Twilio credentials + adapter implementation (pending)

### Not implemented in this repo yet

- [x] Platform service (`services/platform`, port 8001) — identity, cases, care plans, quotes
- [ ] Commerce, vault, assistant, admin services
- [ ] Patient/admin front ends (`apps/web`, `apps/admin`)
- [ ] CRM sync, Redis event bus between services
- [ ] Resend HTTP adapter (DB row exists; use SMTP/SendGrid today)
- [ ] Staff JWT from platform (today: `X-Api-Key` only)

---

## Tests

```bash
uv run --directory services/integration pytest
```

Live Akbar test (optional, hits real Benzy endpoints):

```bash
RUN_LIVE_AKBAR=1 uv run --directory services/integration pytest tests/test_live_akbar.py -q
```

---

## Stop local processes

```bash
pkill -f "uvicorn app.main:app"
pkill -f "app.worker"
pkill -f mailpit
```

---

## Security notes

- Keep Akbar, SendGrid, and `INTEGRATION_API_KEY` values only in `.env`.
- Do not log Signature payloads or SMTP passwords; travel audit rows redact secrets in `integration.travel_calls`.
- Notification bodies for patients should avoid clinical detail (templates are case ref + link only).

For questions on Akbar API fields or allowlisting, contact Akbar Travels / Benzy support with your public IP and test `ClientID`.
