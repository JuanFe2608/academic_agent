from typing import Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class Course(BaseModel):
    course_name: Optional[str] = None
    course_code: Optional[str] = None
    teacher_name: Optional[str] = None
    priority_level: Optional[str] = None
    difficulty_self_report: Optional[int] = None


class SleepSchedule(BaseModel):
    wake_time: Optional[str] = None
    sleep_time: Optional[str] = None


class Commute(BaseModel):
    one_way_minutes: Optional[int] = None
    commute_days: list[str] = Field(default_factory=list)


class StudyPreferences(BaseModel):
    best_study_time: Optional[str] = None
    focus_block_minutes: Optional[int] = None
    break_minutes: Optional[int] = None
    weekly_study_goal_hours: Optional[float] = None


class TimeBlock(BaseModel):
    block_type: Optional[str] = None
    title: Optional[str] = None
    day_of_week: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    recurrence: Optional[str] = None
    source: Optional[str] = None


class NotificationPreferences(BaseModel):
    reminders_enabled: Optional[bool] = None
    reminder_channel: Optional[str] = None
    reminder_minutes_before: Optional[int] = None


class StudentState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    full_name: Optional[str] = None
    preferred_name: Optional[str] = None
    institutional_email: Optional[str] = None
    program: Optional[str] = None
    gpa: Optional[float] = None
    age: Optional[int] = None
    student_code: Optional[str] = None
    current_courses: list[Course] = Field(default_factory=list)
    most_challenging_course: Optional[str] = None
    sleep_schedule: Optional[SleepSchedule] = None
    commute: Optional[Commute] = None
    study_preferences: Optional[StudyPreferences] = None
    time_blocks: list[TimeBlock] = Field(default_factory=list)
    employment_status: Optional[bool] = None
    employment_type: Optional[str] = None
    extracurriculars: list[str] = Field(default_factory=list)
    calendar_sync_consent: Optional[bool] = None
    calendar_event_naming_style: Optional[str] = None
    notification_preferences: Optional[NotificationPreferences] = None
    onboarding_completed: bool = False
    onboarding_completed_at: Optional[str] = None
    intro_sent: bool = False
