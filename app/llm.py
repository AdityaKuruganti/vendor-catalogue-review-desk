from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import get_settings


class MissingApiKeyError(RuntimeError):
    pass


@lru_cache
def get_llm() -> ChatOpenAI:
    """Lazily build the LLM so the app (and CSV preview) works without a key."""
    s = get_settings()
    if not s.openrouter_api_key:
        raise MissingApiKeyError("OPENROUTER_API_KEY is not set. Add it to your .env file.")
    return ChatOpenAI(
        model=s.llm_model,
        temperature=s.llm_temperature,
        api_key=s.openrouter_api_key,
        base_url=s.llm_base_url,
    )


@lru_cache
def get_llm_for(model: str, temperature: float = 0.0) -> ChatOpenAI:
    """Same provider settings as get_llm(), but with an explicit model/temperature
    (used by the CX copilot to run different models for different steps)."""
    s = get_settings()
    if not s.openrouter_api_key:
        raise MissingApiKeyError("OPENROUTER_API_KEY is not set. Add it to your .env file.")
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=s.openrouter_api_key,
        base_url=s.llm_base_url,
        timeout=30,
    )
