"""Pruebas para extraccion de imagenes desde mensajes heterogeneos."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.nodes.utils import detect_new_input, get_last_user_images


def test_get_last_user_images_accepts_input_image_block() -> None:
    """Soporta bloques OpenAI input_image con image_url."""
    messages = [
        HumanMessage(
            content=[
                {"type": "text", "text": "Horario academico"},
                {"type": "input_image", "image_url": {"url": "data:image/png;base64,abc"}},
            ]
        )
    ]

    assert get_last_user_images(messages) == ["data:image/png;base64,abc"]


def test_get_last_user_images_accepts_source_base64_block() -> None:
    """Soporta bloques con source base64 (tipo Anthropic/LangSmith)."""
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "abc123",
                    },
                }
            ],
        }
    ]

    assert get_last_user_images(messages) == ["data:image/png;base64,abc123"]


def test_get_last_user_images_accepts_image_url_in_text() -> None:
    """Detecta URL de imagen cuando llega como texto simple."""
    messages = [{"role": "user", "content": "Mira: https://example.com/schedule.png"}]

    assert get_last_user_images(messages) == ["https://example.com/schedule.png"]


def test_detect_new_input_with_changed_image_and_same_count() -> None:
    """Marca nueva entrada si cambia la imagen aunque no cambie texto/contador."""
    messages = [
        {
            "role": "user",
            "content": [{"type": "input_image", "image_url": {"url": "data:image/png;base64,new"}}],
        }
    ]

    has_new, last_text, current_count = detect_new_input(
        messages,
        last_count=1,
        awaiting_user_input=True,
        last_user_text="",
        last_user_images=["data:image/png;base64,old"],
    )

    assert has_new is True
    assert last_text == ""
    assert current_count == 1


def test_detect_new_input_ignores_same_image_and_same_count() -> None:
    """No marca nueva entrada si la imagen es la misma y no hubo nuevo mensaje."""
    messages = [
        {
            "role": "user",
            "content": [{"type": "input_image", "image_url": {"url": "data:image/png;base64,same"}}],
        }
    ]

    has_new, _, current_count = detect_new_input(
        messages,
        last_count=1,
        awaiting_user_input=True,
        last_user_text="",
        last_user_images=["data:image/png;base64,same"],
    )

    assert has_new is False
    assert current_count == 1


def test_detect_new_input_ignores_images_when_not_tracking_previous() -> None:
    """Si no se rastrean imagenes previas, no debe activar nueva entrada por imagen."""
    messages = [
        {
            "role": "user",
            "content": [{"type": "input_image", "image_url": {"url": "data:image/png;base64,abc"}}],
        }
    ]

    has_new, _, current_count = detect_new_input(
        messages,
        last_count=1,
        awaiting_user_input=True,
        last_user_text="",
        last_user_images=None,
    )

    assert has_new is False
    assert current_count == 1
