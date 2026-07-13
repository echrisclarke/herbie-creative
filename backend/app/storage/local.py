from __future__ import annotations

from pathlib import Path

from app.config import campaigns_root


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or campaigns_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def list_prefix(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.exists():
            return []
        if base.is_file():
            return [prefix]
        results: list[str] = []
        for path in base.rglob("*"):
            if path.is_file():
                results.append(str(path.relative_to(self.root)).replace("\\", "/"))
        return sorted(results)

    def get_url(self, key: str) -> str:
        return f"/outputs/{key}"
