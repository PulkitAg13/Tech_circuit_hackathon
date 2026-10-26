r"""Property-Based & Adversarial Mutation Gate (`tests/engine/test_mutations.py`).

Tests the recall and mathematical invariants of CanonGate across:
1. Five Mutation Operators on Compliant Canon Statements (plus 50-Case Benchmark):
   - `drop_qualifier` (10 cases): Strips mandatory conditions
     (`"under Rs 50,000"`, `"as of Q3 2025"`, `"only for first-time salaried borrowers"`)
     -> must be caught by `claim.slot_nli` (100% recall).
   - `numeric_drift` (10 cases): Perturbs approved numeric bounds or dates beyond Canon limits
     -> must be caught by `claim.algebra` or `claim.slot_nli` (100% recall).
   - `banned_synonym` (10 cases): Injects banned terms (`"cheap"`, `"buy"`, `"users"`)
     across varied casing -> must be caught by `terminology.banned` (100% recall).
   - `homoglyph_injection` (10 cases): Injects Cyrillic/Greek UTS #39 confusables (`'а'`, `'е'`)
     or zero-width characters (`\u200b`) -> must be caught by `unicode.confusable` (100% recall).
   - `wcag_boundary_shift` (10 cases): Shifts foreground/background sRGB luminance ratios across
     the WCAG 2.1 4.5:1 boundary (`#FFFFFF` on `#767676` = 4.54:1 PASS vs `#777777` = 4.48:1 FAIL)
     -> 100% accuracy.
2. Pluggable `MiniCheck-Flan-T5-Large` External NLI Scorer Adapter (`use_minicheck_flan_t5_large`).
3. Conformal Risk Control Invariants (`engine/conformal.py`):
   - Monotonicity:
     $\alpha_1 < \alpha_2 \implies \hat{\lambda}(\alpha_1) \ge \hat{\lambda}(\alpha_2)$.
   - Exact finite-sample risk bound:
     $\frac{n}{n+1}\widehat{R}_n(\hat{\lambda}(\alpha)) + \frac{1}{n+1} \le \alpha$.
4. Standalone Offline CLI Verifier (`canongate verify <cert.json>`) & `canongate benchmark`.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from canongate.checks.accessibility_contrast import (
    AccessibilityContrastCheck,
    wcag_contrast_ratio,
)
from canongate.checks.claim_slot_nli import ClaimSlotNliCheck
from canongate.cli import main as cli_main
from canongate.domain.ast import ContentAST, TextNode
from canongate.domain.canon import Canon, FactClaim, TermRule
from canongate.domain.finding import Finding, Rule, SlotDiffEvidence, Span, Tier, Trace
from canongate.domain.types import NodeId
from canongate.engine.conformal import (
    COMPLIANT_CONTROL_10_CASES,
    REDTEAM_50_CASES,
    ConformalRiskCalibrator,
    run_redteam_benchmark,
)
from canongate.engine.runner import run_checks_collect
from canongate.ledger.certificate import GovernanceCertificate
from canongate.ledger.chain import GENESIS_HASH, compute_event_hash


@dataclass(frozen=True, slots=True)
class _EventStub:
    id: int
    submission_id: int
    action: str
    from_status: str
    to_status: str
    actor_id: int
    comment: str
    prev_hash: str
    event_hash: str
    created_at: str


class TestMutationGateAndConformalCalibration(unittest.TestCase):
    def setUp(self) -> None:
        self.canon = Canon(
            id="mutation-gate-canon",
            version="1.0",
            terminology=(
                TermRule(id="t-cheap", pattern_text="cheap", preferred="affordable", severity=60),
                TermRule(id="t-buy", pattern_text="buy", preferred="purchase", severity=40),
                TermRule(id="t-users", pattern_text="users", preferred="customers", severity=30),
                TermRule(
                    id="t-cutting",
                    pattern_text="cutting-edge",
                    preferred="innovative",
                    severity=20,
                ),
            ),
            facts=(
                FactClaim(
                    id="f-founded",
                    text="Acme Corp was founded in 2020.",
                    conditions=(),
                ),
                FactClaim(
                    id="f-customers",
                    text="Acme Corp serves over 500 enterprise customers as of Q3 2025.",
                    conditions=("as of Q3 2025",),
                ),
                FactClaim(
                    id="f-loan-fee",
                    text="0% processing fee on personal loans under Rs 50,000.",
                    conditions=("under Rs 50,000",),
                    valid_until="2026-09-30",
                ),
                FactClaim(
                    id="f-cashback",
                    text=(
                        "Get 10% instant cashback on UPI payments "
                        "only for first-time salaried borrowers."
                    ),
                    conditions=("only for first-time salaried borrowers",),
                ),
            ),
        )

    def tearDown(self) -> None:
        ClaimSlotNliCheck.set_external_scorer(None)

    def test_five_mutation_operators_recall_gate_and_zero_false_positives_on_clean_controls(
        self,
    ) -> None:
        # 0. Control check: Compliant statements must produce 0 findings
        compliant_controls = [
            "Acme Corp was founded in 2020.",
            "Acme Corp serves over 500 enterprise customers as of Q3 2025.",
            "0% processing fee on personal loans under Rs 50,000.",
            "Get 10% instant cashback on UPI payments only for first-time salaried borrowers.",
            "Purchase our innovative and affordable enterprise platform for customers.",
        ]
        clean_ast = ContentAST.from_texts(compliant_controls)
        clean_findings = asyncio.run(run_checks_collect(clean_ast, self.canon))
        self.assertEqual(
            len(clean_findings),
            0,
            f"Compliant controls triggered false positives: {clean_findings}",
        )

        # Operator 1: `drop_qualifier` (strips required conditions from FactClaims)
        drop_qualifier_mutations = [
            "Acme Corp serves over 500 enterprise customers.",
            "0% processing fee on personal loans today.",
            "Get 10% instant cashback on UPI payments.",
        ]
        detected_drop = 0
        for mut in drop_qualifier_mutations:
            fds = asyncio.run(run_checks_collect(ContentAST.from_texts([mut]), self.canon))
            if any(f.check_id == "claim.slot_nli" for f in fds):
                detected_drop += 1
        self.assertEqual(detected_drop, len(drop_qualifier_mutations))

        # Operator 2: `numeric_drift` (violates numeric/temporal bounds or factual figures)
        numeric_drift_mutations = [
            "Acme Corp was founded in 2018.",
            "Acme Corp was founded in 2015.",
            "0% processing fee on personal loans under Rs 75,000.",
            "0% processing fee on personal loans up to Rs 1,00,000.",
            "0% processing fee on personal loans under Rs 50,000 valid until 2026-12-31.",
        ]
        detected_drift = 0
        for mut in numeric_drift_mutations:
            fds = asyncio.run(run_checks_collect(ContentAST.from_texts([mut]), self.canon))
            if any(f.check_id in ("claim.algebra", "claim.slot_nli") for f in fds):
                detected_drift += 1
        self.assertEqual(detected_drift, len(numeric_drift_mutations))

        # Operator 3: `banned_synonym` (substitutes approved words with banned synonyms)
        banned_synonym_mutations = [
            "Purchase our CHEAP enterprise platform.",
            "Buy our affordable enterprise platform.",
            "Our platform serves enterprise users worldwide.",
            "Discover our Cutting-Edge cloud governance suite.",
        ]
        detected_banned = 0
        for mut in banned_synonym_mutations:
            fds = asyncio.run(run_checks_collect(ContentAST.from_texts([mut]), self.canon))
            if any(f.check_id == "terminology.banned" for f in fds):
                detected_banned += 1
        self.assertEqual(detected_banned, len(banned_synonym_mutations))

        # Operator 4: `homoglyph_injection` (injects Cyrillic homoglyphs & zero-width chars)
        homoglyph_mutations = [
            "Our ch\u0435ap plan is live.",  # Cyrillic 'е' (U+0435)
            "Apply for \u0430ffordable credit.",  # Cyrillic 'а' (U+0430)
            "Zero\u200bwidth space injection.",  # U+200B zero-width space
        ]
        detected_homoglyph = 0
        for mut in homoglyph_mutations:
            fds = asyncio.run(run_checks_collect(ContentAST.from_texts([mut]), self.canon))
            if any(f.check_id == "unicode.confusable" for f in fds):
                detected_homoglyph += 1
        self.assertEqual(detected_homoglyph, len(homoglyph_mutations))

        # Operator 5: `wcag_boundary_shift` (exact WCAG 2.1 AA 4.5:1 boundary test)
        # #FFFFFF on #767676 = 4.54:1 (>= 4.5 PASS) vs #FFFFFF on #777777 = 4.48:1 (< 4.5 FAIL)
        self.assertGreaterEqual(wcag_contrast_ratio((255, 255, 255), (0x76, 0x76, 0x76)), 4.5)
        self.assertLess(wcag_contrast_ratio((255, 255, 255), (0x77, 0x77, 0x77)), 4.5)

        wcag_check = AccessibilityContrastCheck()
        pass_node = TextNode.from_text(
            "color: #FFFFFF; background-color: #767676; Compliant disclaimer",
            path="html/p[0]",
        )
        fail_node_boundary = TextNode.from_text(
            "color: #FFFFFF; background-color: #777777; Single-hex shift failure",
            path="html/p[1]",
        )
        fail_node_severe = TextNode.from_text(
            "color: #FFFFFF; background-color: #9E9E9E; Muted grey disclaimer",
            path="html/p[2]",
        )
        self.assertEqual(len(wcag_check.run(pass_node, self.canon)), 0)
        self.assertEqual(len(wcag_check.run(fail_node_boundary, self.canon)), 1)
        self.assertEqual(len(wcag_check.run(fail_node_severe, self.canon)), 1)

    def test_fifty_case_redteam_benchmark_suite_and_pluggable_minicheck_flan_t5_adapter(
        self,
    ) -> None:
        self.assertEqual(len(REDTEAM_50_CASES), 50)
        self.assertEqual(len(COMPLIANT_CONTROL_10_CASES), 10)

        # 1. Verify pluggable MiniCheck-Flan-T5-Large external scorer adapter
        adapter = ClaimSlotNliCheck.use_minicheck_flan_t5_large()
        self.assertEqual(adapter.model_sha, "minicheck-flan-t5-large-onnx")

        nli_check = ClaimSlotNliCheck()
        dropped_node = TextNode.from_text("0% processing fee on personal loans today.")
        dropped_findings = asyncio.run(nli_check.run_async(dropped_node, self.canon))
        self.assertEqual(len(dropped_findings), 1)
        self.assertEqual(dropped_findings[0].trace.model_sha, "minicheck-flan-t5-large-onnx")

        compliant_node = TextNode.from_text("0% processing fee on personal loans under Rs 50,000.")
        compliant_findings = asyncio.run(nli_check.run_async(compliant_node, self.canon))
        self.assertEqual(len(compliant_findings), 0)

        # 2. Execute the full 50-case red-team benchmark suite
        report = run_redteam_benchmark()
        self.assertEqual(report.total_adversarial_cases, 50)
        self.assertEqual(report.total_detected, 50)
        self.assertEqual(report.overall_recall, 1.0)
        self.assertEqual(report.control_cases, 10)
        self.assertEqual(report.false_positives, 0)
        self.assertEqual(report.false_positive_rate, 0.0)
        self.assertEqual(len(report.operators), 5)
        for op_sum in report.operators:
            self.assertEqual(op_sum.total_cases, 10, f"Operator {op_sum.operator} count != 10")
            self.assertEqual(op_sum.detected_cases, 10, f"Operator {op_sum.operator} missed cases")
            self.assertEqual(op_sum.recall, 1.0)

        md_table = report.to_markdown_table()
        self.assertIn("`drop_qualifier`", md_table)
        self.assertIn("**100.0%**", md_table)
        self.assertEqual(cli_main(["benchmark", "--json"]), 0)

    def test_conformal_risk_control_monotonicity_and_finite_sample_guarantee(self) -> None:
        cal = ConformalRiskCalibrator()
        self.assertEqual(len(cal), 49)
        self.assertEqual(cal.violation_count, 20)

        alphas = [0.02, 0.04, 0.06, 0.10, 0.14, 0.20, 0.25]
        thresholds = [cal.threshold(a) for a in alphas]

        # 1. Monotonicity: stricter alpha (smaller) requires higher entailment cutoff lambda_hat
        for i in range(len(thresholds) - 1):
            self.assertGreaterEqual(
                thresholds[i],
                thresholds[i + 1],
                f"Non-monotonic threshold at alpha={alphas[i]} -> {alphas[i + 1]}",
            )

        # 2. Exact Angelopoulos et al. finite-sample inequality:
        #    (n / (n + 1)) * R_hat(lambda_hat(alpha)) + 1 / (n + 1) <= alpha
        for a, lam in zip(alphas, thresholds, strict=True):
            bound = cal.conformal_upper_bound(lam)
            self.assertLessEqual(bound, a + 1e-9)

        # 3. Verify finding calibration & severity escalation under strict alpha
        borderline_finding = Finding(
            id="f-borderline-1",  # type: ignore[arg-type]
            check_id="claim.slot_nli",
            node_id=NodeId("n1"),
            locator=Span(start=0, end=10),
            severity=40,
            message="Borderline claim",
            rule_ref=Rule(rule_id="r1", rule_type="fact", source_text="fact"),
            evidence=SlotDiffEvidence(
                entailment_prob=0.25,
                canon_claim_id="r1",
                canon_text="fact",
                slots=(),
            ),
            trace=Trace(tier=Tier.NLI, ai_used=True),
        )
        # At strict alpha=0.04 (lambda_hat = 0.42 >= 0.25),
        # borderline warning escalates to Blocker (65)
        strict_res = cal.filter_and_calibrate_findings([borderline_finding], alpha=0.04)
        self.assertEqual(len(strict_res), 1)
        self.assertEqual(strict_res[0].severity, 65)

        # At permissive alpha=0.25 (lambda_hat = 0.18 < 0.25), borderline finding is filtered out
        perm_res = cal.filter_and_calibrate_findings([borderline_finding], alpha=0.25)
        self.assertEqual(len(perm_res), 0)

    def test_standalone_cli_verifier_valid_and_tampered_certificates(self) -> None:
        c_hash = "a" * 64
        k_hash = "b" * 64
        t0 = "2026-10-23T10:00:00+00:00"
        t1 = "2026-10-23T10:05:00+00:00"
        h0 = compute_event_hash(
            prev_hash=GENESIS_HASH,
            submission_id=42,
            action="submit",
            actor_id=1,
            timestamp=t0,
        )
        h1 = compute_event_hash(
            prev_hash=h0,
            submission_id=42,
            action="approve",
            actor_id=2,
            timestamp=t1,
        )
        ev_rows = [
            _EventStub(1, 42, "submit", "draft", "in_review", 1, "Ready", GENESIS_HASH, h0, t0),
            _EventStub(2, 42, "approve", "in_review", "approved", 2, "LGTM", h0, h1, t1),
        ]
        cert = GovernanceCertificate.build(
            submission_id=42,
            title="Monsoon KFS Campaign",
            status="approved",
            content_hash=c_hash,
            canon_id="acme-corp",
            canon_hash=k_hash,
            event_rows=ev_rows,
        )
        self.assertTrue(cert.verify().valid)

        with tempfile.TemporaryDirectory() as tmpdir:
            valid_path = Path(tmpdir) / "valid_cert.json"
            valid_path.write_text(json.dumps(cert.to_dict(), indent=2), encoding="utf-8")

            # 1. Valid certificate CLI exit code == 0
            rc_ok = cli_main(["verify", str(valid_path), "--json"])
            self.assertEqual(rc_ok, 0)

            # 2. Tamper with event 1 timestamp/hash chain -> CLI must exit 1
            tampered_dict = cert.to_dict()
            tampered_dict["events"][1]["created_at"] = "2026-10-23T23:59:59+00:00"
            bad_chain_path = Path(tmpdir) / "bad_chain.json"
            bad_chain_path.write_text(json.dumps(tampered_dict), encoding="utf-8")
            rc_bad_chain = cli_main(["verify", str(bad_chain_path), "--json"])
            self.assertEqual(rc_bad_chain, 1)

            # 3. Tamper with Ed25519 signature -> CLI must exit 1
            bad_sig_dict = cert.to_dict()
            bad_sig_dict["signed_tree_head"]["signature_hex"] = "00" * 64
            bad_sig_path = Path(tmpdir) / "bad_sig.json"
            bad_sig_path.write_text(json.dumps(bad_sig_dict), encoding="utf-8")
            rc_bad_sig = cli_main(["verify", str(bad_sig_path), "--json"])
            self.assertEqual(rc_bad_sig, 1)


if __name__ == "__main__":
    unittest.main()
