from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vogue_npp.sources.r2_product_images import (
    R2ImageConfigurationError,
    R2ImageUnavailable,
    R2ProductImageSettings,
    R2ProductImageStore,
)


JPEG = b"\xff\xd8\xffsynthetic-jpeg"


class FakeBody(io.BytesIO):
    pass


class FakeR2:
    def __init__(self, payload=JPEG):
        self.payload = payload
        self.calls = []

    def get_object(self, **kwargs):
        self.calls.append(kwargs)
        return {"Body": FakeBody(self.payload), "ContentLength": len(self.payload)}


def settings():
    return R2ProductImageSettings(
        account_id="account", bucket="private-bucket", image_prefix="images",
        access_key_id="not-printed", secret_access_key="not-printed",
        endpoint="https://r2.example.test",
    )


class R2ProductImageTests(unittest.TestCase):
    def test_object_key_uses_article_id_prefix_subdirectory(self):
        store = R2ProductImageStore(settings(), client=FakeR2(), cache_dir=Path("/tmp/r2-key-test"))
        self.assertEqual(store.object_key("0999991001"), "images/099/0999991001.jpg")

    def test_load_fetches_only_requested_jpeg_and_caches_it(self):
        client = FakeR2()
        with tempfile.TemporaryDirectory() as directory:
            store = R2ProductImageStore(settings(), client=client, cache_dir=Path(directory))
            content, mime = store.load("0999991001")
            self.assertEqual(content, JPEG)
            self.assertEqual(mime, "image/jpeg")
            self.assertEqual(client.calls[0]["Key"], "images/099/0999991001.jpg")
            self.assertEqual(store.load("0999991001"), (JPEG, "image/jpeg"))
            self.assertEqual(len(client.calls), 1)

    def test_rejects_non_numeric_id_and_non_jpeg_data(self):
        store = R2ProductImageStore(settings(), client=FakeR2(b"not-an-image"), cache_dir=Path("/tmp/r2-invalid-test"))
        with self.assertRaises(ValueError):
            store.object_key("../secret")
        with self.assertRaises(R2ImageUnavailable):
            store.load("0999991001")

    def test_optional_config_returns_none_and_partial_config_is_rejected(self):
        env_names = (
            "R2_ACCOUNT_ID", "R2_BUCKET", "R2_IMAGE_PREFIX", "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT", "Access Key ID", "Secret Access Key",
        )
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(R2ProductImageSettings.from_env())
        with patch.dict(os.environ, {"R2_ACCOUNT_ID": "account"}, clear=True):
            with self.assertRaises(R2ImageConfigurationError):
                R2ProductImageSettings.from_env()


if __name__ == "__main__":
    unittest.main()
