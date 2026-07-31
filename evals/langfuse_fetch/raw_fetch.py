from observability.langfuse_reader import fetch_observations as fetch_all_observations

__all__ = ["fetch_all_observations"]

# `fetch_all_observations` (the eval harness's original name) now lives in
# `observability/langfuse_reader.py::fetch_observations` -- a second
# consumer (the dashboard API's trace-summary endpoint) needed it outside
# the eval harness, and that consumer wants a lighter `fields` value than
# eval reconstruction does, hence `fields` becoming a parameter there
# (default unchanged: `"core,basic,io,metadata"`, so this re-export's
# behavior is identical to before the move). Re-exported under the original
# name here so `evals/cli.py`'s existing
# `from evals.langfuse_fetch.raw_fetch import fetch_all_observations` and
# `evals/langfuse_fetch/reconstruct.py`'s docstring references keep working
# unmodified.
