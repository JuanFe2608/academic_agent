from typing import Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class StudentState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    full_name: Optional[str] = None
    institutional_email: Optional[str] = None
    program: Optional[str] = None
    semester: Optional[int] = None
    gpa: Optional[float] = None
    age: Optional[int] = None
    strengths_topics: Optional[str] = None
    difficulty_topics: Optional[str] = None
    intro_sent: bool = False
