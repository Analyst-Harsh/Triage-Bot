from typing import Literal

from pydantic import BaseModel


class LLMEndpointConfig(BaseModel):
    provider: Literal["anthropic", "openai"]
    model: str
    temperature: float = 0.0


class NodeLLMConfig(BaseModel):
    primary: LLMEndpointConfig
    fallback: LLMEndpointConfig
