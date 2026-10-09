import base64
import hashlib
import hmac
import secrets
import struct
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from tc_common import Unauthenticated

from app.actor import Actor


def generate_rsa_pem() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private, public


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(pepper: str, code: str) -> str:
    return hashlib.sha256(f"{pepper}:{code}".encode()).hexdigest()


def otp_matches(pepper: str, code: str, code_hash: str) -> bool:
    return secrets.compare_digest(hash_otp(pepper, code), code_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"pbkdf2${salt}${digest}"


def password_matches(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("pbkdf2$"):
        return False
    _, salt, digest = stored.split("$", 2)
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return secrets.compare_digest(check, digest)


def totp_code(secret: str, at: float | None = None) -> str:
    moment = time.time() if at is None else at
    counter = int(moment // 30)
    key = base64.b32decode(secret.upper(), casefold=True)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 1_000_000:06d}"


def totp_matches(secret: str, code: str, at: float | None = None) -> bool:
    moment = time.time() if at is None else at
    for skew in (-30, 0, 30):
        if secrets.compare_digest(totp_code(secret, moment + skew), code):
            return True
    return False


def encode_token(payload: dict, private_key: str) -> str:
    return jwt.encode(payload, private_key, algorithm="RS256")


def decode_token(token: str, public_key: str) -> dict:
    try:
        return jwt.decode(token, public_key, algorithms=["RS256"])
    except jwt.PyJWTError as exc:
        raise Unauthenticated("Invalid token") from exc


def issue_access_token(
    actor: Actor,
    private_key: str,
    *,
    minutes: int,
    kind: str | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(actor.id),
        "kind": kind or actor.kind,
        "roles": actor.roles,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    if actor.customer_id:
        payload["customerId"] = str(actor.customer_id)
    return encode_token(payload, private_key)


def actor_from_token(token: str, public_key: str) -> Actor:
    payload = decode_token(token, public_key)
    customer = payload.get("customerId")
    return Actor(
        id=uuid.UUID(payload["sub"]),
        kind=payload.get("kind", ""),
        roles=list(payload.get("roles") or []),
        customer_id=uuid.UUID(customer) if customer else None,
    )
