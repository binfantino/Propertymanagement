"""Local persistence for QuickBooks OAuth tokens.

This is intentionally a single-tenant, single-company JSON file store: the
app is meant to run as one process connected to one QuickBooks company.
Multi-company/multi-user use would need a real database with per-user
encrypted token storage instead - see README roadmap.
"""
from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

_lock = Lock()


class TokenStore:
    def __init__(self, path: str):
        self.path = Path(path)

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        with self.path.open() as f:
            return json.load(f)

    def save(self, data: dict) -> None:
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w") as f:
                json.dump(data, f, indent=2)
            try:
                self.path.chmod(0o600)
            except OSError:
                pass

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
