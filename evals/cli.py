"""CLI entrypoint for the eval suite: `uv run python -m evals.cli <subcommand>`.
Mirrors `scripts/verify_langfuse_metadata.py`'s fail-fast-on-missing-credentials
style; see `docs/agent/evals.md` for the full data flow this drives.

Usage:
    uv run python -m evals.cli fetch-cache --all
    uv run python -m evals.cli fetch-cache --case-id triage-bot-test-6-sqrt-feature-request
    uv run python -m evals.cli run e2e --all
    uv run python -m evals.cli run all --all --no-judge
    uv run python -m evals.cli run drafter --case-id triage-bot-test-3-factorial-zero --json
"""

import argparse
import asyncio
from datetime import UTC, datetime

from config.settings import Settings, get_settings
from evals.cache_store import TraceCache
from evals.golden.cases import GOLDEN_CASES
from evals.graders.drafter_grader import grade_drafter
from evals.graders.e2e_grader import grade_e2e
from evals.graders.researcher_grader import grade_researcher
from evals.judges.drafter_judge import (
    run_drafter_efficiency_judge,
    run_drafter_groundedness_judge,
    run_drafter_tone_judge,
)
from evals.judges.e2e_judge import run_e2e_judge
from evals.judges.researcher_judge import (
    run_researcher_efficiency_judge,
    run_researcher_groundedness_judge,
)
from evals.langfuse_fetch.client import ensure_configured, resolve_trace_id
from evals.langfuse_fetch.raw_fetch import fetch_all_observations
from evals.langfuse_fetch.reconstruct import build_run, build_trajectory
from evals.report import build_report, make_case_result, print_report, report_to_json
from evals.schemas import CachedTraceData, EvalCaseResult, GoldenCase, JudgeVerdict
from graph.nodes.node_names import NodeName


def _select_cases(case_id: str | None) -> list[GoldenCase]:
    if case_id is None:
        return GOLDEN_CASES
    matches = [case for case in GOLDEN_CASES if case.case_id == case_id]
    if not matches:
        raise ValueError(f"no golden case with case_id={case_id!r}")
    return matches


def _fetch_cached_data(cache: TraceCache, case: GoldenCase) -> CachedTraceData:
    trace_id = resolve_trace_id(case)

    def fetch() -> CachedTraceData:
        return CachedTraceData(
            trace_id=trace_id,
            fetched_at=datetime.now(UTC),
            raw_observations=fetch_all_observations(trace_id),
        )

    return cache.get_or_fetch(trace_id, fetch)


async def _run_e2e_case(
    case: GoldenCase, cache: TraceCache, *, settings: Settings, with_judge: bool
) -> EvalCaseResult:
    data = _fetch_cached_data(cache, case)
    run = build_run(data.raw_observations)
    hand_labeled = grade_e2e(case, run)
    llm_judged = [await run_e2e_judge(case.case_id, run, settings=settings)] if with_judge else []
    return make_case_result(case.case_id, "e2e", hand_labeled, llm_judged)


async def _run_researcher_case(
    case: GoldenCase, cache: TraceCache, *, settings: Settings, with_judge: bool
) -> EvalCaseResult:
    data = _fetch_cached_data(cache, case)
    trajectory = build_trajectory(data.raw_observations, node_name=NodeName.RESEARCHER)
    hand_labeled = grade_researcher(case, trajectory)
    llm_judged: list[JudgeVerdict] = []
    if with_judge:
        llm_judged.append(
            await run_researcher_efficiency_judge(case.case_id, trajectory, settings=settings)
        )
        run = build_run(data.raw_observations)
        if run.research_findings is not None:
            llm_judged.append(
                await run_researcher_groundedness_judge(
                    case.case_id, run.research_findings, trajectory, settings=settings
                )
            )
    return make_case_result(case.case_id, "researcher", hand_labeled, llm_judged)


async def _run_drafter_case(
    case: GoldenCase, cache: TraceCache, *, settings: Settings, with_judge: bool
) -> EvalCaseResult:
    data = _fetch_cached_data(cache, case)
    run = build_run(data.raw_observations)
    hand_labeled = grade_drafter(case, run)
    llm_judged: list[JudgeVerdict] = []
    if with_judge:
        trajectory = build_trajectory(data.raw_observations, node_name=NodeName.DRAFTER)
        llm_judged.append(
            await run_drafter_efficiency_judge(case.case_id, trajectory, settings=settings)
        )
        if run.draft is not None:
            llm_judged.append(
                await run_drafter_groundedness_judge(
                    case.case_id, run.draft, run.research_findings, settings=settings
                )
            )
            llm_judged.append(
                await run_drafter_tone_judge(case.case_id, run.draft, settings=settings)
            )
    return make_case_result(case.case_id, "drafter", hand_labeled, llm_judged)


async def _run_selected(
    eval_type: str,
    cases: list[GoldenCase],
    cache: TraceCache,
    *,
    settings: Settings,
    with_judge: bool,
) -> list[EvalCaseResult]:
    """One shared `TraceCache` across every case/eval-type combination in
    this call, so a case used by more than one eval type triggers exactly
    one Langfuse fetch (a cache hit on the second+ use)."""
    results: list[EvalCaseResult] = []
    for case in cases:
        if eval_type in ("e2e", "all"):
            results.append(
                await _run_e2e_case(case, cache, settings=settings, with_judge=with_judge)
            )
        if eval_type in ("researcher", "all"):
            results.append(
                await _run_researcher_case(case, cache, settings=settings, with_judge=with_judge)
            )
        if eval_type in ("drafter", "all"):
            results.append(
                await _run_drafter_case(case, cache, settings=settings, with_judge=with_judge)
            )
    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch-cache", help="Populate the local trace cache (evals/.cache/)."
    )
    fetch_group = fetch_parser.add_mutually_exclusive_group(required=True)
    fetch_group.add_argument("--case-id", help="A single golden case's case_id.")
    fetch_group.add_argument("--all", action="store_true", help="Every golden case.")

    run_parser = subparsers.add_parser("run", help="Run an eval type against golden cases.")
    run_parser.add_argument("eval_type", choices=["e2e", "researcher", "drafter", "all"])
    run_group = run_parser.add_mutually_exclusive_group(required=True)
    run_group.add_argument("--case-id", help="A single golden case's case_id.")
    run_group.add_argument("--all", action="store_true", help="Every golden case.")
    run_parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Hand-labeled checks only -- skip LLM-judge calls (no LLM spend).",
    )
    run_parser.add_argument("--json", action="store_true", help="Print the report as JSON.")

    return parser


def main() -> None:
    args = _build_parser().parse_args()
    settings = ensure_configured(get_settings())
    cache = TraceCache()
    cases = _select_cases(None if args.all else args.case_id)

    if args.command == "fetch-cache":
        for case in cases:
            _fetch_cached_data(cache, case)
            print(f"cached: {case.case_id}")
        return

    eval_types_run = (
        ["e2e", "researcher", "drafter"] if args.eval_type == "all" else [args.eval_type]
    )
    case_results = asyncio.run(
        _run_selected(args.eval_type, cases, cache, settings=settings, with_judge=not args.no_judge)
    )
    report = build_report(case_results, eval_types_run=eval_types_run)
    if args.json:
        print(report_to_json(report))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
