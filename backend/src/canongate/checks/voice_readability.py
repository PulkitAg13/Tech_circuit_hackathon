r"""Tier 1 Deterministic Check: Voice Profile, Passive-Voice %, & Flesch-Kincaid Readability.

Implements Round 1 Plan §3.3 & §3.4 (`VoiceProfileSchema`):
1. Sentence-length bounds (`max_sentence_words`).
2. Passive-voice percentage (`max_passive_voice_pct`) using `SpacyLinguisticAnalyzer`
   (`auxpass` / `be`-auxiliary + `VBN` past-participle tag sequences).
3. Flesch-Kincaid Grade Level (`max_flesch_kincaid_grade`) via `textstat` when
   installed, with an exact deterministic syllable-counting Flesch-Kincaid formula
   (`0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59`).
4. Brand-voice exemplar similarity against `approved_exemplars` via
   `HybridFactRetriever.embed_text`.
"""

from __future__ import annotations

import re
from typing import ClassVar

import numpy as np

from canongate.domain.ast import Node, NodeKind, TextNode
from canongate.domain.canon import Canon
from canongate.domain.finding import (
    Finding,
    Span,
    Tier,
    Trace,
    VoiceReadabilityEvidence,
)
from canongate.engine.check import Check
from canongate.engine.nlp import default_fact_retriever, default_linguistic_analyzer

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD_RE = re.compile(r"[A-Za-z]+")
_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)
_BE_AUX_SET = frozenset({"am", "is", "are", "was", "were", "be", "been", "being"})


def _count_syllables(word: str) -> int:
    w = word.lower().strip()
    if len(w) <= 3:
        return 1
    if w.endswith(("es", "ed")) and not w.endswith(("ted", "ded", "ses", "zes")):
        w = w[:-2]
    elif w.endswith("e") and not w.endswith("le"):
        w = w[:-1]
    groups = _VOWEL_GROUP_RE.findall(w)
    return max(1, len(groups))


def compute_flesch_kincaid_grade(text: str) -> float:
    """Compute Flesch-Kincaid Grade Level using `textstat` or the exact FK formula."""
    try:
        import textstat  # type: ignore[import-not-found]

        return round(float(textstat.flesch_kincaid_grade(text)), 2)
    except Exception:
        pass

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if _WORD_RE.search(s)]
    words = _WORD_RE.findall(text)
    if not sentences or not words:
        return 0.0

    num_sentences = max(1, len(sentences))
    num_words = len(words)
    num_syllables = sum(_count_syllables(w) for w in words)
    grade = 0.39 * (num_words / num_sentences) + 11.8 * (num_syllables / num_words) - 15.59
    return round(max(0.0, grade), 2)


def _sentence_is_passive(sentence: str) -> bool:
    tokens = default_linguistic_analyzer.parse(sentence)
    for idx, tok in enumerate(tokens):
        if tok.dep in {"auxpass", "nsubjpass"}:
            return True
        if tok.text.lower() in _BE_AUX_SET:
            for nxt in tokens[idx + 1 : idx + 4]:
                if nxt.pos == "VERB" and (
                    nxt.text.lower().endswith(("ed", "en", "wn", "ht"))
                    or nxt.dep in {"ROOT", "conj", "advcl"}
                ):
                    return True
    return False


class VoiceReadabilityCheck(Check):
    """Tier 1 check enforcing `VoiceProfile` sentence length, passive voice %, and FK grade."""

    check_id: ClassVar[str] = "voice.readability"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        if not isinstance(node, TextNode) or canon.voice_profile is None:
            return []

        vp = canon.voice_profile
        text = node.text.strip()
        if not text:
            return []

        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if _WORD_RE.search(s)]
        if not sentences:
            return []

        sentence_word_counts = [len(_WORD_RE.findall(s)) for s in sentences]
        max_words_observed = max(sentence_word_counts) if sentence_word_counts else 0
        passive_count = sum(1 for s in sentences if _sentence_is_passive(s))
        passive_pct = round((passive_count / float(len(sentences))) * 100.0, 2)
        fk_grade = compute_flesch_kincaid_grade(text)

        exemplar_sim = 1.0
        if vp.approved_exemplars:
            draft_vec = default_fact_retriever.embed_text(text)
            sims = [
                float(np.dot(draft_vec, default_fact_retriever.embed_text(ex)))
                for ex in vp.approved_exemplars
            ]
            exemplar_sim = round(max(sims), 4)

        issues: list[str] = []
        if fk_grade > vp.max_flesch_kincaid_grade:
            issues.append(
                f"Flesch-Kincaid grade {fk_grade:.1f} exceeds {vp.max_flesch_kincaid_grade:.1f}"
            )
        if passive_pct > vp.max_passive_voice_pct:
            issues.append(
                f"passive voice {passive_pct:.1f}% exceeds {vp.max_passive_voice_pct:.1f}%"
            )
        if max_words_observed > vp.max_sentence_words:
            issues.append(
                f"sentence length {max_words_observed} words exceeds {vp.max_sentence_words}"
            )

        if not issues:
            return []

        return [
            self.finding(
                node=node,
                locator=Span(start=0, end=len(node.text)),
                severity=vp.severity,
                message=f"Brand voice & readability drift: {'; '.join(issues)}.",
                rule_ref=vp.to_rule_ref(),
                evidence=VoiceReadabilityEvidence(
                    flesch_kincaid_grade=fk_grade,
                    max_flesch_kincaid_grade=vp.max_flesch_kincaid_grade,
                    passive_voice_pct=passive_pct,
                    max_passive_voice_pct=vp.max_passive_voice_pct,
                    max_sentence_words_observed=max_words_observed,
                    max_sentence_words_allowed=vp.max_sentence_words,
                    exemplar_similarity=exemplar_sim,
                ),
                trace=Trace(tier=Tier.DETERMINISTIC),
            )
        ]
