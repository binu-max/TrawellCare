# TravelCare (TrawellCare)

Health-travel platform monorepo: **integration** (travel vendors + notifications) and **platform** (identity, cases, quotes, engagement).

Architecture notes live locally under `docs/` (gitignored on GitHub). Each service has its own README and env template.

## Repository layout

| Path | Purpose |
|------|---------|
| [`services/integration`](services/integration) | Port **8004**, schema `integration` — [README](services/integration/README.md) |
| [`services/platform`](services/platform) | Port **8001**, schema `platform` — [README](services/platform/README.md) |
| [`libs/tc_common`](libs/tc_common) | Shared errors and problem JSON |
| [`infra/docker-compose.yml`](infra/docker-compose.yml) | Postgres, Mailpit, both APIs and workers |
| [`.env.example`](.env.example) | Combined env template for repo-root `.env` |

## Quick start

**Prerequisites:** [uv](https://docs.astral.sh/uv/), Python **3.12** ([`.python-version`](.python-version)), PostgreSQL 14+ (or Docker Compose).

```bash
cp .env.example .env
# Edit .env — see services/integration/.env.example and services/platform/.env.example

uv sync

docker compose -f infra/docker-compose.yml up -d postgres   # optional

uv run --directory services/integration alembic upgrade head
uv run --directory services/platform alembic upgrade head
```

**Run locally (four terminals):**

```bash
uv run --directory services/integration uvicorn app.main:app --reload --port 8004
uv run --directory services/integration python -m app.worker
uv run --directory services/platform uvicorn app.main:app --reload --port 8001
uv run --directory services/platform python -m app.worker
```

| Service | Swagger |
|---------|---------|
| Integration | http://127.0.0.1:8004/docs (`X-Api-Key`) |
| Platform | http://127.0.0.1:8001/docs (`Bearer` or `X-Api-Key` for enquiries) |

**Full stack in Docker:**

```bash
docker compose -f infra/docker-compose.yml up --build
```

## Environment

Both services read a single **`.env` at the repo root** (never commit it). Variable groups:

- Integration: [`services/integration/.env.example`](services/integration/.env.example)
- Platform: [`services/platform/.env.example`](services/platform/.env.example)
- Combined template: [`.env.example`](.env.example)

Shared database URL example:

`DATABASE_URL=postgresql+asyncpg://integration_user:integration@localhost:5432/trawellcare`

## Tests

```bash
uv run --directory services/integration pytest
uv run --directory services/platform pytest
```

## Stop local processes

```bash
pkill -f "uvicorn app.main:app"
pkill -f "app.worker"
pkill -f mailpit
```

## Roadmap (not in this repo yet)

Commerce, vault, assistant, admin services; patient/admin front ends; CRM sync; Redis event bus.

For setup checklists, Akbar allowlisting, SendGrid, and API details, use the service READMEs linked above.
