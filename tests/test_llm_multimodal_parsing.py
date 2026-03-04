"""Pruebas para parseo robusto de salidas LLM multimodales."""

from __future__ import annotations

import agents.support.tools.llm as llm_tool


class _DummyResponse:
    def __init__(self, content: object) -> None:
        self.content = content


class _DummyLlm:
    def __init__(self, content: object) -> None:
        self._content = content

    def invoke(self, _payload: object) -> _DummyResponse:
        return _DummyResponse(self._content)


def test_llm_extract_schedule_from_image_parses_list_content(monkeypatch) -> None:
    """La respuesta en lista de bloques debe parsearse como JSON valido."""
    monkeypatch.setattr(
        llm_tool,
        "maybe_get_llm",
        lambda: _DummyLlm(
            [
                {
                    "type": "text",
                    "text": (
                        '{"is_schedule": true, "schedule_type": "academico", '
                        '"extracted_text": "Lunes 08:00-10:00 Algebra"}'
                    ),
                }
            ]
        ),
    )

    extracted = llm_tool.llm_extract_schedule_from_image(
        "data:image/png;base64,abc", "academico"
    )

    assert extracted is not None
    assert extracted["is_schedule"] is True
    assert extracted["schedule_type"] == "academico"
    assert extracted["extracted_text"].startswith("Lunes 08:00-10:00")


def test_safe_json_loads_accepts_python_repr() -> None:
    """Acepta dict serializado con comillas simples."""
    payload = (
        "{'is_schedule': True, 'schedule_type': 'academico', "
        "'extracted_text': 'Martes 10:00-12:00 Fisica'}"
    )
    data = llm_tool._safe_json_loads(payload)

    assert data is not None
    assert data["is_schedule"] is True
    assert data["schedule_type"] == "academico"


def test_llm_normalize_extracurricular_items_parses_json_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_tool,
        "maybe_get_llm",
        lambda: _DummyLlm(
            '{"items":[{"nombre":"Futbol","es_variable":true,'
            '"detalle":"2 veces por semana en la tarde"}]}'
        ),
    )

    items = llm_tool.llm_normalize_extracurricular_items(
        "Futbol variable, 2 veces por semana en la tarde"
    )

    assert items is not None
    assert len(items) == 1
    assert items[0]["nombre"] == "Futbol"
    assert items[0]["es_variable"] is True


def test_llm_extract_text_from_image_returns_plain_text(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_tool,
        "maybe_get_llm",
        lambda: _DummyLlm([{"type": "text", "text": "Lunes 08:00-10:00 Algebra"}]),
    )

    text = llm_tool.llm_extract_text_from_image("data:image/png;base64,abc")

    assert text is not None
    assert text.startswith("Lunes 08:00-10:00")
