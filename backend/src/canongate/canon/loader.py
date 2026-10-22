"""Canon loader: YAML → Canon model.

The YAML format is the human-authored brand book. Later, Pipeline A
compiles PDFs/DOCXs into the same YAML.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from canongate.domain.canon import Canon, ColorToken, FactClaim, TermRule


def load_canon(path: Path) -> Canon:
    """Load a Canon from a YAML file.

    Expected YAML structure:
        id: my-brand
        version: "1.0"
        terminology:
          - id: cheap
            pattern_text: cheap
            preferred: affordable
            severity: 60
        palette:
          - id: primary
            hex: "#1A73E8"
            name: Primary Blue
            max_delta_e: 3.0
        facts:
          - id: founding_year
            text: "Founded in 2024"
    """
    raw = path.read_text(encoding="utf-8")

    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    elif path.suffix == ".json":
        data = json.loads(raw)
    else:
        raise ValueError(f"Unsupported canon file extension: {path.suffix}")

    terminology = tuple(TermRule(**t) for t in data.get("terminology", []))
    palette = tuple(ColorToken(**c) for c in data.get("palette", []))
    facts = tuple(FactClaim(**f) for f in data.get("facts", []))

    return Canon(
        id=data["id"],
        version=data["version"],
        terminology=terminology,
        palette=palette,
        facts=facts,
    )
