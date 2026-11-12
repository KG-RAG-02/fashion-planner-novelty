#!/usr/bin/env python3
"""Merge local synthetic planning fixtures into the R2 DuckDB and publish assets.

Default is a dry run. Use --upload to publish new, versioned R2 objects; existing
objects are never overwritten. R2 credentials are read from the local environment.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
from datetime import date
from pathlib import Path

import duckdb

from vogue_npp.sources.r2_synthetic_workbench import R2PlanningDBSettings, R2PlanningDBStore
from vogue_npp.synthetic_planning_workbench import validate_dataset

ROOT = Path(__file__).resolve().parents[1]
CORE_FIXTURE_FILES = (
    Path("data/fixtures/synthetic_planning_workbench/dataset.json"),
    Path("data/fixtures/synthetic_planning_workbench/DATA_CARD.md"),
    Path("data/fixtures/planning_rag/synthetic_corpus.json"),
    Path("data/fixtures/planning_rag/synthetic_workbench_eval_queries.json"),
)
SUPPLEMENTAL_FILES = (
    Path("data/README.md"),
    Path("data/interim/cross-agent-demo-27ss-planning-draft.md"),
    Path("data/interim/fixture-product-planning-draft.md"),
    Path("data/interim/full-input-test-planning-draft.md"),
    Path("data/local/planning_demos/ss-mens-shorts-all-inputs-received-test-20261106.json"),
    Path("data/local/planning_demos/ss-mens-shorts-four-trend-directions-20261106.json"),
    Path("data/local/planning_demos/ss-mens-shorts-four-trend-directions-evidence-assumed-20261106.json"),
)
ARCHIVE_FILES = (*CORE_FIXTURE_FILES, *SUPPLEMENTAL_FILES)
DEFAULT_SOURCE_ARCHIVE_KEY = "project06-synthetic-planning-assets-7c1a4715e3df571e-source-fixtures.tar.gz"
DOC_TYPES = {
    "approved_brand_guideline": "guideline",
    "approved_precedent": "precedent",
    "approved_taxonomy": "taxonomy",
    "supplied_input_evidence": "trend_observation",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def merged_corpus_records(dataset: dict, corpus_path: Path) -> tuple[list[dict], list[dict]]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if corpus.get("synthetic") is not True:
        raise ValueError("planning corpus must explicitly declare synthetic=true")
    documents, evidence = [], []
    for source in corpus.get("documents", []):
        source_type = source.get("source_type")
        document_type = DOC_TYPES.get(source_type)
        if not document_type:
            raise ValueError(f"unsupported synthetic corpus document type: {source_type}")
        original_id = str(source["document_id"])
        original_evidence_id = str(source["evidence_id"])
        document_id = f"SYN-CORPUS-{original_id}"
        evidence_id = f"SYN-CORPUS-{original_evidence_id}"
        source_id = f"SYN-CORPUS-{source['source_id']}"
        body = str(source.get("text", ""))
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        original_permission = source.get("permission_status", "unknown")
        permission = "synthetic_only" if original_permission == "authorized" else original_permission
        permitted_uses = list(source.get("permitted_uses", []))
        doc = {
            "document_id": document_id,
            "source_id": source_id,
            "document_type": document_type,
            "title": source.get("title", original_id),
            "version": "1.0",
            "lifecycle_status": "approved_example",
            "effective_from": source.get("published_at"),
            "effective_to": None,
            "season": source.get("season"),
            "category_id": source.get("category_id"),
            "product_role": None,
            "brand_line": "SYNTHETIC-CORPUS",
            "channel": source.get("channel", []),
            "market": source.get("market", []),
            "body": body,
            "evidence_ids": [evidence_id],
            "data_nature": "synthetic_test",
            "fictional_record_type": "merged_synthetic_corpus",
            "dataset_id": dataset["dataset_id"],
            "is_synthetic": True,
            "synthetic_notice": dataset["notice"],
            "generator_version": dataset["generator_version"],
            "seed": dataset["seed"],
            "snapshot_date": dataset["snapshot_date"],
            "source_locator": source.get("locator") or f"synthetic-corpus/{original_id}",
            "content_hash": content_hash,
            "permission_status": permission,
            "permitted_uses": permitted_uses,
            "verified": source.get("verified") is True,
        }
        ev = {
            "evidence_id": evidence_id,
            "source_id": source_id,
            "document_id": document_id,
            "locator": source.get("locator") or f"synthetic-corpus/{original_id}",
            "supports": [f"synthetic_corpus:{source_type}"],
            "permission_status": permission,
            "permitted_uses": permitted_uses,
            "verified": source.get("verified") is True,
            "content_hash": content_hash,
            "data_nature": "synthetic_test",
            "dataset_id": dataset["dataset_id"],
            "is_synthetic": True,
            "synthetic_notice": dataset["notice"],
            "generator_version": dataset["generator_version"],
            "seed": dataset["seed"],
        }
        documents.append(doc)
        evidence.append(ev)
    return documents, evidence


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def merge_into_database(source_db: Path, output_db: Path, base_dataset: dict,
                         documents: list[dict], evidence: list[dict], combined_hash: str) -> dict:
    validate_dataset(base_dataset)
    shutil.copy2(source_db, output_db)
    con = duckdb.connect(str(output_db))
    try:
        existing_docs = {row[0] for row in con.execute("SELECT document_id FROM synthetic_planning_documents").fetchall()}
        existing_evidence = {row[0] for row in con.execute("SELECT evidence_id FROM synthetic_evidence").fetchall()}
        if existing_docs.intersection(item["document_id"] for item in documents):
            raise ValueError("synthetic corpus document IDs already exist in the base R2 database")
        if existing_evidence.intersection(item["evidence_id"] for item in evidence):
            raise ValueError("synthetic corpus Evidence IDs already exist in the base R2 database")
        con.execute("BEGIN TRANSACTION")
        for item in documents:
            con.execute("""INSERT INTO synthetic_planning_documents
                (dataset_id, document_id, source_id, document_type, title, body, season,
                 category_id, lifecycle_status, effective_from, effective_to, source_locator,
                 content_hash, permitted_uses, evidence_ids, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::JSON, ?::JSON, ?::JSON)""",
                [item["dataset_id"], item["document_id"], item["source_id"], item["document_type"],
                 item["title"], item["body"], item["season"], item["category_id"],
                 item["lifecycle_status"], item["effective_from"], item["effective_to"],
                 item["source_locator"], item["content_hash"], encode(item["permitted_uses"]),
                 encode(item["evidence_ids"]), encode(item)])
        for item in evidence:
            con.execute("""INSERT INTO synthetic_evidence
                (dataset_id, evidence_id, source_id, document_id, locator, supports,
                 permission_status, permitted_uses, verified, content_hash, payload)
                VALUES (?, ?, ?, ?, ?, ?::JSON, ?, ?::JSON, ?, ?, ?::JSON)""",
                [item["dataset_id"], item["evidence_id"], item["source_id"], item["document_id"],
                 item["locator"], encode(item["supports"]), item["permission_status"],
                 encode(item["permitted_uses"]), item["verified"], item["content_hash"], encode(item)])
        con.execute("UPDATE synthetic_workbench_metadata SET metadata_value=? WHERE metadata_key='source_dataset_sha256'", [combined_hash])
        con.execute("COMMIT")
        meta = dict(con.execute("SELECT metadata_key, metadata_value FROM synthetic_workbench_metadata").fetchall())
        result = dict(base_dataset)
        result["documents"] = [json.loads(row[0]) for row in con.execute("SELECT payload::VARCHAR FROM synthetic_planning_documents ORDER BY document_id").fetchall()]
        result["evidence"] = [json.loads(row[0]) for row in con.execute("SELECT payload::VARCHAR FROM synthetic_evidence ORDER BY evidence_id").fetchall()]
        validate_dataset(result)
        return {"dataset_id": meta["dataset_id"], "documents": len(result["documents"]),
                "evidence": len(result["evidence"]), "added_documents": len(documents),
                "added_evidence": len(evidence)}
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload", action="store_true", help="publish new versioned R2 objects; default only builds and reports")
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    settings = R2PlanningDBSettings.from_env()
    # Always merge from the shared stock/workbench baseline, never from the
    # Project_06 enriched key configured for runtime after the first publish.
    shared_key = os.getenv("R2_DB_KEY", "").strip()
    if shared_key:
        from dataclasses import replace
        settings = replace(settings, db_key=shared_key)
    store = R2PlanningDBStore(settings)
    base_db, base_version, _ = store.prepare_database()
    base_data, _, _ = store.load_dataset()
    source_archive_key = os.getenv("VOGUE_SYNTHETIC_PLANNING_SOURCE_ARCHIVE_KEY", DEFAULT_SOURCE_ARCHIVE_KEY).strip()
    source_tmp = tempfile.TemporaryDirectory(prefix="p06-r2-source-")
    source_root = Path(source_tmp.name)
    response = store.client.get_object(Bucket=settings.bucket, Key=source_archive_key)
    with tarfile.open(fileobj=io.BytesIO(response["Body"].read()), mode="r:gz") as archive:
        available = {member.name: member for member in archive.getmembers() if member.isfile()}
        for relative in ARCHIVE_FILES:
            member = available.get(str(relative))
            if member is None:
                raise ValueError(f"source archive is missing required file: {relative}")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"source archive member cannot be read: {relative}")
            target = source_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())
    planning_dir = source_root / "data/fixtures/planning_rag"
    workbench_path = source_root / "data/fixtures/synthetic_planning_workbench/dataset.json"
    local_workbench = json.loads(workbench_path.read_text(encoding="utf-8"))
    if local_workbench.get("dataset_id") != base_data.get("dataset_id"):
        raise ValueError("local and R2 workbench dataset IDs differ")
    if {item["document_id"] for item in local_workbench["documents"]} != {item["document_id"] for item in base_data["documents"]}:
        raise ValueError("local and R2 workbench documents differ; reconcile before publishing")
    extra_docs, extra_evidence = merged_corpus_records(base_data, planning_dir / "synthetic_corpus.json")
    file_hashes = {str(path): sha256_file(source_root / path) for path in ARCHIVE_FILES}
    db_file_hashes = {str(path): file_hashes[str(path)] for path in CORE_FIXTURE_FILES}
    combined_hash = hashlib.sha256(encode({"base_r2_version": base_version, "files": db_file_hashes}).encode()).hexdigest()
    key_stem = f"project06-synthetic-planning-{combined_hash[:16]}"
    db_key = f"{key_stem}.duckdb"
    archive_hash = hashlib.sha256(encode(file_hashes).encode()).hexdigest()[:16]
    archive_key = f"project06-synthetic-planning-assets-{archive_hash}-source-fixtures.tar.gz"
    with tempfile.TemporaryDirectory(prefix="p06-r2-publish-") as temp:
        tmp = Path(temp)
        merged_db = tmp / db_key
        counts = merge_into_database(base_db, merged_db, base_data, extra_docs, extra_evidence, combined_hash)
        archive_path = tmp / archive_key
        with tarfile.open(archive_path, "w:gz") as archive:
            for relative in ARCHIVE_FILES:
                archive.add(source_root / relative, arcname=str(relative))
        print(json.dumps({"dry_run": not args.upload, "base_db_version": base_version,
                          "database_object_key": db_key, "source_archive_object_key": archive_key,
                          "database_bytes": merged_db.stat().st_size, "archive_bytes": archive_path.stat().st_size,
                          "counts": counts, "source_file_sha256": file_hashes}, ensure_ascii=False, indent=2))
        if args.upload:
            client = store.client
            for key, local_path, content_type, source_hash in (
                (db_key, merged_db, "application/octet-stream", combined_hash),
                (archive_key, archive_path, "application/gzip", archive_hash),
            ):
                try:
                    existing = client.head_object(Bucket=settings.bucket, Key=key)
                    metadata = existing.get("Metadata", {})
                    if (int(existing.get("ContentLength", -1)) != local_path.stat().st_size
                            or metadata.get("source-sha256") != source_hash
                            or metadata.get("data-nature") != "synthetic-only"):
                        raise ValueError(f"R2 object already exists with different content or metadata: {key}")
                    print(f"already_present={key}")
                    continue
                except Exception as exc:
                    code = getattr(exc, "response", {}).get("Error", {}).get("Code")
                    if code not in {"404", "NoSuchKey", "NotFound"}:
                        raise
                with local_path.open("rb") as stream:
                    client.put_object(Bucket=settings.bucket, Key=key, Body=stream,
                                      ContentType=content_type,
                                      Metadata={"data-nature": "synthetic-only", "dataset-id": counts["dataset_id"],
                                                "source-sha256": source_hash})
                print(f"uploaded={key}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
