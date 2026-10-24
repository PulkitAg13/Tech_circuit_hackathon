"""Tier 1 Deterministic Check: Unicode UTS #39 Confusable Homoglyphs & Mixed-Script Spoofing.

Detects:
1. Mixed-script word tokens (e.g., Cyrillic `а` U+0430, `е` U+0435, `о` U+043E,
   `с` U+0441 or Greek homoglyphs embedded inside Latin words like `"chеap"` to
   bypass banned-term regexes).
2. Zero-width / invisible format characters (`U+200B` ZWSP, `U+200C` ZWNJ,
   `U+200D` ZWJ, `U+2060` WJ, `U+FEFF` BOM) injected inside words.
3. Normalizes the spoofed token via the UTS #39 skeleton map + `NFKC` and
   checks whether the unmasked word also matches a banned `TermRule` in
   `Canon.terminology`, proposing the preferred brand replacement directly.
"""

from __future__ import annotations

import re
import unicodedata
from typing import ClassVar

from canongate.domain.ast import Node, NodeKind, TextNode
from canongate.domain.canon import Canon, Rule
from canongate.domain.finding import (
    ConfusableEvidence,
    Finding,
    Replace,
    Span,
    Suggestion,
    Tier,
    Trace,
)
from canongate.engine.check import Check

_ZERO_WIDTH_CHARS = frozenset({"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00ad"})

# Core UTS #39 Cyrillic & Greek -> Latin visual confusable skeleton map
_UTS39_SKELETON_MAP: dict[str, str] = {
    "\u0430": "a",  # Cyrillic small a
    "\u0410": "A",  # Cyrillic capital A
    "\u0435": "e",  # Cyrillic small ie
    "\u0415": "E",  # Cyrillic capital IE
    "\u0456": "i",  # Cyrillic small byelorussian-ukrainian i
    "\u0406": "I",  # Cyrillic capital I
    "\u043e": "o",  # Cyrillic small o
    "\u041e": "O",  # Cyrillic capital O
    "\u0440": "p",  # Cyrillic small er
    "\u0420": "P",  # Cyrillic capital ER
    "\u0441": "c",  # Cyrillic small es
    "\u0421": "C",  # Cyrillic capital ES
    "\u0442": "t",  # Cyrillic capital/small te lookalike
    "\u0422": "T",
    "\u0443": "y",  # Cyrillic small u
    "\u0423": "Y",
    "\u0445": "x",  # Cyrillic small ha
    "\u0425": "X",
    "\u0455": "s",  # Cyrillic small dze
    "\u0405": "S",
    "\u03b1": "a",  # Greek small alpha
    "\u03bf": "o",  # Greek small omicron
    "\u03c1": "p",  # Greek small rho
    "\u03b5": "e",  # Greek small epsilon
    "\u03ba": "k",  # Greek small kappa
    "\u03bd": "v",  # Greek small nu
}

_TOKEN_RE = re.compile(r"\S+")


def _char_script(ch: str) -> str | None:
    if ch in _ZERO_WIDTH_CHARS:
        return "ZERO_WIDTH"
    if not ch.isalpha():
        return None
    name = unicodedata.name(ch, "")
    if not name:
        return None
    first = name.split()[0]
    if first in ("LATIN", "CYRILLIC", "GREEK", "DEVANAGARI", "ARABIC", "HEBREW"):
        return first
    return None


def _normalize_skeleton(token: str) -> tuple[str, tuple[str, ...]]:
    out: list[str] = []
    confusables: list[str] = []
    for ch in token:
        if ch in _ZERO_WIDTH_CHARS:
            confusables.append(f"U+{ord(ch):04X}")
            continue
        if ch in _UTS39_SKELETON_MAP:
            confusables.append(f"{ch}(U+{ord(ch):04X})")
            out.append(_UTS39_SKELETON_MAP[ch])
        else:
            out.append(ch)
    normalized = unicodedata.normalize("NFKC", "".join(out))
    return normalized, tuple(confusables)


class UnicodeConfusableCheck(Check):
    check_id: ClassVar[str] = "unicode.confusable"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        assert isinstance(node, TextNode)
        findings: list[Finding] = []
        rule_ref = Rule(
            rule_id="uts39-confusable-spoof",
            rule_type="security",
            source_text=(
                "Unicode UTS #39: mixed-script homoglyphs and zero-width evasion are prohibited"
            ),
        )

        for match in _TOKEN_RE.finditer(node.text):
            raw_tok = match.group(0)
            scripts: list[str] = []
            for ch in raw_tok:
                sc = _char_script(ch)
                if sc and sc not in scripts:
                    scripts.append(sc)

            has_zero_width = "ZERO_WIDTH" in scripts
            alpha_scripts = [s for s in scripts if s != "ZERO_WIDTH"]
            is_mixed_script = "LATIN" in alpha_scripts and len(alpha_scripts) > 1

            if not has_zero_width and not is_mixed_script:
                continue

            norm_tok, confusable_chars = _normalize_skeleton(raw_tok)
            span = Span(start=match.start(), end=match.end())

            # Check if the unmasked token matches a banned TermRule in Canon
            replacement = norm_tok
            extra_note = ""
            for term_rule in canon.term_rules():
                if term_rule.pattern.search(norm_tok):
                    replacement = term_rule.pattern.sub(term_rule.preferred, norm_tok)
                    extra_note = (
                        f" Unmasked token matches banned term {term_rule.pattern_text!r}; "
                        f"use {term_rule.preferred!r}."
                    )
                    break

            findings.append(
                self.finding(
                    node=node,
                    locator=span,
                    severity=85,
                    message=(
                        f"Unicode UTS #39 spoofing detected in {raw_tok!r} "
                        f"(scripts: {', '.join(scripts)} → {norm_tok!r}).{extra_note}"
                    ),
                    rule_ref=rule_ref,
                    evidence=ConfusableEvidence(
                        spoofed_token=raw_tok,
                        normalized_token=norm_tok,
                        confusable_chars=confusable_chars,
                        scripts_detected=tuple(scripts),
                    ),
                    suggestion=Suggestion(
                        label=f"Replace spoofed token with {replacement!r}",
                        replacements=(Replace(span=span, replacement=replacement),),
                    ),
                    trace=Trace(tier=Tier.DETERMINISTIC),
                )
            )
        return findings
