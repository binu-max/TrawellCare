import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field

SYSTEM_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


@dataclass
class Actor:
    id: uuid.UUID
    kind: str
    roles: list[str] = field(default_factory=list)
    customer_id: uuid.UUID | None = None

    def has_role(self, *names: str) -> bool:
        return any(role in self.roles for role in names)


_current: ContextVar[Actor | None] = ContextVar("platform_actor", default=None)


def set_actor(actor: Actor) -> None:
    _current.set(actor)


def current_actor() -> Actor | None:
    return _current.get()


def clear_actor() -> None:
    _current.set(None)
