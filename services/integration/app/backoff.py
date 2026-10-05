from datetime import UTC, datetime, timedelta

BACKOFF_SECONDS = (5, 30, 120, 600, 1800)
MAX_ATTEMPTS = 8


def next_attempt_at(attempts: int, now: datetime | None = None) -> datetime:
    moment = now or datetime.now(UTC)
    index = min(max(attempts, 1), len(BACKOFF_SECONDS)) - 1
    return moment + timedelta(seconds=BACKOFF_SECONDS[index])
