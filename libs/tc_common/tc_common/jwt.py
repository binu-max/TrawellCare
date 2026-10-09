import uuid
from dataclasses import dataclass, field

import jwt
from tc_common.errors import Unauthenticated


@dataclass
class TokenActor:
    id: uuid.UUID
    kind: str
    roles: list[str] = field(default_factory=list)
    customer_id: uuid.UUID | None = None

    def has_role(self, *names: str) -> bool:
        return any(role in self.roles for role in names)


def decode_rs256_token(token: str, public_key_pem: str) -> dict:
    try:
        return jwt.decode(token, public_key_pem, algorithms=["RS256"])
    except jwt.PyJWTError as exc:
        raise Unauthenticated("Invalid token") from exc


def actor_from_claims(payload: dict) -> TokenActor:
    customer = payload.get("customerId")
    return TokenActor(
        id=uuid.UUID(payload["sub"]),
        kind=payload.get("kind", ""),
        roles=list(payload.get("roles") or []),
        customer_id=uuid.UUID(customer) if customer else None,
    )


def actor_from_bearer_token(token: str, public_key_pem: str) -> TokenActor:
    return actor_from_claims(decode_rs256_token(token, public_key_pem))
