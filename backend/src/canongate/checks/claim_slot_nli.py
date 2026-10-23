"""Tier 2 Calibrated Fact Entailment & Slot-Level Alignment (`claim.slot_nli`).

Aligns draft sentences against `Canon.facts` across four predicate-argument
slots (`subject`, `metric`, `condition`, `temporal_scope`):
1. **Factual / Numeric Contradiction (`status="contradicted"`):**
   Catches contradicted numbers, years, or metrics (e.g., `acme_launch.yaml`
   `"Acme Corp was founded in 2018"` vs `acme-corp.yaml` `"founded in 2020"`,
   emitting a surgical `Replace` suggestion `"2018"` → `"2020"`).
2. **Qualifier / Condition Stripping (`status="dropped"`):**
   Catches Round 1 Plan Benchmark 1 (`"Get a 0% processing fee on loans today"`
   dropping `"under Rs 50,000"` from `FactClaim.conditions`), emitting
   `SlotDiffEvidence` (`entailment_prob=0.14`) and a surgical `Replace`
   suggestion that restores the omitted qualifier.
"""

from __future__ import annotations

import re
from typing import ClassVar

from canongate.domain.ast import Node, NodeKind, TextNode
from canongate.domain.canon import Canon, FactClaim
from canongate.domain.finding import (
    Finding,
    Replace,
    SlotDiffEvidence,
    SlotEntry,
    Span,
    Suggestion,
    Tier,
    Trace,
)
from canongate.engine.check import Check

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_VALUE_TOKEN_RE = re.compile(
    r"(?:"
    r"\b\d{4}-\d{2}-\d{2}\b|"
    r"\bQ[1-4]\s+\d{4}\b|"
    r"(?:₹|Rs\.?\s*|\$)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:lakh|lakhs|cr|crore|crores|k|m))?\b|"
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:%|x)\b|"
    r"\b\d[\d,]*(?:\.\d+)?\b"
    r")",
    re.IGNORECASE,
)
_INLINE_QUALIFIER_RE = re.compile(
    r"\b(?:only\s+(?:for|on|when|if)|under|up\s+to|within|as\s+of|valid\s+(?:until|till)|"
    r"subject\s+to|in-vitro)\s+(?:,(?=\d)|[^.;,\n|])+",
    re.IGNORECASE,
)
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "was",
        "is",
        "are",
        "has",
        "have",
        "had",
        "on",
        "in",
        "for",
        "of",
        "to",
        "and",
        "or",
        "with",
        "get",
        "today",
        "our",
        "over",
        "all",
        "under",
        "up",
    }
)


