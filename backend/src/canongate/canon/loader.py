"""Canon loader: YAML / JSON → Canon model.

The YAML format is the human-authored brand book. Pipeline A also
compiles PDFs/DOCXs into the same structured Canon schema across all
five governance domains (terminology, palette, facts, trigger_obligations,
voice_profile, and logos).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from canongate.domain.canon import (
    Canon,
    ColorToken,
    FactClaim,
    LogoToken,
    TermRule,
    TriggerObligation,
    VoiceProfile,
)


def load_canon(path: Path) -> Canon:
    """Load a Canon from a YAML or JSON file."""
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
    trigger_obligations = tuple(
        TriggerObligation(**tr) for tr in data.get("trigger_obligations", [])
    )
    voice_raw = data.get("voice_profile")
    voice_profile = VoiceProfile(**voice_raw) if isinstance(voice_raw, dict) else None
    logos = tuple(LogoToken(**lg) for lg in data.get("logos", []))

    return Canon(
        id=data["id"],
        version=data["version"],
        terminology=terminology,
        palette=palette,
        facts=facts,
        trigger_obligations=trigger_obligations,
        voice_profile=voice_profile,
        logos=logos,
        require_image_alt=bool(data.get("require_image_alt", False)),
    )
