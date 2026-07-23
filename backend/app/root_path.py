"""Serve the app under a URL prefix (e.g. /pipeline) for herbiecreative.com/pipeline."""
from __future__ import annotations

import os

from starlette.datastructures import URL
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send


def root_path() -> str:
    """Public URL prefix with no trailing slash. Empty for local root hosting."""
    raw = (os.getenv("ROOT_PATH") or "").strip()
    if not raw and os.getenv("HOSTED", "").strip().lower() in {"1", "true", "yes", "on"}:
        raw = "/pipeline"
    if not raw or raw == "/":
        return ""
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/")


class RootPathMiddleware:
    """Redirect bare / to /pipeline/, and strip the prefix before the app sees the path."""

    def __init__(self, app: ASGIApp, prefix: str) -> None:
        self.app = app
        self.prefix = prefix.rstrip("/") or ""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"} or not self.prefix:
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or "/"
        if path == self.prefix:
            # Canonical trailing slash for the SPA entry.
            if scope["type"] == "http":
                url = URL(scope=scope).replace(path=f"{self.prefix}/")
                response = RedirectResponse(url=str(url), status_code=307)
                await response(scope, receive, send)
                return
        if path == "/" or path == "":
            if scope["type"] == "http":
                url = URL(scope=scope).replace(path=f"{self.prefix}/")
                response = RedirectResponse(url=str(url), status_code=307)
                await response(scope, receive, send)
                return

        if path.startswith(self.prefix + "/") or path == self.prefix:
            stripped = path[len(self.prefix) :] or "/"
            scope = dict(scope)
            scope["path"] = stripped
            scope["root_path"] = (scope.get("root_path") or "") + self.prefix
            await self.app(scope, receive, send)
            return

        # Unknown path outside the app prefix.
        if scope["type"] == "http":
            from starlette.responses import PlainTextResponse

            response = PlainTextResponse("Not Found", status_code=404)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
