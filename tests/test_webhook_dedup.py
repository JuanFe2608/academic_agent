"""Tests de deduplicación durable de mensajes webhook de WhatsApp."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from repositories.webhook import InMemoryWebhookMessageRepository


# ---------------------------------------------------------------------------
# Repositorio in-memory
# ---------------------------------------------------------------------------


class TestInMemoryWebhookMessageRepository:
    def test_primer_mensaje_no_es_duplicado(self) -> None:
        repo = InMemoryWebhookMessageRepository()
        assert repo.is_duplicate_and_register("wamid.abc123") is False

    def test_segundo_registro_mismo_id_es_duplicado(self) -> None:
        repo = InMemoryWebhookMessageRepository()
        repo.is_duplicate_and_register("wamid.abc123")
        assert repo.is_duplicate_and_register("wamid.abc123") is True

    def test_ids_distintos_no_interfieren(self) -> None:
        repo = InMemoryWebhookMessageRepository()
        assert repo.is_duplicate_and_register("wamid.111") is False
        assert repo.is_duplicate_and_register("wamid.222") is False
        assert repo.is_duplicate_and_register("wamid.111") is True
        assert repo.is_duplicate_and_register("wamid.222") is True

    def test_registered_ids_refleja_estado(self) -> None:
        repo = InMemoryWebhookMessageRepository()
        repo.is_duplicate_and_register("wamid.aaa")
        repo.is_duplicate_and_register("wamid.bbb")
        assert repo.registered_ids() == {"wamid.aaa", "wamid.bbb"}

    def test_cleanup_expired_elimina_entradas_vencidas(self) -> None:
        repo = InMemoryWebhookMessageRepository()
        repo.is_duplicate_and_register("wamid.viejo")
        repo.is_duplicate_and_register("wamid.nuevo")

        # Simular que wamid.viejo tiene timestamp de hace 73 horas
        old_ts = datetime.now(tz=timezone.utc) - timedelta(hours=73)
        repo._seen["wamid.viejo"] = old_ts

        deleted = repo.cleanup_expired(max_age_hours=72)

        assert deleted == 1
        assert "wamid.viejo" not in repo.registered_ids()
        assert "wamid.nuevo" in repo.registered_ids()

    def test_cleanup_sin_entradas_vencidas_retorna_cero(self) -> None:
        repo = InMemoryWebhookMessageRepository()
        repo.is_duplicate_and_register("wamid.reciente")
        assert repo.cleanup_expired(max_age_hours=72) == 0

    def test_cleanup_tabla_vacia_retorna_cero(self) -> None:
        repo = InMemoryWebhookMessageRepository()
        assert repo.cleanup_expired(max_age_hours=72) == 0


# ---------------------------------------------------------------------------
# Comportamiento del AgentRunner con dedup
# ---------------------------------------------------------------------------


def _make_inbound_message(message_id: str, from_number: str = "573001112233") -> MagicMock:
    msg = MagicMock()
    msg.message_id = message_id
    msg.from_number = from_number
    msg.text = "hola"
    msg.media = None
    return msg


def _make_runner_with_mock_repo(repo: InMemoryWebhookMessageRepository) -> MagicMock:
    """Construye un AgentRunner parcialmente mockeado con el repo dado."""
    from api.agent_runner import AgentRunner

    runner = AgentRunner.__new__(AgentRunner)
    runner._dedup_repo = repo
    runner._whatsapp_service = MagicMock()
    runner._executor = MagicMock()
    runner._thread_locks = MagicMock()
    runner._thread_locks.get_or_create.return_value = AsyncMock(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    )
    runner._run_agent_sync = MagicMock()
    return runner


class TestAgentRunnerDedup:
    def test_mensaje_nuevo_ejecuta_agente(self) -> None:
        repo = InMemoryWebhookMessageRepository()
        runner = _make_runner_with_mock_repo(repo)
        msg = _make_inbound_message("wamid.new001")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            asyncio.run(runner.process_message(msg))

        assert "wamid.new001" in repo.registered_ids()

    def test_mensaje_duplicado_no_ejecuta_agente(self) -> None:
        repo = InMemoryWebhookMessageRepository()
        repo.is_duplicate_and_register("wamid.dup001")  # ya procesado
        runner = _make_runner_with_mock_repo(repo)
        msg = _make_inbound_message("wamid.dup001")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            asyncio.run(runner.process_message(msg))

        # run_in_executor nunca debería haberse llamado
        mock_loop.return_value.run_in_executor.assert_not_called()

    def test_fallo_en_repo_procesa_de_todas_formas(self) -> None:
        """Si el repositorio falla (DB caída), el mensaje se procesa (fail-open)."""
        broken_repo = MagicMock()
        broken_repo.is_duplicate_and_register.side_effect = Exception("DB unavailable")
        runner = _make_runner_with_mock_repo(broken_repo)
        msg = _make_inbound_message("wamid.failopen")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            asyncio.run(runner.process_message(msg))

        # A pesar del error en el repo, el agente debe correr
        mock_loop.return_value.run_in_executor.assert_called_once()
