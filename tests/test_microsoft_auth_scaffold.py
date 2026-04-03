"""Pruebas del flujo OAuth real para Microsoft."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from auth.microsoft_auth import (
    InMemoryMicrosoftTokenStore,
    MicrosoftOAuthClient,
    MicrosoftOAuthConfig,
    build_microsoft_oauth_client_from_env,
)


class _FakeOAuthTransport:
    def __init__(self) -> None:
        self.form_calls: list[tuple[str, dict[str, str]]] = []
        self.profile_calls: list[tuple[str, str]] = []

    def post_form(self, *, url: str, form_data: dict[str, str]) -> dict[str, object]:
        self.form_calls.append((url, dict(form_data)))
        if form_data["grant_type"] == "authorization_code":
            return {
                "access_token": "access-token-from-code-1234567890",
                "refresh_token": "refresh-token-from-code-1234567890",
                "expires_in": 3600,
                "scope": form_data["scope"],
                "token_type": "Bearer",
            }
        return {
            "access_token": "access-token-from-refresh-1234567890",
            "refresh_token": "refresh-token-from-refresh-1234567890",
            "expires_in": 7200,
            "scope": form_data["scope"],
            "token_type": "Bearer",
        }

    def get_json(self, *, url: str, access_token: str) -> dict[str, object]:
        self.profile_calls.append((url, access_token))
        return {
            "id": "ms-user-1",
            "userPrincipalName": "student@example.edu",
            "mail": "student@example.edu",
            "displayName": "Student Test",
        }


def test_microsoft_oauth_client_builds_authorization_url() -> None:
    client = MicrosoftOAuthClient(
        config=MicrosoftOAuthConfig(
            client_id="client-123",
            tenant_id="tenant-456",
            redirect_uri="https://example.com/oauth/callback",
        ),
        token_store=InMemoryMicrosoftTokenStore(),
    )

    request = client.build_authorization_request(student_id=77)

    assert request.ready is True
    assert request.authorization_url is not None
    assert "client_id=client-123" in request.authorization_url
    assert "redirect_uri=https%3A%2F%2Fexample.com%2Foauth%2Fcallback" in request.authorization_url
    assert "Calendars.ReadWrite" in request.authorization_url
    assert request.state == "student:77:microsoft"


def test_microsoft_oauth_client_exchanges_authorization_code_and_persists_profile() -> None:
    transport = _FakeOAuthTransport()
    store = InMemoryMicrosoftTokenStore()
    client = MicrosoftOAuthClient(
        config=MicrosoftOAuthConfig(
            client_id="client-123",
            tenant_id="tenant-456",
            client_secret="secret-789",
            redirect_uri="https://example.com/oauth/callback",
        ),
        token_store=store,
        transport=transport,
    )

    result = client.exchange_authorization_code(
        student_id=11,
        authorization_code="code-abc",
    )
    loaded = client.get_stored_token(student_id=11)

    assert result.ok is True
    assert loaded is not None
    assert loaded.access_token == "access-token-from-code-1234567890"
    assert loaded.refresh_token == "refresh-token-from-code-1234567890"
    assert loaded.email == "student@example.edu"
    assert loaded.microsoft_user_id == "ms-user-1"
    assert transport.form_calls[0][1]["grant_type"] == "authorization_code"
    assert transport.profile_calls


def test_microsoft_oauth_client_refreshes_expired_token() -> None:
    transport = _FakeOAuthTransport()
    client = MicrosoftOAuthClient(
        config=MicrosoftOAuthConfig(
            client_id="client-123",
            tenant_id="tenant-456",
            client_secret="secret-789",
            redirect_uri="https://example.com/oauth/callback",
        ),
        token_store=InMemoryMicrosoftTokenStore(),
        transport=transport,
    )
    client.save_manual_token(
        student_id=22,
        access_token="expired-access-token-1234567890",
        refresh_token="refresh-token-1234567890",
        scopes=("User.Read", "Calendars.ReadWrite"),
        email="student@example.edu",
    )
    expired = client.get_stored_token(student_id=22)
    client.token_store.save_token(
        token=expired.__class__(
            **{
                **expired.__dict__,
                "expires_at": datetime.now(timezone.utc) - timedelta(minutes=10),
            }
        )
    )

    refreshed = client.refresh_access_token(student_id=22)

    assert refreshed.ok is True
    assert refreshed.token is not None
    assert refreshed.token.access_token == "access-token-from-refresh-1234567890"
    assert refreshed.token.refresh_token == "refresh-token-from-refresh-1234567890"
    assert transport.form_calls[-1][1]["grant_type"] == "refresh_token"


def test_build_microsoft_oauth_client_from_env_accepts_ms_aliases(monkeypatch) -> None:
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    monkeypatch.delenv("MICROSOFT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("MICROSOFT_TENANT_ID", raising=False)
    monkeypatch.delenv("MICROSOFT_REDIRECT_URI", raising=False)
    monkeypatch.setenv("MS_CLIENT_ID", "client-alias")
    monkeypatch.setenv("MS_CLIENT_SECRET", "secret-alias")
    monkeypatch.setenv("MS_TENANT_ID", "tenant-alias")
    monkeypatch.setenv("MS_REDIRECT_URI", "https://example.com/ms/callback")

    client = build_microsoft_oauth_client_from_env()

    assert client.config.client_id == "client-alias"
    assert client.config.client_secret == "secret-alias"
    assert client.config.tenant_id == "tenant-alias"
    assert client.config.redirect_uri == "https://example.com/ms/callback"
