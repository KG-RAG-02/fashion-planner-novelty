import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.generate_synthetic_planning_workbench import build_dataset
from vogue_npp.domain.retrieval import RetrievalQuery
from vogue_npp.sources.r2_synthetic_workbench import (
    R2PlanningDBSettings,
    R2PlanningDBStore,
    R2PlanningDBUnavailable,
    R2SyntheticWorkbenchRetriever,
)


DUCKDB_AVAILABLE = importlib.util.find_spec("duckdb") is not None


@unittest.skipUnless(DUCKDB_AVAILABLE, "duckdb is an application dependency")
class R2SyntheticWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import duckdb

        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "merged.duckdb"
        cls.dataset = build_dataset(20261110)
        cls.source_hash = hashlib.sha256(json.dumps(
            cls.dataset, ensure_ascii=False, indent=2,
        ).encode("utf-8")).hexdigest()
        metadata = {
            key: str(cls.dataset.get(key, ""))
            for key in ("dataset_id", "schema_version", "generator_version", "seed", "snapshot_date", "data_nature", "notice")
        }
        metadata["source_dataset_sha256"] = cls.source_hash
        con = duckdb.connect(str(cls.db_path))
        try:
            con.execute("CREATE TABLE synthetic_workbench_metadata (metadata_key VARCHAR, metadata_value VARCHAR)")
            con.executemany("INSERT INTO synthetic_workbench_metadata VALUES (?, ?)", list(metadata.items()))
            table_rows = {
                "synthetic_taxonomy": ("taxonomy_id", [row.get("taxonomy_id") or row.get("category_id") for row in cls.dataset["taxonomy"]], cls.dataset["taxonomy"]),
                "synthetic_products": ("style_id", [row["style_id"] for row in cls.dataset["products"]], cls.dataset["products"]),
                "synthetic_inventory_snapshots": ("snapshot_id", [row.get("snapshot_id") or f"{row.get('style_id')}:{row.get('as_of')}" for row in cls.dataset["inventory_snapshots"]], cls.dataset["inventory_snapshots"]),
                "synthetic_planning_documents": ("document_id", [row["document_id"] for row in cls.dataset["documents"]], cls.dataset["documents"]),
                "synthetic_evidence": ("evidence_id", [row["evidence_id"] for row in cls.dataset["evidence"]], cls.dataset["evidence"]),
                "synthetic_assortment_relations": ("relation_id", [row["relation_id"] for row in cls.dataset["assortment_relations"]], cls.dataset["assortment_relations"]),
                "synthetic_planning_inputs": ("request_id", [row["request_id"] for row in cls.dataset["planning_inputs"]], cls.dataset["planning_inputs"]),
                "synthetic_sales_market_handoffs": ("handoff_id", [row["handoff_id"] for row in cls.dataset["sales_market_handoffs"]], cls.dataset["sales_market_handoffs"]),
            }
            for table, (key, keys, rows) in table_rows.items():
                con.execute(f'CREATE TABLE {table} ({key} VARCHAR, payload JSON)')
                con.executemany(
                    f'INSERT INTO {table} VALUES (?, ?::JSON)',
                    [(row_key, json.dumps(row, ensure_ascii=False)) for row_key, row in zip(keys, rows)],
                )
            con.execute('''CREATE TABLE articles (
                article_id VARCHAR, prod_name VARCHAR, product_type_name VARCHAR, product_group_name VARCHAR,
                graphical_appearance_name VARCHAR, colour_group_name VARCHAR, detail_desc VARCHAR)''')
            con.execute("INSERT INTO articles VALUES ('0999991001', 'Strap top', 'Vest top', 'Garment Upper body', 'Solid', 'Black', 'Jersey top')")
            con.execute('''CREATE TABLE article_attrs (
                article_id VARCHAR, kf_area VARCHAR, kf_category VARCHAR, kf_color VARCHAR,
                materials VARCHAR[], fit VARCHAR, season_fit VARCHAR[])''')
            con.execute("INSERT INTO article_attrs VALUES ('0999991001', '상의', '탑', '블랙', ['저지'], NULL, ['여름'])")
        finally:
            con.close()
        cls.db_bytes = cls.db_path.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def make_store(self, directory):
        from vogue_npp.sources.r2_synthetic_workbench import R2PlanningDBSettings

        class Body(io.BytesIO):
            pass

        class FakeR2:
            get_calls = 0

            def head_object(self, **kwargs):
                return {"ETag": '"r2-test-version"', "ContentLength": len(self_bytes), "Metadata": {"data-nature": "synthetic-only"}}

            def get_object(self, **kwargs):
                self.get_calls += 1
                return {"Body": Body(self_bytes), "ContentLength": len(self_bytes)}

        self_bytes = self.db_bytes
        client = FakeR2()
        settings = R2PlanningDBSettings("account", "bucket", "merged.duckdb", "key", "secret")
        return R2PlanningDBStore(settings, client=client, cache_dir=Path(directory)), client

    def test_from_env_prefers_planning_key_without_printing_credentials(self):
        with patch.dict(os.environ, {
            "R2_ACCOUNT_ID": "account", "R2_BUCKET": "bucket", "R2_DB_KEY": "stock.duckdb",
            "VOGUE_SYNTHETIC_PLANNING_R2_DB_KEY": "planning/merged.duckdb",
            "R2_ACCESS_KEY_ID": "access-secret", "R2_SECRET_ACCESS_KEY": "secret-value",
        }, clear=True):
            settings = R2PlanningDBSettings.from_env()
        self.assertEqual(settings.db_key, "planning/merged.duckdb")
        self.assertNotIn("secret-value", repr(settings))

    def test_cloud_snapshot_is_cached_and_retrieved_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            store, client = self.make_store(directory)
            retriever = R2SyntheticWorkbenchRetriever(store)
            query = RetrievalQuery(
                request_id="cloud-test", purpose="catalog_comparison", season="27SS",
                category_ids=("outerwear",), product_roles=("upper_body",),
                attribute_terms=("sage",), exact_terms=("sage",),
                allowed_source_types=("catalog_record",), dataset_id=retriever.dataset_id,
                allow_synthetic=True,
            )
            result = retriever.retrieve(query)
            self.assertEqual(result.status, "ok")
            self.assertEqual({item.evidence_id for item in result.evidence}, {"SYN-EV-ATTR-001-COLOR"})
            self.assertIn(":r2:r2-test-version", result.index_version)
            self.assertTrue(all(item.is_synthetic and item.content_hash for item in result.evidence))
            store.prepare_database()
            self.assertEqual(client.get_calls, 1)

    def test_non_synthetic_r2_object_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store, client = self.make_store(directory)
            client.head_object = lambda **kwargs: {
                "ETag": '"r2-test-version"', "ContentLength": len(self.db_bytes),
                "Metadata": {"data-nature": "unknown"},
            }
            with self.assertRaises(R2PlanningDBUnavailable):
                store.load_dataset()

    def test_hm_image_candidate_query_accepts_korean_category(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _client = self.make_store(directory)
            rows = store.find_hm_catalog_candidates("상의", limit=3)
        self.assertEqual([row["article_id"] for row in rows], ["0999991001"])
        self.assertEqual(rows[0]["kf_area"], "상의")


if __name__ == "__main__":
    unittest.main()
