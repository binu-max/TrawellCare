# Vault service

Document metadata and signed access for TrawellCare cases. Port **8003**, Postgres schema **`vault`**. File bytes live under **`VAULT_STORAGE_ROOT`** (local filesystem MVP; S3 later).

Parent repo: [TravelCare](../../README.md).

## APIs (MVP)

| Method | Path |
|--------|------|
| POST | `/v1/cases/{caseId}/documents/uploads` |
| PUT | `/v1/documents/{documentId}/upload?token=...` |
| POST | `/v1/documents/{documentId}/complete` |
| GET | `/v1/documents/{documentId}/url` |
| GET | `/v1/documents/{documentId}/download?token=...` |
| GET | `/v1/cases/{caseId}/documents?audience=customer\|staff` |

**Auth:** `Authorization: Bearer` (RS256 JWT from platform). Commands need **`Idempotency-Key`**.

**Case access:** vault forwards the bearer to platform `GET /v1/cases/{caseId}` unless `PLATFORM_CASE_CHECK_ENABLED=false` (tests only).

Production UIs should call vault **via BFF/proxy**, not from the browser directly ([architecture](../../docs/trawellCareArch_v1.md)).

## Setup

```bash
uv sync
uv run --directory services/vault alembic upgrade head
uv run --directory services/vault uvicorn app.main:app --reload --host 127.0.0.1 --port 8003
```

Swagger: http://127.0.0.1:8003/docs

## Environment (repo-root `.env`)

See [`.env.example`](.env.example). Important:

- `JWT_PUBLIC_KEY` — same PEM as platform (required in multi-process dev)
- `VAULT_SERVICE_API_KEY` — signs upload/download tokens
- `VAULT_STORAGE_ROOT` — local storage directory
- `PLATFORM_BASE_URL` — case ownership checks

## Tests

```bash
uv run --directory services/vault pytest
```

## Scan status

MVP marks documents **`clean` on complete** (stub). Replace with real AV before production PHI.
