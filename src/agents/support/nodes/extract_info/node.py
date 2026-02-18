import re
from typing import Optional

from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

from agents.support import config
from agents.support.nodes.ask_next.node import next_question as _next_question
from agents.support.nodes.ask_next.prompt import (
    STEP_1_QUESTIONS,
    STEP_2_QUESTIONS,
    STEP_3_QUESTIONS,
    STEP_4_QUESTIONS,
    STEP_5_QUESTIONS,
)
from agents.support.nodes.extract_info.prompt import EXTRACT_INFO_PROMPT
from agents.support.state import (
    Commute,
    Course,
    NotificationPreferences,
    SleepSchedule,
    StudentState,
    StudyPreferences,
    TimeBlock,
)
from agents.support.utils import coerce_text


class StudentInfo(BaseModel):
    full_name: Optional[str] = Field(default=None, description="Nombre completo con apellidos.")
    preferred_name: Optional[str] = Field(
        default=None, description="Nombre como le gusta que lo llamen."
    )
    institutional_email: Optional[str] = Field(
        default=None, description="Correo institucional @ucatolica.edu.co"
    )
    program: Optional[str] = Field(
        default=None, description="Programa academico del estudiante."
    )
    gpa: Optional[float] = Field(
        default=None, description="Promedio acumulado en escala 0 a 100."
    )
    age: Optional[int] = Field(default=None, description="Edad del estudiante.")
    student_code: Optional[str] = Field(default=None, description="Codigo del estudiante.")
    current_courses: Optional[list[Course]] = Field(default=None)
    most_challenging_course: Optional[str] = Field(default=None)
    sleep_schedule: Optional[SleepSchedule] = Field(default=None)
    commute: Optional[Commute] = Field(default=None)
    study_preferences: Optional[StudyPreferences] = Field(default=None)
    time_blocks: Optional[list[TimeBlock]] = Field(default=None)
    employment_status: Optional[bool] = Field(default=None)
    employment_type: Optional[str] = Field(default=None)
    extracurriculars: Optional[list[str]] = Field(default=None)
    calendar_sync_consent: Optional[bool] = Field(default=None)
    calendar_event_naming_style: Optional[str] = Field(default=None)
    notification_preferences: Optional[NotificationPreferences] = Field(default=None)


_DAY_MAP = {
    "lunes": "mon",
    "lun": "mon",
    "monday": "mon",
    "martes": "tue",
    "mar": "tue",
    "tuesday": "tue",
    "miercoles": "wed",
    "mier": "wed",
    "wednesday": "wed",
    "jueves": "thu",
    "jue": "thu",
    "thursday": "thu",
    "viernes": "fri",
    "vie": "fri",
    "friday": "fri",
    "sabado": "sat",
    "sab": "sat",
    "saturday": "sat",
    "domingo": "sun",
    "dom": "sun",
    "sunday": "sun",
}

_PRIORITY_MAP = {
    "alta": "alta",
    "high": "alta",
    "media": "media",
    "medium": "media",
    "baja": "baja",
    "low": "baja",
}

_BEST_STUDY_TIME = {
    "manana": "manana",
    "mañana": "manana",
    "tarde": "tarde",
    "noche": "noche",
    "variable": "variable",
}

_BLOCK_TYPE_MAP = {
    "class": "class",
    "clase": "class",
    "clases": "class",
    "work": "work",
    "trabajo": "work",
    "extracurricular": "extracurricular",
    "extracurriculars": "extracurricular",
    "personal_fixed": "personal_fixed",
    "personal": "personal_fixed",
}

_SOURCE_MAP = {
    "user_text": "user_text",
    "imagen": "image",
    "image": "image",
    "calendar_import": "calendar_import",
}

_QUESTION_FIELD_MAP = {}
for _step_questions in (
    STEP_1_QUESTIONS,
    STEP_2_QUESTIONS,
    STEP_3_QUESTIONS,
    STEP_4_QUESTIONS,
    STEP_5_QUESTIONS,
):
    _QUESTION_FIELD_MAP.update(
        {question: field_key for field_key, question in _step_questions.items()}
    )


