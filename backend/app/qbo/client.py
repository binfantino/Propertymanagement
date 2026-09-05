"""Builds an authenticated QuickBooks client from the stored tokens, refreshing
the access token first if it's old enough to likely have expired."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from intuitlib.client import AuthClient
from quickbooks import QuickBooks

from .config import QBOSettings
from .store import TokenStore

# QBO access tokens last ~60 minutes; refresh a bit early to be safe.
ACCESS_TOKEN_LIFETIME = timedelta(minutes=50)


class QBONotConnectedError(RuntimeError):
    """No stored QuickBooks connection - visit /api/qbo/connect first."""


def get_client(settings: QBOSettings, store: TokenStore) -> QuickBooks:
    data = store.load()
    if not data:
        raise QBONotConnectedError("Not connected to QuickBooks yet. Visit /api/qbo/connect first.")

    auth_client = AuthClient(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
        environment=data.get("environment", settings.environment),
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        realm_id=data["realm_id"],
    )

    obtained_at = datetime.fromisoformat(data["token_obtained_at"])
    if datetime.now(timezone.utc) - obtained_at > ACCESS_TOKEN_LIFETIME:
        auth_client.refresh(refresh_token=data["refresh_token"])
        data["access_token"] = auth_client.access_token
        data["refresh_token"] = auth_client.refresh_token
        data["token_obtained_at"] = datetime.now(timezone.utc).isoformat()
        store.save(data)

    return QuickBooks(
        auth_client=auth_client,
        refresh_token=auth_client.refresh_token,
        company_id=data["realm_id"],
    )
