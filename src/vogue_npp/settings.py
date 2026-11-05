"""Provider-neutral local settings for future LLM integration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Runtime settings; secret values are excluded from repr output."""

    llm_api_key: str | None = field(default=None, repr=False)


def load_settings() -> Settings:
    """Load local .env values without selecting a provider or making a request."""

    load_dotenv()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    return Settings(llm_api_key=api_key or None)