def _clean_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = " ".join(str(value).strip().split())
    return cleaned or None


def _expected_field(state: StudentState) -> Optional[str]:
    next_item = _next_question(state)
    if not next_item:
        return None
    _, question, _ = next_item
    return _QUESTION_FIELD_MAP.get(question)


def _split_items(user_text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\n,;/]+", user_text) if item.strip()]


def _fallback_courses(user_text: str) -> Optional[list[Course]]:
    items = _split_items(user_text)
    if not items:
        return None
    courses = []
    for item in items:
        cleaned = _clean_text(item)
        if cleaned:
            courses.append(Course(course_name=cleaned))
    return courses or None


def _fallback_extracurriculars(user_text: str) -> Optional[list[str]]:
    items = _split_items(user_text)
    cleaned = [value for value in (_clean_text(item) for item in items) if value]
    return cleaned or None


def _clean_full_name(value: Optional[str]) -> Optional[str]:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    return cleaned if len(cleaned.split()) >= 2 else None


def _clean_email(value: Optional[str]) -> Optional[str]:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    lowered = cleaned.lower()
    return lowered if config.EMAIL_PATTERN.match(lowered) else None


def _clean_program(value: Optional[str]) -> Optional[str]:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    lower = cleaned.lower()
    if "sistemas" in lower and "comput" in lower:
        return "Ingenieria de Sistemas y Computacion"
    if "sistemas" in lower:
        return "Ingenieria de Sistemas"
    return cleaned


