"""Environment-based configuration for the QuickBooks Online integration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_TOKEN_STORE = Path(__file__).resolve().parent.parent.parent.parent / ".qbo_tokens.json"


@dataclass
class QBOSettings:
    client_id: str
    client_secret: str
    redirect_uri: str
    environment: str
    token_store_path: str

    @classmethod
    def from_env(cls) -> "QBOSettings":
        return cls(
            client_id=os.environ.get("QBO_CLIENT_ID", ""),
            client_secret=os.environ.get("QBO_CLIENT_SECRET", ""),
            redirect_uri=os.environ.get("QBO_REDIRECT_URI", "http://localhost:8000/api/qbo/callback"),
            environment=os.environ.get("QBO_ENVIRONMENT", "sandbox"),
            token_store_path=os.environ.get("QBO_TOKEN_STORE_PATH", str(_DEFAULT_TOKEN_STORE)),
        )

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)
