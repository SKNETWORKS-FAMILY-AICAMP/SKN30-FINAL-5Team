"""Score the retriever and write `results/retrieval_metrics.json`.

    # offline, hash-derived vectors: wiring only
    uv run python -m backend.tests.evaluation.report_retrieval_cli

    # real embeddings (costs a small amount)
    export OPENAI_API_KEY=...
    uv run python -m backend.tests.evaluation.report_retrieval_cli --real-embeddings

The offline mode always marks its output `is_semantic: false`, because a score
computed from hash vectors describes the pipeline and not the retriever. Both
modes are written to the same schema so the two can be compared directly once
real numbers exist.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from backend.app.integrations.qdrant.embedding import EmbeddingContract, EmbeddingPort
from backend.tests.evaluation.evaluators.retrieval_evaluator import (
    RetrievalReport,
    load_retrieval_dataset,
    score_case,
)
from backend.tests.evaluation.retrieval.index import (
    EMBEDDING_INPUT_SCHEMA_VERSION,
    build_evaluation_index,
)
from backend.tests.evaluation.scenario import QUERY_HASH

DEFAULT_OUTPUT_DIR = Path("results")

# Only used with --real-embeddings. Overridable so the evaluation follows
# whatever embedding model is approved, and the choice is recorded in the report.
EMBEDDING_MODEL_ENV = "EVAL_EMBEDDING_MODEL_VERSION"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSION = 256


def _real_embedding() -> EmbeddingPort:
    """Build the production embedding adapter from an environment key."""

    from openai import OpenAI  # noqa: PLC0415 -- optional, only for a paid run

    from backend.app.integrations.qdrant.openai_embedding import OpenAIEmbeddingAdapter

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set; see docs/test/PAID_EVALUATION.md")
    contract = EmbeddingContract(
        provider_code="OPENAI",
        model_version=os.environ.get(EMBEDDING_MODEL_ENV, DEFAULT_EMBEDDING_MODEL),
        input_schema_version=EMBEDDING_INPUT_SCHEMA_VERSION,
        vector_dimension=DEFAULT_EMBEDDING_DIMENSION,
        distance_metric_code="COSINE",
    )
    return OpenAIEmbeddingAdapter(contract=contract, client=OpenAI(api_key=api_key))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-embeddings", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()

    embedding = _real_embedding() if arguments.real_embeddings else None
    index = build_evaluation_index(embedding=embedding)
    dataset = load_retrieval_dataset()

    report = RetrievalReport(
        embedding_provider_code=index.embedding_contract.provider_code,
        embedding_model_version=index.embedding_contract.model_version,
        query_mode="NORMALIZED_CODES",
        is_semantic=index.is_semantic,
    )
    for case in dataset.cases:
        request = case.to_request(
            catalog_version=index.contract.catalog_version, envelope_hash=QUERY_HASH
        )
        report.scores.append(score_case(case, index.retriever.retrieve(request)))

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    body = report.to_json()
    (arguments.output_dir / "retrieval_metrics.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    with (arguments.output_dir / "retrieval_cases.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "case_id",
                "returned",
                "recall_at_1",
                "recall_at_3",
                "recall_at_5",
                "reciprocal_rank",
                "first_relevant_rank",
                "eligibility_respected",
                "previous_plan_excluded",
                "mandatory_retained",
                "metadata_match_rate",
                "retrieval_status_code",
            ]
        )
        for case_body in body["cases"]:  # type: ignore[index]
            writer.writerow(
                [
                    case_body["case_id"],
                    case_body["returned"],
                    case_body["recall_at_1"],
                    case_body["recall_at_3"],
                    case_body["recall_at_5"],
                    case_body["reciprocal_rank"],
                    case_body["first_relevant_rank"],
                    case_body["eligibility_respected"],
                    case_body["previous_plan_excluded"],
                    case_body["mandatory_retained"],
                    case_body["metadata_match_rate"],
                    case_body["retrieval_status_code"],
                ]
            )

    print(f"embedding: {body['embedding_provider_code']}:{body['embedding_model_version']}")
    print(f"semantic:  {body['is_semantic']}")
    print(
        f"R@1={body['recall_at_1']} R@3={body['recall_at_3']} "
        f"R@5={body['recall_at_5']} MRR={body['mrr']}"
    )
    print(f"filter guarantees pass rate: {body['filter_guarantee_pass_rate']}")
    if not body["is_semantic"]:
        print("\nNOTE: hash-derived vectors. Ranking numbers validate wiring only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