def _clean_gpa(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value if 0 <= value <= 100 else None


def _clean_age(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return value if 10 <= value <= 100 else None


def _clean_student_code(value: Optional[str]) -> Optional[str]:
    cleaned = _clean_text(value)
    return cleaned


def _fallback_preferred_name(user_text: str, state: StudentState) -> Optional[str]:
    if not state.full_name or state.preferred_name:
        return None
    cleaned = _clean_text(user_text)
    if not cleaned:
        return None
    if "@" in cleaned or re.search(r"\d", cleaned):
        return None
    if len(cleaned.split()) > 3:
        return None
    if _is_negative(cleaned):
        return None
    return cleaned


def _extract_number(text: str) -> Optional[float]:
    match = re.search(r"(-?\d+(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _parse_bool(text: Optional[str]) -> Optional[bool]:
    if not text:
        return None
    lowered = text.strip().lower()
    if lowered in {"si", "sí", "s", "yes", "y"}:
        return True
    if lowered in {"no", "n"}:
        return False
    return None


def _parse_reminder_channel(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    lowered = text.lower()
    if "whatsapp" in lowered:
        return "whatsapp"
    if "email" in lowered or "correo" in lowered:
        return "email"
    if "both" in lowered or "ambos" in lowered:
        return "both"
    return None


def _is_negative(text: Optional[str]) -> bool:
    if not text:
        return False
    lowered = text.strip().lower()
    return lowered in {"no", "ninguna", "ninguno", "ningun", "n/a", "na"}


def _clean_priority_level(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _PRIORITY_MAP:
            return _PRIORITY_MAP[lowered]
        if lowered.isdigit():
            numeric = int(lowered)
        else:
            numeric = None
    else:
        numeric = int(value)
    if numeric == 1:
        return "alta"
    if numeric == 2:
        return "media"
    if numeric == 3:
        return "baja"
    return None


def _clean_difficulty(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return numeric if 1 <= numeric <= 5 else None


def _clean_best_study_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.strip().lower()
    return _BEST_STUDY_TIME.get(lowered)


def _clean_focus_block(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric in {25, 45, 60, 90} else None


def _clean_break_minutes(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None


def _clean_weekly_goal(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None


def _clean_day(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.strip().lower()
    return _DAY_MAP.get(lowered, lowered if lowered in _DAY_MAP.values() else None)


def _clean_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", value.strip().lower())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = match.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _clean_block_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.strip().lower()
    return _BLOCK_TYPE_MAP.get(lowered, lowered)


def _clean_source(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.strip().lower()
    return _SOURCE_MAP.get(lowered, lowered)


def _clean_calendar_style(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.strip().lower()
    if "emoji" in lowered:
        return "emoji_prefix"
    if "plain" in lowered or "simple" in lowered:
        return "plain"
    return lowered


def _merge_model(existing: Optional[BaseModel], incoming: Optional[BaseModel]) -> Optional[BaseModel]:
    if incoming is None:
        return existing
    if existing is None:
        return incoming
    for field_name in incoming.model_fields:
        incoming_value = getattr(incoming, field_name)
        existing_value = getattr(existing, field_name)
        if existing_value in (None, "", [], {}):
            if incoming_value not in (None, "", [], {}):
                setattr(existing, field_name, incoming_value)
    return existing


def _merge_courses(existing: list[Course], incoming: Optional[list[Course]]) -> list[Course]:
    if not incoming:
        return existing
    merged = list(existing)
    seen_keys = {
        (course.course_name or "").strip().lower()
        for course in merged
        if course.course_name
    }
    for course in incoming:
        name = (course.course_name or "").strip().lower()
        if name and name in seen_keys:
            continue
        merged.append(course)
        if name:
            seen_keys.add(name)
    return merged


def _merge_time_blocks(existing: list[TimeBlock], incoming: Optional[list[TimeBlock]]) -> list[TimeBlock]:
    if not incoming:
        return existing
    merged = list(existing)
    seen_keys = {
        (
            (block.title or "").strip().lower(),
            block.day_of_week,
            block.start_time,
            block.end_time,
        )
        for block in merged
    }
    for block in incoming:
        key = (
            (block.title or "").strip().lower(),
            block.day_of_week,
            block.start_time,
            block.end_time,
        )
        if key in seen_keys:
            continue
        merged.append(block)
        seen_keys.add(key)
    return merged


def _get_extractor():
    if not config.DEFAULT_DEPLOYMENT:
        raise ValueError("Missing AZURE_OPENAI_DEPLOYMENT_NAME.")
    if not config.DEFAULT_AZURE_ENDPOINT:
        raise ValueError("Missing AZURE_OPENAI_ENDPOINT.")
    if not config.DEFAULT_AZURE_API_KEY:
        raise ValueError("Missing AZURE_OPENAI_API_KEY.")
    if not config.DEFAULT_API_VERSION:
        raise ValueError("Missing OPENAI_API_VERSION.")
    llm = AzureChatOpenAI(
        azure_deployment=config.DEFAULT_DEPLOYMENT,
        api_key=config.DEFAULT_AZURE_API_KEY,
        azure_endpoint=config.DEFAULT_AZURE_ENDPOINT,
        api_version=config.DEFAULT_API_VERSION,
        temperature=0,
    )
    return llm.with_structured_output(StudentInfo)


def extract_info(state: StudentState) -> dict:
    if not state.messages or not isinstance(state.messages[-1], HumanMessage):
        return {}

    user_text = coerce_text(state.messages[-1].content)
    expected_field = _expected_field(state)
    extractor = _get_extractor()

    extracted: StudentInfo = extractor.invoke(
        [{"role": "system", "content": EXTRACT_INFO_PROMPT}, {"role": "user", "content": user_text}]
    )

    fallback_full_name = _clean_full_name(user_text) if expected_field == "full_name" else None
    fallback_preferred_name: Optional[str] = None
    if extracted.preferred_name is None and expected_field == "preferred_name":
        fallback_preferred_name = _fallback_preferred_name(user_text, state)
    fallback_institutional_email = (
        _clean_email(user_text) if expected_field == "institutional_email" else None
    )
    fallback_program = _clean_program(user_text) if expected_field == "program" else None
    fallback_student_code = (
        _clean_student_code(user_text) if expected_field == "student_code" else None
    )
    fallback_current_courses = (
        _fallback_courses(user_text)
        if expected_field == "current_courses" and not _is_negative(user_text)
        else None
    )
    fallback_most_challenging_course = (
        _clean_text(user_text)
        if expected_field == "most_challenging_course" and not _is_negative(user_text)
        else None
    )
    fallback_wake_time = _clean_time(user_text) if expected_field == "wake_time" else None
    fallback_sleep_time = _clean_time(user_text) if expected_field == "sleep_time" else None
    fallback_best_study_time = (
        _clean_best_study_time(user_text) if expected_field == "best_study_time" else None
    )
    fallback_employment_type = (
        _clean_text(user_text)
        if expected_field == "employment_type" and not _is_negative(user_text)
        else None
    )
    fallback_extracurriculars: Optional[list[str]] = None
    if expected_field == "extracurriculars":
        if _is_negative(user_text):
            fallback_extracurriculars = ["ninguna"]
        else:
            fallback_extracurriculars = _fallback_extracurriculars(user_text)
    fallback_calendar_sync_consent = (
        _parse_bool(user_text) if expected_field == "calendar_sync_consent" else None
    )
    fallback_event_style = (
        _clean_calendar_style(user_text)
        if expected_field == "calendar_event_naming_style"
        else None
    )
    fallback_reminders_enabled = (
        _parse_bool(user_text) if expected_field == "reminders_enabled" else None
    )
    fallback_reminder_channel = (
        _parse_reminder_channel(user_text) if expected_field == "reminder_channel" else None
    )

    fallback_number = _extract_number(user_text)
    fallback_gpa: Optional[float] = None
    fallback_age: Optional[int] = None
    fallback_one_way: Optional[int] = None
    fallback_focus_block: Optional[int] = None
    fallback_break_minutes: Optional[int] = None
    fallback_weekly_goal: Optional[float] = None
    if fallback_number is not None:
        if state.gpa is None and extracted.gpa is None and 0 <= fallback_number <= 100:
            fallback_gpa = fallback_number
        if state.gpa is not None and state.age is None and extracted.age is None:
            if fallback_number.is_integer():
                candidate = int(fallback_number)
                if 10 <= candidate <= 100:
                    fallback_age = candidate
        if state.commute is None or state.commute.one_way_minutes is None:
            if fallback_number.is_integer():
                candidate = int(fallback_number)
                if candidate > 0:
                    fallback_one_way = candidate
        if state.study_preferences is None or state.study_preferences.focus_block_minutes is None:
            if fallback_number.is_integer():
                candidate = int(fallback_number)
                if candidate in {25, 45, 60, 90}:
                    fallback_focus_block = candidate
        if state.study_preferences is None or state.study_preferences.break_minutes is None:
            if fallback_number.is_integer():
                candidate = int(fallback_number)
                if candidate in {5, 10, 15, 20, 30}:
                    fallback_break_minutes = candidate
        if state.study_preferences is None or state.study_preferences.weekly_study_goal_hours is None:
            fallback_weekly_goal = fallback_number

    cleaned_courses: Optional[list[Course]] = None
    if extracted.current_courses:
        cleaned_courses = []
        for course in extracted.current_courses:
            cleaned_courses.append(
                Course(
                    course_name=_clean_text(course.course_name),
                    course_code=_clean_text(course.course_code),
                    teacher_name=_clean_text(course.teacher_name),
                    priority_level=_clean_priority_level(course.priority_level),
                    difficulty_self_report=_clean_difficulty(course.difficulty_self_report),
                )
            )
    if not cleaned_courses and fallback_current_courses:
        cleaned_courses = fallback_current_courses

    cleaned_blocks: Optional[list[TimeBlock]] = None
    if extracted.time_blocks:
        cleaned_blocks = []
        for block in extracted.time_blocks:
            cleaned_blocks.append(
                TimeBlock(
                    block_type=_clean_block_type(block.block_type),
                    title=_clean_text(block.title),
                    day_of_week=_clean_day(block.day_of_week),
                    start_time=_clean_time(block.start_time),
                    end_time=_clean_time(block.end_time),
                    location=_clean_text(block.location),
                    recurrence=_clean_text(block.recurrence) or "weekly",
                    source=_clean_source(block.source) or "user_text",
                )
            )

    cleaned_sleep: Optional[SleepSchedule] = None
    if extracted.sleep_schedule:
        cleaned_sleep = SleepSchedule(
            wake_time=_clean_time(extracted.sleep_schedule.wake_time) or fallback_wake_time,
            sleep_time=_clean_time(extracted.sleep_schedule.sleep_time) or fallback_sleep_time,
        )
    elif fallback_wake_time or fallback_sleep_time:
        cleaned_sleep = SleepSchedule(
            wake_time=fallback_wake_time,
            sleep_time=fallback_sleep_time,
        )

    cleaned_commute: Optional[Commute] = None
    if extracted.commute:
        cleaned_commute = Commute(
            one_way_minutes=(
                extracted.commute.one_way_minutes
                if extracted.commute.one_way_minutes is not None
                else fallback_one_way
            ),
            commute_days=[
                day for day in (_clean_day(item) for item in extracted.commute.commute_days) if day
            ],
        )
    elif fallback_one_way is not None:
        cleaned_commute = Commute(one_way_minutes=fallback_one_way)

    cleaned_prefs: Optional[StudyPreferences] = None
    if extracted.study_preferences:
        cleaned_prefs = StudyPreferences(
            best_study_time=_clean_best_study_time(
                extracted.study_preferences.best_study_time
            )
            or fallback_best_study_time,
            focus_block_minutes=_clean_focus_block(extracted.study_preferences.focus_block_minutes)
            or fallback_focus_block,
            break_minutes=_clean_break_minutes(extracted.study_preferences.break_minutes)
            or fallback_break_minutes,
            weekly_study_goal_hours=_clean_weekly_goal(
                extracted.study_preferences.weekly_study_goal_hours
            )
            or fallback_weekly_goal,
        )
    elif any(
        value is not None
        for value in [
            fallback_best_study_time,
            fallback_focus_block,
            fallback_break_minutes,
            fallback_weekly_goal,
        ]
    ):
        cleaned_prefs = StudyPreferences(
            best_study_time=fallback_best_study_time,
            focus_block_minutes=fallback_focus_block,
            break_minutes=fallback_break_minutes,
            weekly_study_goal_hours=fallback_weekly_goal,
        )

    cleaned_notifications: Optional[NotificationPreferences] = None
    if extracted.notification_preferences:
        reminders_enabled = extracted.notification_preferences.reminders_enabled
        if reminders_enabled is None:
            reminders_enabled = _parse_bool(user_text)
        cleaned_notifications = NotificationPreferences(
            reminders_enabled=reminders_enabled,
            reminder_channel=_clean_text(extracted.notification_preferences.reminder_channel)
            or fallback_reminder_channel,
            reminder_minutes_before=extracted.notification_preferences.reminder_minutes_before,
        )
    else:
        if expected_field in {"reminders_enabled", "reminder_channel"} and state.calendar_event_naming_style:
            reminders_enabled = fallback_reminders_enabled
            reminder_channel = fallback_reminder_channel
            reminder_minutes = None
            if reminder_channel or reminders_enabled is not None:
                reminder_minutes = _extract_number(user_text)
            if reminders_enabled is not None or reminder_channel or reminder_minutes is not None:
                cleaned_notifications = NotificationPreferences(
                    reminders_enabled=reminders_enabled,
                    reminder_channel=reminder_channel,
                    reminder_minutes_before=(
                        int(reminder_minutes)
                        if reminder_minutes and reminder_minutes.is_integer()
                        else None
                    ),
                )
        else:
            lowered_text = user_text.lower()
            mentions_reminders = any(
                keyword in lowered_text
                for keyword in [
                    "recordatorio",
                    "recordatorios",
                    "whatsapp",
                    "email",
                    "correo",
                    "notificacion",
                ]
            )
            if mentions_reminders and state.calendar_event_naming_style:
                reminders_enabled = _parse_bool(user_text)
                reminder_channel = _parse_reminder_channel(user_text)
                reminder_minutes = None
                if reminder_channel or reminders_enabled is not None:
                    reminder_minutes = _extract_number(user_text)
                if reminders_enabled is not None or reminder_channel or reminder_minutes is not None:
                    cleaned_notifications = NotificationPreferences(
                        reminders_enabled=reminders_enabled,
                        reminder_channel=reminder_channel,
                        reminder_minutes_before=(
                            int(reminder_minutes)
                            if reminder_minutes and reminder_minutes.is_integer()
                            else None
                        ),
                    )

    employment_status = extracted.employment_status
    if employment_status is None:
        if expected_field == "employment_status":
            employment_status = _parse_bool(user_text)
        elif state.student_code:
            employment_status = _parse_bool(user_text)

    calendar_sync_consent = extracted.calendar_sync_consent
    if calendar_sync_consent is None:
        if expected_field == "calendar_sync_consent":
            calendar_sync_consent = _parse_bool(user_text)
        elif state.time_blocks:
            calendar_sync_consent = _parse_bool(user_text)

    extracurriculars = extracted.extracurriculars or []
    if not extracurriculars and fallback_extracurriculars:
        extracurriculars = fallback_extracurriculars
    if (
        not extracurriculars
        and state.employment_status is not None
        and not state.extracurriculars
        and _is_negative(user_text)
    ):
        extracurriculars = ["ninguna"]

    return {
        "full_name": _clean_full_name(extracted.full_name) or fallback_full_name or state.full_name,
        "preferred_name": _clean_text(extracted.preferred_name)
        or fallback_preferred_name
        or state.preferred_name,
        "institutional_email": _clean_email(extracted.institutional_email)
        or fallback_institutional_email
        or state.institutional_email,
        "program": _clean_program(extracted.program) or fallback_program or state.program,
        "gpa": _clean_gpa(extracted.gpa) or fallback_gpa or state.gpa,
        "age": _clean_age(extracted.age) or fallback_age or state.age,
        "student_code": _clean_student_code(extracted.student_code)
        or fallback_student_code
        or state.student_code,
        "current_courses": _merge_courses(state.current_courses, cleaned_courses),
        "most_challenging_course": _clean_text(extracted.most_challenging_course)
        or fallback_most_challenging_course
        or state.most_challenging_course,
        "sleep_schedule": _merge_model(state.sleep_schedule, cleaned_sleep),
        "commute": _merge_model(state.commute, cleaned_commute),
        "study_preferences": _merge_model(state.study_preferences, cleaned_prefs),
        "time_blocks": _merge_time_blocks(state.time_blocks, cleaned_blocks),
        "employment_status": employment_status
        if employment_status is not None
        else state.employment_status,
        "employment_type": _clean_text(extracted.employment_type)
        or fallback_employment_type
        or state.employment_type,
        "extracurriculars": (
            [item for item in (_clean_text(value) for value in extracurriculars) if item]
            or state.extracurriculars
        ),
        "calendar_sync_consent": calendar_sync_consent
        if calendar_sync_consent is not None
        else state.calendar_sync_consent,
        "calendar_event_naming_style": _clean_calendar_style(extracted.calendar_event_naming_style)
        or fallback_event_style
        or state.calendar_event_naming_style,
        "notification_preferences": _merge_model(
            state.notification_preferences, cleaned_notifications
        ),
    }
