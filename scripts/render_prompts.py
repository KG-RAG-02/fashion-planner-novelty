"""Refresh human-reviewable rendered prompt copies from versioned templates."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"


def main() -> None:
    manifest = json.loads((PROMPTS / "manifest.json").read_text(encoding="utf-8"))
    for component, entry in manifest.items():
        directory = (PROMPTS / entry["directory"]).resolve()
        if PROMPTS.resolve() not in directory.parents:
            raise ValueError(f"Prompt path escapes prompts/: {component}")
        source = directory / "system_template.md"
        rendered = directory / "rendered_system.md"
        rendered.write_text(source.read_text(encoding="utf-8").rstrip("\n") + "\n", encoding="utf-8")
        print(f"Rendered {component} {entry['version']} -> {rendered.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
