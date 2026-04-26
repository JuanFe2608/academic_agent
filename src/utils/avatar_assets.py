"""Rutas de avatar del personaje para mensajes WhatsApp por contexto del flujo."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage

_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets" / "whatsapp"

AVATAR_HOLA_SALUDO = _ASSETS_DIR / "hola_saludo.png"
AVATAR_ORGANICEMOS_TU_SEMANA = _ASSETS_DIR / "organicemos_tu_semana.png"
AVATAR_ESTOY_ANALIZANDO = _ASSETS_DIR / "estoy_analizando.png"
AVATAR_CONFIRMACION = _ASSETS_DIR / "confirmacion_de_alguna_modificacio_o_plan.png"
AVATAR_TE_ESCUCHO = _ASSETS_DIR / "te_escucho.png"
AVATAR_PERFIL_LISTO = _ASSETS_DIR / "perfil_listo.png"
AVATAR_PRIORIDAD_ALTA = _ASSETS_DIR / "prioridad_alta.png"
AVATAR_PLAN_LISTO = _ASSETS_DIR / "plan_del_dia_listo.png"
AVATAR_SE_ACERCA_ENTREGA = _ASSETS_DIR / "se_acerca_una_entrega_importante.png"
AVATAR_BUEN_TRABAJO = _ASSETS_DIR / "buen_trabajo.png"
AVATAR_HORA_DE_ESTUDIAR = _ASSETS_DIR / "hora_de_estudiar.png"
AVATAR_NECESITO_CONTEXTO = _ASSETS_DIR / "necesito_mas_contexto.png"
AVATAR_TIENES_ACTIVIDAD = _ASSETS_DIR / "tienes_una_actividad_hoy.png"
AVATAR_BLOQUE_CREADO = _ASSETS_DIR / "bloque_de_estudio_creado.png"
AVATAR_VAMOS_PASO_A_PASO = _ASSETS_DIR / "vamos_paso_apaso.png"
AVATAR_TOMAR_PAUSA = _ASSETS_DIR / "tomar_una_pausa.png"


def with_avatar(text: str, avatar_path: Path | str) -> list[dict]:
    """Retorna contenido multimodal: texto + imagen de avatar del personaje."""
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": str(avatar_path)}},
    ]


def inject_avatar_into_update(update: dict, avatar_path: Path | str) -> dict:
    """Agrega el avatar a la ultima respuesta del agente en el update del nodo.

    No modifica mensajes que ya contienen imagen (ej: render del horario semanal).
    Solo actua sobre el ultimo AIMessage de la lista messages del update.
    """
    msgs = list(update.get("messages", []))
    if not msgs:
        return update
    last = msgs[-1]
    if not isinstance(last, AIMessage):
        return update
    content = last.content
    if isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") in {"image_url", "input_image"}
        for b in content
    ):
        return update
    if isinstance(content, str) and content.strip():
        new_content: list = with_avatar(content, avatar_path)
    elif isinstance(content, list):
        new_content = list(content) + [
            {"type": "image_url", "image_url": {"url": str(avatar_path)}}
        ]
    else:
        return update
    msgs[-1] = AIMessage(content=new_content)
    return {**update, "messages": msgs}


__all__ = [
    "AVATAR_HOLA_SALUDO",
    "AVATAR_ORGANICEMOS_TU_SEMANA",
    "AVATAR_ESTOY_ANALIZANDO",
    "AVATAR_CONFIRMACION",
    "AVATAR_TE_ESCUCHO",
    "AVATAR_PERFIL_LISTO",
    "AVATAR_PRIORIDAD_ALTA",
    "AVATAR_PLAN_LISTO",
    "AVATAR_SE_ACERCA_ENTREGA",
    "AVATAR_BUEN_TRABAJO",
    "AVATAR_HORA_DE_ESTUDIAR",
    "AVATAR_NECESITO_CONTEXTO",
    "AVATAR_TIENES_ACTIVIDAD",
    "AVATAR_BLOQUE_CREADO",
    "AVATAR_VAMOS_PASO_A_PASO",
    "AVATAR_TOMAR_PAUSA",
    "with_avatar",
    "inject_avatar_into_update",
]
