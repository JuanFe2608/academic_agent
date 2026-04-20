"""Formateadores conversacionales del plan semanal de estudio."""

from __future__ import annotations

from collections import Counter

from schemas.planning import StudyPlanState, SubjectItem
from schemas.reminders import RemindersState

# ── Tablas de referencia ───────────────────────────────────────────────────────

_DAY_SORT: dict[str, int] = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
    "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}
_DAY_LABEL: dict[str, str] = {
    "lunes": "Lunes", "martes": "Martes", "miercoles": "Miércoles", "miércoles": "Miércoles",
    "jueves": "Jueves", "viernes": "Viernes", "sabado": "Sábado", "sábado": "Sábado",
    "domingo": "Domingo",
}
_URGENCY_RATIONALE: dict[str, str] = {
    "parcial":         "parcial próximo",
    "quiz":            "quiz próximo",
    "entrega":         "entrega pendiente",
    "tarea":           "tarea pendiente",
    "taller":          "taller pendiente",
    "exposicion":      "exposición próxima",
    "exposición":      "exposición próxima",
    "proyecto":        "proyecto en curso",
    "estudio_pendiente": "requiere repaso",
}
_BLOCK_ACTION_PREFIX: dict[str, str] = {
    "parcial":    "preparación para parcial de",
    "quiz":       "preparación para quiz de",
    "entrega":    "avance de entrega de",
    "tarea":      "avance de tarea de",
    "taller":     "avance de taller de",
    "exposicion": "preparación para exposición de",
    "exposición": "preparación para exposición de",
    "proyecto":   "avance de proyecto de",
}
_ACTIVITY_LABEL: dict[str, str] = {
    "parcial":           "parcial",
    "quiz":              "quiz",
    "tarea":             "tarea",
    "taller":            "taller",
    "entrega":           "entrega",
    "exposicion":        "exposición",
    "exposición":        "exposición",
    "proyecto":          "proyecto",
    "estudio_pendiente": "sesión de estudio",
}
_DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


# ── Función principal ──────────────────────────────────────────────────────────

def build_study_plan_summary(
    subjects: list[SubjectItem],
    study_plan: StudyPlanState,
    *,
    reminders: RemindersState | dict | None = None,
) -> str:
    """Construye el resumen conversacional del plan semanal de estudio.

    Formato objetivo:
      📚 Plan semanal sugerido
      Enfoques principales → Bloques recomendados → Recomendaciones
      Guía pedagógica RAG (si aplica) → Método aplicado (si aplica)
      Estado operativo → Oferta de sincronización con Outlook
    """
    rules = dict(study_plan.rules or {})
    events = list(study_plan.plan_events)
    event_count = len(events)

    # Intro contextual: qué revisó Lara para generar el plan
    intro_parts = ["tus horarios fijos", "tus materias registradas"]
    if event_count > 0:
        intro_parts.append("tus actividades académicas")
    study_profile_hint = bool(rules.get("primary_technique_name"))
    if study_profile_hint:
        intro_parts.append("tu estilo de estudio")
    intro_list = ", ".join(intro_parts[:-1]) + (" y " + intro_parts[-1] if len(intro_parts) > 1 else intro_parts[0])

    lines: list[str] = [
        "🗓️ Revisé tu semana considerando " + intro_list + ".",
        "",
        "📚 *Plan semanal sugerido*",
    ]

    # §1 — Enfoques principales
    focus = _format_focus_subjects(subjects, events)
    if focus:
        lines += ["", "*Enfoques principales de la semana*"]
        lines += focus

    # §2 — Bloques recomendados
    blocks = _format_plan_blocks(events, subjects)
    if blocks:
        lines += ["", "*Bloques recomendados*"]
        lines += blocks
    else:
        unscheduled = list(rules.get("unscheduled_requests") or [])
        if unscheduled:
            lines += [
                "",
                f"No pude ubicar {len(unscheduled)} sesión(es) con la disponibilidad actual.",
                "Puedes pedirme un replanning para ajustar los horarios.",
            ]
        else:
            lines += ["", "Todavía no hay bloques ubicados. Puedes pedirme un replanning para generarlos."]

    # §3 — Recomendaciones dinámicas
    recs = _smart_recommendations(subjects, events, rules)
    if recs:
        lines += ["", "*Recomendaciones*"]
        lines += recs

    # §4 — Consejo pedagógico RAG (primera oración, no el bloque completo)
    rag_tip = _format_rag_tip(rules)
    if rag_tip:
        lines += ["", rag_tip]

    # §5 — Método aplicado a actividad prioritaria (resumen breve)
    method_tip = _format_applied_method_tip(rules)
    if method_tip:
        lines += ["", method_tip]

    # §6 — Estado operativo (sesiones materializadas, recordatorios)
    status = _format_operational_status(study_plan, reminders)
    if status:
        lines += [""] + status

    # Cierre — oferta de sincronización
    lines += ["", "¿Quieres que sincronice este plan con tu Outlook Calendar? 📅"]

    return "\n".join(lines)


