from typing import Literal

from pydantic import BaseModel


class ResearchSource(BaseModel):
    source_type: Literal["codebase", "docs", "web", "mcp"]
    reference: str
    snippet: str
    relevance: float


class ResearchFindings(BaseModel):
    summary: str
    sources: list[ResearchSource] = []
    code_references: list[str] = []
    confidence: float
    open_questions: list[str] = []
