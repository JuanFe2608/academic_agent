"""Context builder para el sistema prompt del agente académico Lara.

Construye la cadena de contexto completa del estudiante que se inyecta como
system message en cada invocación del agente ReAct.
"""

from __future__ import annotations

from datetime import date

from agents.support.state import AgentState

_DAYS_ES: dict[str, str] = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miércoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sábado",
    "sunday": "Domingo",
}

_DAYS_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def build_agent_context(state: AgentState) -> str:
    """Construye el contexto completo del estudiante para inyectarlo como system prompt."""
    profile = state.student_profile
    study_profile = state.study_profile
    today = date.today().isoformat()

    techniques = list(study_profile.top_techniques or [])
    tech_lines = "\n".join(f"  - {t}" for t in techniques[:3]) or "  - No configuradas"
    weakness = ", ".join(study_profile.weakness_tags) if study_profile.weakness_tags else "ninguna"

    return (
        f"Eres Lara, asistente académica autónoma de {profile.full_name or 'el estudiante'}.\n"
        "\n"
        "Tu objetivo es ayudar al estudiante a:\n"
        "1. Planificar su tiempo de estudio de forma efectiva\n"
        "2. Registrar y hacer seguimiento de actividades académicas (parciales, tareas, proyectos)\n"
        "3. Recomendar técnicas de estudio adaptadas a su perfil (usa search_study_methods)\n"
        "4. Mantener su plan semanal actualizado\n"
        "\n"
        "CÓMO ACTUAR:\n"
        "- Cuando el estudiante mencione un examen, tarea o entrega → usa add_academic_activity\n"
        "- Cuando pida reorganizar su semana o actualizar el plan → usa update_study_plan\n"
        "- Cuando pregunte cómo estudiar algo → usa search_study_methods con sus técnicas top\n"
        "- Cuando pida ver su agenda o plan → usa get_weekly_plan + get_schedule\n"
        "- Actúa proactivamente: si registras una actividad urgente, sugiere una técnica inmediatamente\n"
        "- Si recibes una imagen: interpreta su contenido académico (enunciado, rúbrica, fecha de entrega, etc.) "
        "y ofrece ayuda concreta — registra actividades, sugiere técnicas o ajusta el plan según corresponda\n"
        "\n"
        "LÍMITES:\n"
        "- Solo apoyas con planificación académica y técnicas de estudio\n"
        "- No resuelves ejercicios ni tareas directamente\n"
        "- Si el estudiante necesita apoyo emocional, reconócelo brevemente y redirige a recursos de bienestar\n"
        "\n"
        "---\n"
        "PERFIL DEL ESTUDIANTE:\n"
        f"- Nombre: {profile.full_name or '—'}\n"
        f"- Semestre: {profile.semester or '—'}\n"
        f"- Promedio: {profile.average_grade or '—'}\n"
        f"- Ocupación: {profile.occupation or '—'}\n"
        "\n"
        "TÉCNICAS DE ESTUDIO PREFERIDAS (Radar):\n"
        f"{tech_lines}\n"
        f"Señales de debilidad: {weakness}\n"
        "\n"
        "HORARIO FIJO:\n"
        f"{format_schedule_blocks(state.schedule.blocks)}\n"
        "\n"
        "MATERIAS CON PRIORIDAD:\n"
        f"{format_subjects(state.subjects)}\n"
        "\n"
        "ACTIVIDADES ACADÉMICAS PENDIENTES:\n"
        f"{format_activities(state.academic_activities)}\n"
        "\n"
        "PLAN DE ESTUDIO ACTUAL:\n"
        f"{format_study_plan(state.study_plan)}\n"
        "\n"
        f"Fecha actual: {today} | Zona horaria: {state.timezone}"
    )


def format_schedule_blocks(blocks: list) -> str:
    if not blocks:
        return "  Sin horario registrado."
    day_groups: dict[str, list[str]] = {}
    for block in blocks:
        if not getattr(block, "is_active", True):
            continue
        day_key = getattr(block, "day_of_week", "")
        day_label = _DAYS_ES.get(day_key, day_key)
        entry = f"{block.start_time}–{block.end_time} {block.title} [{block.block_type}]"
        day_groups.setdefault(day_label, []).append(entry)
    if not day_groups:
        return "  Sin bloques activos."
    lines = []
    for day_key in _DAYS_ORDER:
        day_label = _DAYS_ES[day_key]
        if day_label in day_groups:
            lines.append(f"  {day_label}: {', '.join(day_groups[day_label])}")
    return "\n".join(lines)


def format_subjects(subjects: list) -> str:
    if not subjects:
        return "  Sin materias configuradas."
    lines = []
    for s in subjects:
        nombre = getattr(s, "nombre", "—")
        prioridad = getattr(s, "prioridad", "—")
        dificultad = getattr(s, "dificultad", "—")
        carga = getattr(s, "carga_semanal_min", None)
        carga_str = f", {carga}min/sem" if carga else ""
        lines.append(f"  - {nombre}: prioridad={prioridad}, dificultad={dificultad}{carga_str}")
    return "\n".join(lines)


def format_activities(activities: list) -> str:
    from services.planning.academic_activity_service import active_academic_activities

    active = active_academic_activities(list(activities)) if activities else []
    pending = [a for a in active if getattr(a, "status", "") == "pending"]
    if not pending:
        return "  Sin actividades pendientes."
    lines = []
    for a in pending[:10]:
        due = getattr(a, "due_date", None) or "sin fecha"
        lines.append(
            f"  - [{a.activity_type}] {a.subject_name}: {a.activity_title}"
            f" — vence {due} (prioridad {a.priority_level or 'media'})"
        )
    return "\n".join(lines)


def format_study_plan(study_plan) -> str:
    events = getattr(study_plan, "plan_events", []) or []
    if not events:
        return "  Sin plan generado."
    by_title: dict[str, list[str]] = {}
    for ev in events[:20]:
        titulo = getattr(ev, "titulo", "Sesión")
        dia_key = getattr(ev, "dia", "")
        dia = _DAYS_ES.get(dia_key, dia_key)
        inicio = getattr(ev, "inicio", "—")
        by_title.setdefault(titulo, []).append(f"{dia} {inicio}")
    lines = []
    for titulo, slots in list(by_title.items())[:6]:
        lines.append(f"  - {titulo}: {', '.join(slots[:3])}")
    extra = len(by_title) - 6
    if extra > 0:
        lines.append(f"  ... y {extra} materia(s) más")
    return "\n".join(lines)


__all__ = [
    "build_agent_context",
    "format_schedule_blocks",
    "format_subjects",
    "format_activities",
    "format_study_plan",
]
