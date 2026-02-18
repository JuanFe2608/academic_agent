import re
from typing import Optional

from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

from agents.support import config
from agents.support.state import StudentState
from agents.support.utils import coerce_text
from agents.support.nodes.extract_info.prompt import EXTRACT_INFO_PROMPT


class StudentInfo(BaseModel):
    full_name: Optional[str] = Field(default=None, description="Nombre completo con apellidos.")
    institutional_email: Optional[str] = Field(
        default=None, description="Correo institucional @ucatolica.edu.co"
    )
    program: Optional[str] = Field(
        default=None, description="Programa academico del estudiante."
    )
    semester: Optional[int] = Field(
        default=None, description="Semestre actual del estudiante."
    )
    gpa: Optional[float] = Field(
        default=None, description="Promedio acumulado en escala 0 a 100."
    )
    age: Optional[int] = Field(default=None, description="Edad del estudiante.")
    strengths_topics: Optional[str] = Field(
        default=None, description="Temas o areas que se le facilitan."
    )
    difficulty_topics: Optional[str] = Field(
        default=None, description="Temas o areas que se le dificultan."
    )


def _clean_full_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned if len(cleaned.split()) >= 2 else None


def _clean_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip().lower()
    return cleaned if config.EMAIL_PATTERN.match(cleaned) else None


def _clean_program(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = " ".join(value.strip().split())
    if "sistemas" in cleaned.lower() and "comput" in cleaned.lower():
        return "Ingenieria de Sistemas y Computacion"
    return cleaned


def _clean_semester(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return value if 1 <= value <= 10 else None


def _clean_gpa(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value if 0 <= value <= 100 else None


def _clean_age(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return value if 10 <= value <= 100 else None


def _clean_topics(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _extract_number(text: str) -> Optional[float]:
    match = re.search(r"(-?\d+(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


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
    extractor = _get_extractor()

    extracted: StudentInfo = extractor.invoke(
        [{"role": "system", "content": EXTRACT_INFO_PROMPT}, {"role": "user", "content": user_text}]
    )

    fallback_number = _extract_number(user_text)
    fallback_semester: Optional[int] = None
    fallback_gpa: Optional[float] = None
    fallback_age: Optional[int] = None
    fallback_strengths: Optional[str] = None
    fallback_difficulties: Optional[str] = None
    if fallback_number is not None:
        if state.semester is None and extracted.semester is None:
            if fallback_number.is_integer():
                candidate = int(fallback_number)
                if 1 <= candidate <= 10:
                    fallback_semester = candidate
        if (
            fallback_semester is None
            and state.gpa is None
            and extracted.gpa is None
            and 0 <= fallback_number <= 100
        ):
            fallback_gpa = fallback_number
        if (
            fallback_semester is None
            and fallback_gpa is None
            and state.gpa is not None
            and state.semester is not None
            and state.age is None
            and extracted.age is None
            and fallback_number.is_integer()
        ):
            candidate = int(fallback_number)
            if 10 <= candidate <= 100:
                fallback_age = candidate
    if (
        state.full_name
        and state.institutional_email
        and state.program
        and state.semester is not None
        and state.gpa is not None
        and state.age is not None
    ):
        if not state.strengths_topics and not extracted.strengths_topics and user_text:
            fallback_strengths = user_text.strip()
        if (
            state.strengths_topics
            and not state.difficulty_topics
            and not extracted.difficulty_topics
            and user_text
        ):
            fallback_difficulties = user_text.strip()

    return {
        "full_name": _clean_full_name(extracted.full_name) or state.full_name,
        "institutional_email": _clean_email(extracted.institutional_email)
        or state.institutional_email,
        "program": _clean_program(extracted.program) or state.program,
        "semester": _clean_semester(extracted.semester)
        or fallback_semester
        or state.semester,
        "gpa": _clean_gpa(extracted.gpa) or fallback_gpa or state.gpa,
        "age": _clean_age(extracted.age) or fallback_age or state.age,
        "strengths_topics": _clean_topics(extracted.strengths_topics)
        or _clean_topics(fallback_strengths)
        or state.strengths_topics,
        "difficulty_topics": _clean_topics(extracted.difficulty_topics)
        or _clean_topics(fallback_difficulties)
        or state.difficulty_topics,
    }
