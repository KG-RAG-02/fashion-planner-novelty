import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vogue_npp.sources.r2_hm_catalog import R2HMCatalogSettings, R2HMCatalogStore


DUCKDB_AVAILABLE = importlib.util.find_spec("duckdb") is not None


@unittest.skipUnless(DUCKDB_AVAILABLE, "duckdb is an application dependency")
class R2HMCatalogTests(unittest.TestCase):
    def setUp(self):
        import duckdb

        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "hm-catalog.duckdb"
        con = duckdb.connect(str(self.db_path))
        try:
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
        self.db_bytes = self.db_path.read_bytes()

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_store(self, directory):
        db_bytes = self.db_bytes

        class FakeR2:
            get_calls = 0

            def head_object(self, **kwargs):
                return {"ETag": '"r2-test-version"', "ContentLength": len(db_bytes), "Metadata": {}}

            def get_object(self, **kwargs):
                self.get_calls += 1
                return {"Body": io.BytesIO(db_bytes), "ContentLength": len(db_bytes)}

        client = FakeR2()
        settings = R2HMCatalogSettings("account", "bucket", "hm.duckdb", "key", "secret")
        return R2HMCatalogStore(settings, client=client, cache_dir=Path(directory)), client

    def test_from_env_prefers_hm_metadata_key_without_printing_credentials(self):
        with patch.dict(os.environ, {
            "R2_ACCOUNT_ID": "account", "R2_BUCKET": "bucket", "R2_DB_KEY": "stock.duckdb",
            "VOGUE_R2_HM_CATALOG_DB_KEY": "hm/catalog.duckdb",
            "R2_ACCESS_KEY_ID": "access-secret", "R2_SECRET_ACCESS_KEY": "secret-value",
        }, clear=True):
            settings = R2HMCatalogSettings.from_env()
        self.assertEqual(settings.db_key, "hm/catalog.duckdb")
        self.assertNotIn("secret-value", repr(settings))

    def test_hm_image_candidate_query_accepts_korean_category_and_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            store, client = self.make_store(directory)
            rows = store.find_hm_catalog_candidates("상의", limit=3)
            store.prepare_database()
        self.assertEqual([row["article_id"] for row in rows], ["0999991001"])
        self.assertEqual(rows[0]["kf_area"], "상의")
        self.assertEqual(client.get_calls, 1)


if __name__ == "__main__":
    unittest.main()
