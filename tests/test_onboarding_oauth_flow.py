"""Pruebas del OAuth Microsoft bloqueante durante onboarding."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from langchain_core.messages import HumanMessage

from agents.support.agent import _route_collect_profile
from agents.support.dependencies import (
    set_microsoft_oauth_flow_service,
    set_onboarding_service,
)
from agents.support.nodes.request_microsoft_oauth.node import request_microsoft_oauth
from agents.support.state import AgentState
from integrations.microsoft_graph.auth_client import (
    MicrosoftAuthorizationRequest,
    MicrosoftTokenOperationResult,
)
from repositories.microsoft_graph.state_repository import InMemoryMicrosoftGraphStateRepository
from repositories.onboarding.repository import InMemoryOnboardingRepository
from services.onboarding import InMemoryEmailSender, OnboardingConfig, OnboardingService
from services.sync.microsoft_oauth_callback_handler import handle_microsoft_oauth_callback
from services.sync.microsoft_oauth_flow_service import MicrosoftOAuthFlowService


class _FakeOAuthClient:
    def __init__(self) -> None:
        self.connected_student_ids: set[int] = set()
        self.authorization_states: list[str] = []
        self.exchange_calls: list[tuple[int, str, tuple[str, ...]]] = []

    def build_authorization_request(
        self,
        *,
        student_id: int,
        state_token: str | None = None,
        scopes: tuple[str, ...] | None = None,
        redirect_uri: str | None = None,
    ) -> MicrosoftAuthorizationRequest:
        del redirect_uri
        effective_state = state_token or f"student:{student_id}:microsoft"
        effective_scopes = tuple(scopes or ("User.Read", "Calendars.ReadWrite"))
        self.authorization_states.append(effective_state)
        return MicrosoftAuthorizationRequest(
            ready=True,
            authorization_url=f"https://login.example.test/authorize?state={effective_state}",
            state=effective_state,
            scopes=effective_scopes,
        )

    def get_stored_token(self, *, student_id: int) -> object | None:
        return object() if int(student_id) in self.connected_student_ids else None

    def exchange_authorization_code(
        self,
        *,
        student_id: int,
        authorization_code: str,
        scopes: tuple[str, ...] | None = None,
    ) -> MicrosoftTokenOperationResult:
        effective_scopes = tuple(scopes or ())
        self.exchange_calls.append((int(student_id), authorization_code, effective_scopes))
        self.connected_student_ids.add(int(student_id))
        return MicrosoftTokenOperationResult(ok=True)


def test_collect_profile_routes_to_oauth_only_when_flag_requires_it(monkeypatch) -> None:
    state = _verified_profile_state()

    monkeypatch.setenv("ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH", "0")
    assert _route_collect_profile(state) == "collect_profile"

    monkeypatch.setenv("ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH", "1")
    assert _route_collect_profile(state) == "request_microsoft_oauth"


def test_request_microsoft_oauth_creates_identity_and_blocks_with_random_state(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH", "1")
    repository = InMemoryMicrosoftGraphStateRepository()
    fake_client = _FakeOAuthClient()
    service = MicrosoftOAuthFlowService(
        state_repository=repository,
        auth_client=fake_client,
        now_factory=lambda: datetime(2026, 4, 18, tzinfo=timezone.utc),
    )
    set_onboarding_service(_onboarding_service())
    set_microsoft_oauth_flow_service(service)

    try:
        update = request_microsoft_oauth(_verified_profile_state())

        assert update["phase"] == "microsoft_oauth"
        assert update["awaiting_user_input"] is True
        assert update["student_profile"]["persisted_student_id"] == 1
        oauth_state = update["onboarding"]["microsoft_oauth"]
        assert oauth_state["status"] == "pending"
        assert oauth_state["state_token"].startswith("student:1:microsoft:")
        assert oauth_state["state_token"] != "student:1:microsoft"
        assert fake_client.authorization_states == [oauth_state["state_token"]]
        assert "https://login.example.test/authorize" in update["messages"][0].content
        assert update["interaction"]["is_waiting_for_oauth"] is True
    finally:
        set_onboarding_service(None)
        set_microsoft_oauth_flow_service(None)


def test_microsoft_oauth_flow_callback_persists_connection_and_marks_state() -> None:
    repository = InMemoryMicrosoftGraphStateRepository()
    fake_client = _FakeOAuthClient()
    service = MicrosoftOAuthFlowService(
        state_repository=repository,
        auth_client=fake_client,
        now_factory=lambda: datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    first = service.start_authorization(
        student_id=7,
        institutional_email="ana@ucatolica.edu.co",
    )
    second = service.start_authorization(
        student_id=7,
        institutional_email="ana@ucatolica.edu.co",
    )

    assert first.ok is True
    assert second.ok is True
    assert first.state_token != second.state_token
    assert first.state_token != "student:7:microsoft"

    callback = handle_microsoft_oauth_callback(
        {"state": first.state_token, "code": "code-abc"},
        flow_service=service,
    )

    assert callback.ok is True
    assert callback.student_id == 7
    assert callback.status_code == 200
    assert service.has_connection(student_id=7) is True
    assert fake_client.exchange_calls == [(7, "code-abc", ("User.Read", "Calendars.ReadWrite"))]
    stored_state = repository.get_oauth_pending_state(state_token=first.state_token)
    assert stored_state is not None
    assert stored_state.status == "completed"


def test_request_microsoft_oauth_allows_retry_with_new_state(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH", "1")
    repository = InMemoryMicrosoftGraphStateRepository()
    service = MicrosoftOAuthFlowService(
        state_repository=repository,
        auth_client=_FakeOAuthClient(),
        now_factory=lambda: datetime(2026, 4, 18, tzinfo=timezone.utc),
    )
    set_onboarding_service(_onboarding_service())
    set_microsoft_oauth_flow_service(service)

    try:
        first_update = request_microsoft_oauth(_verified_profile_state())
        retry_state = _state_from_update(
            _verified_profile_state(),
            first_update,
            user_message="reintentar",
        )
        retry_update = request_microsoft_oauth(retry_state)

        assert retry_update["phase"] == "microsoft_oauth"
        assert retry_update["awaiting_user_input"] is True
        assert retry_update["onboarding"]["microsoft_oauth"]["state_token"] != (
            first_update["onboarding"]["microsoft_oauth"]["state_token"]
        )
        assert retry_update["onboarding"]["microsoft_oauth"]["attempts"] == 2
    finally:
        set_onboarding_service(None)
        set_microsoft_oauth_flow_service(None)


def test_request_microsoft_oauth_continues_when_connection_exists(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_REQUIRE_MICROSOFT_OAUTH", "1")
    fake_client = _FakeOAuthClient()
    fake_client.connected_student_ids.add(1)
    service = MicrosoftOAuthFlowService(
        state_repository=InMemoryMicrosoftGraphStateRepository(),
        auth_client=fake_client,
    )
    set_onboarding_service(_onboarding_service())
    set_microsoft_oauth_flow_service(service)

    try:
        state = _verified_profile_state(
            student_profile={"persisted_student_id": 1},
            phase="microsoft_oauth",
            onboarding={
                "microsoft_oauth": {
                    "status": "pending",
                    "state_token": "old-state",
                    "authorization_url": "https://login.example.test/old",
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(minutes=10)
                    ).isoformat(),
                    "attempts": 1,
                }
            },
            messages=[HumanMessage(content="listo")],
            awaiting_user_input=True,
            user_message_count=0,
        )

        update = request_microsoft_oauth(state)

        assert update["phase"] == "profile"
        assert update["awaiting_user_input"] is False
        assert update["onboarding"]["microsoft_oauth"]["status"] == "authorized"
        assert update["interaction"]["is_waiting_for_oauth"] is False
        assert update["calendar"]["authorized"] is True
    finally:
        set_onboarding_service(None)
        set_microsoft_oauth_flow_service(None)


def _verified_profile_state(
    *,
    student_profile: dict | None = None,
    onboarding: dict | None = None,
    **overrides: object,
) -> AgentState:
    profile = {
        "full_name": "Ana Maria Perez",
        "student_code": "67000912",
        "age": 20,
        "institutional_email": "ana@ucatolica.edu.co",
        "email_verified": True,
        "academic_program": "Ingenieria de Sistemas y Computacion",
        "supported_program": True,
    }
    profile.update(student_profile or {})
    payload = {
        "phase": "profile",
        "student_profile": profile,
        "onboarding": onboarding or {},
        "awaiting_user_input": False,
    }
    payload.update(overrides)
    return AgentState(**payload)


def _onboarding_service() -> OnboardingService:
    return OnboardingService(
        config=OnboardingConfig(verification_secret="test-secret"),
        repository=InMemoryOnboardingRepository(),
        email_sender=InMemoryEmailSender(),
    )


def _state_from_update(
    base_state: AgentState,
    update: dict,
    *,
    user_message: str,
) -> AgentState:
    payload = base_state.model_dump()
    payload.update(update)
    payload["messages"] = list(update.get("messages", [])) + [
        HumanMessage(content=user_message)
    ]
    payload["awaiting_user_input"] = True
    payload["user_message_count"] = 0
    return AgentState(**payload)
