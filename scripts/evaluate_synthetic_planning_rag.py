"""Run the fixed, synthetic-only retrieval regression set and emit JSON metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from vogue_npp.sources.synthetic_workbench_retriever import SyntheticWorkbenchRetriever
from vogue_npp.synthetic_planning_workbench import DEFAULT_DATASET
from vogue_npp.domain.retrieval import RetrievalQuery

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERIES = ROOT / "data/fixtures/planning_rag/synthetic_workbench_eval_queries.json"


def _load_queries(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("is_synthetic") is not True or not isinstance(data.get("queries"), list):
        raise ValueError("evaluation query set must be explicitly marked synthetic")
    return data


def _query(row: dict[str, Any], retriever: SyntheticWorkbenchRetriever, limit: int) -> RetrievalQuery:
    return RetrievalQuery(
        request_id=row["query_id"],
        purpose=row["purpose"],
        season=row.get("season"),
        category_ids=tuple(row.get("category_ids", ())),
        product_roles=tuple(row.get("product_roles", ())),
        attribute_terms=tuple(row.get("attribute_terms", ())),
        exact_terms=tuple(row.get("exact_terms", ())),
        evidence_ids=tuple(row.get("evidence_ids", ())),
        allowed_source_types=tuple(row["allowed_source_types"]),
        limit=limit,
        candidate_limit=max(limit, min(500, limit * 3)),
        query_plan_version="synthetic-rag-eval-v1",
        dataset_id=retriever.dataset_id,
        allow_synthetic=True,
    )


def evaluate(*, dataset_path: Path = DEFAULT_DATASET, queries_path: Path = DEFAULT_QUERIES) -> dict[str, Any]:
    retriever = SyntheticWorkbenchRetriever(dataset_path)
    evaluation = _load_queries(queries_path)
    documents = {row["document_id"]: row for row in retriever.dataset["documents"]}
    evidence = retriever._evidence
    cases = []
    totals = {key: 0 for key in (
        "expected_positive", "positive_recall_sum", "precision_sum", "no_results_correct",
        "locator_complete", "returned_count", "permission_violations", "stale_document_leakage",
        "evidence_free_observations", "observation_count",
    )}
    for row in evaluation["queries"]:
        expected = set(row.get("expected_evidence_ids", ()))
        result = retriever.retrieve(_query(row, retriever, int(evaluation.get("top_k", 10))))
        returned = [item.evidence_id for item in result.evidence]
        returned_set = set(returned)
        hits = expected.intersection(returned_set)
        if expected:
            totals["expected_positive"] += 1
            totals["positive_recall_sum"] += len(hits) / len(expected)
        precision = len(hits) / len(returned_set) if returned_set else (1.0 if not expected else 0.0)
        totals["precision_sum"] += precision
        no_result_correct = (not returned) == bool(row.get("expect_no_results"))
        totals["no_results_correct"] += int(no_result_correct)
        violations = 0
        stale = 0
        complete = 0
        for item in result.evidence:
            source = evidence.get(item.evidence_id, {})
            doc = documents.get(source.get("document_id"), {})
            violations += int(not (
                item.verified and item.permission_status == "synthetic_only"
                and item.is_synthetic and item.dataset_id == retriever.dataset_id
                and "product_planning" in item.permitted_uses
            ))
            stale += int(doc.get("lifecycle_status") != "approved_example" or bool(doc.get("effective_to") and doc["effective_to"] < retriever.dataset["snapshot_date"]))
            complete += int(bool(item.source_id and item.locator and item.content_hash))
        totals["permission_violations"] += violations
        totals["stale_document_leakage"] += stale
        totals["locator_complete"] += complete
        totals["returned_count"] += len(result.evidence)
        totals["observation_count"] += len(result.evidence)
        totals["evidence_free_observations"] += sum(not item.evidence_id for item in result.evidence)
        cases.append({
            "query_id": row["query_id"],
            "purpose": row["purpose"],
            "expected_evidence_ids": sorted(expected),
            "returned_evidence_ids": returned,
            "recall_at_k": len(hits) / len(expected) if expected else None,
            "precision_at_k": precision,
            "expected_no_results": bool(row.get("expect_no_results")),
            "no_results_correct": no_result_correct,
            "permission_violations": violations,
            "stale_document_leakage": stale,
            "source_locator_content_hash_complete": complete == len(result.evidence),
            "retrieval_run_id": result.retrieval_run_id,
            "index_version": result.index_version,
        })
    count = len(cases)
    returned_count = totals["returned_count"]
    metrics = {
        "recall_at_k": totals["positive_recall_sum"] / totals["expected_positive"] if totals["expected_positive"] else 0,
        "precision_at_k": totals["precision_sum"] / count if count else 0,
        "source_locator_content_hash_completeness": totals["locator_complete"] / returned_count if returned_count else 1,
        "permission_violation_count": totals["permission_violations"],
        "stale_document_leakage_count": totals["stale_document_leakage"],
        "evidence_free_observation_rate": totals["evidence_free_observations"] / totals["observation_count"] if totals["observation_count"] else 0,
        "no_results_accuracy": totals["no_results_correct"] / count if count else 0,
    }
    no_rag_recall = 0.0 if totals["expected_positive"] else 1.0
    no_rag_no_result_correct = sum(bool(row.get("expect_no_results")) for row in evaluation["queries"])
    baseline = {
        "recall_at_k": no_rag_recall,
        "precision_at_k": sum(1.0 if not row.get("expected_evidence_ids") else 0.0 for row in evaluation["queries"]) / count if count else 0,
        "source_locator_content_hash_completeness": None,
        "permission_violation_count": 0,
        "stale_document_leakage_count": 0,
        "evidence_free_observation_rate": None,
        "no_results_accuracy": no_rag_no_result_correct / count if count else 0,
    }
    return {
        "evaluation_set_id": evaluation["evaluation_set_id"],
        "notice": evaluation["notice"],
        "dataset_id": retriever.dataset_id,
        "snapshot_sha256": retriever.snapshot_sha256,
        "index_version": retriever.index_version,
        "generator_version": retriever.dataset["generator_version"],
        "seed": retriever.dataset["seed"],
        "query_count": count,
        "top_k": evaluation.get("top_k", 10),
        "retrieval_mode": "deterministic lexical synthetic-only",
        "baseline_without_rag": baseline,
        "rag": metrics,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(dataset_path=args.dataset, queries_path=args.queries)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
