"""Request-scoped tenant identity and API keys for hosted multi-user mode."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_user_id: ContextVar[str | None] = ContextVar("tenant_user_id", default=None)
_user_email: ContextVar[str | None] = ContextVar("tenant_user_email", default=None)
_api_keys: ContextVar[dict[str, str] | None] = ContextVar("tenant_api_keys", default=None)


def current_user_id() -> str | None:
    return _user_id.get()


def current_user_email() -> str | None:
    return _user_email.get()


def current_api_keys() -> dict[str, str] | None:
    return _api_keys.get()


def set_tenant(
    *,
    user_id: str | None,
    email: str | None = None,
    api_keys: dict[str, str] | None = None,
) -> tuple:
    t_uid = _user_id.set(user_id)
    t_email = _user_email.set(email)
    t_keys = _api_keys.set(api_keys)
    return t_uid, t_email, t_keys


def reset_tenant(tokens: tuple) -> None:
    t_uid, t_email, t_keys = tokens
    _user_id.reset(t_uid)
    _user_email.reset(t_email)
    _api_keys.reset(t_keys)


def update_current_api_keys(api_keys: dict[str, str] | None) -> None:
    """Replace keys in the active request context (does not nest a new token)."""
    _api_keys.set(api_keys)


@contextmanager
def tenant_context(
    *,
    user_id: str | None,
    email: str | None = None,
    api_keys: dict[str, str] | None = None,
) -> Iterator[None]:
    tokens = set_tenant(user_id=user_id, email=email, api_keys=api_keys)
    try:
        yield
    finally:
        reset_tenant(tokens)
