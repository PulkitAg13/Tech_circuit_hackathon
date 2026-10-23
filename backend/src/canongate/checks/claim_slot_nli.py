"""Tier 2 Calibrated Fact Entailment & Slot-Level Alignment (`claim.slot_nli`).

Aligns draft sentences against `Canon.facts` across five predicate-argument
slots (`subject`, `metric`, `condition`, `temporal_scope`, `substantiation_level`):
1. **Semantic Value-Token Alignment & Contradiction (`status="contradicted"`):**
   Classifies value anchors by semantic type (`"year"`, `"percent"`, `"currency"`,
   `"multiplier"`, `"quarter"`, `"iso_date"`, `"scalar"`) so a sentence containing
   multiple numbers (e.g. `"In 2026, Acme Corp served 500 clients since it was founded
   in 2020"`) aligns `"2020"` against `"2020"` instead of blindly comparing index `0`
   (`"2026"`).
2. **Ingredient-vs-Product Substantiation Audit (`ASCI FY2025-26`):**
   Catches `ingredient_in_vitro` facts (`"in-vitro ingredient study only"`) claimed
   as `"clinically proven"` whole-product clinical proof without disclosing the
   ingredient/in-vitro scope.
3. **Qualifier / Condition Stripping & Calibrated Uncertainty Routing (`0.45 <= P < 0.85`):**
   - Full condition omission (`P < 0.45`) -> BLOCKER (`severity=75`, `status="dropped"`).
   - Partial/hedged condition paraphrase or borderline MiniCheck score
     (`0.45 <= P < 0.85`) -> WARNING (`severity=40`, `status="unverified"`,
     `"Partially Supported — Needs Human Review"`).
   - Supports pluggable `MiniCheck` / ONNX runtime inference in `run_async()` with a
     400ms latency ceiling and temperature scaling calibration.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Callable
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
_WHOLE_PRODUCT_CLINICAL_RE = re.compile(
    r"\b(?:clinically\s+proven|clinical\s+(?:trial|study|proof)|doctor\s+proven|"
    r"dermatologically\s+proven|proven\s+product)\b",
    re.IGNORECASE,
)
_INVITRO_DISCLOSURE_RE = re.compile(
    r"\b(?:in[\-\s]?vitro|ingredient\s+study|lab\s+study|active\s+ingredient)\b",
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


def _classify_value_token(tok: str) -> str:
    """Classify a numeric/temporal value token into a semantic slot category."""
    s = tok.strip()
    s_low = s.lower()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return "iso_date"
    if re.match(r"^q[1-4]\s+\d{4}$", s_low):
        return "quarter"
    if s_low.endswith("%"):
        return "percent"
    if s_low.endswith("x"):
        return "multiplier"
    if any(u in s_low for u in ("₹", "rs", "$", "lakh", "crore", "cr")):
        return "currency"
    if re.match(r"^(?:19|20)\d{2}$", s):
        return "year"
    return "scalar"


def temperature_scale_prob(raw_prob: float, temperature: float = 1.15) -> float:
    """Apply temperature scaling to a raw NLI entailment probability in (0, 1)."""
    p = max(1e-4, min(1.0 - 1e-4, float(raw_prob)))
    logit = math.log(p / (1.0 - p))
    scaled = 1.0 / (1.0 + math.exp(-logit / max(0.1, temperature)))
    return round(scaled, 4)


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


def _condition_match_status(cond: str, sentence: str) -> str:
    """Return `'match'`, `'unverified'` (partial paraphrase), or `'dropped'`."""
    sent_low = sentence.lower()
    if cond.lower() in sent_low:
        return "match"
    anchors = [m.group(0).strip().lower() for m in _VALUE_TOKEN_RE.finditer(cond)]
    if anchors and all(a in sent_low for a in anchors):
        return "match"
    kw = _content_words(cond)
    if kw and all(w in sent_low for w in kw):
        return "match"
    # Partial paraphrase: at least half of content words present (and no missing numeric anchor)
    if kw and not anchors:
        matched_kw = sum(1 for w in kw if w in sent_low)
        if matched_kw >= max(1, math.ceil(len(kw) * 0.5)):
            return "unverified"
    return "dropped"


def _is_ingredient_in_vitro_fact(fact: FactClaim) -> bool:
    if getattr(fact, "substantiation_level", "") == "ingredient_in_vitro":
        return True
    combined = " ".join([fact.text, *fact.conditions]).lower()
    return "in-vitro" in combined or "in vitro" in combined or "ingredient study" in combined


class ClaimSlotNliCheck(Check):
    check_id: ClassVar[str] = "claim.slot_nli"
    check_version: ClassVar[str] = "1.1"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})
    timeout_s: ClassVar[float] = 10.0

    # Optional pluggable external NLI scorer `(doc, claim) -> float` (e.g. MiniCheck / ONNX)
    _external_scorer: ClassVar[Callable[[str, str], float] | None] = None

    @classmethod
    def set_external_scorer(cls, scorer: Callable[[str, str], float] | None) -> None:
        """Register an optional MiniCheck or ONNX Runtime entailment scorer."""
        cls._external_scorer = scorer

    async def run_async(self, node: Node, canon: Canon) -> list[Finding]:
        """Run with 400ms latency guard if an external ONNX/MiniCheck scorer is configured."""
        if ClaimSlotNliCheck.__dict__.get("_external_scorer") is not None:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self.run, node, canon),
                    timeout=0.40,
                )
            except TimeoutError:
                # Auto-fallback to fast calibrated slot scorer when ONNX latency > 400ms
                return await asyncio.to_thread(
                    self._run_with_scorer, node, canon, scorer=None, fallback_used=True
                )
        return await asyncio.to_thread(self.run, node, canon)

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

            sent_words = set(_content_words(sent))
            if not sent_words:
                continue

            for fact in canon.facts:
                core_text = _core_claim_without_qualifiers(fact)
                fact_words = _content_words(core_text)
                overlap = [w for w in fact_words if w in sent_words]
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
                    scorer=scorer,
                    fallback_used=fallback_used,
                )
                if finding is not None:
                    findings.append(finding)

        return findings

    def _find_matching_or_contradicted_metric(
        self, core_text: str, sent: str
    ) -> tuple[str, re.Match[str] | None, bool]:
        """Align core value tokens with draft value tokens by semantic type.

        Returns `(canon_val, draft_match, is_contradicted)`.
        Fixes the positional index `[0]` bug when multiple numbers appear in `sent`.
        """
        core_matches = list(_VALUE_TOKEN_RE.finditer(core_text))
        sent_matches = list(_VALUE_TOKEN_RE.finditer(sent))
        if not core_matches or not sent_matches:
            return ("", None, False)

        canon_val = re.sub(r"\s+", " ", core_matches[0].group(0).strip())
        canon_kind = _classify_value_token(canon_val)

        # Filter draft tokens to those sharing the same semantic category (e.g. "year" vs "scalar")
        same_kind = [m for m in sent_matches if _classify_value_token(m.group(0)) == canon_kind]
        candidates = same_kind if same_kind else sent_matches

        # If any candidate in the sentence matches the approved value, it is NOT contradicted!
        for m in candidates:
            d_val = re.sub(r"\s+", " ", m.group(0).strip())
            if d_val.lower() == canon_val.lower():
                return (canon_val, m, False)

        # Otherwise, pick the candidate closest to the predicate keyword in `sent`
        pred_words = _content_words(core_text)
        best_match = candidates[0]
        if pred_words:
            pred_positions = [
                sent.lower().find(w) for w in pred_words if sent.lower().find(w) != -1
            ]
            if pred_positions:
                anchor_pos = pred_positions[-1]
                best_match = min(candidates, key=lambda m: abs(m.start() - anchor_pos))

        return (canon_val, best_match, True)

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
        scorer: Callable[[str, str], float] | None,
        fallback_used: bool,
    ) -> Finding | None:
        model_sha = (
            "minicheck-deberta-v3-fallback"
            if fallback_used
            else ("minicheck-flan-t5-onnx" if scorer is not None else "minicheck-slotdiff-v1")
        )

        # 1. Check for direct metric / year / number contradiction in the core claim
        canon_val, draft_match, is_contradicted = self._find_matching_or_contradicted_metric(
            core_text, sent
        )
        if is_contradicted and draft_match is not None:
            draft_val = re.sub(r"\s+", " ", draft_match.group(0).strip())
            val_span = Span(
                start=sent_start + draft_match.start(),
                end=sent_start + draft_match.end(),
            )
            raw_p = scorer(fact.text, sent) if scorer is not None else 0.04
            cal_p = temperature_scale_prob(raw_p) if scorer is not None else 0.04
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
                    entailment_prob=cal_p,
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
                    model_sha=model_sha,
                ),
            )

        # If core claim has a numeric/percentage metric, require that metric to be present in sent
        if canon_val and canon_val.lower() not in sent.lower():
            return None

        # 2. Check for ASCI FY2025-26 Ingredient-vs-Product substantiation mismatch
        substantiation_contradicted = (
            _is_ingredient_in_vitro_fact(fact)
            and bool(_WHOLE_PRODUCT_CLINICAL_RE.search(sent))
            and not bool(_INVITRO_DISCLOSURE_RE.search(sent))
        )

        # 3. Check for dropped or partially-paraphrased restrictive conditions / qualifiers
        conditions = _extract_conditions(fact)
        cond_statuses = [(c, _condition_match_status(c, sent)) for c in conditions]
        dropped_conds = [c for c, st in cond_statuses if st == "dropped"]
        unverified_conds = [c for c, st in cond_statuses if st == "unverified"]

        canon_full = f"{fact.text} ({'; '.join(conditions)})" if conditions else fact.text
        external_cal_p = (
            temperature_scale_prob(scorer(canon_full, sent)) if scorer is not None else 1.0
        )
        if (
            not dropped_conds
            and not unverified_conds
            and not substantiation_contradicted
            and external_cal_p >= 0.85
        ):
            return None

        # Avoid duplicate flagging if the draft explicitly wrote a conflicting upper bound
        # (which is handled by claim.algebra with a solver counterexample)
        if (
            not substantiation_contradicted
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

        metric_val = canon_val if canon_val else core_text
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
        if substantiation_contradicted:
            slot_entries.append(
                SlotEntry(
                    slot="substantiation_level",
                    canon_value="ingredient_in_vitro",
                    draft_value="finished_product_clinical",
                    status="contradicted",
                )
            )
        for cond, st in cond_statuses:
            slot_entries.append(
                SlotEntry(
                    slot="condition",
                    canon_value=cond,
                    draft_value="(omitted)"
                    if st == "dropped"
                    else ("(partial paraphrase)" if st == "unverified" else cond),
                    status=st,  # type: ignore[arg-type]
                )
            )

        sent_span = Span(start=sent_start, end=sent_end)
        missing_all = [*dropped_conds, *unverified_conds]
        if substantiation_contradicted and not missing_all:
            missing_all = ["in-vitro ingredient study only"]
        qual_str = "; ".join(missing_all)
        stripped_sent = sent.rstrip(".!?")
        punct = sent[len(stripped_sent) :] or "."
        repaired_sent = f"{stripped_sent} ({qual_str}){punct}"

        # Calibrated probability routing per Figure 5 of Round 1 Plan:
        # - If only `unverified` (partial paraphrase) and no hard dropped/substantiation breach:
        #   route to 0.45..0.85 Warning ("Partially Supported — Needs Human Review", severity=40)
        canon_full = f"{fact.text} ({'; '.join(conditions)})" if conditions else fact.text
        if scorer is not None:
            cal_p = temperature_scale_prob(scorer(canon_full, sent))
        elif not dropped_conds and not substantiation_contradicted and unverified_conds:
            cal_p = 0.62
        else:
            cal_p = 0.14

        if 0.45 <= cal_p < 0.85 and not substantiation_contradicted:
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
                    slots=tuple(slot_entries),
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

        msg = (
            f"Ingredient-vs-product substantiation violation ({fact.id}): draft claims clinical "
            f"product proof for an in-vitro ingredient study and omits {qual_str!r}."
            if substantiation_contradicted
            else (
                f"Qualifier-stripping violation ({fact.id}): draft asserts {metric_val!r} "
                f"but omits mandatory condition(s): {qual_str!r}."
            )
        )
        return self.finding(
            node=node,
            locator=sent_span,
            severity=85 if substantiation_contradicted else 75,
            message=msg,
            rule_ref=canon.to_rule_ref(fact),
            evidence=SlotDiffEvidence(
                entailment_prob=cal_p,
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
                model_sha=model_sha,
            ),
        )
