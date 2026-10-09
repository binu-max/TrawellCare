import hashlib
import hmac
import secrets
import time
from uuid import UUID


def _key(secret: str) -> bytes:
    return secret.encode()


def issue_upload_token(secret: str, document_id: UUID, *, ttl_seconds: int, max_bytes: int) -> str:
    expires = int(time.time()) + ttl_seconds
    payload = f"upload:{document_id}:{expires}:{max_bytes}"
    sig = hmac.new(_key(secret), payload.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def verify_upload_token(secret: str, document_id: UUID, token: str, *, max_bytes: int) -> None:
    try:
        expires_str, sig = token.split(".", 1)
        expires = int(expires_str)
    except ValueError as exc:
        raise ValueError("Invalid upload token") from exc
    if expires < int(time.time()):
        raise ValueError("Upload token expired")
    payload = f"upload:{document_id}:{expires}:{max_bytes}"
    expected = hmac.new(_key(secret), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise ValueError("Invalid upload token")


def issue_download_token(secret: str, document_id: UUID, *, ttl_seconds: int) -> str:
    expires = int(time.time()) + ttl_seconds
    nonce = secrets.token_hex(8)
    payload = f"download:{document_id}:{expires}:{nonce}"
    sig = hmac.new(_key(secret), payload.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{nonce}.{sig}"


def verify_download_token(secret: str, document_id: UUID, token: str) -> None:
    try:
        expires_str, nonce, sig = token.split(".", 2)
        expires = int(expires_str)
    except ValueError as exc:
        raise ValueError("Invalid download token") from exc
    if expires < int(time.time()):
        raise ValueError("Download link expired")
    payload = f"download:{document_id}:{expires}:{nonce}"
    expected = hmac.new(_key(secret), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise ValueError("Invalid download token")
