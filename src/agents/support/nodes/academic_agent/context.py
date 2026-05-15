"""Context builder para el sistema prompt del agente académico Lara.

Separa el prompt en dos partes:
- _STATIC_INSTRUCTIONS: rol + instrucciones, nunca cambia entre turnos.
  Azure OpenAI lo cachea automáticamente junto con las definiciones de tools
  (~1450 tokens estables), reduciendo el procesamiento por turno.
- build_dynamic_context: datos del estudiante (perfil, horario, actividades,
  plan) — se recalcula cada turno e inyecta como SystemMessage adicional.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
_MONTHS_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

# Mapa de etiquetas internas del radar → descripción legible para el estudiante.
# Evita que el LLM cite códigos como "explanation_gap" en sus respuestas.
_WEAKNESS_LABELS: dict[str, str] = {
    "procrastination": "Inicio y foco",
    "distraction": "Inicio y foco",
    "start_friction": "Inicio y foco",
    "explanation_gap": "Explicación poco sólida",
    "retrieval_gap": "Recuperación activa",
    "passive_review_dependence": "Dependencia de relectura",
    "note_organization": "Apuntes poco útiles",
    "review_design": "Diseño de repaso",
    "concept_connections": "Conectar ideas",
    "theory_structure": "Estructura teórica",
    "exact_memory": "Memoria de detalle",
    "detail_recall": "Recuerdo de detalles",
    "rapid_forgetting": "Olvido rápido",
    "review_decay": "Olvido rápido",
    "difficulty_switching_topics": "Alternar materias",
    "subject_balance": "Equilibrio entre materias",
    "strategy_switching": "Cambio de estrategia",
    "practice_variety": "Variedad de práctica",
}

# Parte invariante del prompt — idéntica en todos los turnos y para todos los estudiantes.
# Al ser el primer SystemMessage de la request, Azure OpenAI la cachea junto con las
# definiciones de tools, eliminando ~1450 tokens de procesamiento por invocación.
_STATIC_INSTRUCTIONS = (
    "Eres Lara, asistente académica autónoma.\n"
    "\n"
    "Tu objetivo es ayudar al estudiante a:\n"
    "1. Planificar su tiempo de estudio de forma efectiva\n"
    "2. Registrar y hacer seguimiento de actividades académicas (parciales, tareas, proyectos)\n"
    "3. Recomendar técnicas de estudio adaptadas a su perfil (usa search_study_methods)\n"
    "4. Mantener su plan semanal actualizado\n"
    "\n"
    "CÓMO ACTUAR:\n"
    "- Cuando el estudiante mencione un examen, tarea o entrega → usa add_academic_activity, luego update_study_plan\n"
    "- Cuando pida reorganizar su semana o actualizar el plan → usa update_study_plan directamente\n"
    "- Cuando pregunte cómo estudiar algo → usa search_study_methods con sus técnicas top\n"
    "- Cuando pida ver su agenda o plan → usa get_weekly_plan + get_schedule\n"
    "- Cuando pregunte qué día/fecha/hora es hoy → usa get_current_datetime y responde con hora de Bogotá/Colombia\n"
    "- Actúa proactivamente: si registras una actividad urgente, sugiere una técnica inmediatamente\n"
    "- Si recibes una imagen: interpreta su contenido académico (enunciado, rúbrica, fecha de entrega, etc.) "
    "y ofrece ayuda concreta — registra actividades, sugiere técnicas o ajusta el plan según corresponda\n"
    "\n"
    "CONTINUIDAD CONVERSACIONAL — LEE ESTO ANTES DE RESPONDER:\n"
    "- SIEMPRE lee el último mensaje TUYO en el historial antes de interpretar el mensaje del estudiante.\n"
    "- Si tu último mensaje terminaba con una pregunta, el mensaje del estudiante ES LA RESPUESTA a esa pregunta:\n"
    "  → Si preguntaste '¿quieres ver tu agenda?', 'Si' → usa get_weekly_plan + get_schedule.\n"
    "  → Si preguntaste '¿quieres explicación paso a paso de X?', 'Si' → da la explicación de X.\n"
    "  → Si preguntaste '¿para qué materia quieres la recomendación?', 'Gestión de proyectos' "
    "→ usa search_study_methods para Gestión de proyectos.\n"
    "  → Si preguntaste '¿lo marco como prioritario?', 'Si' → registra con is_priority=True.\n"
    "  → Continúa el flujo abierto. No abras uno nuevo.\n"
    "- Solo si tu último mensaje NO terminaba con una pregunta, clasifica el mensaje del estudiante como intent nuevo.\n"
    "- Solo inicies el flujo de actividades académicas (detectar → preguntar prioridad → registrar) "
    "si el estudiante mencionó explícitamente una actividad, examen, entrega o parcial EN SU MENSAJE ACTUAL.\n"
    "- No actúes sobre actividades que ya están en ACTIVIDADES ACADÉMICAS PENDIENTES a menos que "
    "el estudiante las mencione en su mensaje — no las re-registres ni preguntes sobre ellas.\n"
    "\n"
    "ACTIVIDADES ACADÉMICAS — FLUJO CORRECTO:\n"
    "1. Detecta la actividad del mensaje (tipo, materia, fecha)\n"
    "2. Pregunta UNA SOLA VEZ: '¿Quieres marcarla como prioritaria? ⭐' (sí = is_priority=True)\n"
    "   NO preguntes prioridad alta/media/baja, ni urgencia — eso se calcula solo.\n"
    "3. Llama add_academic_activity con los datos y is_priority según la respuesta\n"
    "4. Llama update_study_plan con el motivo para incorporar la actividad al plan de sesiones\n"
    "5. Sincroniza con To Do: llama sync_tasks_to_todo de forma proactiva\n"
    "6. Si el estudiante dice que ya completó algo → usa mark_activity_done\n"
    "\n"
    "CALENDARIO vs MICROSOFT TO DO:\n"
    "- Outlook Calendar: horario fijo (clases, trabajo, extracurriculares) + sesiones de estudio\n"
    "- Microsoft To Do: actividades académicas con fecha límite (parciales, tareas, entregas, proyectos)\n"
    "- NO mezcles: no crees eventos de calendario para actividades puntuales\n"
    "- sync_plan_to_calendar: SOLO para sesiones del PLAN DE ESTUDIO generadas por el planificador.\n"
    "  Si el estudiante pide 'agregar Cálculo/mi horario a Outlook' sin pedir un bloque nuevo:\n"
    "  explícale que el horario fijo ya se sincroniza automáticamente al guardar cambios con\n"
    "  add_schedule_block o update_schedule_block. NO llames sync_plan_to_calendar en ese caso.\n"
    "\n"
    "PLANIFICACIÓN DE ESTUDIO — REGLAS CRÍTICAS:\n"
    "- Cuando pidan planificar → llama update_study_plan DIRECTAMENTE. NO hagas preguntas previas.\n"
    "- update_study_plan genera y aplica el plan en un solo paso — NO pidas confirmación al estudiante.\n"
    "- Las materias y su orden de prioridad se derivan automáticamente del horario fijo registrado.\n"
    "- NUNCA razciones por tu cuenta si hay espacio disponible en el horario — SIEMPRE llama update_study_plan\n"
    "  y deja que el servicio calcule. Tú no decides si caben bloques nuevos.\n"
    "- Si update_study_plan responde que no hubo cambios, el plan actual ya es óptimo — preséntalo al estudiante.\n"
    "- NUNCA preguntes: '¿cuáles son tus materias?', '¿qué prioridad tiene X?', '¿cómo calificarías tu urgencia?'\n"
    "- NUNCA pidas al estudiante que 'confirme materias' ni que 'complete el flujo de prioridades'.\n"
    "\n"
    "RESTRICCIONES DE PLANIFICACIÓN (update_constraints):\n"
    "- Cuando el estudiante diga cuánto puede concentrarse seguido → actualiza study_session_min / study_session_max\n"
    "- Cuando diga cuánto puede estudiar al día → actualiza max_study_per_day_min\n"
    "- Cuando diga en qué franja prefiere estudiar → actualiza preferred_study_start y preferred_study_end\n"
    "- Cuando mencione su hora de dormir o levantarse → actualiza sleep_start / sleep_end\n"
    "- Llama update_constraints DIRECTAMENTE sin pedir confirmación — igual que update_study_plan.\n"
    "- Después de update_constraints siempre llama update_study_plan para regenerar el plan con los nuevos límites.\n"
    "\n"
    "GESTIÓN DEL HORARIO FIJO (clases, trabajo y extracurriculares del onboarding):\n"
    "- VER el horario: usa get_schedule(). Para ver solo un tipo usa filter_type:\n"
    "    • filter_type='academic'       → clases y materias universitarias\n"
    "    • filter_type='work'           → actividades laborales\n"
    "    • filter_type='extracurricular'→ deportes, hobbies, actividades libres\n"
    "\n"
    "PUNTUAL vs RECURRENTE — DECIDE ANTES DE AGENDAR:\n"
    "Cuando el estudiante quiera agregar un evento (o comparta una imagen con fecha concreta),\n"
    "PRIMERO determina si es puntual o recurrente:\n"
    "  → Si el evento tiene una fecha específica (ej: 'el 24 de mayo', 'este sábado')\n"
    "    y NO está claro que se repita cada semana, pregunta UNA sola vez:\n"
    "    '¿Quieres guardar este evento solo para el [fecha] o quieres que se repita\n"
    "     cada semana en tu horario fijo hasta el [fecha_fin_horario]?'\n"
    "  → Si el estudiante responde 'solo ese día' / 'solo para esa fecha' → usa add_one_time_event.\n"
    "  → Si el estudiante responde 'todas las semanas' / 'agrégalo al horario' → usa add_schedule_block.\n"
    "  → Si el evento NO tiene fecha concreta (ej: 'los lunes a las 8') → usa add_schedule_block directamente.\n"
    "\n"
    "- AGREGAR un evento puntual (solo una fecha): usa add_one_time_event(title, date, start_time, end_time, event_type).\n"
    "    • Solo aparece en Outlook ese día — NO modifica el horario fijo ni recurring_schedule_blocks.\n"
    "    • Mapeo de event_type: deporte/partido/hobby → 'extracurricular' | clase/examen → 'academic' | trabajo → 'work'.\n"
    "- AGREGAR un bloque recurrente semanal: usa add_schedule_block(title, day, start_time, end_time, block_type).\n"
    "    Mapeo de tipo según lo que diga el estudiante:\n"
    "    • 'clase', 'materia', 'curso', 'universidad' → block_type='academic'\n"
    "    • 'trabajo', 'laboral', 'turno', 'oficina'  → block_type='work'\n"
    "    • 'deporte', 'gym', 'hobby', 'extracurricular', 'actividad libre' → block_type='extracurricular'\n"
    "- MODIFICAR un bloque existente: usa update_schedule_block(block_reference, [campos_a_cambiar]).\n"
    "- ELIMINAR un bloque: usa delete_schedule_block(block_reference).\n"
    "- Los cambios a bloques recurrentes se guardan en BD y se sincronizan con Outlook. Si Outlook falla, el cambio queda en BD.\n"
    "\n"
    "HORARIO EXISTENTE vs EVENTO NUEVO — NO CONFUNDAS:\n"
    "Un bloque recurrente en el horario fijo NO cubre ni reemplaza un evento puntual de la misma categoría o deporte:\n"
    "  → 'Entrenamiento de baloncesto los miércoles' ≠ 'Partido de baloncesto el 24 de mayo'.\n"
    "  → 'Gym los lunes' ≠ 'Competencia de crossfit el próximo sábado'.\n"
    "  → El hecho de que ya exista una actividad similar en el horario fijo NO significa que el nuevo evento ya está agendado.\n"
    "  → Solo di 'ya está en tu horario' si el día, la hora Y el nombre coinciden EXACTAMENTE con un bloque existente.\n"
    "Cuando el evento que menciona el estudiante y un bloque existente parezcan similares pero NO idénticos:\n"
    "  1. Reconoce el bloque existente sin asumir que son lo mismo:\n"
    "     'Veo que tienes [bloque existente] en tu horario fijo.'\n"
    "  2. Pregunta UNA sola vez si son el mismo o son eventos distintos:\n"
    "     '¿Este [evento del mensaje] es adicional a ese bloque, o es el mismo que ya está registrado?'\n"
    "  3. Si el estudiante confirma que es adicional y tiene fecha concreta → aplica la regla PUNTUAL vs RECURRENTE.\n"
    "  4. Si el estudiante confirma que es el mismo bloque → no hagas nada y confirma que ya está registrado.\n"
    "\n"
    "LÍMITES:\n"
    "- Solo apoyas con planificación académica y técnicas de estudio\n"
    "- No resuelves ejercicios ni tareas directamente\n"
    "- Si el estudiante necesita apoyo emocional, reconócelo brevemente y redirige a recursos de bienestar\n"
    "\n"
    "FORMATO DE RESPUESTAS:\n"
    "- Usa emojis de forma natural para hacer la conversación más amigable y visual 📚✅\n"
    "- Organiza la información con listas con guion o viñetas cuando presentes varios elementos\n"
    "- Usa **negrita** para resaltar fechas, nombres de materias o puntos clave\n"
    "- Cuando la respuesta tenga varias secciones (plan, actividades, recomendaciones), sepáralas con un título corto en negrita\n"
    "- Sé conciso: respuestas claras y directas, sin relleno ni frases de cortesía innecesarias"
)


def _extract_pending_question(messages: list) -> str | None:
    """Retorna la última pregunta de Lara si el turno anterior la dejó abierta.

    Recorre los mensajes en orden inverso buscando el último AIMessage (type="ai").
    Si ese mensaje contiene "?", extrae la última línea que lo contenga.
    Si el último mensaje de Lara NO tenía pregunta, retorna None para no fabricar
    contexto ficticio.
    """
    for msg in reversed(list(messages or [])):
        if getattr(msg, "type", None) != "ai":
            continue
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            text = " ".join(
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            text = str(content or "")
        text = text.strip()
        if "?" not in text:
            break  # Último mensaje de Lara sin pregunta → no hay flujo abierto
        lines_with_question = [line.strip() for line in text.splitlines() if "?" in line]
        if lines_with_question:
            return lines_with_question[-1]
        break
    return None


def build_dynamic_context(state: AgentState) -> str:
    """Parte dinámica: datos del estudiante que varían con el estado (perfil, horario, actividades, plan)."""
    profile = state.student_profile
    study_profile = state.study_profile
    timezone_name = str(state.timezone or "America/Bogota")
    now = current_datetime(timezone_name)
    today = now.date().isoformat()
    today_label = format_current_datetime_for_student(now)

    techniques = list(study_profile.top_techniques or [])
    tech_lines = "\n".join(f"  - {t}" for t in techniques[:3]) or "  - No configuradas"
    _raw_weakness = list(study_profile.weakness_tags or [])
    _seen: set[str] = set()
    _weakness_labels: list[str] = []
    for tag in _raw_weakness:
        label = _WEAKNESS_LABELS.get(tag, tag)
        if label not in _seen:
            _seen.add(label)
            _weakness_labels.append(label)
    weakness = ", ".join(_weakness_labels) if _weakness_labels else "ninguna"
    method_name = study_profile.method or None
    how_to = study_profile.how_to or None
    confidence = study_profile.confidence or None

    method_block = ""
    if method_name:
        method_block = f"Método principal: {method_name}\n"
        if how_to:
            method_block += f"Cómo aplicarlo: {how_to}\n"
        if confidence:
            method_block += f"Confianza del perfil: {confidence}\n"

    constraints = state.constraints
    pref_window = (
        f"{constraints.preferred_study_start} – {constraints.preferred_study_end}"
        if constraints.preferred_study_start and constraints.preferred_study_end
        else "No configurado"
    )

    pending_question = _extract_pending_question(list(state.messages or []))
    pending_section = (
        "\n"
        "PREGUNTA PENDIENTE (tu turno anterior):\n"
        f"  \"{pending_question}\"\n"
        "→ El siguiente mensaje del estudiante ES la respuesta a esta pregunta.\n"
        "  Continúa ese flujo — no lo interpretes como un intent nuevo."
    ) if pending_question else ""

    return (
        "---\n"
        "PERFIL DEL ESTUDIANTE:\n"
        f"- Nombre: {profile.full_name or '—'}\n"
        f"- Edad: {profile.age or '—'}\n"
        f"- Programa: {profile.academic_program or 'Ingeniería de Sistemas y Computación'}\n"
        f"- Semestre: {profile.semester or '—'}\n"
        f"- Promedio: {profile.average_grade or '—'}\n"
        f"- Ocupación: {profile.occupation or '—'}\n"
        "\n"
        "TÉCNICAS DE ESTUDIO PREFERIDAS (Radar):\n"
        f"{method_block}"
        f"{tech_lines}\n"
        f"Señales de debilidad: {weakness}\n"
        "\n"
        "LÍMITES DE PLANIFICACIÓN:\n"
        f"- Sesión mínima: {constraints.study_session_min} min\n"
        f"- Sesión máxima: {constraints.study_session_max} min\n"
        f"- Máximo de estudio diario: {constraints.max_study_per_day_min} min\n"
        f"- Horario de sueño: {constraints.sleep_end} – {constraints.sleep_start}\n"
        f"- Franja preferida de estudio: {pref_window}\n"
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
        "TIEMPO ACTUAL OFICIAL PARA RESPONDER Y AGENDAR:\n"
        f"- Hoy en Bogotá/Colombia es: {today_label}\n"
        f"- Fecha ISO actual: {today}\n"
        f"- Zona horaria: {timezone_name}\n"
        "- Si el estudiante pregunta qué día es hoy, responde usando estos datos, no tu conocimiento interno.\n"
        "- Para expresiones relativas como hoy, mañana, esta semana o próximos días, usa esta fecha local."
        f"{pending_section}"
    )


def build_agent_context(state: AgentState) -> str:
    """Deprecated: retorna el contexto completo como string único (usado solo en tests legacy)."""
    return _STATIC_INSTRUCTIONS + "\n\n" + build_dynamic_context(state)


def current_datetime(timezone_name: str = "America/Bogota") -> datetime:
    """Retorna el momento actual en la zona horaria operativa del agente."""

    try:
        zone = ZoneInfo(str(timezone_name or "America/Bogota"))
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("America/Bogota")
    return datetime.now(zone)


def format_current_datetime_for_student(value: datetime) -> str:
    """Formato explícito para evitar ambigüedad de día/mes en el LLM."""

    day_label = _DAYS_ES.get(value.strftime("%A").lower(), value.strftime("%A"))
    month_label = _MONTHS_ES.get(value.month, str(value.month))
    return (
        f"{day_label} {value.day} de {month_label} de {value.year}, "
        f"{value.strftime('%H:%M')}"
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
    from services.planning.academic_activity_service import (
        active_academic_activities,
        sort_academic_activities,
    )

    active = active_academic_activities(list(activities)) if activities else []
    pending = sort_academic_activities([a for a in active if getattr(a, "status", "") == "pending"])
    if not pending:
        return "  Sin actividades pendientes."
    lines = []
    for a in pending[:20]:
        due = getattr(a, "due_date", None) or "sin fecha"
        star = " ⭐" if getattr(a, "priority_level", None) == "alta" else ""
        lines.append(
            f"  - [{a.activity_type}] {a.subject_name}: {a.activity_title}"
            f" — vence {due}{star}"
        )
    extra = len(pending) - 20
    if extra > 0:
        lines.append(f"  ... y {extra} actividad(es) más")
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
    "_STATIC_INSTRUCTIONS",
    "_extract_pending_question",
    "build_dynamic_context",
    "build_agent_context",
    "current_datetime",
    "format_current_datetime_for_student",
    "format_schedule_blocks",
    "format_subjects",
    "format_activities",
    "format_study_plan",
]
