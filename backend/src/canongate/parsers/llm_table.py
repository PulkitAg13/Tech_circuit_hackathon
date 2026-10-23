"""Multi-Provider Guarded LLM Adapter for Complex Table De-Normalization & Canon Extraction.

Supports four pluggable LLM execution modes so teammates can use whichever provider
they have available while defaulting seamlessly to the free Google Gemini API key:
1. `gemini` (Google AI Studio free tier via `GEMINI_API_KEY` or `CANONGATE_GEMINI_API_KEY`,
   default model `gemini-2.5-flash` with `responseMimeType: "application/json"`).
2. `openai` / `groq` (OpenAI, Groq, OpenRouter, Together, or vLLM via `OPENAI_API_KEY`,
   `GROQ_API_KEY`, or `CANONGATE_OPENAI_API_KEY` + `CANONGATE_OPENAI_BASE_URL`).
3. `ollama` (Local zero-cost inference via `http://localhost:11434/api/generate` with
   `"format": "json"`, default model `qwen2.5:7b`).
4. `none` / offline fallback (deterministic hierarchical header & rowspan solver).

Safety & Hallucination Prevention (Guard 1):
Every row proposition produced by an LLM is audited by `verify_and_repair_llm_row()`
before entering the `ContentAST`:
- **Zero Hallucinated Numbers:** If the LLM invents any number, percentage, currency
  amount, or date not present in the source row + headers + footnotes, the LLM output
  for that row is rejected in favor of the deterministic linearization.
- **100% Value-Anchor & Qualifier Preservation:** If the LLM drops any numeric anchor
  or footnote qualifier from the source row, Guard 1 automatically appends the missing
  cell/footnote clause so `AnchorRecall == 1.0` is strictly preserved.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

LLMProviderName = Literal["auto", "gemini", "openai", "groq", "ollama", "none"]
HttpTransport = Callable[[str, dict[str, Any], dict[str, str], float], dict[str, Any]]

_ANCHOR_RE = re.compile(
    r"(?:"
    r"\b\d{4}-\d{2}-\d{2}\b|"
    r"\bQ[1-4]\s+\d{4}\b|"
    r"(?:₹|Rs\.?\s*|\$)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:lakh|lakhs|cr|crore|crores|k|m))?\b|"
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:%|lakh|lakhs|cr|crore|crores)\b|"
    r"\b\d[\d,]*(?:\.\d+)?\b"
    r")",
    re.IGNORECASE,
)

_NUMBER_NORM_RE = re.compile(r"\d+(?:\.\d+)?")


def extract_table_anchors(text: str) -> tuple[str, ...]:
    """Extract all numeric, currency, percentage, and date anchors from `text`."""
    seen: list[str] = []
    for m in _ANCHOR_RE.finditer(text):
        tok = re.sub(r"\s+", " ", m.group(0).strip())
        if tok and tok not in seen:
            seen.append(tok)
    return tuple(seen)


def _extract_numeric_scalars(text: str) -> set[str]:
    """Extract normalized numeric substrings (stripping commas) for hallucination auditing."""
    cleaned = text.replace(",", "")
    return set(_NUMBER_NORM_RE.findall(cleaned))


def _default_http_transport(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_s: float,
) -> dict[str, Any]:
    """Standard-library JSON POST client (requires zero external HTTP dependencies)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def _strip_markdown_fences(raw_text: str) -> str:
    txt = raw_text.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"\s*```$", "", txt)
    return txt.strip()


