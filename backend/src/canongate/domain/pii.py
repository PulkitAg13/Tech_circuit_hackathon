"""DPDP 2025 & Microsoft Presidio PII Scrubber (`canongate.domain.pii`).

Implements the Round 1 Plan §6 Figure 6 Trust Boundary:
- In Air-Gapped Local Mode (default), nothing leaves the container.
- In opt-in Cloud Mode (`gemini` / `openai` / `groq`), outbound text is scrubbed
  locally before leaving the container using Microsoft Presidio (`presidio_analyzer`
  + `presidio_anonymizer` when installed) paired with deterministic Indian statutory
  PII recognizers (PAN card numbers, 12-digit Aadhaar IDs, Indian +91 mobile numbers,
  emails, and internal project codenames).
- Typed placeholders (`<EMAIL_1>`, `<PHONE_1>`, `<PAN_ID_1>`, `<AADHAAR_ID_1>`,
  `<CODENAME_1>`, `<PERSON_1>`) are restored locally after the cloud call completes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_AADHAAR_RE = re.compile(r"\b[2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}\b")
_PHONE_RE = re.compile(
    r"(?:(?:\+91|0091)[\s\-]?[6-9]\d{9}\b|\b[6-9]\d{4}[\s\-]?\d{5}\b|"
    r"\+\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b)"
)
_CODENAME_RE = re.compile(r"\bProject\s+[A-Z][A-Za-z0-9_\-]{2,24}\b")

_PATTERN_SPECS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", _EMAIL_RE),
    ("PAN_ID", _PAN_RE),
    ("AADHAAR_ID", _AADHAAR_RE),
    ("PHONE", _PHONE_RE),
    ("CODENAME", _CODENAME_RE),
)


@dataclass(frozen=True, slots=True)
class ScrubbedText:
    """Result of scrubbing PII from text prior to an outbound LLM request."""

    original_text: str
    masked_text: str
    placeholders: dict[str, str]

    @property
    def pii_count(self) -> int:
        return len(self.placeholders)

    def restore(self, candidate_text: str) -> str:
        """Unmask typed placeholders (`<EMAIL_1>`, `<PAN_ID_1>`, etc.) back to original values."""
        restored = candidate_text
        for placeholder, raw_val in self.placeholders.items():
            restored = restored.replace(placeholder, raw_val)
        return restored


class PresidioPiiScrubber:
    """Hybrid Microsoft Presidio + Indian DPDP regex PII scrubber with reversible placeholders."""

    __slots__ = ("_presidio_analyzer",)

    def __init__(self) -> None:
        self._presidio_analyzer = self._load_presidio()

    @staticmethod
    def _load_presidio() -> object | None:
        try:
            from presidio_analyzer import AnalyzerEngine  # type: ignore[import-not-found]

            return AnalyzerEngine()
        except Exception:
            return None

    def scrub(self, text: str) -> ScrubbedText:
        """Mask all PII and trade-secret codenames into reversible typed placeholders."""
        if not text:
            return ScrubbedText(original_text=text, masked_text=text, placeholders={})

        spans: list[tuple[int, int, str]] = []

        # 1. Deterministic Indian DPDP & contact patterns (PAN, Aadhaar, Phone, Email, Codename)
        for label, pattern in _PATTERN_SPECS:
            for match in pattern.finditer(text):
                spans.append((match.start(), match.end(), label))

        # 2. Optional Microsoft Presidio NER spans (PERSON, LOCATION, etc.) when installed
        if self._presidio_analyzer is not None:
            try:
                results = self._presidio_analyzer.analyze(  # type: ignore[attr-defined]
                    text=text,
                    entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"],
                    language="en",
                )
                for res in results:
                    lbl = (
                        "EMAIL"
                        if res.entity_type == "EMAIL_ADDRESS"
                        else "PHONE"
                        if res.entity_type == "PHONE_NUMBER"
                        else str(res.entity_type)
                    )
                    spans.append((int(res.start), int(res.end), lbl))
            except Exception:
                pass

        if not spans:
            return ScrubbedText(original_text=text, masked_text=text, placeholders={})

        # Deduplicate overlapping spans (prefer earlier start, then longer match)
        spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
        non_overlapping: list[tuple[int, int, str]] = []
        last_end = -1
        for start, end, label in spans:
            if start >= last_end:
                non_overlapping.append((start, end, label))
                last_end = end

        counters: dict[str, int] = {}
        placeholders: dict[str, str] = {}
        val_to_placeholder: dict[str, str] = {}
        pieces: list[str] = []
        cursor = 0

        for start, end, label in non_overlapping:
            pieces.append(text[cursor:start])
            raw_val = text[start:end]
            if raw_val in val_to_placeholder:
                ph = val_to_placeholder[raw_val]
            else:
                idx = counters.get(label, 0) + 1
                counters[label] = idx
                ph = f"<{label}_{idx}>"
                val_to_placeholder[raw_val] = ph
                placeholders[ph] = raw_val
            pieces.append(ph)
            cursor = end

        pieces.append(text[cursor:])
        masked = "".join(pieces)
        return ScrubbedText(original_text=text, masked_text=masked, placeholders=placeholders)


default_pii_scrubber = PresidioPiiScrubber()
