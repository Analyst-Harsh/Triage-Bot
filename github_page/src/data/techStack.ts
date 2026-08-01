export interface TechCategory {
  label: string
  items: string[]
}

export const TECH_STACK: TechCategory[] = [
  { label: 'Agent framework', items: ['LangGraph', 'LangChain'] },
  { label: 'LLM providers', items: ['OpenAI', 'Anthropic'] },
  { label: 'Tooling', items: ['MCP', 'E2B sandbox', 'PyGithub', 'Tavily'] },
  { label: 'API layer', items: ['FastAPI', 'Pydantic v2', 'Uvicorn'] },
  { label: 'Database', items: ['Postgres', 'pgvector', 'SQLAlchemy'] },
  { label: 'Observability', items: ['OpenTelemetry', 'Langfuse', 'structlog'] },
  { label: 'Quality', items: ['pytest', 'pyright', 'ruff', 'uv'] },
  { label: 'Dashboard', items: ['Next.js', 'TypeScript'] },
]
