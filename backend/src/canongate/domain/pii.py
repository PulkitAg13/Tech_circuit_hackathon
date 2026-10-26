"""DPDP 2025 & Microsoft Presidio PII Scrubber (`canongate.domain.pii`).

Implements the Round 1 Plan §6 Figure 6 Trust Boundary & Round 2 Improvement #2:
- In Air-Gapped Local Mode (default when no API key is configured), nothing leaves
  the container, and the user is explicitly informed that no LLM API key is active.
- In opt-in Cloud Mode (`inkloom` / `openrouter` / `gemini` / `openai` / `groq`),
  outbound text is scrubbed locally before leaving the container using Microsoft
  Presidio (`presidio_analyzer` + `presidio_anonymizer` when installed) paired with
  deterministic Indian statutory PII recognizers:
    * `PAN_ID` (`[A-Z]{5}[0-9]{4}[A-Z]`)
    * `AADHAAR_ID` (12-digit Indian UIDAI pattern `[2-9]\\d{3}[\\s\\-]?\\d{4}[\\s\\-]?\\d{4}`)
    * `GSTIN` (15-character Indian Goods & Services Tax ID:
      `\\d{2}[A-Z]{5}\\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]`)
    * `UPI_VPA` (Unified Payments Interface handles `user@okaxis`, `merchant@ybl`, etc.)
    * `IFSC` (11-character Indian bank branch code `[A-Z]{4}0[A-Z0-9]{6}`)
    * `PHONE` (Indian `+91` / 10-digit mobile numbers and international numbers)
    * `EMAIL` (RFC 5322 email addresses)
    * `CODENAME` (Internal trade-secret identifiers like `Project Titan`)
- Typed placeholders (`<EMAIL_1>`, `<PHONE_1>`, `<PAN_ID_1>`, `<AADHAAR_ID_1>`,
  `<GSTIN_1>`, `<UPI_VPA_1>`, `<IFSC_1>`, `<CODENAME_1>`, `<PERSON_1>`) are
  bijectively verified via `verify_placeholder_integrity()` before being restored
  locally after the cloud call completes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_UPI_VPA_RE = re.compile(
    r"\b[A-Za-z0-9._\-]{2,64}@(?:okaxis|okhdfcbank|okicici|oksbi|ybl|ibl|axl|paytm|upi|apl|kotak|sbi|icici|hdfcbank|axisbank)\b",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_AADHAAR_RE = re.compile(r"\b[2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}\b")
_PHONE_RE = re.compile(
    r"(?:(?:\+91|0091)[\s\-]?[6-9]\d{9}\b|\b[6-9]\d{4}[\s\-]?\d{5}\b|"
    r"\+\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b)"
)
_CODENAME_RE = re.compile(r"\bProject\s+[A-Z][A-Za-z0-9_\-]{2,24}\b")

_PLACEHOLDER_TOKEN_RE = re.compile(
    r"<(?:GSTIN|PAN_ID|IFSC|UPI_VPA|EMAIL|AADHAAR_ID|PHONE|CODENAME|PERSON|LOCATION)_\d+>"
)

# Order matters: GSTIN before PAN_ID (since GSTIN embeds a 10-char PAN at chars 2..12),
# and UPI_VPA before EMAIL.
_PATTERN_SPECS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GSTIN", _GSTIN_RE),
    ("PAN_ID", _PAN_RE),
    ("IFSC", _IFSC_RE),
    ("UPI_VPA", _UPI_VPA_RE),
    ("EMAIL", _EMAIL_RE),
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

    def __len__(self) -> int:
        return len(self.placeholders)

    def __bool__(self) -> bool:
        return bool(self.placeholders)

    def verify_placeholder_integrity(self, candidate_masked_text: str) -> tuple[bool, str | None]:
        """Verify candidate preserved all input PII placeholders without hallucinating."""
        for ph in self.placeholders:
            expected_count = self.masked_text.count(ph)
            actual_count = candidate_masked_text.count(ph)
            if actual_count < expected_count:
                return (
                    False,
                    f"LLM dropped required PII placeholder {ph} "
                    f"(expected {expected_count}, found {actual_count})",
                )
        for m in _PLACEHOLDER_TOKEN_RE.finditer(candidate_masked_text):
            tok = m.group(0)
            if tok not in self.placeholders:
                return (
                    False,
                    f"LLM hallucinated unknown PII placeholder token {tok}",
                )
        return True, None

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

        # 1. Deterministic Indian DPDP patterns (GSTIN, PAN, IFSC, UPI, Email, Aadhaar, Phone)
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
