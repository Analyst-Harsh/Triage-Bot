from abc import ABC
from collections.abc import Sequence
from typing import ClassVar

from langchain_core.messages import BaseMessage

from config.settings import get_settings
from graph.nodes.base import TriageNode
from llm.config import NodeLLMConfig
from llm.factory import create_chat_model
from llm.result import LLMResult
from llm.structured import call_structured


class LLMNode(TriageNode, ABC):
    """Shared seam for every LLM-backed node: call a model for structured
    output, with an automatic cross-provider fallback and cost accounting,
    without each concrete node re-deriving it.

    `execute()` stays abstract, inherited from `TriageNode` — this class
    only adds `call_structured()`.
    """

    llm_config: ClassVar[NodeLLMConfig]
    """Primary/fallback model choice for this node. Set on the concrete
    subclass"""

    def __init__(self) -> None:
        """Self-contained: builds its own primary/fallback chat models from
        `self.llm_config` + the global `Settings`, so a concrete node
        constructs with zero args, exactly like every other `TriageNode`
        (e.g. `ResearcherNode()`). Tests that need fake models inject them
        via a test-only subclass overriding `__init__` (see
        `tests/graph/nodes/conftest.py`), not via constructor params here —
        keeping this the one, unambiguous production construction path."""
        settings = get_settings()
        self._primary_model = create_chat_model(self.llm_config.primary, settings)
        self._fallback_model = create_chat_model(self.llm_config.fallback, settings)

    async def call_structured[T](
        self, messages: Sequence[BaseMessage], schema: type[T]
    ) -> LLMResult[T]:
        """Thin delegate onto `llm.structured.call_structured` — see that
        function's docstring for the fallback/cost-accounting behavior."""
        return await call_structured(self._primary_model, self._fallback_model, messages, schema)
