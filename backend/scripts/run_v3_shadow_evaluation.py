"""Run the synthetic V3 shadow harness and emit privacy-checked offline reports."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from pydantic_core import to_jsonable_python

from backend.app.modules.decisions.v3_evaluation import (
    V3ApprovedPricingReference,
    build_expert_review_artifact,
    calculate_decision_cost,
    compare_shadow_result,
    evaluate_shadow_results,
    summary_markdown,
    validate_report_privacy,
)
from backend.app.modules.decisions.v3_evaluation_fixtures import (
    FIXED_TIME,
    SYNTHETIC_FIXTURE_VERSION,
    V3SyntheticFixtureBundle,
    build_synthetic_fixture_bundle,
)
from backend.app.modules.decisions.v3_shadow import (
    V3ShadowExecutionResult,
    V3ShadowRunnerPort,
)

HARNESS_VERSION = "v3-shadow-evaluation-harness-v1"
REVIEW_POLICY_VERSION = "v3-expert-review-policy-v1"


def _json(value: object, *, pretty: bool = False) -> str:
    return json.dumps(
        to_jsonable_python(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=None if pretty else (",", ":"),
        indent=2 if pretty else None,
        allow_nan=False,
    )


async def collect_results(
    bundle: V3SyntheticFixtureBundle,
    *,
    repeat_count: int,
    runner: V3ShadowRunnerPort | None,
    allow_provider_calls: bool,
) -> tuple[V3ShadowExecutionResult, ...]:
    if repeat_count <= 0:
        raise ValueError("repeat_count must be positive")
    if allow_provider_calls and runner is None:
        raise ValueError("provider calls require an explicitly injected V3ShadowRunnerPort")
    results: list[V3ShadowExecutionResult] = []
    for _ in range(repeat_count):
        for fixture in bundle.fixtures:
            if not allow_provider_calls:
                results.append(fixture.stored_result)
                continue
            assert runner is not None
            results.append(
                await runner.execute(
                    fixture.request,
                    constraint_envelope=fixture.constraint_envelope,
                    exercise_pool=fixture.exercise_pool,
                    regeneration_context=fixture.regeneration_context,
                )
            )
    return tuple(sorted(results, key=lambda item: (item.scenario_code, item.result_hash)))


def _apply_pricing(
    results: tuple[V3ShadowExecutionResult, ...],
    pricing: V3ApprovedPricingReference | None,
) -> tuple[V3ShadowExecutionResult, ...]:
    if pricing is None:
        return results
    priced: list[V3ShadowExecutionResult] = []
    for result in results:
        cost = calculate_decision_cost(result, pricing)
        if cost is None:
            priced.append(result)
            continue
        usage = result.usage.model_copy(
            update={
                "decision_cost": cost,
                "currency_code": pricing.currency_code,
                "pricing_reference_version": pricing.pricing_schema_version,
            }
        )
        payload = result.model_dump(exclude={"result_hash"})
        payload["usage"] = usage
        priced.append(V3ShadowExecutionResult.create(**payload))
    return tuple(priced)


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8", newline="\n")


def write_reports(
    output_directory: Path,
    *,
    bundle: V3SyntheticFixtureBundle,
    results: tuple[V3ShadowExecutionResult, ...],
    repeat_count: int,
    provider_calls_allowed: bool,
) -> tuple[Path, ...]:
    output_directory.mkdir(parents=True, exist_ok=True)
    summary = evaluate_shadow_results(results)
    fixtures_by_code = {item.case.scenario_code: item for item in bundle.fixtures}
    comparisons = tuple(
        compare_shadow_result(fixtures_by_code[item.scenario_code].case.baseline_plan, item)
        for item in results
    )
    reviews = tuple(
        build_expert_review_artifact(
            comparison,
            result,
            review_policy_version=REVIEW_POLICY_VERSION,
        )
        for comparison, result in zip(comparisons, results, strict=True)
    )
    for value in (*results, summary, *reviews):
        validate_report_privacy(value)

    result_path = output_directory / "results.jsonl"
    summary_path = output_directory / "summary.json"
    markdown_path = output_directory / "summary.md"
    review_path = output_directory / "expert_review_template.jsonl"
    manifest_path = output_directory / "manifest.json"
    _write_text(result_path, "".join(f"{_json(item)}\n" for item in results))
    _write_text(summary_path, f"{_json(summary, pretty=True)}\n")
    _write_text(markdown_path, summary_markdown(summary))
    _write_text(review_path, "".join(f"{_json(item)}\n" for item in reviews))

    report_paths = (result_path, summary_path, markdown_path, review_path)
    manifest = {
        "generated_at": FIXED_TIME.isoformat(),
        "harness_version": HARNESS_VERSION,
        "fixture_version": bundle.fixture_version,
        "fixture_hash": bundle.fixture_hash,
        "repeat_count": repeat_count,
        "provider_calls_allowed": provider_calls_allowed,
        "files": [
            {
                "file_name": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "record_count": (len(results) if path.suffix == ".jsonl" else 1),
            }
            for path in report_paths
        ],
    }
    validate_report_privacy(manifest)
    _write_text(manifest_path, f"{_json(manifest, pretty=True)}\n")
    return (*report_paths, manifest_path)


def _load_pricing(path: Path | None) -> V3ApprovedPricingReference | None:
    if path is None:
        return None
    return V3ApprovedPricingReference.model_validate_json(path.read_text(encoding="utf-8"))


async def run(
    *,
    output_directory: Path,
    repeat_count: int,
    pricing_reference: V3ApprovedPricingReference | None = None,
    allow_provider_calls: bool = False,
    runner: V3ShadowRunnerPort | None = None,
) -> tuple[Path, ...]:
    bundle = build_synthetic_fixture_bundle()
    results = await collect_results(
        bundle,
        repeat_count=repeat_count,
        runner=runner,
        allow_provider_calls=allow_provider_calls,
    )
    priced = _apply_pricing(results, pricing_reference)
    return write_reports(
        output_directory,
        bundle=bundle,
        results=priced,
        repeat_count=repeat_count,
        provider_calls_allowed=allow_provider_calls,
    )


def main(argv: list[str] | None = None, *, runner: V3ShadowRunnerPort | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-version",
        default=SYNTHETIC_FIXTURE_VERSION,
        choices=(SYNTHETIC_FIXTURE_VERSION,),
    )
    parser.add_argument("--repeat-count", type=int, default=1)
    parser.add_argument("--output-directory", type=Path, default=Path("outputs/v3-shadow"))
    parser.add_argument("--pricing-reference", type=Path)
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    try:
        paths = asyncio.run(
            run(
                output_directory=args.output_directory,
                repeat_count=args.repeat_count,
                pricing_reference=_load_pricing(args.pricing_reference),
                allow_provider_calls=args.allow_provider_calls,
                runner=runner,
            )
        )
    except (OSError, ValueError) as exc:
        print(f"V3 shadow evaluation failed: {exc}", file=sys.stderr)
        return 2
    print("\n".join(str(path) for path in paths))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())


__all__ = ["HARNESS_VERSION", "collect_results", "main", "run", "write_reports"]
