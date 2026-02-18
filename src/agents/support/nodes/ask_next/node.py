from typing import Optional

from langchain_core.messages import AIMessage

from agents.support.nodes.ask_next.prompt import INTRO_PROMPT, QUESTIONS, SUMMARY_TEMPLATE
from agents.support.state import StudentState


def next_question(state: StudentState) -> Optional[str]:
    if not state.full_name:
        return QUESTIONS["full_name"]
    if not state.institutional_email:
        return QUESTIONS["institutional_email"]
    if not state.program:
        return QUESTIONS["program"]
    if not state.semester:
        return QUESTIONS["semester"]
    if state.gpa is None:
        return QUESTIONS["gpa"]
    if state.age is None:
        return QUESTIONS["age"]
    if not state.strengths_topics:
        return QUESTIONS["strengths_topics"]
    if not state.difficulty_topics:
        return QUESTIONS["difficulty_topics"]
    return None


def ask_next(state: StudentState) -> dict:
    question = next_question(state)
    if not question:
        summary = SUMMARY_TEMPLATE.format(
            full_name=state.full_name,
            institutional_email=state.institutional_email,
            program=state.program,
            semester=state.semester,
            gpa=state.gpa,
            age=state.age,
            strengths_topics=state.strengths_topics,
            difficulty_topics=state.difficulty_topics,
        )
        if not state.intro_sent:
            return {
                "messages": [AIMessage(content=INTRO_PROMPT), AIMessage(content=summary)],
                "intro_sent": True,
            }
        return {"messages": [AIMessage(content=summary)], "intro_sent": True}
    if not state.intro_sent:
        return {
            "messages": [AIMessage(content=INTRO_PROMPT), AIMessage(content=question)],
            "intro_sent": True,
        }
    return {"messages": [AIMessage(content=question)]}
