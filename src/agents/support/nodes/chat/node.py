from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import AzureChatOpenAI

from agents.support import config
from agents.support.nodes.chat.prompt import build_system_prompt
from agents.support.state import StudentState
from agents.support.utils import coerce_text


def _get_chat_model():
    if not config.DEFAULT_DEPLOYMENT:
        raise ValueError("Missing AZURE_OPENAI_DEPLOYMENT_NAME.")
    if not config.DEFAULT_AZURE_ENDPOINT:
        raise ValueError("Missing AZURE_OPENAI_ENDPOINT.")
    if not config.DEFAULT_AZURE_API_KEY:
        raise ValueError("Missing AZURE_OPENAI_API_KEY.")
    if not config.DEFAULT_API_VERSION:
        raise ValueError("Missing OPENAI_API_VERSION.")
    return AzureChatOpenAI(
        azure_deployment=config.DEFAULT_DEPLOYMENT,
        api_key=config.DEFAULT_AZURE_API_KEY,
        azure_endpoint=config.DEFAULT_AZURE_ENDPOINT,
        api_version=config.DEFAULT_API_VERSION,
        temperature=0.6,
    )


def chat_with_student(state: StudentState) -> dict:
    if not state.messages or not isinstance(state.messages[-1], HumanMessage):
        return {}
    user_text = coerce_text(state.messages[-1].content)
    llm = _get_chat_model()
    system_prompt = build_system_prompt(state)
    response = llm.invoke(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}]
    )
    return {"messages": [AIMessage(content=response.content)]}