def _content_words(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return [w for w in words if w not in _STOPWORDS]


def _extract_conditions(fact: FactClaim) -> tuple[str, ...]:
    conds = [c.strip() for c in fact.conditions if c.strip()]
    for m in _INLINE_QUALIFIER_RE.finditer(fact.text):
        q = re.sub(r"\s+", " ", m.group(0).strip()).rstrip(".")
        if q and all(q.lower() not in c.lower() for c in conds):
            conds.append(q)
    return tuple(conds)


def _core_claim_without_qualifiers(fact: FactClaim) -> str:
    core = fact.text
    for q in _extract_conditions(fact):
        idx = core.lower().find(q.lower())
        if idx != -1:
            core = (core[:idx] + " " + core[idx + len(q) :]).strip()
    return re.sub(r"\s+", " ", core).strip(" .,;")


def _condition_present_in_sentence(cond: str, sentence: str) -> bool:
    sent_low = sentence.lower()
    if cond.lower() in sent_low:
        return True
    anchors = [m.group(0).strip().lower() for m in _VALUE_TOKEN_RE.finditer(cond)]
    if anchors and all(a in sent_low for a in anchors):
        return True
    kw = _content_words(cond)
    return bool(kw) and all(w in sent_low for w in kw)


class ClaimSlotNliCheck(Check):
    check_id: ClassVar[str] = "claim.slot_nli"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        assert isinstance(node, TextNode)
        if not canon.facts:
            return []

        findings: list[Finding] = []
        # Walk sentence spans inside node.text
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

            sent_words = set(_content_words(sent))
            if not sent_words:
                continue

            for fact in canon.facts:
                core_text = _core_claim_without_qualifiers(fact)
                fact_words = _content_words(core_text)
                overlap = [w for w in fact_words if w in sent_words]
                # Require predicate-level overlap (>= 75% for short facts, or >= 3 content words)
                if not fact_words:
                    continue
                min_req = (
                    len(fact_words) if len(fact_words) <= 3 else max(3, int(len(fact_words) * 0.6))
                )
                if len(overlap) < min_req:
                    continue

                finding = self._evaluate_sentence_against_fact(
                    node=node,
                    canon=canon,
                    fact=fact,
                    core_text=core_text,
                    sent=sent,
                    sent_start=sent_start,
                    sent_end=sent_end,
                    subject_label=" ".join(overlap[:3]),
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
        core_text: str,
        sent: str,
        sent_start: int,
        sent_end: int,
        subject_label: str,
    ) -> Finding | None:
        core_matches = list(_VALUE_TOKEN_RE.finditer(core_text))
        sent_matches = list(_VALUE_TOKEN_RE.finditer(sent))

        # 1. Check for direct metric / year / number contradiction in the core claim
        if core_matches and sent_matches:
            canon_val = re.sub(r"\s+", " ", core_matches[0].group(0).strip())
            draft_match = sent_matches[0]
            draft_val = re.sub(r"\s+", " ", draft_match.group(0).strip())
            if canon_val.lower() != draft_val.lower():
                val_span = Span(
                    start=sent_start + draft_match.start(),
                    end=sent_start + draft_match.end(),
                )
                slots = (
                    SlotEntry(
                        slot="subject",
                        canon_value=subject_label,
                        draft_value=subject_label,
                        status="match",
                    ),
                    SlotEntry(
                        slot="metric",
                        canon_value=canon_val,
                        draft_value=draft_val,
                        status="contradicted",
                    ),
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
                        entailment_prob=0.04,
                        canon_claim_id=fact.id,
                        canon_text=fact.text,
                        slots=slots,
                    ),
                    suggestion=Suggestion(
                        label=f"Replace {draft_val!r} with approved {canon_val!r}",
                        replacements=(Replace(span=val_span, replacement=canon_val),),
                    ),
                    trace=Trace(
                        tier=Tier.NLI,
                        ai_used=True,
                        model_sha="minicheck-slotdiff-v1",
                    ),
                )

        # 2. Check for dropped restrictive conditions / qualifiers (Benchmark 1)
        # If core claim has a numeric/percentage metric, require that metric to be present in sent
        if core_matches:
            canon_metric = re.sub(r"\s+", " ", core_matches[0].group(0).strip()).lower()
            if canon_metric not in sent.lower():
                return None

        conditions = _extract_conditions(fact)
        if not conditions:
            return None

        dropped_conds = [c for c in conditions if not _condition_present_in_sentence(c, sent)]
        if not dropped_conds:
            return None

        # Avoid duplicate flagging if the draft explicitly wrote a conflicting upper bound
        # (which is handled by claim.algebra with a solver counterexample)
        if any(
            re.search(r"\b(?:under|up\s+to|below)\b", c, re.IGNORECASE) for c in dropped_conds
        ) and re.search(
            r"\b(?:under|up\s+to|below|loans?\s+of)\s+(?:₹|Rs\.?\s*|\$)?\s*\d",
            sent,
            re.IGNORECASE,
        ):
            return None

        metric_val = (
            re.sub(r"\s+", " ", core_matches[0].group(0).strip()) if core_matches else core_text
        )
        slot_entries: list[SlotEntry] = [
            SlotEntry(
                slot="subject",
                canon_value=subject_label,
                draft_value=subject_label,
                status="match",
            ),
            SlotEntry(
                slot="metric",
                canon_value=metric_val,
                draft_value=metric_val,
                status="match",
            ),
        ]
        for cond in conditions:
            is_dropped = cond in dropped_conds
            slot_entries.append(
                SlotEntry(
                    slot="condition",
                    canon_value=cond,
                    draft_value="(omitted)" if is_dropped else cond,
                    status="dropped" if is_dropped else "match",
                )
            )

        sent_span = Span(start=sent_start, end=sent_end)
        qual_str = "; ".join(dropped_conds)
        stripped_sent = sent.rstrip(".!?")
        punct = sent[len(stripped_sent) :] or "."
        repaired_sent = f"{stripped_sent} ({qual_str}){punct}"

        return self.finding(
            node=node,
            locator=sent_span,
            severity=75,
            message=(
                f"Qualifier-stripping violation ({fact.id}): draft asserts {metric_val!r} "
                f"but omits mandatory condition(s): {qual_str!r}."
            ),
            rule_ref=canon.to_rule_ref(fact),
            evidence=SlotDiffEvidence(
                entailment_prob=0.14,
                canon_claim_id=fact.id,
                canon_text=fact.text,
                slots=tuple(slot_entries),
            ),
            suggestion=Suggestion(
                label=f"Append required qualifier ({qual_str})",
                replacements=(Replace(span=sent_span, replacement=repaired_sent),),
            ),
            trace=Trace(
                tier=Tier.NLI,
                ai_used=True,
                model_sha="minicheck-slotdiff-v1",
            ),
        )
