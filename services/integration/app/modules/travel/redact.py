import json

_SECRET_KEYS = {
    "apikey",
    "password",
    "key",
    "token",
    "authorization",
    "browserkey",
    "cvv",
    "number",
}


def redact(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key.lower() in _SECRET_KEYS:
                cleaned[key] = "***"
            else:
                cleaned[key] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def shrink(value: dict, limit: int = 200_000) -> dict:
    encoded = json.dumps(value, default=str)
    if len(encoded) <= limit:
        return value
    return {
        "truncated": True,
        "code": value.get("Code") or value.get("code"),
        "tui": value.get("TUI") or value.get("tui"),
    }
