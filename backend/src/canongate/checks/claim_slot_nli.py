"""Tier 2 Calibrated Fact Entailment & Slot-Level Alignment (`claim.slot_nli`).

Implements the full Tier 2 verification pipeline from Round 1 Plan §3.4 & §4.1:
1. **Top-3 Hybrid `pgvector + BM25` Retrieval (`HybridFactRetriever`):**
   Ranks `Canon.facts` via Okapi BM25 ($k_1 = 1.5, b = 0.75$) + 128-D L2-normalized
   dense vector cosine similarity to retrieve the top-3 candidate facts per sentence.
2. **QASem & spaCy Predicate-Argument Slot Alignment (`QASemSlotAligner`):**
   Aligns draft sentences against retrieved `FactClaim`s across five semantic slots
   (`subject`, `metric`, `condition`, `temporal_scope`, `substantiation_level`),
   classifying value anchors by semantic category (`year`, `percent`, `currency`,
   `multiplier`, `quarter`, `iso_date`, `scalar`) and catching ASCI FY2025-26
   `ingredient_in_vitro` vs. whole-product clinical substantiation violations.
3. **ONNX Runtime `MiniCheck-Flan-T5-Large` & `MiniCheck-DeBERTa-v3-Large` Fallback:**
   Evaluates directional entailment $P(\\text{Canon} \\models \\text{Draft})$ via
   `MiniCheckNliScorer` (`onnxruntime.InferenceSession` + temperature scaling $T=1.15$).
   If `run_async()` exceeds the 400ms latency budget, automatically falls back to the
   lightweight `MiniCheck-DeBERTa-v3-Large` ONNX model (`minicheck-deberta-v3-fallback`).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import ClassVar

from canongate.domain.ast import Node, NodeKind, TextNode
from canongate.domain.canon import Canon, FactClaim
from canongate.domain.finding import (
    Finding,
    Replace,
    SlotDiffEvidence,
    Span,
    Suggestion,
    Tier,
    Trace,
)
from canongate.engine.check import Check
from canongate.engine.nlp import (
    QASemSlotAligner,
    content_words,
    default_fact_retriever,
    default_nli_scorer,
    default_slot_aligner,
    normalize_stem,
    temperature_scale_prob,
)

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

__all__ = ["ClaimSlotNliCheck", "temperature_scale_prob"]


class ClaimSlotNliCheck(Check):
    check_id: ClassVar[str] = "claim.slot_nli"
    check_version: ClassVar[str] = "2.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})
    timeout_s: ClassVar[float] = 10.0

    # Optional pluggable external NLI scorer `(doc, claim) -> float`
    _external_scorer: ClassVar[Callable[[str, str], float] | None] = None

    @classmethod
    def set_external_scorer(cls, scorer: Callable[[str, str], float] | None) -> None:
        """Register an optional custom MiniCheck or ONNX Runtime entailment scorer."""
        cls._external_scorer = scorer

    async def run_async(self, node: Node, canon: Canon) -> list[Finding]:
        """Run with 400ms latency guard; auto-falls back to DeBERTa-v3 ONNX if exceeded."""
        ext = ClaimSlotNliCheck.__dict__.get("_external_scorer")
        if ext is not None:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(
                        self._run_with_scorer,
                        node,
                        canon,
                        scorer=ext,
                        fallback_used=False,
                    ),
                    timeout=0.40,
                )
            except TimeoutError:
                return await asyncio.to_thread(
                    self._run_with_scorer,
                    node,
                    canon,
                    scorer=None,
                    fallback_used=True,
                )
        return await asyncio.to_thread(
            self._run_with_scorer,
            node,
            canon,
            scorer=None,
            fallback_used=False,
        )

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        return self._run_with_scorer(
            node,
            canon,
            scorer=ClaimSlotNliCheck.__dict__.get("_external_scorer"),
            fallback_used=False,
        )

    def _run_with_scorer(
        self,
        node: Node,
        canon: Canon,
        *,
        scorer: Callable[[str, str], float] | None,
        fallback_used: bool,
    ) -> list[Finding]:
        assert isinstance(node, TextNode)
        if not canon.facts:
            return []

        findings: list[Finding] = []
        cursor = 0
        for raw_sent in _SENT_SPLIT_RE.split(node.text):
            sent = raw_sent.strip()
            if not sent:
                continue
            sent_start = node.text.find(sent, cursor)
            if sent_start == -1:
                sent_start = cursor
            sent_end = sent_start + len(sent)
            cursor = sent_end

            sent_stems = {normalize_stem(w) for w in content_words(sent)}
            if not sent_stems:
                continue

            # Step 1: Retrieve top-3 candidate Canon facts via Hybrid BM25 + Dense Vector
            top_candidates = default_fact_retriever.retrieve_top_k(sent, canon.facts, k=3)
            for candidate in top_candidates:
                fact = candidate.fact
                core_text = QASemSlotAligner.core_claim_without_qualifiers(fact)
                fact_words = content_words(core_text)
                if not fact_words:
                    continue
                fact_stems = [normalize_stem(w) for w in fact_words]
                overlap = [
                    w for w, s in zip(fact_words, fact_stems, strict=False) if s in sent_stems
                ]
                min_req = (
                    len(fact_words) if len(fact_words) <= 3 else max(3, int(len(fact_words) * 0.6))
                )
                if len(overlap) < min_req:
                    continue

                finding = self._evaluate_sentence_against_fact(
                    node=node,
                    canon=canon,
                    fact=fact,
                    sent=sent,
                    sent_start=sent_start,
                    sent_end=sent_end,
                    subject_label=" ".join(overlap[:3]),
                    scorer=scorer,
                    fallback_used=fallback_used,
                )
                if finding is not None:
                    findings.append(finding)

        return findings

    def _evaluate_sentence_against_fact(
        self,
        *,
        node: TextNode,
        canon: Canon,
        fact: FactClaim,
        sent: str,
        sent_start: int,
        sent_end: int,
        subject_label: str,
        scorer: Callable[[str, str], float] | None,
        fallback_used: bool,
    ) -> Finding | None:
        # Step 2: Align QASem predicate-argument slots & compute feature vector
        alignment = default_slot_aligner.align(fact, sent, subject_label=subject_label)
        _, cal_p, model_sha = default_nli_scorer.score_alignment(
            alignment,
            external_scorer=scorer,
            use_deberta_fallback=fallback_used,
        )

        # 1. Direct metric / year / number contradiction in the core claim
        if alignment.is_metric_contradicted and alignment.draft_metric_match is not None:
            draft_match = alignment.draft_metric_match
            draft_val = re.sub(r"\s+", " ", draft_match.group(0).strip())
            canon_val = alignment.canon_metric
            val_span = Span(
                start=sent_start + draft_match.start(),
                end=sent_start + draft_match.end(),
            )
            return self.finding(
                node=node,
                locator=val_span,
                severity=80,
                message=(
                    f"Factual contradiction against Canon rule {fact.id!r}: "
                    f"draft states {draft_val!r}, but approved fact is {canon_val!r} "
                    f"({fact.text!r})."
                ),
                rule_ref=canon.to_rule_ref(fact),
                evidence=SlotDiffEvidence(
                    entailment_prob=cal_p,
                    canon_claim_id=fact.id,
                    canon_text=fact.text,
                    slots=alignment.slot_entries[:2],
                ),
                suggestion=Suggestion(
                    label=f"Replace {draft_val!r} with approved {canon_val!r}",
                    replacements=(Replace(span=val_span, replacement=canon_val),),
                ),
                trace=Trace(
                    tier=Tier.NLI,
                    ai_used=True,
                    model_sha=model_sha,
                ),
            )

        # If core claim has a numeric/percentage metric, require that metric to be present in sent
        if alignment.canon_metric and alignment.canon_metric.lower() not in sent.lower():
            return None

        dropped_conds = [c for c, st in alignment.condition_statuses if st == "dropped"]
        unverified_conds = [c for c, st in alignment.condition_statuses if st == "unverified"]

        if (
            not dropped_conds
            and not unverified_conds
            and not alignment.substantiation_contradicted
            and not alignment.negation_contradicted
            and cal_p >= 0.85
        ):
            return None

        # Avoid duplicate flagging when the draft explicitly wrote a conflicting upper bound
        # (which is proven with a formal counterexample by claim.algebra)
        if (
            not alignment.substantiation_contradicted
            and any(
                re.search(r"\b(?:under|up\s+to|below)\b", c, re.IGNORECASE) for c in dropped_conds
            )
            and re.search(
                r"\b(?:under|up\s+to|below|loans?\s+of)\s+(?:₹|Rs\.?\s*|\$)?\s*\d",
                sent,
                re.IGNORECASE,
            )
        ):
            return None

        sent_span = Span(start=sent_start, end=sent_end)
        missing_all = [*dropped_conds, *unverified_conds]
        if alignment.substantiation_contradicted and not missing_all:
            missing_all = ["in-vitro ingredient study only"]
        qual_str = "; ".join(missing_all) if missing_all else "approved scope"
        stripped_sent = sent.rstrip(".!?")
        punct = sent[len(stripped_sent) :] or "."
        repaired_sent = f"{stripped_sent} ({qual_str}){punct}"

        # Calibrated uncertainty routing per Figure 5 of Round 1 Plan (0.45 <= P < 0.85 -> Warning)
        if (
            0.45 <= cal_p < 0.85
            and not alignment.substantiation_contradicted
            and not alignment.negation_contradicted
        ):
            return self.finding(
                node=node,
                locator=sent_span,
                severity=40,
                message=(
                    f"Partially Supported — Needs Human Review ({fact.id}): draft paraphrases "
                    f"condition(s) {qual_str!r} with calibrated entailment P = {cal_p:.2f}."
                ),
                rule_ref=canon.to_rule_ref(fact),
                evidence=SlotDiffEvidence(
                    entailment_prob=cal_p,
                    canon_claim_id=fact.id,
                    canon_text=fact.text,
                    slots=alignment.slot_entries,
                ),
                suggestion=Suggestion(
                    label=f"Clarify exact qualifier ({qual_str})",
                    replacements=(Replace(span=sent_span, replacement=repaired_sent),),
                ),
                trace=Trace(
                    tier=Tier.NLI,
                    ai_used=True,
                    model_sha=model_sha,
                ),
            )

        metric_val = alignment.canon_metric or alignment.core_text
        msg = (
            f"Ingredient-vs-product substantiation violation ({fact.id}): draft claims clinical "
            f"product proof for an in-vitro ingredient study and omits {qual_str!r}."
            if alignment.substantiation_contradicted
            else (
                f"Qualifier-stripping violation ({fact.id}): draft asserts {metric_val!r} "
                f"but omits mandatory condition(s): {qual_str!r}."
            )
        )
        return self.finding(
            node=node,
            locator=sent_span,
            severity=85 if alignment.substantiation_contradicted else 75,
            message=msg,
            rule_ref=canon.to_rule_ref(fact),
            evidence=SlotDiffEvidence(
                entailment_prob=cal_p,
                canon_claim_id=fact.id,
                canon_text=fact.text,
                slots=alignment.slot_entries,
            ),
            suggestion=Suggestion(
                label=f"Append required qualifier ({qual_str})",
                replacements=(Replace(span=sent_span, replacement=repaired_sent),),
            ),
            trace=Trace(
                tier=Tier.NLI,
                ai_used=True,
                model_sha=model_sha,
            ),
        )
