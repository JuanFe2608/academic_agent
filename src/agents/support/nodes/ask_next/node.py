from datetime import datetime, timezone
from typing import Optional

from langchain_core.messages import AIMessage

from agents.support.nodes.ask_next.prompt import (
    COURSE_FORMAT_HINT,
    PURPOSE_MESSAGE,
    STEP_1_QUESTIONS,
    STEP_2_QUESTIONS,
    STEP_3_QUESTIONS,
    STEP_4_QUESTIONS,
    STEP_5_QUESTIONS,
    STEP_LABELS,
    SUMMARY_TEMPLATE,
    TIME_BLOCKS_FORMAT_HINT,
    WELCOME_MESSAGE,
)
from agents.support.state import StudentState


def _needs_sleep_schedule(state: StudentState) -> bool:
    return not state.sleep_schedule or not state.sleep_schedule.wake_time or not state.sleep_schedule.sleep_time


def _needs_commute(state: StudentState) -> bool:
    return not state.commute or state.commute.one_way_minutes is None


def _needs_study_preferences(state: StudentState) -> bool:
    return not state.study_preferences or state.study_preferences.best_study_time is None


def _needs_focus_block(state: StudentState) -> bool:
    return not state.study_preferences or state.study_preferences.focus_block_minutes is None


def _needs_notifications(state: StudentState) -> bool:
    return not state.notification_preferences or state.notification_preferences.reminders_enabled is None


def _needs_reminder_channel(state: StudentState) -> bool:
    return (
        state.notification_preferences
        and state.notification_preferences.reminders_enabled
        and not state.notification_preferences.reminder_channel
    )


def _count_blocks(state: StudentState) -> dict:
    counts = {"class": 0, "work": 0, "extracurricular": 0, "personal_fixed": 0, "other": 0}
    for block in state.time_blocks:
        block_type = block.block_type or "other"
        if block_type in counts:
            counts[block_type] += 1
        else:
            counts["other"] += 1
    counts["total"] = sum(counts.values())
    return counts


def _build_messages(step: int, question: str, extra: Optional[str] = None) -> list[AIMessage]:
    messages = [AIMessage(content=STEP_LABELS[step]), AIMessage(content=question)]
    if extra:
        messages.append(AIMessage(content=extra))
    return messages


def next_question(state: StudentState) -> Optional[tuple[int, str, Optional[str]]]:
    if not state.full_name:
        return 1, STEP_1_QUESTIONS["full_name"], None
    if not state.preferred_name:
        return 1, STEP_1_QUESTIONS["preferred_name"], None
    if not state.institutional_email:
        return 1, STEP_1_QUESTIONS["institutional_email"], None
    if not state.program:
        return 1, STEP_1_QUESTIONS["program"], None
    if state.gpa is None:
        return 1, STEP_1_QUESTIONS["gpa"], None
    if state.age is None:
        return 1, STEP_1_QUESTIONS["age"], None
    if not state.student_code:
        return 1, STEP_1_QUESTIONS["student_code"], None

    if not state.current_courses:
        return 2, STEP_2_QUESTIONS["current_courses"], COURSE_FORMAT_HINT
    if not state.most_challenging_course:
        return 2, STEP_2_QUESTIONS["most_challenging_course"], None

    if _needs_sleep_schedule(state):
        if not state.sleep_schedule or not state.sleep_schedule.wake_time:
            return 3, STEP_3_QUESTIONS["wake_time"], None
        return 3, STEP_3_QUESTIONS["sleep_time"], None
    if _needs_commute(state):
        return 3, STEP_3_QUESTIONS["commute_one_way"], None
    if _needs_study_preferences(state):
        return 3, STEP_3_QUESTIONS["best_study_time"], None
    if _needs_focus_block(state):
        return 3, STEP_3_QUESTIONS["focus_block_minutes"], None

    if state.employment_status is None:
        return 4, STEP_4_QUESTIONS["employment_status"], None
    if state.employment_status and not state.employment_type:
        return 4, STEP_4_QUESTIONS["employment_type"], None
    if not state.extracurriculars:
        return 4, STEP_4_QUESTIONS["extracurriculars"], None
    if not state.time_blocks:
        return 4, STEP_4_QUESTIONS["time_blocks"], TIME_BLOCKS_FORMAT_HINT

    if state.calendar_sync_consent is None:
        return 5, STEP_5_QUESTIONS["calendar_sync_consent"], None
    if not state.calendar_event_naming_style:
        return 5, STEP_5_QUESTIONS["calendar_event_naming_style"], None
    if _needs_notifications(state):
        return 5, STEP_5_QUESTIONS["reminders_enabled"], None
    if _needs_reminder_channel(state):
        return 5, STEP_5_QUESTIONS["reminder_channel"], None

    return None


def ask_next(state: StudentState) -> dict:
    next_item = next_question(state)
    if not next_item:
        if not state.onboarding_completed:
            completed_at = datetime.now(timezone.utc).isoformat()
            return {
                "messages": [
                    AIMessage(content="Listo! Tu onboarding quedo completo."),
                    AIMessage(content="Con esto ya puedo encontrarte huecos reales."),
                    AIMessage(content="Quieres que empecemos a planear tu semana?"),
                ],
                "onboarding_completed": True,
                "onboarding_completed_at": completed_at,
            }
        return {"messages": [AIMessage(content="Listo. En que te ayudo ahora?")]}

    step, question, extra = next_item
    messages: list[AIMessage] = []
    if not state.intro_sent:
        messages.extend(
            [AIMessage(content=WELCOME_MESSAGE), AIMessage(content=PURPOSE_MESSAGE)]
        )

    if step == 5 and question == STEP_5_QUESTIONS["calendar_sync_consent"]:
        counts = _count_blocks(state)
        summary = SUMMARY_TEMPLATE.format(
            class_blocks=counts["class"],
            work_blocks=counts["work"],
            extra_blocks=counts["extracurricular"],
            personal_blocks=counts["personal_fixed"] + counts["other"],
            total_blocks=counts["total"],
        )
        messages.append(AIMessage(content=summary))

    messages.extend(_build_messages(step, question, extra))

    response = {"messages": messages}
    if not state.intro_sent:
        response["intro_sent"] = True
    return response
