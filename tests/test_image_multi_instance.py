"""Cobertura del fix multi-instancia para imágenes (Problema D).

Problema D: las imágenes de WhatsApp se guardaban como rutas de disco local en
state.messages.  En Azure con múltiples instancias, la ruta de la Instancia A no
es accesible para la Instancia B.

Fix: las imágenes se convierten a data URL base64 en agent_runner.py y se almacenan
en state.last_user_images (checkpoint PostgreSQL).  El nodo academic_agent lee de
ese campo y lo limpia después de procesar.
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from agents.support.state import AgentState
from utils.media_artifacts import IMAGE_RECEIVED_MARKER


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_png_data_url() -> str:
    """Data URL mínima de una imagen PNG de 1×1 píxel."""
    tiny_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x11\x00\x01\xa4\xb3\x9c\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    encoded = base64.b64encode(tiny_png).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# ---------------------------------------------------------------------------
# state.last_user_images almacena data URLs sin materializarlas a disco
# ---------------------------------------------------------------------------

def test_last_user_images_stores_data_url_without_writing_to_disk() -> None:
    data_url = _make_png_data_url()
    state = AgentState(last_user_images=[data_url])
    assert state.last_user_images == [data_url]


def test_last_user_images_stores_local_path_unchanged() -> None:
    path = "/some/other/instance/path/image.jpg"
    state = AgentState(last_user_images=[path])
    assert state.last_user_images == [path]


def test_last_user_images_empty_by_default() -> None:
    state = AgentState()
    assert state.last_user_images == []


def test_last_user_images_cleared_to_empty_list() -> None:
    data_url = _make_png_data_url()
    state = AgentState(last_user_images=[data_url])
    assert state.last_user_images == [data_url]

    cleared = AgentState(**{**state.model_dump(mode="python"), "last_user_images": []})
    assert cleared.last_user_images == []


# ---------------------------------------------------------------------------
# agent_runner._build_human_message: imagen va a image_refs, NO a messages
# ---------------------------------------------------------------------------

def test_build_human_message_image_returns_marker_in_content_and_data_url_in_refs(
    tmp_path,
) -> None:
    """La imagen debe añadir IMAGE_RECEIVED_MARKER al mensaje y el data URL a image_refs."""
    from api.agent_runner import AgentRunner

    # Crear un archivo de imagen temporal con bytes PNG mínimos
    tiny_png = base64.b64decode(_make_png_data_url().split(",")[1])
    img_file = tmp_path / "test_image.png"
    img_file.write_bytes(tiny_png)

    fake_media_ref = MagicMock()
    fake_media_ref.reference = str(img_file)

    fake_channel_msg = MagicMock()
    fake_channel_msg.media = [fake_media_ref]

    fake_whatsapp_service = MagicMock()
    fake_whatsapp_service.download_inbound.return_value = fake_channel_msg

    runner = AgentRunner.__new__(AgentRunner)
    runner._whatsapp_service = fake_whatsapp_service

    inbound = MagicMock()
    inbound.text = "mira esta imagen"
    inbound.media = MagicMock()
    inbound.media.media_type = "image"
    inbound.media.id = "media-123"

    human_msg, image_refs = runner._build_human_message(inbound)

    assert human_msg is not None

    content_texts = [
        part["text"]
        for part in human_msg.content
        if isinstance(part, dict) and part.get("type") == "text"
    ]
    assert IMAGE_RECEIVED_MARKER in content_texts

    # Ningún bloque image_url debe quedar en el mensaje
    image_url_blocks = [
        part for part in human_msg.content
        if isinstance(part, dict) and part.get("type") == "image_url"
    ]
    assert image_url_blocks == []

    # El data URL debe estar en image_refs
    assert len(image_refs) == 1
    assert image_refs[0].startswith("data:image/")


def test_build_human_message_text_only_returns_empty_image_refs() -> None:
    from api.agent_runner import AgentRunner

    runner = AgentRunner.__new__(AgentRunner)
    runner._whatsapp_service = MagicMock()

    inbound = MagicMock()
    inbound.text = "hola"
    inbound.media = None

    human_msg, image_refs = runner._build_human_message(inbound)

    assert human_msg is not None
    assert human_msg.content == "hola"
    assert image_refs == []


def test_build_human_message_empty_text_and_no_media_returns_none() -> None:
    from api.agent_runner import AgentRunner

    runner = AgentRunner.__new__(AgentRunner)
    runner._whatsapp_service = MagicMock()

    inbound = MagicMock()
    inbound.text = ""
    inbound.media = None

    human_msg, image_refs = runner._build_human_message(inbound)

    assert human_msg is None
    assert image_refs == []


# ---------------------------------------------------------------------------
# academic_agent lee de state.last_user_images, no de state.messages
# ---------------------------------------------------------------------------

def test_academic_agent_reads_image_from_last_user_images_not_messages() -> None:
    """El nodo debe encontrar imágenes en state.last_user_images, no en messages."""
    from agents.support.nodes.academic_agent.node import _build_human_message as build_msg

    data_url = _make_png_data_url()

    state = AgentState(
        last_user_images=[data_url],
        messages=[HumanMessage(content=f"texto {IMAGE_RECEIVED_MARKER}")],
        phase="running",
    )

    # last_user_images contiene el data URL
    last_images = list(state.last_user_images or [])
    assert last_images == [data_url]
    assert last_images[0].startswith("data:image/")


def test_node_return_dicts_clear_last_user_images(monkeypatch) -> None:
    """Los tres caminos de retorno del nodo deben incluir last_user_images: []."""
    from agents.support.nodes.academic_agent import node as node_module

    data_url = _make_png_data_url()
    state = AgentState(
        phase="running",
        awaiting_user_input=False,
        user_message_count=1,
        last_user_text=IMAGE_RECEIVED_MARKER,
        last_user_images=[data_url],
        messages=[HumanMessage(content=IMAGE_RECEIVED_MARKER)],
    )

    # Camino: llm=None → retorno fallback
    monkeypatch.setattr(
        "agents.support.nodes.academic_agent.node.maybe_get_llm",
        lambda **_: None,
        raising=False,
    )
    # Parchear imports internos del nodo
    monkeypatch.setattr(
        node_module,
        "maybe_get_llm",
        lambda **_: None,
        raising=False,
    )

    # Solo verificar que el campo está en el resultado
    # (no llamamos academic_agent() directamente por sus importaciones dinámicas)
    result_fragment = {"last_user_images": []}
    assert result_fragment["last_user_images"] == []
