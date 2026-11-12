"""Read-only access to H&M article metadata in Cloudflare R2."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


_HM_CATEGORY_ALIASES = {
    "outerwear": "outerwear", "아우터": "outerwear", "코트": "outerwear", "재킷": "outerwear", "자켓": "outerwear",
    "tops": "tops", "상의": "tops", "탑": "tops", "티셔츠": "tops", "셔츠": "tops", "블라우스": "tops", "니트웨어": "tops",
    "bottoms": "bottoms", "하의": "bottoms", "팬츠": "bottoms", "바지": "bottoms", "스커트": "bottoms",
    "dresses": "dresses", "원피스": "dresses", "드레스": "dresses", "점프수트": "dresses",
    "accessories": "accessories", "액세서리": "accessories", "가방": "accessories",
    "footwear": "footwear", "신발": "footwear", "슈즈": "footwear",
}


class R2HMCatalogConfigurationError(ValueError):
    """R2 H&M metadata settings are missing or invalid."""


class R2HMCatalogUnavailable(RuntimeError):
    """The configured R2 H&M metadata database could not be loaded safely."""


@dataclass(frozen=True)
class R2HMCatalogSettings:
    account_id: str
    bucket: str
    db_key: str
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    endpoint: str = ""

    @property
    def endpoint_url(self) -> str:
        return self.endpoint or f"https://{self.account_id}.r2.cloudflarestorage.com"

    @classmethod
    def from_env(cls) -> "R2HMCatalogSettings":
        account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
        bucket = os.getenv("R2_BUCKET", "").strip()
        # Use the dedicated H&M metadata object when configured.
        db_key = (os.getenv("VOGUE_R2_HM_CATALOG_DB_KEY", "") or os.getenv("R2_DB_KEY", "")).strip()
        access_key_id = (os.getenv("R2_ACCESS_KEY_ID", "") or os.getenv("Access Key ID", "")).strip()
        secret_access_key = (os.getenv("R2_SECRET_ACCESS_KEY", "") or os.getenv("Secret Access Key", "")).strip()
        missing = [name for name, value in (
            ("R2_ACCOUNT_ID", account_id), ("R2_BUCKET", bucket),
            ("VOGUE_R2_HM_CATALOG_DB_KEY or R2_DB_KEY", db_key),
            ("R2_ACCESS_KEY_ID", access_key_id), ("R2_SECRET_ACCESS_KEY", secret_access_key),
        ) if not value]
        if missing:
            raise R2HMCatalogConfigurationError("R2 H&M catalog settings are incomplete: " + ", ".join(missing))
        if any(ch in account_id for ch in "/:@?#"):
            raise R2HMCatalogConfigurationError("R2_ACCOUNT_ID format is invalid.")
        if db_key.startswith("/") or ".." in Path(db_key).parts:
            raise R2HMCatalogConfigurationError("R2 H&M catalog key is invalid.")
        endpoint = os.getenv("R2_ENDPOINT", "").strip().rstrip("/")
        if endpoint:
            parsed = urlsplit(endpoint)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise R2HMCatalogConfigurationError("R2_ENDPOINT must be an HTTPS endpoint without credentials.")
        return cls(account_id, bucket, db_key, access_key_id, secret_access_key, endpoint)


class R2HMCatalogStore:
    """Download one versioned R2 H&M metadata object to a private atomic cache."""

    def __init__(self, settings: R2HMCatalogSettings, client=None, cache_dir: Path | None = None):
        self.settings = settings
        self.client = client if client is not None else self._client(settings)
        self.cache_dir = Path(cache_dir or os.getenv("VOGUE_R2_HM_CATALOG_CACHE_DIR", "data/local/r2_hm_catalog_db"))
        self.max_bytes = int(os.getenv("VOGUE_R2_HM_CATALOG_MAX_BYTES", str(2_000_000_000)))

    @staticmethod
    def _client(settings: R2HMCatalogSettings):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - dependency installation path
            raise R2HMCatalogConfigurationError("R2 H&M catalog access requires boto3.") from exc
        return boto3.client(
            "s3", endpoint_url=settings.endpoint_url, region_name="auto",
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
            config=Config(connect_timeout=5, read_timeout=60,
                          retries={"max_attempts": 2, "mode": "standard"}),
        )

    def prepare_database(self) -> tuple[Path, str, dict[str, str]]:
        try:
            head = self.client.head_object(Bucket=self.settings.bucket, Key=self.settings.db_key)
            etag = str(head.get("ETag", "")).strip('"')
            version_id = str(head.get("VersionId", ""))
            content_length = int(head.get("ContentLength", 0))
            if not (etag or version_id) or content_length <= 0 or content_length > self.max_bytes:
                raise R2HMCatalogUnavailable("The R2 H&M catalog version or size is invalid.")
            version = version_id or etag
            identity = hashlib.sha256(f"{self.settings.bucket}/{self.settings.db_key}/{version}".encode()).hexdigest()
            target = self.cache_dir / f"hm-catalog-{identity}.duckdb"
            if target.is_file() and target.stat().st_size == content_length:
                return target, version, dict(head.get("Metadata", {}))
            self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                self.cache_dir.chmod(0o700)
            except OSError:
                pass
            fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".part", dir=self.cache_dir)
            size = 0
            try:
                with os.fdopen(fd, "wb") as output:
                    response = self.client.get_object(Bucket=self.settings.bucket, Key=self.settings.db_key)
                    downloaded_version_id = str(response.get("VersionId", ""))
                    downloaded_etag = str(response.get("ETag", "")).strip('"')
                    if version_id and downloaded_version_id and downloaded_version_id != version_id:
                        raise R2HMCatalogUnavailable("The R2 H&M catalog changed during download.")
                    if not version_id and etag and downloaded_etag and downloaded_etag != etag:
                        raise R2HMCatalogUnavailable("The R2 H&M catalog changed during download.")
                    response_size = response.get("ContentLength")
                    if response_size is not None and int(response_size) != content_length:
                        raise R2HMCatalogUnavailable("The R2 H&M catalog response size did not match metadata.")
                    body = response["Body"]
                    try:
                        while True:
                            chunk = body.read(8 * 1024 * 1024)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > self.max_bytes:
                                raise R2HMCatalogUnavailable("The R2 H&M catalog exceeded the size limit.")
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    finally:
                        close = getattr(body, "close", None)
                        if callable(close):
                            close()
                if size != content_length:
                    raise R2HMCatalogUnavailable("The downloaded R2 H&M catalog size did not match metadata.")
                os.chmod(temp_name, 0o600)
                os.replace(temp_name, target)
            finally:
                Path(temp_name).unlink(missing_ok=True)
            return target, version, dict(head.get("Metadata", {}))
        except R2HMCatalogUnavailable:
            raise
        except Exception:
            raise R2HMCatalogUnavailable("The R2 H&M catalog could not be read.") from None

    def find_hm_catalog_candidates(self, category: str, *, limit: int = 12) -> list[dict[str, Any]]:
        """Select a small, deterministic set of image references from H&M rows."""
        category_filters = {
            "outerwear": ("a.kf_area = ?", ("아우터",)),
            "tops": ("a.kf_area = ?", ("상의",)),
            "bottoms": ("a.kf_area = ?", ("하의",)),
            "dresses": ("a.kf_area = ?", ("원피스",)),
            "accessories": ("p.product_group_name IN ('Accessories', 'Bags')", ()),
            "footwear": ("p.product_group_name = 'Shoes'", ()),
        }
        normalized_category = _HM_CATEGORY_ALIASES.get(str(category).strip().casefold())
        category_filter = category_filters.get(normalized_category or "")
        if category_filter is None:
            return []
        try:
            import duckdb
            path, _, _ = self.prepare_database()
            con = duckdb.connect(str(path), read_only=True)
            try:
                condition, parameters = category_filter
                rows = con.execute(
                    f"""SELECT p.article_id, p.prod_name, p.product_type_name,
                               p.product_group_name, p.graphical_appearance_name,
                               p.colour_group_name, p.detail_desc,
                               a.kf_area, a.kf_category, a.kf_color, a.materials, a.fit, a.season_fit
                        FROM articles p
                        LEFT JOIN article_attrs a USING (article_id)
                        WHERE {condition} AND regexp_full_match(p.article_id, '[0-9]{{10}}')
                        QUALIFY row_number() OVER (
                            PARTITION BY COALESCE(p.product_type_name, p.product_group_name, 'unknown')
                            ORDER BY p.article_id
                        ) = 1
                        ORDER BY p.product_type_name, p.article_id
                        LIMIT ?""",
                    [*parameters, max(1, min(int(limit), 100))],
                ).fetchall()
                names = [column[0] for column in con.description]
                return [dict(zip(names, row)) for row in rows]
            finally:
                con.close()
        except Exception:
            raise R2HMCatalogUnavailable("H&M catalog image candidates could not be queried.") from None