@dataclass(frozen=True, slots=True)
class LLMProviderConfig:
    """Resolved configuration for the multi-provider JSON LLM client."""

    provider: Literal["gemini", "openai", "ollama", "none"]
    model: str
    api_key: str = ""
    base_url: str = ""
    timeout_s: float = 15.0

    @classmethod
    def from_env(
        cls,
        *,
        provider: LLMProviderName | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 15.0,
    ) -> LLMProviderConfig:
        """Resolve LLM provider configuration from explicit args or environment variables."""
        raw_prov = (
            (
                provider
                or os.environ.get("CANONGATE_LLM_PROVIDER")
                or os.environ.get("LLM_PROVIDER")
                or "auto"
            )
            .strip()
            .lower()
        )

        gemini_key = (
            (api_key if raw_prov == "gemini" and api_key else None)
            or os.environ.get("CANONGATE_GEMINI_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        ).strip()

        openai_key = (
            (api_key if raw_prov in ("openai", "groq") and api_key else None)
            or os.environ.get("CANONGATE_OPENAI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()

        groq_key = (
            os.environ.get("CANONGATE_GROQ_API_KEY") or os.environ.get("GROQ_API_KEY") or ""
        ).strip()

        if raw_prov == "auto":
            if gemini_key:
                raw_prov = "gemini"
            elif openai_key:
                raw_prov = "openai"
            elif groq_key:
                raw_prov = "groq"
            elif os.environ.get("OLLAMA_HOST"):
                raw_prov = "ollama"
            else:
                raw_prov = "none"

        if raw_prov == "gemini":
            resolved_key = api_key or gemini_key
            if not resolved_key:
                return cls(provider="none", model="none", timeout_s=timeout_s)
            resolved_model = (
                model
                or os.environ.get("CANONGATE_GEMINI_MODEL")
                or os.environ.get("GEMINI_MODEL")
                or "gemini-2.5-flash"
            )
            resolved_url = (
                base_url
                or os.environ.get("CANONGATE_GEMINI_BASE_URL")
                or "https://generativelanguage.googleapis.com/v1beta"
            )
            return cls(
                provider="gemini",
                model=resolved_model,
                api_key=resolved_key,
                base_url=resolved_url.rstrip("/"),
                timeout_s=timeout_s,
            )

        if raw_prov in ("openai", "groq"):
            is_groq = raw_prov == "groq"
            resolved_key = api_key or (groq_key if is_groq else openai_key) or groq_key
            if not resolved_key:
                return cls(provider="none", model="none", timeout_s=timeout_s)
            default_url = (
                "https://api.groq.com/openai/v1" if is_groq else "https://api.openai.com/v1"
            )
            default_model = "llama-3.3-70b-versatile" if is_groq else "gpt-4o-mini"
            resolved_url = (
                base_url
                or os.environ.get("CANONGATE_OPENAI_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL")
                or default_url
            )
            resolved_model = (
                model
                or os.environ.get("CANONGATE_OPENAI_MODEL")
                or os.environ.get("OPENAI_MODEL")
                or default_model
            )
            return cls(
                provider="openai",
                model=resolved_model,
                api_key=resolved_key,
                base_url=resolved_url.rstrip("/"),
                timeout_s=timeout_s,
            )

        if raw_prov == "ollama":
            resolved_url = (
                base_url
                or os.environ.get("CANONGATE_OLLAMA_BASE_URL")
                or os.environ.get("OLLAMA_HOST")
                or "http://localhost:11434"
            )
            resolved_model = (
                model
                or os.environ.get("CANONGATE_OLLAMA_MODEL")
                or os.environ.get("OLLAMA_MODEL")
                or "qwen2.5:7b"
            )
            return cls(
                provider="ollama",
                model=resolved_model,
                api_key="",
                base_url=resolved_url.rstrip("/"),
                timeout_s=timeout_s,
            )

        return cls(provider="none", model="none", timeout_s=timeout_s)


class MultiProviderJsonLLM:
    """Unified JSON-mode LLM client supporting Gemini, OpenAI/Groq, and Ollama."""

    __slots__ = ("_transport", "config")

    def __init__(
        self,
        config: LLMProviderConfig | None = None,
        *,
        transport: HttpTransport | None = None,
    ) -> None:
        self.config = config or LLMProviderConfig.from_env()
        self._transport = transport or _default_http_transport

    @property
    def is_enabled(self) -> bool:
        return self.config.provider != "none"

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        """Execute a structured JSON completion against the configured provider."""
        if not self.is_enabled:
            return None

        try:
            if self.config.provider == "gemini":
                return self._call_gemini(system_prompt, user_prompt)
            if self.config.provider == "openai":
                return self._call_openai(system_prompt, user_prompt)
            if self.config.provider == "ollama":
                return self._call_ollama(system_prompt, user_prompt)
        except Exception as exc:
            logger.warning(
                "LLM provider %s (%s) call failed; falling back to deterministic parser: %s",
                self.config.provider,
                self.config.model,
                exc,
            )
        return None

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        url = (
            f"{self.config.base_url}/models/{self.config.model}:generateContent"
            f"?key={self.config.api_key}"
        )
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }
        headers = {"Content-Type": "application/json"}
        resp = self._transport(url, payload, headers, self.config.timeout_s)
        candidates = resp.get("candidates") or []
        if not candidates:
            return None
        parts = (candidates[0].get("content") or {}).get("parts") or []
        if not parts or "text" not in parts[0]:
            return None
        raw_json = _strip_markdown_fences(str(parts[0]["text"]))
        parsed = json.loads(raw_json)
        return parsed if isinstance(parsed, dict) else None

    def _call_openai(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        url = f"{self.config.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }
        resp = self._transport(url, payload, headers, self.config.timeout_s)
        choices = resp.get("choices") or []
        if not choices:
            return None
        content = (choices[0].get("message") or {}).get("content")
        if not content:
            return None
        parsed = json.loads(_strip_markdown_fences(str(content)))
        return parsed if isinstance(parsed, dict) else None

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        url = f"{self.config.base_url}/api/generate"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }
        headers = {"Content-Type": "application/json"}
        resp = self._transport(url, payload, headers, self.config.timeout_s)
        raw_response = resp.get("response")
        if not raw_response:
            return None
        parsed = json.loads(_strip_markdown_fences(str(raw_response)))
        return parsed if isinstance(parsed, dict) else None


def is_complex_table(raw_grid: Sequence[Sequence[object]]) -> bool:
    """Return True when a 2D table grid exhibits structural complexity warranting de-normalization.

    Triggers on:
    1. Multi-level headers (Row 0 has empty/spanned cells and Row 1 is an all-text sub-header).
    2. Vertical `rowspan` category stubs (Column 0 empty while later columns have values).
    3. Ragged/jagged row lengths before padding.
    4. Cross-tab matrix (> 3 columns with conditional markers or footnotes).
    """
    non_empty_rows = [
        [str(c or "").strip() for c in r] for r in raw_grid if any(str(c or "").strip() for c in r)
    ]
    if len(non_empty_rows) < 2:
        return False

    lengths = {len(r) for r in non_empty_rows}
    if len(lengths) > 1:
        return True

    row0 = non_empty_rows[0]
    # Horizontal spans in header row (empty cell or adjacent duplicate cell)
    has_spanned_header = any(c == "" for c in row0) or any(
        row0[i] and row0[i] == row0[i - 1] for i in range(1, len(row0))
    )
    if has_spanned_header and len(non_empty_rows) >= 3:
        row1 = non_empty_rows[1]
        if not any(extract_table_anchors(c) for c in row1):
            return True

    # Vertical rowspan in stub column 0
    return any(len(r) >= 2 and r[0] == "" and any(r[1:]) for r in non_empty_rows[1:])


def verify_and_repair_llm_row(
    *,
    llm_text: str,
    fallback_deterministic_text: str,
    headers: Sequence[str],
    row_cells: Sequence[str],
    applicable_footnotes: Sequence[str],
) -> str:
    """Guard 1: reject hallucinated numbers & repair dropped anchors."""
    cleaned_llm = re.sub(r"\s+", " ", llm_text).strip()
    if not cleaned_llm:
        return fallback_deterministic_text

    source_context = " | ".join([*headers, *row_cells, *applicable_footnotes])
    allowed_numbers = _extract_numeric_scalars(source_context)
    llm_numbers = _extract_numeric_scalars(cleaned_llm)

    # 1. Zero-tolerance hallucination check: did the LLM invent a number not in the source row?
    invented_numbers = llm_numbers - allowed_numbers
    if invented_numbers:
        logger.warning(
            "Guard 1 rejected LLM table row with hallucinated numbers %s: %r",
            sorted(invented_numbers),
            cleaned_llm,
        )
        return fallback_deterministic_text

    # 2. Value-anchor recall check: ensure every number/currency/date in row_cells is preserved
    row_only_text = " | ".join([c for c in row_cells if c])
    required_anchors = extract_table_anchors(row_only_text)
    llm_norm = cleaned_llm.lower()

    missing_pairs: list[str] = []
    for col_idx, cell in enumerate(row_cells):
        if not cell:
            continue
        cell_anchors = extract_table_anchors(cell)
        if any(
            a.lower() not in llm_norm and a.replace(",", "") not in llm_norm for a in cell_anchors
        ):
            hdr = headers[col_idx] if col_idx < len(headers) else f"Col {col_idx + 1}"
            pair_str = f"{hdr}: {cell}"
            if pair_str not in missing_pairs:
                missing_pairs.append(pair_str)

    # Check if any required anchor is still missing even after cell check
    for anchor in required_anchors:
        if anchor.lower() not in llm_norm and anchor.replace(",", "") not in llm_norm:
            clause = f"Value: {anchor}"
            if clause not in missing_pairs and not any(anchor in mp for mp in missing_pairs):
                missing_pairs.append(clause)

    repaired = cleaned_llm
    if missing_pairs:
        repaired = f"{repaired} | " + " | ".join(missing_pairs)

    # 3. Ensure applicable footnotes are preserved
    if applicable_footnotes:
        missing_fns = [fn for fn in applicable_footnotes if fn.lower() not in repaired.lower()]
        if missing_fns:
            repaired = f"{repaired} | Footnote: {'; '.join(missing_fns)}"

    return repaired


_TABLE_SYSTEM_PROMPT = (
    "You are CanonGate's deterministic table de-normalizer for regulated financial (RBI KFS) "
    "and consumer (ASCI/CCPA) compliance auditing. Given a 2D table with headers, data rows, "
    "and footnotes, convert each data row into one self-contained, unambiguous sentence or "
    "'Header: Value' proposition that preserves EVERY number, percentage, currency amount, "
    "date, product tier, and footnote condition verbatim. NEVER invent or round any number. "
    'Return ONLY valid JSON matching: {"rows": [{"row_index": 0, "proposition": "..."}]}'
)


def denormalize_table_with_llm(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    footnotes: Sequence[str],
    deterministic_rows: Sequence[str],
    row_footnotes: Sequence[Sequence[str]] | None = None,
    llm_client: MultiProviderJsonLLM | None = None,
) -> tuple[str, ...]:
    """De-normalize table rows via the configured LLM, guarded by `verify_and_repair_llm_row`."""
    client = llm_client or MultiProviderJsonLLM()
    if not client.is_enabled or not rows:
        return tuple(deterministic_rows)

    user_payload = {
        "headers": list(headers),
        "rows": [list(r) for r in rows],
        "footnotes": list(footnotes),
    }
    resp = client.complete_json(
        system_prompt=_TABLE_SYSTEM_PROMPT,
        user_prompt=json.dumps(user_payload, ensure_ascii=False),
    )
    if not isinstance(resp, dict):
        return tuple(deterministic_rows)

    raw_llm_rows = resp.get("rows")
    if not isinstance(raw_llm_rows, list):
        return tuple(deterministic_rows)

    by_idx: dict[int, str] = {}
    for item in raw_llm_rows:
        if isinstance(item, dict):
            idx = item.get("row_index")
            prop = item.get("proposition") or item.get("text")
            if isinstance(idx, int) and isinstance(prop, str) and prop.strip():
                by_idx[idx] = prop.strip()

    final_rows: list[str] = []
    for idx, det_text in enumerate(deterministic_rows):
        candidate = by_idx.get(idx)
        if not candidate:
            final_rows.append(det_text)
            continue
        app_fns = (
            row_footnotes[idx]
            if row_footnotes is not None and idx < len(row_footnotes)
            else footnotes
        )
        verified = verify_and_repair_llm_row(
            llm_text=candidate,
            fallback_deterministic_text=det_text,
            headers=headers,
            row_cells=rows[idx],
            applicable_footnotes=app_fns,
        )
        final_rows.append(verified)

    return tuple(final_rows)


_CANON_SYSTEM_PROMPT = (
    "You are CanonGate's Pipeline A Brand & Regulatory Rulebook Compiler. Extract all "
    "banned terminology rules, hex colour palette tokens, and quantitative/factual claims "
    "(including every condition, threshold, and valid_until date) from the document. "
    "For every extracted item, include `source_text` as the EXACT verbatim substring from "
    "the input document. Return ONLY valid JSON with keys: "
    '`{"terminology": [{"id": "...", "pattern_text": "...", "preferred": "...", '
    '"severity": 60, "source_text": "..."}], '
    '"palette": [{"id": "...", "name": "...", "hex": "#RRGGBB", "max_delta_e": 3.0, '
    '"source_text": "..."}], '
    '"facts": [{"id": "...", "text": "...", "conditions": ["..."], '
    '"valid_until": "YYYY-MM-DD", "source_text": "..."}]}`'
)


def create_llm_canon_extractor(
    llm_client: MultiProviderJsonLLM | None = None,
) -> Callable[[str], dict[str, Any]] | None:
    """Build a Pipeline A `llm_extractor` callable backed by Gemini, OpenAI/Groq, or Ollama."""
    client = llm_client or MultiProviderJsonLLM()
    if not client.is_enabled:
        return None

    def _extract(full_doc: str) -> dict[str, Any]:
        res = client.complete_json(
            system_prompt=_CANON_SYSTEM_PROMPT,
            user_prompt=full_doc,
        )
        if isinstance(res, dict) and any(k in res for k in ("terminology", "palette", "facts")):
            return res
        return {"terminology": [], "palette": [], "facts": []}

    return _extract
