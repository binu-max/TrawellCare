import base64


def encode_offset(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode_offset(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(base64.urlsafe_b64decode(cursor.encode()).decode()))
    except (ValueError, UnicodeDecodeError):
        return 0


def page(limit: int | None) -> int:
    if limit is None:
        return 50
    return max(1, min(limit, 100))
