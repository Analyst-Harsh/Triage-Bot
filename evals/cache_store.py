import json
import os
from collections.abc import Callable
from pathlib import Path

import structlog
from pydantic import ValidationError

from evals.schemas import CachedTraceData

log = structlog.get_logger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).parent / ".cache"


class TraceCache:
    """Read-through cache in front of a Langfuse trace fetch -- one JSON
    file per trace_id under `cache_dir`. Only `CachedTraceData.raw_observations`
    is ever stored; `evals.langfuse_fetch.reconstruct`'s derived views are
    recomputed fresh from that on every call, never persisted (see
    `docs/agent/evals.md`). This exists so eval runs don't depend on
    Langfuse still holding a historical trace -- free-tier retention is
    ~2 months."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
        self._cache_dir = cache_dir

    def _path(self, trace_id: str) -> Path:
        return self._cache_dir / f"{trace_id}.json"

    def get(self, trace_id: str) -> CachedTraceData | None:
        """A hit requires the file to exist and parse; a missing file or a
        corrupt/invalid one are both treated as a miss (narrow except
        clauses, not a bare `except Exception` -- same convention as
        `EpisodicMemoryGateway`), logged at `warning` level, never raised."""
        path = self._path(trace_id)
        if not path.exists():
            return None
        try:
            return CachedTraceData.model_validate_json(path.read_text())
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning(
                "trace_cache_corrupt_entry", trace_id=trace_id, path=str(path), error=str(exc)
            )
            return None

    def put(self, trace_id: str, data: CachedTraceData) -> None:
        """Atomic write (`.tmp` + `os.replace`) so a crash mid-write can't
        leave an unparseable cache file for a later `get()` to trip over."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(trace_id)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(data.model_dump_json())
        os.replace(tmp_path, path)

    def get_or_fetch(self, trace_id: str, fetch: Callable[[], CachedTraceData]) -> CachedTraceData:
        """The one entry point every grader/CLI path uses. `fetch` is a
        thunk so a cache hit costs zero Langfuse API calls."""
        cached = self.get(trace_id)
        if cached is not None:
            return cached
        data = fetch()
        self.put(trace_id, data)
        return data
