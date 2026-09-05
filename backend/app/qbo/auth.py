"""OAuth2 handshake with Intuit (authorization URL, code exchange, refresh)."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from quickbooks import QuickBooks
from quickbooks.objects.company_info import CompanyInfo

from .config import QBOSettings
from .store import TokenStore

# Single-process, short-lived CSRF guard for the OAuth redirect round-trip.
# Not persisted: if the process restarts mid-flow the user just retries connect.
_pending_state: str | None = None


class QBONotConfiguredError(RuntimeError):
    """QBO_CLIENT_ID / QBO_CLIENT_SECRET / QBO_REDIRECT_URI aren't set."""


def _build_auth_client(settings: QBOSettings, **kwargs) -> AuthClient:
    return AuthClient(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
        environment=settings.environment,
        **kwargs,
    )


def get_authorization_url(settings: QBOSettings) -> str:
    global _pending_state
    if not settings.is_configured():
        raise QBONotConfiguredError(
            "Set QBO_CLIENT_ID, QBO_CLIENT_SECRET and QBO_REDIRECT_URI environment variables "
            "(from an Intuit Developer app) before connecting to QuickBooks."
        )
    auth_client = _build_auth_client(settings)
    _pending_state = secrets.token_urlsafe(24)
    return auth_client.get_authorization_url([Scopes.ACCOUNTING], state_token=_pending_state)


def handle_callback(
    settings: QBOSettings, store: TokenStore, *, code: str, realm_id: str, state: str
) -> dict:
    global _pending_state
    if not _pending_state or state != _pending_state:
        raise ValueError("OAuth state didn't match - please restart the connection flow.")
    _pending_state = None

    auth_client = _build_auth_client(settings)
    auth_client.get_bearer_token(code, realm_id=realm_id)

    client = QuickBooks(
        auth_client=auth_client,
        refresh_token=auth_client.refresh_token,
        company_id=realm_id,
    )
    company = CompanyInfo.get(realm_id, qb=client)

    data = {
        "realm_id": realm_id,
        "access_token": auth_client.access_token,
        "refresh_token": auth_client.refresh_token,
        "environment": settings.environment,
        "company_name": company.CompanyName,
        "token_obtained_at": datetime.now(timezone.utc).isoformat(),
    }
    store.save(data)
    return data
