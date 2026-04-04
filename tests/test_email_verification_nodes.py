"""Pruebas de nodos de verificacion de correo."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.dependencies import set_onboarding_service
from agents.support.nodes.send_email_verification.node import send_email_verification
from agents.support.nodes.verify_email_code.node import verify_email_code
from agents.support.state import AgentState
from repositories.onboarding.repository import InMemoryOnboardingRepository
from services.onboarding import InMemoryEmailSender, OnboardingConfig, OnboardingService


def test_email_verification_nodes_send_and_verify() -> None:
    repository = InMemoryOnboardingRepository()
    sender = InMemoryEmailSender()
    service = OnboardingService(
        config=OnboardingConfig(verification_secret="test-secret"),
        repository=repository,
        email_sender=sender,
    )
    set_onboarding_service(service)

    try:
        initial_state = AgentState(
            phase="email_verification_send",
            student_profile={
                "institutional_email": "ana@ucatolica.edu.co",
                "email_verified": False,
            },
        )

        send_update = send_email_verification(initial_state)
        sent_code = sender.sent_messages[-1][1]

        payload = initial_state.model_dump()
        payload.update(send_update)
        payload.update(
            awaiting_user_input=True,
            user_message_count=0,
            messages=[HumanMessage(content=sent_code)],
        )
        verify_state = AgentState(**payload)
        verify_update = verify_email_code(verify_state)

        assert send_update["phase"] == "email_verification"
        assert "codigo enviado" in send_update["messages"][0].content.lower()
        assert verify_update["phase"] == "profile"
        assert verify_update["student_profile"]["email_verified"] is True
    finally:
        set_onboarding_service(None)


def test_send_email_verification_can_skip_in_disabled_mode() -> None:
    service = OnboardingService(
        config=OnboardingConfig(verification_mode="disabled"),
        repository=InMemoryOnboardingRepository(),
        email_sender=InMemoryEmailSender(),
    )
    set_onboarding_service(service)

    try:
        state = AgentState(
            phase="email_verification_send",
            student_profile={
                "institutional_email": "ana@ucatolica.edu.co",
                "email_verified": False,
            },
        )

        update = send_email_verification(state)

        assert update["phase"] == "profile"
        assert update["student_profile"]["email_verified"] is True
        assert "omiti la verificacion" in update["messages"][0].content.lower()
    finally:
        set_onboarding_service(None)