# ── Secciones ──────────────────────────────────────────────────────────────────

def _format_focus_subjects(subjects: list[SubjectItem], events: list) -> list[str]:
    """Genera la lista de enfoques con rationale según urgencia/prioridad real."""
    if not subjects:
        return []
    lines: list[str] = []
    for subject in subjects[:5]:
        if len(lines) >= 4:
            break
        rationale = _subject_rationale(subject)
        lines.append(f"- {subject.nombre}: {rationale}")
    return lines


def _format_plan_blocks(events: list, subjects: list[SubjectItem]) -> list[str]:
    """Formatea los bloques del plan ordenados por día y hora en lenguaje natural."""
    study_events = [e for e in events if str(getattr(e, "categoria", "") or "") == "estudio"]
    if not study_events:
        study_events = list(events)
    if not study_events:
        return []

    subject_urgency: dict[str, str] = {
        s.nombre.lower(): str(s.urgency_type or "").lower()
        for s in subjects
        if s.nombre
    }

    sorted_events = sorted(
        study_events,
        key=lambda e: (
            _DAY_SORT.get(str(getattr(e, "dia", "") or "").lower(), 99),
            str(getattr(e, "inicio", "") or ""),
        ),
    )

    lines: list[str] = []
    for event in sorted_events[:8]:
        dia_raw = str(getattr(event, "dia", "") or "").lower()
        day = _DAY_LABEL.get(dia_raw, dia_raw.capitalize())
        start = _fmt_time(str(getattr(event, "inicio", "") or ""))
        end = _fmt_time(str(getattr(event, "fin", "") or ""))
        titulo = str(getattr(event, "titulo", "") or "")
        subject = _subject_from_title(titulo)
        urgency_type = subject_urgency.get(subject.lower(), "")
        action = _block_action_label(urgency_type, subject)
        lines.append(f"- {day} {start} a {end} → {action}")
    return lines


def _smart_recommendations(
    subjects: list[SubjectItem],
    events: list,
    rules: dict,
) -> list[str]:
    """Genera recomendaciones contextuales basadas en la carga y urgencia real."""
    recs: list[str] = []

    has_high_urgency = any(str(s.urgencia or "") == "alta" for s in subjects)
    if has_high_urgency:
        recs.append("✅ Prioriza primero lo que tiene fecha cercana")

    if len(subjects) > 1 and _one_subject_dominates(events):
        recs.append("✅ No dejes que una sola materia consuma toda la semana")

    session_min = _int_or_none(rules.get("session_minutes"))
    if session_min and session_min <= 60:
        recs.append("✅ Usa bloques cortos cuando tengas días muy cargados")
    elif len(events) >= 5:
        recs.append("✅ Distribuye el esfuerzo entre varios días para no agotarte")

    recs.append("✅ Reserva un espacio al final de la semana para revisar pendientes")
    return recs[:4]


def _format_rag_tip(rules: dict) -> str | None:
    """Extrae la primera oración del consejo RAG para no saturar al estudiante."""
    guidance = dict(rules.get("rag_session_guidance") or {})
    answer = str(guidance.get("answer") or "").strip()
    if not answer:
        return None
    subject = str(guidance.get("subject_name") or "").strip()
    first = _first_sentence(answer, max_chars=220)
    if not first or len(first) < 20:
        return None
    context = f" para {subject}" if subject else ""
    return f"🧠 Consejo de estudio{context}: {first}"


def _format_applied_method_tip(rules: dict) -> str | None:
    """Muestra el resumen del método aplicado a la actividad más prioritaria."""
    guidance = dict(rules.get("applied_method_guidance") or {})
    items = list(guidance.get("items") or [])
    if not items:
        return None
    first = dict(items[0]) if isinstance(items[0], dict) else {}
    subject = str(first.get("subject_name") or "").strip()
    activity_type = str(first.get("activity_type") or "").strip()
    summary = str(first.get("summary") or "").strip()
    steps = [str(s) for s in (first.get("steps") or []) if s]

    activity = _ACTIVITY_LABEL.get(activity_type, activity_type or "actividad")
    label = f"tu {activity}"
    if subject:
        label += f" de {subject}"

    if summary:
        return f"📖 Método sugerido para {label}:\n{_compact_text(summary, max_chars=200)}"
    if steps:
        step_lines = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps[:3]))
        return f"📖 Pasos para {label}:\n{step_lines}"
    return None


