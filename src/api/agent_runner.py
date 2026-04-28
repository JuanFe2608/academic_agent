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
from services.channels.whatsapp_service import WhatsAppChannelService

logger = logging.getLogger(__name__)


class _BoundedIdSet:
    """Conjunto acotado con política FIFO para deduplicar message_ids.

    Evita que el mismo webhook procesado dos veces (retry de WhatsApp)
    ejecute el agente dos veces. maxsize limita el uso de memoria.
    """

    def __init__(self, maxsize: int = 500) -> None:
        self._data: OrderedDict[str, None] = OrderedDict()
        self._maxsize = maxsize

    def contains_and_add(self, item: str) -> bool:
        """Retorna True si el item ya existía (duplicado). Lo registra si es nuevo."""
        if item in self._data:
            return True
        self._data[item] = None
        if len(self._data) > self._maxsize:
            self._data.popitem(last=False)  # Evicta el más antiguo
        return False


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
        max_workers: int = 4,
    ) -> None:
        from agents.support.agent import build_agent

        self._whatsapp_service = whatsapp_service
        self._checkpointer = checkpointer
        self._agent = build_agent(checkpointer=checkpointer)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="lara-agent")
        # Deduplicación: evita procesar el mismo message_id dos veces (retries de WhatsApp)
        self._seen_ids: _BoundedIdSet = _BoundedIdSet(maxsize=500)
        # Lock por thread_id: garantiza procesamiento secuencial por usuario (acotado a 1000 entradas)
        self._thread_locks: _BoundedLockMap = _BoundedLockMap(maxsize=1000)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "AgentRunner":
        """Construye un AgentRunner desde variables de entorno."""
        checkpoint_url = checkpoint_database_url_from_env()
        if not checkpoint_url:
            raise RuntimeError(
                "La URL de la base de datos de checkpoints no esta configurada. "
                "Verifica ACADEMIC_AGENT_DATABASE_URL o PGHOST/PGDATABASE/PGUSER/PGPASSWORD."
            )

        checkpointer = PostgresLangGraphCheckpointer(checkpoint_url)
        client = WhatsAppCloudClient.from_env()
        whatsapp_service = WhatsAppChannelService(client)

        return cls(
            whatsapp_service=whatsapp_service,
            checkpointer=checkpointer,
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
        # 1. Dedup — silenciosamente ignorar si ya se procesó este message_id
        if self._seen_ids.contains_and_add(message.message_id):
            logger.info("Mensaje duplicado %s ignorado.", message.message_id)
            return

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

        human_message = self._build_human_message(message)
        if human_message is None:
            return

        logger.info("Procesando mensaje de %s: %.60s...", thread_id, str(human_message.content))

        config = {"configurable": {"thread_id": thread_id}}
        input_data = {"messages": [human_message]}

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

    def _build_human_message(self, message: WhatsAppInboundMessage) -> HumanMessage | None:
        """Construye el HumanMessage adecuado segun el tipo de contenido recibido."""
        text = (message.text or "").strip()

        if message.media is None:
            if not text:
                return None
            return HumanMessage(content=text)

        if message.media.media_type in {"image", "sticker"}:
            content: list[dict] = []
            if text:
                content.append({"type": "text", "text": text})
            try:
                channel_msg = self._whatsapp_service.download_inbound(message)
                if channel_msg.media:
                    image_ref = channel_msg.media[0].reference
                    from utils.media_artifacts import is_inline_preview_enabled, path_to_data_url
                    url = path_to_data_url(image_ref) if is_inline_preview_enabled() else image_ref
                    content.append({"type": "image_url", "image_url": {"url": url}})
                else:
                    content.append({"type": "text", "text": f"[imagen no disponible id={message.media.id}]"})
            except Exception:
                logger.warning("No se pudo descargar la imagen %s", message.media.id, exc_info=True)
                content.append({"type": "text", "text": f"[imagen no disponible id={message.media.id}]"})
            return HumanMessage(content=content)

        ref = message.media.caption or f"[{message.media.media_type} adjunto]"
        combined = f"{text}\n{ref}".strip() if text else ref
        return HumanMessage(content=combined)

    def _send_error_message(self, recipient_id: str) -> None:
        """Notifica al estudiante que ocurrio un error temporal."""
        try:
            self._whatsapp_service.send_agent_messages(
                recipient_id=recipient_id,
                messages=["Ocurrio un problema procesando tu mensaje. Por favor intentalo de nuevo."],
            )
        except Exception:
            logger.exception("Error al enviar mensaje de error a %s", recipient_id)


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


__all__ = ["AgentRunner"]
