"""Local runtime settings: the model API key."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # Keep the local API runnable with stdlib only.
    def load_dotenv() -> None:
        """Read simple KEY=VALUE lines without replacing existing env values."""
        env_file = Path.cwd() / ".env"
        if not env_file.is_file():
            return
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, value = line.partition("=")
            if not separator or not key.strip():
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)


@dataclass(frozen=True)
class Settings:
    """Runtime settings; secret values are excluded from repr output."""

    image_generation_api_key: str | None = field(default=None, repr=False)


def load_settings() -> Settings:
    """Load local .env values without selecting a provider or making a request."""

    load_dotenv()
    image_api_key = os.getenv("LLM_API_KEY", "").strip()
    return Settings(
        image_generation_api_key=image_api_key or None,
    )
