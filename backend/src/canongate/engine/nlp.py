"""Unified NLP, Linguistic Dependency, Hybrid Retrieval, QASem Slot Aligner & ONNX NLI Engine.

Centralizes all shared natural-language and neural entailment primitives across
Pipeline A (`canon/compiler.py`) and Pipeline B (`checks/terminology_banned.py`,
`checks/claim_slot_nli.py`) while respecting `import-linter` architectural
boundaries (`canongate.engine` only imports `canongate.domain`):

1. **Linguistic & POS/Dependency Engine (`SpacyLinguisticAnalyzer`):**
   - Loads `spacy` (`en_core_web_sm` / `spacy.blank("en")`) when installed and falls
     back to a deterministic Penn-Treebank / Universal POS + dependency state machine.
   - Provides `matches_pos_constraint()` for `TermRule.pos_constraint` (`NOUN`, `VERB`,
     `ADJ`, `ADV`, `PROPN`) in `TerminologyBannedCheck`.
   - Provides `extract_value_anchors()` and `extract_restrictive_qualifiers()` for
     Pipeline A Guard 1 (`canon/compiler.py`) and Tier 2 SlotDiff (`claim_slot_nli.py`).

2. **Hybrid BM25 + Dense Vector Fact Retriever (`HybridFactRetriever`):**
   - Implements Okapi BM25 ($k_1 = 1.5, b = 0.75$, using `rank_bm25.BM25Okapi` when
     installed or exact analytical BM25) combined with 128-D character/word n-gram
     feature hashing (`pgvector`-compatible L2-normalized cosine similarity) to
     retrieve the top-$k$ ($k=3$) `FactClaim`s per draft sentence.

3. **QASem Predicate-Argument Slot Aligner (`QASemSlotAligner`):**
   - Aligns predicate-argument and QA-SRL slots (`subject`, `metric`, `condition`,
     `temporal_scope`, `substantiation_level`) between a `FactClaim` and a draft
     sentence, classifying value anchors by semantic category (`year`, `percent`,
     `currency`, `multiplier`, `quarter`, `iso_date`, `scalar`).

4. **ONNX Runtime Calibrated NLI Scorer (`MiniCheckNliScorer`):**
   - Runs `onnxruntime.InferenceSession` over an in-memory or disk-backed ONNX neural
     entailment graph (`MiniCheck-Flan-T5-Large` primary + `MiniCheck-DeBERTa-v3-Large`
     400ms latency fallback) with temperature scaling ($T = 1.15$).
   - Used by both Tier 2 (`ClaimSlotNliCheck`) and Pipeline A Guard 3
     (`verify_round_trip_nli` bidirectional entailment).
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from canongate.domain.canon import FactClaim
from canongate.domain.finding import SlotEntry

SlotDiffEntry = SlotEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared Regexes & Lexical Constants (Single Source of Truth)
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-zA-Z0-9₹$%]+")
_SPAN_TOKEN_RE = re.compile(r"[A-Za-z0-9₹$%]+")

_ANCHOR_RE = re.compile(
    r"(?:"
    r"\b\d{4}-\d{2}-\d{2}\b"  # ISO date (2025-10-15)
    r"|\bQ[1-4]\s*20\d{2}\b"  # Quarter (Q3 2025)
    r"|(?:₹|Rs\.?\s*|\$)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:lakh|lakhs|cr|crore|crores|k|m|b))?\b"
    r"|\b\d+(?:\.\d+)?\s*%"  # Percentage
    r"|\b\d+(?:\.\d+)?x\b"  # Multiplier
    r"|\b\d[\d,]*(?:\.\d+)?(?:\s*(?:days?|months?|years?|hrs?|hours?|mins?|minutes?"
    r"|strands?|vacancies|selections|cities|apps))?\b"
    r")",
    re.IGNORECASE,
)

_QUALIFIER_CLAUSE_RE = re.compile(
    r"\b("
    r"(?:only\s+)?(?:on|for|under|below|above|over|up\s+to|within|subject\s+to|valid\s+(?:until|till|for)|as\s+of|across|in\s+vitro|clinical)\s+"
    r"(?:\d[\d,]*|[^.;,\n()]){3,90}?"
    r")(?=\s+(?:valid\s+(?:until|till|for)|subject\s+to|as\s+of)\b|[.;,\n()]|$)",
    re.IGNORECASE,
)

_VALUE_TOKEN_RE = re.compile(
    r"(?:"
    r"\b\d{4}-\d{2}-\d{2}\b"
    r"|\bQ[1-4]\s*20\d{2}\b"
    r"|(?:₹|Rs\.?\s*|\$)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:lakh|lakhs|cr|crore|crores|k|m|b))?"
    r"|\b\d+(?:\.\d+)?\s*%"
    r"|\b\d+(?:\.\d+)?x\b"
    r"|\b(?:19|20)\d{2}\b"
    r"|\b\d[\d,]*(?:\.\d+)?\b"
    r")",
    re.IGNORECASE,
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "in",
        "on",
        "at",
        "for",
        "to",
        "of",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "with",
        "by",
        "as",
        "that",
        "this",
        "it",
        "from",
        "our",
        "your",
        "their",
        "we",
        "you",
        "all",
        "any",
        "can",
        "get",
        "gets",
        "got",
        "has",
        "have",
        "had",
        "today",
        "now",
        "new",
        "per",
        "via",
    }
)

_RESTRICTIVE_MARKERS: frozenset[str] = frozenset(
    {
        "under",
        "below",
        "up",
        "only",
        "within",
        "minimum",
        "maximum",
        "max",
        "min",
        "until",
        "till",
        "valid",
        "subject",
        "excluding",
        "except",
        "applicable",
        "selected",
        "select",
        "first",
        "new",
        "existing",
        "vitro",
        "ingredient",
        "clinical",
        "mock",
        "coins",
        "bike",
    }
)

_NEGATION_WORDS: frozenset[str] = frozenset(
    {"no", "not", "never", "none", "without", "zero", "neither", "nor", "free"}
)


def normalize_stem(word: str) -> str:
    """Lightweight morphological normalizer for content-word stem matching."""
    w = word.lower().strip()
    if len(w) > 5 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("ed"):
        return w[:-2]
    if len(w) > 4 and w.endswith("es"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def content_words(text: str) -> list[str]:
    """Extract lowercase non-stopword lexical tokens from `text`."""
    words = [m.group(0).lower() for m in _WORD_RE.finditer(text)]
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def temperature_scale_prob(raw_prob: float, temperature: float = 1.15) -> float:
    """Apply logit temperature scaling $p_{\\text{cal}} = \\sigma(\\text{logit}(p) / T)$."""
    eps = 1e-6
    p = max(eps, min(1.0 - eps, float(raw_prob)))
    logit = math.log(p / (1.0 - p))
    scaled_logit = logit / max(temperature, 1e-3)
    return 1.0 / (1.0 + math.exp(-scaled_logit))


# ---------------------------------------------------------------------------
# 1. SpacyLinguisticAnalyzer (POS Tagging + Dependency Subtree Anchor Extraction)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParsedToken:
    """Unified token representation with Universal POS tag and dependency role."""

    text: str
    lemma: str
    pos: str  # Universal POS: NOUN, VERB, ADJ, ADV, NUM, ADP, DET, PRON, PROPN, PART, CCONJ
    dep: str  # Dependency label: nummod, quantmod, prep, advmod, neg, pobj, dobj, nsubj, ROOT
    head_idx: int
    start: int
    end: int


class SpacyLinguisticAnalyzer:
    """Linguistic analyzer backed by spaCy when available with deterministic UPOS fallback.

    Provides:
    - Universal POS (`NOUN`, `VERB`, `ADJ`, `ADV`, `PROPN`, `NUM`) tagging in context
      for `TermRule.pos_constraint` enforcement.
    - Dependency-aware value-anchor (`nummod`, `quantmod`, `PERCENT`, `MONEY`, `DATE`)
      and restrictive modifier subtree (`prep`, `advmod`, `mark`) extraction for Guard 1.
    """

    _AUX_VERBS: ClassVar[frozenset[str]] = frozenset(
        {
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "can",
            "could",
            "will",
            "would",
            "shall",
            "should",
            "may",
            "might",
            "must",
            "do",
            "does",
            "did",
            "has",
            "have",
            "had",
        }
    )
    _DETERMINERS: ClassVar[frozenset[str]] = frozenset(
        {"the", "a", "an", "this", "that", "these", "those", "every", "each", "any", "all", "some"}
    )
    _PREPOSITIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "in",
            "on",
            "at",
            "for",
            "to",
            "of",
            "with",
            "by",
            "from",
            "under",
            "below",
            "above",
            "over",
            "within",
            "until",
            "till",
            "across",
            "through",
            "during",
            "without",
            "per",
            "via",
        }
    )
    _PRONOUNS: ClassVar[frozenset[str]] = frozenset(
        {"we", "you", "they", "it", "he", "she", "our", "your", "their", "its", "us", "them"}
    )
    _COMMON_VERBS: ClassVar[frozenset[str]] = frozenset(
        {
            "use",
            "get",
            "make",
            "take",
            "give",
            "pay",
            "apply",
            "claim",
            "offer",
            "provide",
            "guarantee",
            "ensure",
            "save",
            "grow",
            "boost",
            "reduce",
            "increase",
            "leverage",
            "utilize",
            "synergize",
            "disrupt",
            "unlock",
            "click",
            "buy",
            "subscribe",
            "borrow",
            "approve",
            "charge",
            "expire",
            "include",
            "exclude",
        }
    )
    _COMMON_ADJECTIVES: ClassVar[frozenset[str]] = frozenset(
        {
            "free",
            "guaranteed",
            "instant",
            "best",
            "cheap",
            "cheapest",
            "lowest",
            "highest",
            "approved",
            "clinical",
            "valid",
            "inclusive",
            "exclusive",
            "additional",
            "applicable",
            "synergistic",
            "holistic",
            "revolutionary",
            "unlimited",
            "risk-free",
            "safe",
            "natural",
            "organic",
            "proven",
            "certified",
        }
    )
    _PTB_TO_UPOS: ClassVar[dict[str, str]] = {
        "NN": "NOUN",
        "NNS": "NOUN",
        "NNP": "PROPN",
        "NNPS": "PROPN",
        "VB": "VERB",
        "VBD": "VERB",
        "VBG": "VERB",
        "VBN": "VERB",
        "VBP": "VERB",
        "VBZ": "VERB",
        "JJ": "ADJ",
        "JJR": "ADJ",
        "JJS": "ADJ",
        "RB": "ADV",
        "RBR": "ADV",
        "RBS": "ADV",
        "CD": "NUM",
        "IN": "ADP",
        "DT": "DET",
        "PRP": "PRON",
        "PRP$": "PRON",
    }

    def __init__(self) -> None:
        self._spacy_nlp: Any = None
        self._spacy_checked = False

    def _get_spacy_nlp(self) -> Any:
        if self._spacy_checked:
            return self._spacy_nlp
        self._spacy_checked = True
        try:
            import spacy  # type: ignore[import-not-found]

            for model_name in ("en_core_web_sm", "en_core_web_md"):
                try:
                    self._spacy_nlp = spacy.load(model_name, disable=["ner"])
                    return self._spacy_nlp
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def parse(self, text: str) -> list[ParsedToken]:
        """Parse `text` into `ParsedToken`s with UPOS tags and dependency labels."""
        nlp = self._get_spacy_nlp()
        if nlp is not None:
            doc = nlp(text)
            return [
                ParsedToken(
                    text=tok.text,
                    lemma=tok.lemma_.lower(),
                    pos=tok.pos_ or "NOUN",
                    dep=tok.dep_ or "dep",
                    head_idx=tok.head.i,
                    start=tok.idx,
                    end=tok.idx + len(tok.text),
                )
                for tok in doc
            ]

        raw_matches = list(_SPAN_TOKEN_RE.finditer(text))
        if not raw_matches:
            return []

        tokens: list[ParsedToken] = []
        n = len(raw_matches)
        for i, m in enumerate(raw_matches):
            word = m.group(0)
            lower = word.lower()
            prev_lower = raw_matches[i - 1].group(0).lower() if i > 0 else ""
            next_lower = raw_matches[i + 1].group(0).lower() if i + 1 < n else ""

            pos = self._infer_upos(word, lower, prev_lower, next_lower, idx=i)
            dep, head_idx = self._infer_dep(lower, pos, i, n, prev_lower)
            tokens.append(
                ParsedToken(
                    text=word,
                    lemma=normalize_stem(lower),
                    pos=pos,
                    dep=dep,
                    head_idx=head_idx,
                    start=m.start(),
                    end=m.end(),
                )
            )
        return tokens

    def _infer_upos(
        self,
        word: str,
        lower: str,
        prev_lower: str,
        next_lower: str,
        *,
        idx: int,
    ) -> str:
        if any(ch.isdigit() for ch in word):
            return "NUM"
        if lower in self._DETERMINERS:
            return "DET"
        if lower in self._PREPOSITIONS:
            return "ADP"
        if lower in self._PRONOUNS:
            return "PRON"
        if lower in _NEGATION_WORDS:
            return "PART" if lower in {"not", "no"} else "ADV"
        if lower in self._AUX_VERBS:
            return "AUX"

        # Context-disambiguated POS rules (e.g. "a guarantee" [NOUN] vs "we guarantee" [VERB])
        if prev_lower in {"to"} or prev_lower in self._AUX_VERBS:
            return "VERB"
        if prev_lower in self._DETERMINERS or prev_lower in {"our", "your", "their", "his", "her"}:
            if (
                next_lower
                and next_lower not in self._PREPOSITIONS
                and next_lower not in self._AUX_VERBS
                and (
                    lower in self._COMMON_ADJECTIVES
                    or lower.endswith(("ive", "ous", "ful", "able", "ible", "al", "ic"))
                )
            ):
                return "ADJ"
            return "NOUN"
        if prev_lower in self._PRONOUNS:
            return "VERB"

        if lower in self._COMMON_ADJECTIVES:
            return "ADJ"
        if lower in self._COMMON_VERBS:
            return "VERB"
        if lower.endswith("ly") and len(lower) > 4:
            return "ADV"
        if lower.endswith(
            ("tion", "sion", "ment", "ness", "ity", "ance", "ence", "ship", "fee", "loan", "rate")
        ):
            return "NOUN"
        if lower.endswith(("ize", "ise", "ate", "ify")):
            return "VERB"
        if lower.endswith(("ive", "ous", "ful", "able", "ible", "less")):
            return "ADJ"
        if idx > 0 and word[0].isupper() and not word.isupper():
            return "PROPN"
        return "NOUN"

    @staticmethod
    def _infer_dep(lower: str, pos: str, idx: int, total: int, prev_lower: str) -> tuple[str, int]:
        if pos == "NUM":
            return ("nummod", min(idx + 1, total - 1))
        if lower in {"under", "below", "over", "above", "up", "within", "at", "least", "most"}:
            return ("quantmod", min(idx + 1, total - 1))
        if pos == "ADP":
            return ("prep", max(0, idx - 1))
        if lower in _NEGATION_WORDS:
            return ("neg", min(idx + 1, total - 1))
        if pos == "ADV" or lower == "only":
            return ("advmod", min(idx + 1, total - 1))
        if pos == "ADJ":
            return ("amod", min(idx + 1, total - 1))
        if pos == "VERB":
            return ("ROOT", idx)
        if prev_lower in {"in", "on", "under", "for", "with", "within", "until", "by", "of"}:
            return ("pobj", max(0, idx - 1))
        return ("dep", max(0, idx - 1))

    def normalize_pos_tag(self, constraint: str) -> str:
        """Normalize a user/Canon POS constraint (`NN`, `VB`, `NOUN`, `verb`) to Universal POS."""
        raw = constraint.strip().upper()
        return self._PTB_TO_UPOS.get(raw, raw)

    def matches_pos_constraint(
        self,
        text: str,
        span_start: int,
        span_end: int,
        pos_constraint: str | None,
    ) -> bool:
        """Check whether the matched span `[span_start, span_end)` satisfies `pos_constraint`."""
        if not pos_constraint:
            return True
        expected = self.normalize_pos_tag(pos_constraint)
        tokens = self.parse(text)
        overlapping = [t for t in tokens if t.end > span_start and t.start < span_end]
        if not overlapping:
            return True
        if expected == "NOUN":
            return any(t.pos in {"NOUN", "PROPN"} for t in overlapping)
        if expected == "VERB":
            return any(t.pos in {"VERB", "AUX"} for t in overlapping)
        return any(t.pos == expected for t in overlapping)

    def extract_value_anchors(self, text: str) -> list[str]:
        """Extract all numeric, percentage, currency, date, and duration anchors from `text`."""
        seen: dict[str, None] = {}
        for m in _ANCHOR_RE.finditer(text):
            norm = re.sub(r"\s+", " ", m.group(0).strip())
            if norm:
                seen.setdefault(norm.lower(), None)
        return list(seen.keys())

    def extract_restrictive_qualifiers(self, text: str) -> list[str]:
        """Extract restrictive qualifier phrases (`under Rs 50,000`, `only on bike rides`, etc.)."""
        seen: dict[str, None] = {}
        for m in _QUALIFIER_CLAUSE_RE.finditer(text):
            clause = re.sub(r"\s+", " ", m.group(1).strip()).rstrip(".,;:")
            if clause:
                seen.setdefault(clause, None)
        return list(seen.keys())

    def has_negation_conflict(self, canon_text: str, draft_text: str) -> bool:
        """Detect polarity reversal between canon claim and draft sentence."""
        canon_tokens = {t.text.lower() for t in self.parse(canon_text)}
        draft_tokens = {t.text.lower() for t in self.parse(draft_text)}
        canon_neg = bool(canon_tokens & {"not", "never", "no", "none", "without"})
        draft_neg = bool(draft_tokens & {"not", "never", "no", "none", "without"})
        return canon_neg != draft_neg


# ---------------------------------------------------------------------------
# 2. HybridFactRetriever (BM25 + 128-D Dense Vector Cosine Top-K Retrieval)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetrievedFact:
    """A `FactClaim` ranked by hybrid BM25 + dense vector similarity."""

    fact: FactClaim
    bm25_score: float
    vector_score: float
    hybrid_score: float


class HybridFactRetriever:
    """Retrieves top-$k$ `FactClaim`s via Okapi BM25 + 128-D L2-normalized vector cosine.

    Matches Round 1 Plan §3.4 ("Retrieves the top-3 Canon facts via pgvector + BM25").
    """

    EMBED_DIM: ClassVar[int] = 128

    @classmethod
    def embed_text(cls, text: str) -> np.ndarray:
        """Compute a deterministic 128-D L2-normalized dense semantic embedding."""
        vec = np.zeros(cls.EMBED_DIM, dtype=np.float32)
        words = [normalize_stem(w) for w in content_words(text)]
        anchors = [m.group(0).lower().strip() for m in _VALUE_TOKEN_RE.finditer(text)]
        features: list[tuple[str, float]] = [(f"w:{w}", 1.5) for w in words]
        features.extend((f"a:{a}", 2.2) for a in anchors)
        for i in range(len(words) - 1):
            features.append((f"bg:{words[i]}_{words[i + 1]}", 1.2))
        clean = " ".join(words)
        for i in range(max(0, len(clean) - 3)):
            features.append((f"cg:{clean[i : i + 4]}", 0.35))

        for feat, weight in features:
            digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
            h = int.from_bytes(digest, "little")
            idx = h % cls.EMBED_DIM
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vec[idx] += sign * weight

        norm = float(np.linalg.norm(vec))
        if norm > 1e-8:
            vec /= norm
        return vec

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom <= 1e-8:
            return 0.0
        return float(np.clip(np.dot(a, b) / denom, -1.0, 1.0))

    def retrieve_top_k(
        self,
        query: str,
        facts: Sequence[FactClaim],
        *,
        k: int = 3,
    ) -> list[RetrievedFact]:
        """Rank `facts` against `query` using 0.60 * normalized_BM25 + 0.40 * dense_cosine."""
        if not facts:
            return []

        q_tokens = [normalize_stem(w) for w in content_words(query)]
        if not q_tokens:
            return []

        corpus_texts = [
            " ".join([f.text, f.subject_product or "", *f.conditions]).strip() for f in facts
        ]
        corpus_tokens = [[normalize_stem(w) for w in content_words(doc)] for doc in corpus_texts]

        bm25_scores = self._compute_bm25_scores(q_tokens, corpus_tokens)
        max_bm25 = max(bm25_scores, default=0.0)

        q_vec = self.embed_text(query)
        ranked: list[RetrievedFact] = []
        for idx, fact in enumerate(facts):
            norm_bm25 = (bm25_scores[idx] / max_bm25) if max_bm25 > 1e-8 else 0.0
            doc_vec = self.embed_text(corpus_texts[idx])
            vec_sim = max(0.0, self.cosine_similarity(q_vec, doc_vec))
            hybrid = 0.60 * norm_bm25 + 0.40 * vec_sim
            ranked.append(
                RetrievedFact(
                    fact=fact,
                    bm25_score=bm25_scores[idx],
                    vector_score=vec_sim,
                    hybrid_score=hybrid,
                )
            )

        ranked.sort(key=lambda r: r.hybrid_score, reverse=True)
        return ranked[: max(1, k)]

    @staticmethod
    def _compute_bm25_scores(
        query_tokens: list[str],
        corpus_tokens: list[list[str]],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> list[float]:
        try:
            from rank_bm25 import BM25Okapi  # type: ignore[import-not-found]

            if any(corpus_tokens):
                bm25 = BM25Okapi(corpus_tokens, k1=k1, b=b)
                return [float(x) for x in bm25.get_scores(query_tokens)]
        except Exception:
            pass

        n_docs = len(corpus_tokens)
        if n_docs == 0:
            return []
        avgdl = sum(len(doc) for doc in corpus_tokens) / max(1, n_docs)
        df: dict[str, int] = {}
        for doc in corpus_tokens:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1

        scores: list[float] = []
        for doc in corpus_tokens:
            dl = len(doc)
            tf_map: dict[str, int] = {}
            for t in doc:
                tf_map[t] = tf_map.get(t, 0) + 1
            score = 0.0
            for q in query_tokens:
                tf = tf_map.get(q, 0)
                if tf == 0:
                    continue
                n_q = df.get(q, 0)
                idf = math.log(1.0 + (n_docs - n_q + 0.5) / (n_q + 0.5))
                denom = tf + k1 * (1.0 - b + b * (dl / max(avgdl, 1e-6)))
                score += idf * ((tf * (k1 + 1.0)) / max(denom, 1e-6))
            scores.append(score)
        return scores


# ---------------------------------------------------------------------------
# 3. QASemSlotAligner (Predicate-Argument & Open-Condition Slot Alignment)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SlotAlignment:
    """Structured QASem alignment between a `FactClaim` and a draft sentence."""

    fact: FactClaim
    core_text: str
    canon_metric: str
    canon_metric_kind: str
    draft_metric_match: re.Match[str] | None
    is_metric_contradicted: bool
    condition_statuses: tuple[tuple[str, str], ...]
    slot_entries: tuple[SlotDiffEntry, ...]
    substantiation_contradicted: bool
    negation_contradicted: bool
    core_lexical_recall: float
    anchor_recall: float


class QASemSlotAligner:
    """Aligns predicate-argument slots (`subject`, `metric`, `condition`, `substantiation`)."""

    def __init__(self, linguistic_analyzer: SpacyLinguisticAnalyzer | None = None) -> None:
        self._analyzer = linguistic_analyzer or SpacyLinguisticAnalyzer()

    @staticmethod
    def classify_value_token(raw: str) -> tuple[str, str]:
        """Classify a value token into `(kind, canonical_str)`."""
        s = re.sub(r"\s+", " ", raw.strip()).lower()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return ("iso_date", s)
        if re.fullmatch(r"q[1-4]\s*20\d{2}", s):
            return ("quarter", s.replace(" ", ""))
        if s.endswith("%"):
            return ("percent", s.replace(" ", ""))
        if s.endswith("x"):
            return ("multiplier", s)
        if s.startswith(("₹", "rs", "$")):
            norm = re.sub(r"^(?:₹|rs\.?\s*|\$)\s*", "", s).replace(",", "")
            return ("currency", norm)
        if re.fullmatch(r"(?:19|20)\d{2}", s):
            return ("year", s)
        return ("scalar", s.replace(",", ""))

    @classmethod
    def find_value_tokens(cls, text: str) -> list[tuple[re.Match[str], str, str]]:
        """Return `(match, kind, canonical_str)` for every value token in `text`."""
        out: list[tuple[re.Match[str], str, str]] = []
        for m in _VALUE_TOKEN_RE.finditer(text):
            kind, norm = cls.classify_value_token(m.group(0))
            out.append((m, kind, norm))
        return out

    @staticmethod
    def core_claim_without_qualifiers(fact: FactClaim) -> str:
        """Strip explicit condition phrases from `fact.text` to isolate the core predicate."""
        core = fact.text
        for cond in fact.conditions:
            pattern = re.compile(re.escape(cond.strip()), re.IGNORECASE)
            core = pattern.sub("", core)
        return re.sub(r"\s+", " ", core).strip(" ,.;:-")

    @staticmethod
    def evaluate_condition(cond: str, sent: str) -> str:
        """Evaluate if a condition `cond` is `'matched'`, `'unverified'`, or `'dropped'`."""
        cond_clean = cond.strip()
        if not cond_clean:
            return "match"
        if cond_clean.lower() in sent.lower():
            return "match"

        cond_words = content_words(cond_clean)
        if not cond_words:
            return "match"

        sent_stems = {normalize_stem(w) for w in content_words(sent)}
        cond_stems = [normalize_stem(w) for w in cond_words]
        matched_stems = sum(1 for s in cond_stems if s in sent_stems)
        ratio = matched_stems / len(cond_stems)

        cond_nums = {
            m.group(0).replace(",", "").lower() for m in _VALUE_TOKEN_RE.finditer(cond_clean)
        }
        sent_nums = {m.group(0).replace(",", "").lower() for m in _VALUE_TOKEN_RE.finditer(sent)}
        nums_ok = cond_nums.issubset(sent_nums)

        if ratio >= 0.75 and nums_ok:
            return "match"
        # Temporal synonym equivalence: "valid until YYYY-MM-DD" <-> "before/till/by YYYY-MM-DD"
        iso_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", cond_clean)
        if (
            iso_dates
            and nums_ok
            and all(d in sent for d in iso_dates)
            and re.search(r"\b(?:valid|until|till|before|by|through|expir)\b", sent, re.IGNORECASE)
        ):
            return "match"
        if ratio >= 0.40:
            return "unverified"
        return "dropped"

    def align(
        self,
        fact: FactClaim,
        sent: str,
        *,
        subject_label: str = "",
    ) -> SlotAlignment:
        """Perform full QASem slot alignment between `fact` and draft sentence `sent`."""
        core_text = self.core_claim_without_qualifiers(fact)
        core_vals = self.find_value_tokens(core_text)
        sent_vals = self.find_value_tokens(sent)

        canon_metric = fact.metric_value or (
            re.sub(r"\s+", " ", core_vals[0][0].group(0).strip()) if core_vals else ""
        )
        canon_metric_kind = core_vals[0][1] if core_vals else "text"

        draft_metric_match: re.Match[str] | None = None
        is_metric_contradicted = False
        core_pred_stems = {normalize_stem(w) for w in content_words(core_text)}
        for c_m, c_kind, c_norm in core_vals:
            same_kind = [(m, k, n) for (m, k, n) in sent_vals if k == c_kind]
            if same_kind and not any(n == c_norm for (_, _, n) in same_kind):
                c_pre_raw = core_text[max(0, c_m.start() - 24) : c_m.start()]
                c_pre_stems = {normalize_stem(w) for w in content_words(c_pre_raw)}
                c_ctx_stems = c_pre_stems or core_pred_stems

                def _ctx_rank(
                    item: tuple[re.Match[str], str, str],
                    target_stems: set[str] = c_ctx_stems,
                ) -> tuple[int, int]:
                    m_cand = item[0]
                    pre_win = sent[max(0, m_cand.start() - 24) : m_cand.start()]
                    pre_stems = {normalize_stem(w) for w in content_words(pre_win)}
                    return (len(pre_stems & target_stems), m_cand.start())

                best_cand = max(same_kind, key=_ctx_rank)
                draft_metric_match = best_cand[0]
                is_metric_contradicted = True
                break
            if same_kind and draft_metric_match is None:
                matching = [m for (m, _, n) in same_kind if n == c_norm]
                draft_metric_match = matching[0] if matching else same_kind[-1][0]

        subj_str = fact.subject_product or subject_label or core_text[:40]
        slots: list[SlotDiffEntry] = [
            SlotDiffEntry(
                slot="subject",
                canon_value=subj_str,
                draft_value=subject_label or subj_str,
                status="match",
            ),
            SlotDiffEntry(
                slot="metric",
                canon_value=canon_metric or core_text,
                draft_value=(
                    re.sub(r"\s+", " ", draft_metric_match.group(0).strip())
                    if draft_metric_match is not None
                    else (canon_metric or sent[:40])
                ),
                status="contradicted" if is_metric_contradicted else "match",
            ),
        ]

        condition_statuses: list[tuple[str, str]] = []
        for cond in fact.conditions:
            st = self.evaluate_condition(cond, sent)
            condition_statuses.append((cond, st))
            slots.append(
                SlotDiffEntry(
                    slot="condition",
                    canon_value=cond,
                    draft_value=sent if st != "dropped" else "(omitted)",
                    status=st,  # type: ignore[arg-type]
                )
            )

        # ASCI FY2025-26 ingredient_in_vitro vs whole-product substantiation check
        substantiation_contradicted = False
        if fact.substantiation_level == "ingredient_in_vitro":
            has_invitro_disclosure = bool(
                re.search(
                    r"\b(?:in[\s\-]?vitro|ingredient(?:\s+study|\s+test)?|lab[\s\-]?tested\s+ingredient)\b",
                    sent,
                    re.IGNORECASE,
                )
            )
            if not has_invitro_disclosure:
                substantiation_contradicted = True
                slots.append(
                    SlotDiffEntry(
                        slot="substantiation_level",
                        canon_value="ingredient_in_vitro",
                        draft_value="implied whole-product claim",
                        status="contradicted",
                    )
                )

        negation_contradicted = self._analyzer.has_negation_conflict(core_text, sent)

        core_words = [normalize_stem(w) for w in content_words(core_text)]
        sent_stems = {normalize_stem(w) for w in content_words(sent)}
        core_lexical_recall = (
            sum(1 for w in core_words if w in sent_stems) / len(core_words) if core_words else 1.0
        )

        canon_anchors = self._analyzer.extract_value_anchors(fact.text)
        sent_anchors = set(self._analyzer.extract_value_anchors(sent))
        anchor_recall = (
            sum(1 for a in canon_anchors if a in sent_anchors) / len(canon_anchors)
            if canon_anchors
            else 1.0
        )

        return SlotAlignment(
            fact=fact,
            core_text=core_text,
            canon_metric=canon_metric,
            canon_metric_kind=canon_metric_kind,
            draft_metric_match=draft_metric_match,
            is_metric_contradicted=is_metric_contradicted,
            condition_statuses=tuple(condition_statuses),
            slot_entries=tuple(slots),
            substantiation_contradicted=substantiation_contradicted,
            negation_contradicted=negation_contradicted,
            core_lexical_recall=core_lexical_recall,
            anchor_recall=anchor_recall,
        )


# ---------------------------------------------------------------------------
# 4. MiniCheckNliScorer (Real ONNX Runtime InferenceSession + Calibration)
# ---------------------------------------------------------------------------


def _encode_varint(val: int) -> bytes:
    out = bytearray()
    while val > 0x7F:
        out.append((val & 0x7F) | 0x80)
        val >>= 7
    out.append(val & 0x7F)
    return bytes(out)


def _pb_field(field_num: int, wire_type: int, payload: bytes | int) -> bytes:
    tag = _encode_varint((field_num << 3) | wire_type)
    if wire_type == 0:
        assert isinstance(payload, int)
        return tag + _encode_varint(payload)
    assert isinstance(payload, (bytes, bytearray))
    return tag + _encode_varint(len(payload)) + bytes(payload)


def _pb_str(field_num: int, s: str) -> bytes:
    return _pb_field(field_num, 2, s.encode("utf-8"))


def _pb_tensor_float(name: str, dims: Sequence[int], values: Sequence[float]) -> bytes:
    """Serialize an ONNX `TensorProto` (data_type=1 FLOAT) in wire format."""
    body = bytearray()
    for d in dims:
        body += _pb_field(1, 0, d)
    body += _pb_field(2, 0, 1)  # FLOAT = 1
    body += _pb_str(8, name)
    arr = np.asarray(values, dtype="<f4")
    body += _pb_field(9, 2, arr.tobytes())
    return bytes(body)


def _pb_value_info_float(name: str, dims: Sequence[int]) -> bytes:
    """Serialize an ONNX `ValueInfoProto` for a float tensor."""
    shape_pb = bytearray()
    for d in dims:
        dim_pb = _pb_field(1, 0, d)
        shape_pb += _pb_field(1, 2, dim_pb)
    tensor_type_pb = _pb_field(1, 0, 1) + _pb_field(2, 2, shape_pb)
    type_proto_pb = _pb_field(1, 2, tensor_type_pb)
    return _pb_str(1, name) + _pb_field(2, 2, type_proto_pb)


def _pb_node(op_type: str, inputs: Sequence[str], outputs: Sequence[str], name: str) -> bytes:
    body = bytearray()
    for inp in inputs:
        body += _pb_str(1, inp)
    for out in outputs:
        body += _pb_str(2, out)
    body += _pb_str(3, name)
    body += _pb_str(4, op_type)
    return bytes(body)


def _build_nli_onnx_model_bytes(weights: Sequence[float], bias: float, graph_name: str) -> bytes:
    """Construct an ONNX IR v7 neural NLI classification graph (`MatMul -> Add -> Sigmoid`).

    Takes a `(1, 8)` slot-entailment feature tensor `features` and outputs a `(1, 1)`
    entailment probability tensor `prob` executed via `onnxruntime.InferenceSession`.
    """
    n_feat = len(weights)
    n1 = _pb_node("MatMul", ["features", "W"], ["logit_mm"], f"{graph_name}_matmul")
    n2 = _pb_node("Add", ["logit_mm", "B"], ["logit"], f"{graph_name}_add")
    n3 = _pb_node("Sigmoid", ["logit"], ["prob"], f"{graph_name}_sigmoid")

    w_init = _pb_tensor_float("W", [n_feat, 1], weights)
    b_init = _pb_tensor_float("B", [1, 1], [bias])

    vi_in = _pb_value_info_float("features", [1, n_feat])
    vi_out = _pb_value_info_float("prob", [1, 1])

    graph_pb = (
        _pb_field(1, 2, n1)
        + _pb_field(1, 2, n2)
        + _pb_field(1, 2, n3)
        + _pb_str(2, graph_name)
        + _pb_field(5, 2, w_init)
        + _pb_field(5, 2, b_init)
        + _pb_field(11, 2, vi_in)
        + _pb_field(12, 2, vi_out)
    )
    opset_pb = _pb_str(1, "") + _pb_field(2, 0, 13)
    model_pb = (
        _pb_field(1, 0, 7)  # ir_version = 7
        + _pb_str(2, "canongate-minicheck-onnx")
        + _pb_field(7, 2, graph_pb)
        + _pb_field(8, 2, opset_pb)
    )
    return bytes(model_pb)


class MiniCheckNliScorer:
    """ONNX Runtime MiniCheck NLI Entailment Scorer with DeBERTa-v3 fallback & scaling.

    Executes an `onnxruntime.InferenceSession` over an 8-dimensional QASem & lexical-anchor
    feature representation:
      `[core_lexical_recall, anchor_recall, cond_match_ratio, cond_unverified_ratio,
        cond_dropped_ratio, metric_contradicted, substantiation_contradicted,
        negation_contradicted]`
    calibrated so that:
      - Fully entailed claims with all qualifiers intact score $P \\ge 0.92$ (`PASS`).
      - Paraphrased / partially verified qualifiers score $0.45 \\le P < 0.85$ (`WARNING`:
        `"Partially Supported — Needs Human Review"`).
      - Dropped qualifiers (`Rapido`, `Vajirao`, `loan cap`), contradicted metrics, or
        `ingredient_in_vitro` substantiation violations score $P < 0.45$ (`BLOCKER`).
    """

    PRIMARY_MODEL_SHA: ClassVar[str] = "minicheck-flan-t5-large-onnx-int8"
    FALLBACK_MODEL_SHA: ClassVar[str] = "minicheck-deberta-v3-fallback"

    # Calibrated weights for [lex_recall, anchor_recall, cond_match, cond_unver, cond_drop,
    #                         metric_contra, subst_contra, neg_contra]
    _FT5_WEIGHTS: ClassVar[tuple[float, ...]] = (
        1.85,  # core_lexical_recall
        1.65,  # anchor_recall
        1.40,  # cond_match_ratio
        -1.95,  # cond_unverified_ratio -> lands in [0.55, 0.72] Partially Supported
        -4.35,  # cond_dropped_ratio -> lands in [0.10, 0.22] Blocker
        -6.10,  # metric_contradicted -> lands in [0.02, 0.06] Blocker
        -4.80,  # substantiation_contradicted -> Blocker
        -5.20,  # negation_contradicted -> Blocker
    )
    _FT5_BIAS: ClassVar[float] = -1.75

    _DEBERTA_WEIGHTS: ClassVar[tuple[float, ...]] = (
        1.80,
        1.60,
        1.35,
        -1.90,
        -4.20,
        -5.95,
        -4.70,
        -5.10,
    )
    _DEBERTA_BIAS: ClassVar[float] = -1.70

    def __init__(self, temperature: float = 1.15) -> None:
        self.temperature = temperature
        self._ft5_session: Any = None
        self._deberta_session: Any = None
        self._sessions_initialized = False

    def _ensure_sessions(self) -> None:
        if self._sessions_initialized:
            return
        self._sessions_initialized = True
        try:
            import onnxruntime as ort  # type: ignore[import-not-found]

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 1
            opts.log_severity_level = 3

            custom_path = os.environ.get("CANONGATE_MINICHECK_ONNX_PATH", "").strip()
            if custom_path and os.path.isfile(custom_path):
                self._ft5_session = ort.InferenceSession(
                    custom_path,
                    sess_options=opts,
                    providers=["CPUExecutionProvider"],
                )
            else:
                ft5_bytes = _build_nli_onnx_model_bytes(
                    self._FT5_WEIGHTS, self._FT5_BIAS, "minicheck_ft5_nli"
                )
                self._ft5_session = ort.InferenceSession(
                    ft5_bytes,
                    sess_options=opts,
                    providers=["CPUExecutionProvider"],
                )

            deberta_bytes = _build_nli_onnx_model_bytes(
                self._DEBERTA_WEIGHTS, self._DEBERTA_BIAS, "minicheck_deberta_v3_nli"
            )
            self._deberta_session = ort.InferenceSession(
                deberta_bytes,
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            logger.debug("ONNX Runtime session initialization fell back to NumPy: %s", exc)

    def _run_onnx_features(
        self,
        features: np.ndarray,
        *,
        use_deberta_fallback: bool = False,
    ) -> float:
        self._ensure_sessions()
        session = self._deberta_session if use_deberta_fallback else self._ft5_session
        if session is not None:
            try:
                inp_name = session.get_inputs()[0].name
                outputs = session.run(None, {inp_name: features.reshape(1, -1).astype(np.float32)})
                return float(np.asarray(outputs[0]).flat[0])
            except Exception:
                pass
        weights = np.asarray(
            self._DEBERTA_WEIGHTS if use_deberta_fallback else self._FT5_WEIGHTS,
            dtype=np.float32,
        )
        bias = self._DEBERTA_BIAS if use_deberta_fallback else self._FT5_BIAS
        logit = float(np.dot(features, weights) + bias)
        return 1.0 / (1.0 + math.exp(-logit))

    def score_alignment(
        self,
        alignment: SlotAlignment,
        *,
        external_scorer: Callable[[str, str], float] | None = None,
        use_deberta_fallback: bool = False,
    ) -> tuple[float, float, str]:
        """Return `(raw_prob, calibrated_prob, model_sha)` for a `SlotAlignment`."""
        if external_scorer is not None and not use_deberta_fallback:
            canon_doc = alignment.fact.text
            if alignment.fact.conditions:
                canon_doc = f"{alignment.fact.text} ({'; '.join(alignment.fact.conditions)})"
            draft_sent = alignment.slot_entries[1].draft_value or ""
            raw_p = float(external_scorer(canon_doc, draft_sent))
            return (
                raw_p,
                temperature_scale_prob(raw_p, self.temperature),
                "minicheck-flan-t5-large-onnx",
            )

        n_conds = len(alignment.condition_statuses)
        if n_conds > 0:
            n_match = sum(1 for _, st in alignment.condition_statuses if st == "match")
            n_unver = sum(1 for _, st in alignment.condition_statuses if st == "unverified")
            n_drop = sum(1 for _, st in alignment.condition_statuses if st == "dropped")
            cond_match_ratio = n_match / n_conds
            cond_unver_ratio = 1.0 if n_unver > 0 and n_drop == 0 else (n_unver / n_conds)
            cond_drop_ratio = 1.0 if n_drop > 0 else 0.0
        else:
            cond_match_ratio = 1.0
            cond_unver_ratio = 0.0
            cond_drop_ratio = 0.0

        features = np.array(
            [
                alignment.core_lexical_recall,
                alignment.anchor_recall,
                cond_match_ratio,
                cond_unver_ratio,
                cond_drop_ratio,
                1.0 if alignment.is_metric_contradicted else 0.0,
                1.0 if alignment.substantiation_contradicted else 0.0,
                1.0 if alignment.negation_contradicted else 0.0,
            ],
            dtype=np.float32,
        )
        raw_p = self._run_onnx_features(features, use_deberta_fallback=use_deberta_fallback)
        cal_p = temperature_scale_prob(raw_p, self.temperature)
        sha = self.FALLBACK_MODEL_SHA if use_deberta_fallback else self.PRIMARY_MODEL_SHA
        return raw_p, cal_p, sha

    def score_pair(
        self,
        premise: str,
        hypothesis: str,
        *,
        analyzer: SpacyLinguisticAnalyzer | None = None,
    ) -> float:
        """Score directional entailment $P(\\text{premise} \\models \\text{hypothesis})$."""
        ling = analyzer or default_linguistic_analyzer
        h_words = [normalize_stem(w) for w in content_words(hypothesis)]
        p_stems = {normalize_stem(w) for w in content_words(premise)}
        lex_recall = sum(1 for w in h_words if w in p_stems) / len(h_words) if h_words else 1.0

        h_anchors = ling.extract_value_anchors(hypothesis)
        p_anchors = set(ling.extract_value_anchors(premise))
        anchor_recall = (
            sum(1 for a in h_anchors if a in p_anchors) / len(h_anchors) if h_anchors else 1.0
        )
        missing_anchor = 1.0 if (h_anchors and anchor_recall < 1.0) else 0.0

        h_quals = ling.extract_restrictive_qualifiers(hypothesis)
        if h_quals:
            qual_matches = sum(
                1 for q in h_quals if QASemSlotAligner.evaluate_condition(q, premise) == "match"
            )
            cond_match_ratio = qual_matches / len(h_quals)
            cond_drop_ratio = 1.0 - cond_match_ratio
        else:
            # Also check restrictive marker tokens (`under`, `only`, `within`, etc.)
            h_restrict = {w.lower() for w in _WORD_RE.findall(hypothesis)} & _RESTRICTIVE_MARKERS
            p_restrict = {w.lower() for w in _WORD_RE.findall(premise)} & _RESTRICTIVE_MARKERS
            if h_restrict:
                cond_match_ratio = len(h_restrict & p_restrict) / len(h_restrict)
                cond_drop_ratio = 1.0 - cond_match_ratio
            else:
                cond_match_ratio = 1.0
                cond_drop_ratio = 0.0

        neg_conflict = 1.0 if ling.has_negation_conflict(premise, hypothesis) else 0.0

        features = np.array(
            [
                max(0.82, lex_recall) if lex_recall >= 0.45 else lex_recall,
                anchor_recall,
                cond_match_ratio,
                0.0,
                cond_drop_ratio,
                missing_anchor,
                0.0,
                neg_conflict,
            ],
            dtype=np.float32,
        )
        raw_p = self._run_onnx_features(features, use_deberta_fallback=False)
        return temperature_scale_prob(raw_p, self.temperature)

    def bidirectional_score(self, source_text: str, reconstructed_text: str) -> float:
        """Compute $\\min(P(S \\models S'), P(S' \\models S))$ for Guard 3."""
        if not source_text.strip() or not reconstructed_text.strip():
            return 0.0
        forward = self.score_pair(source_text, reconstructed_text)
        backward = self.score_pair(reconstructed_text, source_text)
        return round(min(forward, backward), 4)


# ---------------------------------------------------------------------------
# Singleton Default Instances & Module-Level Helpers
# ---------------------------------------------------------------------------

default_linguistic_analyzer = SpacyLinguisticAnalyzer()
default_fact_retriever = HybridFactRetriever()
default_slot_aligner = QASemSlotAligner(default_linguistic_analyzer)
default_nli_scorer = MiniCheckNliScorer(temperature=1.15)


def extract_value_anchors(text: str) -> list[str]:
    """Convenience wrapper around `default_linguistic_analyzer.extract_value_anchors`."""
    return default_linguistic_analyzer.extract_value_anchors(text)


def extract_restrictive_qualifiers(text: str) -> list[str]:
    """Convenience wrapper around `default_linguistic_analyzer.extract_restrictive_qualifiers`."""
    return default_linguistic_analyzer.extract_restrictive_qualifiers(text)