def _format_operational_status(
    study_plan: StudyPlanState,
    reminders: RemindersState | dict | None,
) -> list[str]:
    """Estado operativo de materializacion y recordatorios en tono conversacional."""
    lines: list[str] = []

    if study_plan.materialization_error:
        lines.append(
            "⚠️ No pude dejar listas las sesiones fechadas todavía. "
            "El plan queda guardado y se reintentará luego."
        )
        return lines

    if study_plan.materialized_instance_count is not None:
        count = int(study_plan.materialized_instance_count or 0)
        through = (
            f" hasta el {study_plan.materialized_through_date}"
            if study_plan.materialized_through_date
            else ""
        )
        if count:
            lines.append(f"✅ {count} sesión(es) programada(s){through}.")
        if study_plan.superseded_instance_count:
            lines.append(
                f"↩️ Reemplacé {study_plan.superseded_instance_count} sesión(es) de un plan anterior."
            )

    reminder_state = _coerce_reminders(reminders)
    if reminder_state is None:
        return lines
    if reminder_state.last_dispatch_error:
        lines.append(
            "⚠️ No pude activar los recordatorios todavía. Se reintentarán automáticamente."
        )
        return lines
    if reminder_state.last_sync_at:
        dispatches = int(reminder_state.created_dispatch_count or 0)
        if dispatches:
            channels = _format_channels(reminder_state.policy.get("channels"))
            lines.append(f"🔔 {dispatches} recordatorio(s) activado(s) por {channels}.")
    return lines


# ── Helpers ────────────────────────────────────────────────────────────────────

def _subject_rationale(subject: SubjectItem) -> str:
    """Genera la justificación de foco de una materia usando sus datos reales."""
    urgency_type = str(subject.urgency_type or "").lower().strip()
    urgencia = str(subject.urgencia or "").lower().strip()
    due = subject.urgency_due_at

    if urgency_type in _URGENCY_RATIONALE:
        base = _URGENCY_RATIONALE[urgency_type]
    elif urgencia == "alta":
        base = "requiere atención esta semana"
    elif urgencia == "media":
        base = "seguimiento continuo"
    else:
        base = "repaso preventivo"

    if due:
        try:
            from datetime import datetime
            d = datetime.strptime(str(due)[:10], "%Y-%m-%d")
            day_name = _DAYS_ES[d.weekday()]
            base += f" — {day_name} {d.day}/{d.month}"
        except Exception:
            pass
    return base


def _subject_from_title(titulo: str) -> str:
    """Extrae el nombre de la materia del título del evento de estudio."""
    if "·" in titulo:
        return titulo.split("·", maxsplit=1)[-1].strip()
    for prefix in ("sesión de estudio", "sesion de estudio", "estudio", "repaso", "bloque"):
        if titulo.lower().strip().startswith(prefix):
            rest = titulo[len(prefix):].strip(" -–:")
            if rest:
                return rest
    return titulo.strip()


def _block_action_label(urgency_type: str, subject: str) -> str:
    """Genera la etiqueta de acción del bloque según el tipo de urgencia."""
    prefix = _BLOCK_ACTION_PREFIX.get(urgency_type.lower() if urgency_type else "", "")
    if prefix:
        return f"{prefix} {subject}"
    return f"estudio de {subject}"


def _one_subject_dominates(events: list) -> bool:
    subjects = [
        _subject_from_title(str(getattr(e, "titulo", "") or ""))
        for e in events
    ]
    if len(subjects) < 3:
        return False
    counts = Counter(subjects)
    top_count = counts.most_common(1)[0][1]
    return top_count > len(subjects) * 0.6


def _fmt_time(time_str: str) -> str:
    """Convierte HH:MM (24h) a formato 12h con am/pm natural."""
    try:
        parts = time_str.strip().split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        period = "am" if h < 12 else "pm"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {period}" if m else f"{h12}:00 {period}"
    except (ValueError, IndexError):
        return time_str


def _first_sentence(text: str, *, max_chars: int = 220) -> str:
    cleaned = " ".join(text.split())
    for i, ch in enumerate(cleaned[:max_chars]):
        if ch in ".!?":
            return cleaned[: i + 1].strip()
    return cleaned[:max_chars].strip()


def _coerce_reminders(reminders: RemindersState | dict | None) -> RemindersState | None:
    if reminders is None:
        return None
    if isinstance(reminders, RemindersState):
        return reminders
    return RemindersState(**dict(reminders or {}))


def _format_channels(raw_channels: object) -> str:
    if isinstance(raw_channels, str):
        channels = [raw_channels]
    elif isinstance(raw_channels, (list, tuple, set)):
        channels = [str(c) for c in raw_channels]
    else:
        channels = ["in_app"]
    labels = {"in_app": "canal interno", "whatsapp": "WhatsApp", "email": "correo"}
    return ", ".join(labels.get(c, c) for c in channels if c) or "canal interno"


def _compact_text(text: str, *, max_chars: int = 520) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    cutoff = cleaned.rfind(".", 0, max_chars)
    if cutoff < int(max_chars * 0.55):
        cutoff = max_chars
    return cleaned[:cutoff].rstrip(" .,;:") + "..."


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
