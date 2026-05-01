"""Pipeline WhatsApp → LangGraph: recibe mensajes y devuelve respuestas al estudiante."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from langchain_core.messages import AIMessage, HumanMessage

from integrations.langgraph.checkpointer import (
    PostgresLangGraphCheckpointer,
    checkpoint_database_url_from_env,
)
from integrations.whatsapp import WhatsAppCloudClient, WhatsAppInboundMessage
from repositories.webhook import InMemoryWebhookMessageRepository, WebhookMessageRepository
from services.channels.input_normalization import NormalizedAgentInput, WhatsAppInputNormalizer
from services.channels.whatsapp_service import WhatsAppChannelService

logger = logging.getLogger(__name__)


class _BoundedLockMap:
    """Mapa acotado de asyncio.Lock con eviction LRU de locks inactivos.

    Garantiza procesamiento secuencial por usuario y acota el uso de memoria
    evitando que phone numbers inactivos acumulen locks indefinidamente.
    Solo evicta locks que no están siendo sostenidos (lock.locked() == False)
    para preservar la garantía de serialización del checkpointer de LangGraph.
    """

    def __init__(self, maxsize: int = 1000) -> None:
        self._locks: OrderedDict[str, asyncio.Lock] = OrderedDict()
        self._maxsize = maxsize

    def get_or_create(self, key: str) -> asyncio.Lock:
        """Devuelve el lock existente (promovido a MRU) o crea uno nuevo."""
        if key in self._locks:
            self._locks.move_to_end(key)
            return self._locks[key]
        lock = asyncio.Lock()
        self._locks[key] = lock
        if len(self._locks) > self._maxsize:
            self._evict_oldest_idle()
        return lock

    def _evict_oldest_idle(self) -> None:
        """Evicta el lock libre más antiguo. No-op si todos están activos."""
        for key in list(self._locks.keys()):
            if not self._locks[key].locked():
                del self._locks[key]
                return


class AgentRunner:
    """Conecta el canal WhatsApp con el agente LangGraph manteniendo estado por estudiante."""

    def __init__(
        self,
        *,
        whatsapp_service: WhatsAppChannelService,
        checkpointer: PostgresLangGraphCheckpointer,
        dedup_repo: WebhookMessageRepository | None = None,
        input_normalizer: WhatsAppInputNormalizer | None = None,
        max_workers: int = 4,
    ) -> None:
        from agents.support.agent import build_agent

        self._whatsapp_service = whatsapp_service
        self._input_normalizer = input_normalizer or WhatsAppInputNormalizer(
            whatsapp_service=whatsapp_service,
            audio_transcriber=_build_audio_transcriber(),
        )
        self._checkpointer = checkpointer
        self._agent = build_agent(checkpointer=checkpointer)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="lara-agent")
        # Deduplicación durable: persiste message_ids en PostgreSQL para sobrevivir
        # reinicios y ser compartida entre réplicas. Fallback a in-memory si no hay DB.
        self._dedup_repo: WebhookMessageRepository = dedup_repo or InMemoryWebhookMessageRepository()
        # Lock por thread_id: garantiza procesamiento secuencial por usuario (acotado a 1000 entradas)
        self._thread_locks: _BoundedLockMap = _BoundedLockMap(maxsize=1000)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "AgentRunner":
        """Construye un AgentRunner desde variables de entorno."""
        from bootstrap.settings import database_url_from_env
        from repositories.webhook import PostgresWebhookMessageRepository

        checkpoint_url = checkpoint_database_url_from_env()
        if not checkpoint_url:
            raise RuntimeError(
                "La URL de la base de datos de checkpoints no esta configurada. "
                "Verifica ACADEMIC_AGENT_DATABASE_URL o PGHOST/PGDATABASE/PGUSER/PGPASSWORD."
            )

        checkpointer = PostgresLangGraphCheckpointer(checkpoint_url)
        client = WhatsAppCloudClient.from_env()
        whatsapp_service = WhatsAppChannelService(client)

        dedup_repo: WebhookMessageRepository | None = None
        try:
            db_url = database_url_from_env()
            dedup_repo = PostgresWebhookMessageRepository(db_url)
            logger.info("Deduplicacion de webhooks: PostgreSQL activo.")
        except Exception:
            logger.warning(
                "No se pudo inicializar la deduplicacion PostgreSQL. "
                "Usando fallback in-memory (no es seguro con multiples replicas).",
                exc_info=True,
            )

        return cls(
            whatsapp_service=whatsapp_service,
            checkpointer=checkpointer,
            dedup_repo=dedup_repo,
        )

    # ------------------------------------------------------------------
    # Public async interface
    # ------------------------------------------------------------------

    async def process_message(self, message: WhatsAppInboundMessage) -> None:
        """Procesa un mensaje entrante de WhatsApp de forma asincrona.

        Garantías:
        - Deduplicación por message_id: los reintentos de WhatsApp no ejecutan el agente dos veces.
        - Procesamiento secuencial por usuario: nunca hay dos invocaciones paralelas del agente
          para el mismo thread_id, evitando race conditions en el checkpointer.
        - Feedback inmediato: marca el mensaje como leído antes de invocar el agente.
        """
        # 1. Dedup — silenciosamente ignorar si ya se procesó este message_id.
        # Fail-open: si el repo falla, procesamos el mensaje para no perderlo.
        try:
            if self._dedup_repo.is_duplicate_and_register(message.message_id):
                logger.info("Mensaje duplicado %s ignorado.", message.message_id)
                return
        except Exception:
            logger.warning(
                "Error al verificar deduplicacion para %s. Procesando de todas formas.",
                message.message_id,
                exc_info=True,
            )

        # 2. Marcar como leído inmediatamente (checkmarks azules al usuario)
        self._executor.submit(self._whatsapp_service.mark_message_read, message.message_id)

        # 3. Lock por usuario — serializa mensajes del mismo thread_id
        thread_id = message.from_number
        lock = self._thread_locks.get_or_create(thread_id)

        async with lock:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(self._executor, self._run_agent_sync, message)
            except Exception:
                logger.exception("Error procesando mensaje de %s", thread_id)

    # ------------------------------------------------------------------
    # Sync agent invocation (runs in thread pool)
    # ------------------------------------------------------------------

    def _run_agent_sync(self, message: WhatsAppInboundMessage) -> None:
        """Invoca el agente sincrono y envia las respuestas generadas."""
        thread_id = message.from_number

        normalized = self._normalize_inbound_message(message)
        if normalized is None:
            return
        if normalized.direct_response:
            self._send_direct_message(thread_id, normalized.direct_response)
            return

        human_message = normalized.human_message
        image_refs = normalized.image_refs
        if human_message is None:
            return

        logger.info("Procesando mensaje de %s: %.60s...", thread_id, str(human_message.content))

        config = {"configurable": {"thread_id": thread_id}}
        input_data: dict = {"messages": [human_message]}
        if image_refs:
            input_data["last_user_images"] = image_refs

        try:
            result = self._agent.invoke(input_data, config=config)
        except Exception:
            logger.exception("Fallo la invocacion del agente para thread_id=%s", thread_id)
            self._send_error_message(thread_id)
            return

        new_responses = _extract_new_ai_messages(result.get("messages", []))
        if not new_responses:
            logger.warning("El agente no genero respuestas para thread_id=%s", thread_id)
            return

        try:
            self._whatsapp_service.send_agent_messages(
                recipient_id=thread_id,
                messages=new_responses,
            )
            logger.info(
                "Enviadas %d respuestas a %s", len(new_responses), thread_id
            )
        except Exception:
            logger.exception("Error al enviar respuestas a %s", thread_id)

    def _build_human_message(
        self, message: WhatsAppInboundMessage
    ) -> tuple[HumanMessage | None, list[str]]:
        """Construye el HumanMessage y extrae referencias de imagen por separado.

        Las imágenes se devuelven como data URLs base64 en la segunda parte de la
        tupla para ser almacenadas en state.last_user_images (checkpoint PostgreSQL),
        no en state.messages.  Esto garantiza que cualquier instancia pueda acceder
        a la imagen sin depender del filesystem local.
        """
        from utils.media_artifacts import IMAGE_RECEIVED_MARKER, path_to_data_url

        text = (message.text or "").strip()

        if message.media is None:
            if not text:
                return None, []
            return HumanMessage(content=text), []

        media_type = str(message.media.media_type or "").strip().lower()
        if media_type == "image":
            content: list[dict] = []
            if text:
                content.append({"type": "text", "text": text})
            content.append({"type": "text", "text": IMAGE_RECEIVED_MARKER})

            image_refs: list[str] = []
            try:
                channel_msg = self._whatsapp_service.download_inbound(message)
                if channel_msg.media:
                    local_path = channel_msg.media[0].reference
                    data_url = path_to_data_url(local_path)
                    if data_url and data_url.startswith("data:image"):
                        image_refs.append(data_url)
            except Exception:
                logger.warning("No se pudo descargar la imagen %s", message.media.id, exc_info=True)

            return HumanMessage(content=content), image_refs

        ref = message.media.caption or f"[{media_type or 'media'} adjunto]"
        combined = f"{text}\n{ref}".strip() if text else ref
        return HumanMessage(content=combined), []

    def _normalize_inbound_message(
        self,
        message: WhatsAppInboundMessage,
    ) -> NormalizedAgentInput | None:
        """Normaliza modalidades no textuales antes de invocar LangGraph."""

        normalized = self._input_normalizer.normalize(message)
        if normalized is None:
            human_message, image_refs = self._build_human_message(message)

            return NormalizedAgentInput(
                human_message=human_message,
                image_refs=image_refs,
            )
        return normalized

    def _send_error_message(self, recipient_id: str) -> None:
        """Notifica al estudiante que ocurrio un error temporal."""
        try:
            self._whatsapp_service.send_agent_messages(
                recipient_id=recipient_id,
                messages=["Ocurrio un problema procesando tu mensaje. Por favor intentalo de nuevo."],
            )
        except Exception:
            logger.exception("Error al enviar mensaje de error a %s", recipient_id)

    def _send_direct_message(self, recipient_id: str, text: str) -> None:
        """Envía una respuesta determinística sin invocar el agente."""

        try:
            self._whatsapp_service.send_agent_messages(
                recipient_id=recipient_id,
                messages=[text],
            )
        except Exception:
            logger.exception("Error al enviar mensaje directo a %s", recipient_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_new_ai_messages(messages: list) -> list[AIMessage]:
    """Devuelve los AIMessages con respuesta textual generados en el turno actual.

    Busca el ultimo HumanMessage y retorna los AIMessages que lo siguen,
    filtrando mensajes intermedios del ciclo ReAct (tool_calls pendientes o
    content vacio) que no deben enviarse al usuario de WhatsApp.
    """
    last_human_idx = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = i

    slice_start = last_human_idx + 1 if last_human_idx != -1 else len(messages)
    return [
        m for m in messages[slice_start:]
        if isinstance(m, AIMessage) and not m.tool_calls and m.content
    ]


def _build_audio_transcriber():
    """Construye transcriptor de audio si las variables Azure están configuradas."""

    from integrations.ai.audio_transcription import maybe_build_audio_transcription_service

    return maybe_build_audio_transcription_service()


__all__ = ["AgentRunner"]
