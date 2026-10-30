"""Comprehensive tests for the 4 Planned Stack Upgrades + Voyage 4 / rerank-2.5.

Covers:
1. Banner OCR (`BannerOCREngine`, `parse_banner_image`, `parse_text`,
   `BundleParser`, `LegibilityPlacementCheck`)
2. Tier 2 NLI & SlotDiff (`HybridFactRetriever` with Voyage 4 dense embeddings,
   `QASemSlotAligner`, `MiniCheckNliScorer` with Voyage `rerank-2.5` & ONNX Runtime,
   `ClaimSlotNliCheck`)
3. Tier 1.5 SMT Solver (`SmtConstraintSolver`, `ClaimAlgebraCheck` upper/lower bounds,
   KFS validity, temporal expiry, drip pricing)
4. Pipeline A Guards 1 & 3 + POS Constraints (`SpacyLinguisticAnalyzer`,
   `TerminologyBannedCheck`, `CanonCompiler`, `verify_round_trip_nli`)
5. `DesignAlternativeProvider` 3-candidate visual repair synthesis, HMAC-SHA256
   Ed25519 key derivation, and `ConstrainedRewriter` empty-choices resilience.
"""

from __future__ import annotations

import asyncio
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from canongate.canon.compiler import (
    audit_and_repair_fact_claim,
    verify_round_trip_nli,
)
from canongate.canon.impact import _canon_to_yaml
from canongate.checks._vision import (
    CielabDesignAlternativeProvider,
    DesignAlternativeProvider,
    default_design_alternative_provider,
)
from canongate.checks.claim_algebra import ClaimAlgebraCheck, SmtConstraintSolver
from canongate.checks.claim_slot_nli import ClaimSlotNliCheck
from canongate.checks.legibility_placement import LegibilityPlacementCheck
from canongate.checks.terminology_banned import TerminologyBannedCheck
from canongate.domain.ast import TextNode
from canongate.domain.canon import Canon, ColorToken, FactClaim, TermRule
from canongate.domain.finding import BBox
from canongate.engine.nlp import (
    HybridFactRetriever,
    MiniCheckNliScorer,
    default_fact_retriever,
    default_nli_scorer,
    default_slot_aligner,
)
from canongate.engine.rewriter import ConstrainedRewriter, ResolvedRewriterBackend
from canongate.engine.runner import run_checks_collect
from canongate.ledger.certificate import derive_audit_signing_key
from canongate.parsers.banner import BannerOCREngine, parse_banner_image
from canongate.parsers.bundle import parse_bundle
from canongate.parsers.text import parse_text


class TestFourPlannedStackUpgrades(unittest.TestCase):
    """End-to-end verification of all four upgraded subsystems + Voyage 4 & rerank-2.5."""

    def tearDown(self) -> None:
        ClaimSlotNliCheck.set_external_scorer(None)

    # ── 1. Banner OCR (PaddleOCR 3.x PP-OCRv5 + Tesseract 5 Live Auto-OCR) ──

    def test_live_banner_auto_ocr_via_tesseract_and_bundle_parser(self) -> None:
        """Verify `parse_bundle` and `parse_banner_image` OCR raster text automatically."""
        canvas = np.full((160, 600, 3), 255, dtype=np.uint8)
        cv2.putText(
            canvas,
            "CHEAP LOANS TODAY",
            (25, 95),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.4,
            (10, 10, 10),
            3,
            cv2.LINE_AA,
        )
        buf = io.BytesIO()
        Image.fromarray(canvas).save(buf, format="PNG")
        png_bytes = buf.getvalue()

        ast = parse_bundle((png_bytes, "promo_banner.png"))
        text_nodes = ast.text_nodes()
        self.assertGreaterEqual(len(text_nodes), 1, "Live banner must auto-extract OCR TextNode")
        combined_ocr = " ".join(tn.text.lower() for tn in text_nodes)
        self.assertIn("cheap", combined_ocr)

        canon = Canon(
            id="brand-ocr",
            version="1.0",
            terminology=(
                TermRule(id="t-cheap", pattern_text="cheap", preferred="affordable", severity=65),
            ),
        )
        findings = asyncio.run(run_checks_collect(ast, canon))
        self.assertTrue(any(f.check_id == "terminology.banned" for f in findings))

        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "ad_banner.png"
            img_path.write_bytes(png_bytes)
            md_ast = parse_text(f"Headline copy.\n\n![Ad Banner]({img_path})")
            md_texts = " ".join(tn.text.lower() for tn in md_ast.text_nodes())
            self.assertIn("cheap", md_texts)

    def test_paddleocr_v3_predict_and_v2_ocr_normalization_and_confidence_gating(self) -> None:
        """Verify PaddleOCR 3.x predict, 2.x ocr format, and < 0.75 / < 10px gating."""

        class _MockPaddleV3Engine:
            def predict(self, _img: object) -> list[dict[str, object]]:
                return [
                    {
                        "rec_texts": [
                            "AUTO IN 5 MIN OR GET Rs 50",
                            "T&C Apply: paid in coins",
                            "नियम और शर्तें लागू",
                        ],
                        "rec_scores": [0.96, 0.62, 0.91],
                        "dt_polys": [
                            [[20, 20], [420, 20], [420, 65], [20, 65]],
                            [
                                [20, 170],
                                [200, 170],
                                [200, 178],
                                [20, 178],
                            ],
                            [[20, 100], [260, 100], [260, 130], [20, 130]],
                        ],
                    }
                ]

        canvas = np.full((200, 500, 3), 240, dtype=np.uint8)
        buf = io.BytesIO()
        Image.fromarray(canvas).save(buf, format="PNG")

        ast = parse_banner_image(
            buf.getvalue(),
            path="rapido_banner.png",
            alt="Rapido promotional banner",
            ocr_engine=_MockPaddleV3Engine(),
        )
        t_nodes = ast.text_nodes()
        self.assertEqual(len(t_nodes), 3)
        self.assertIn("/ocr[0]", t_nodes[0].path)
        self.assertIn("/ocr_low_conf[1][conf=0.62,bbox=20_170_180_8,img_h=200]", t_nodes[1].path)
        self.assertIn("/ocr[2]", t_nodes[2].path)

        leg_check = LegibilityPlacementCheck()
        canon = Canon(id="ccpa-pack", version="1.0")
        low_conf_findings = leg_check.run(t_nodes[1], canon)
        self.assertEqual(len(low_conf_findings), 1)
        self.assertIn("OCR confidence 0.62 < 0.75", low_conf_findings[0].message)
        self.assertIn("8px < 10px", low_conf_findings[0].message)

        v2_boxes = BannerOCREngine.normalize_raw_ocr_output(
            [[[[[10, 10], [110, 10], [110, 30], [10, 30]], ("Instant Loan", 0.94)]]]
        )
        self.assertEqual(len(v2_boxes), 1)
        self.assertEqual(v2_boxes[0].text, "Instant Loan")
        self.assertEqual(v2_boxes[0].bbox, BBox(x=10, y=10, w=100, h=20))

    # ── 2. Tier 2 NLI & SlotDiff (BM25 + Dense Vector + QASem + ONNX MiniCheck) ──

    def test_hybrid_bm25_dense_vector_retriever_and_onnx_minicheck_scorer(self) -> None:
        """Verify hybrid retrieval, ONNX sessions, calibration, and 400ms fallback."""
        facts = (
            FactClaim(
                id="f-loan",
                text="0% processing fee on loans under Rs 50,000",
                conditions=("on loans under Rs 50,000",),
                subject_product="instant personal loan",
                metric_value="0%",
            ),
            FactClaim(
                id="f-serum",
                text="Redensyl serum boosts hair growth by 23,800 strands",
                conditions=("in 84-day clinical study",),
                subject_product="Redensyl hair serum",
                metric_value="23,800",
                substantiation_level="ingredient_in_vitro",
            ),
            FactClaim(
                id="f-upsc",
                text="Over 645 selections out of 1016 vacancies in UPSC CSE 2023",
                conditions=("includes Mock Interview programme enrollees",),
                subject_product="UPSC coaching",
                metric_value="645",
            ),
            FactClaim(
                id="f-founded",
                text="Acme Corp was founded in 2020",
                conditions=(),
                subject_product="Acme Corp",
                metric_value="2020",
            ),
        )

        top3 = default_fact_retriever.retrieve_top_k(
            "Get a 0% processing fee on personal loans today!", facts, k=3
        )
        self.assertEqual(len(top3), 3)
        self.assertEqual(top3[0].fact.id, "f-loan")
        self.assertGreater(top3[0].bm25_score, 0.0)
        self.assertGreater(top3[0].vector_score, 0.0)

        default_nli_scorer._ensure_sessions()
        self.assertIsNotNone(default_nli_scorer._ft5_session)
        self.assertIsNotNone(default_nli_scorer._deberta_session)

        def _slow_scorer(_doc: str, _claim: str) -> float:
            time.sleep(0.55)
            return 0.99

        ClaimSlotNliCheck.set_external_scorer(_slow_scorer)
        check = ClaimSlotNliCheck()
        canon = Canon(id="bfsi", version="1.0", facts=facts)
        node = TextNode.from_text("Get a 0% processing fee on loans today.")
        findings = asyncio.run(check.run_async(node, canon))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].trace.model_sha, "minicheck-deberta-v3-fallback")

    def test_voyage4_embeddings_rerank25_nli_design_alternatives_and_security_fixes(self) -> None:
        """Verify Voyage 4 dense embeddings, rerank-2.5 NLI, DesignAlternativeProvider & fixes."""
        facts = (
            FactClaim(
                id="f-loan",
                text="0% processing fee on loans under Rs 50,000",
                conditions=("on loans under Rs 50,000",),
                subject_product="instant personal loan",
                metric_value="0%",
            ),
            FactClaim(
                id="f-serum",
                text="Redensyl serum boosts hair growth by 23,800 strands",
                conditions=("in 84-day clinical study",),
                subject_product="Redensyl hair serum",
                metric_value="23,800",
            ),
        )

        # 1. Verify Voyage 4 HybridFactRetriever (`voyage-4-lite`, PII scrubbing, caching)
        embed_calls: list[dict[str, Any]] = []

        def mock_voyage_embed_transport(
            url: str, payload: dict[str, Any], headers: dict[str, str], timeout_s: float
        ) -> dict[str, Any]:
            embed_calls.append({"url": url, "payload": payload, "headers": headers})
            inputs = payload["input"]
            dim = payload.get("output_dimension", 512)
            data = []
            for txt in inputs:
                vec = [0.0] * dim
                if "loan" in txt.lower() or "processing" in txt.lower():
                    vec[0] = 0.95
                    vec[1] = 0.31
                else:
                    vec[2] = 0.95
                data.append({"embedding": vec})
            return {"data": data, "model": payload["model"]}

        retriever = HybridFactRetriever(
            http_transport=mock_voyage_embed_transport,
            voyage_model="voyage-4-lite",
            output_dimension=512,
        )
        ranked = retriever.retrieve_top_k(
            "Applicant rahul@fintech.in (PAN ABCDE1234F) gets a 0% processing fee on loans!",
            facts,
            k=2,
        )
        self.assertEqual(ranked[0].fact.id, "f-loan")
        self.assertEqual(ranked[0].vector_backend, "voyage:voyage-4-lite")
        self.assertGreater(ranked[0].vector_score, 0.90)
        self.assertEqual(len(embed_calls), 2)  # 1 query call + 1 batch document call
        query_wire = json.dumps(embed_calls[0]["payload"])
        self.assertNotIn("ABCDE1234F", query_wire)
        self.assertNotIn("rahul@fintech.in", query_wire)

        # Second call with same facts must use cached document embeddings (only 1 new query call)
        retriever.retrieve_top_k("Another loan processing fee query", facts, k=2)
        self.assertEqual(len(embed_calls), 3)

        # 2. Verify Voyage rerank-2.5 & rerank-2.5-lite in MiniCheckNliScorer
        rerank_calls: list[dict[str, Any]] = []

        def mock_voyage_rerank_transport(
            url: str, payload: dict[str, Any], headers: dict[str, str], timeout_s: float
        ) -> dict[str, Any]:
            rerank_calls.append({"url": url, "payload": payload})
            doc = payload["documents"][0]
            score = 0.96 if "under rs 50,000" in doc.lower() else 0.14
            return {"results": [{"index": 0, "relevance_score": score}]}

        voyage_scorer = MiniCheckNliScorer(http_transport=mock_voyage_rerank_transport)
        align_dropped = default_slot_aligner.align(
            facts[0], "Contact PAN ABCDE1234F for a 0% processing fee on loans today."
        )
        _raw_d, cal_d, sha_d = voyage_scorer.score_alignment(align_dropped)
        self.assertEqual(sha_d, "voyage:rerank-2.5")
        self.assertLess(cal_d, 0.30)
        rerank_wire = json.dumps(rerank_calls[0]["payload"])
        self.assertNotIn("ABCDE1234F", rerank_wire)

        align_entailed = default_slot_aligner.align(
            facts[0], "Get a 0% processing fee on loans under Rs 50,000 today."
        )
        _raw_ok, cal_ok, sha_fb = voyage_scorer.score_alignment(
            align_entailed, use_deberta_fallback=True
        )
        self.assertEqual(sha_fb, "voyage:rerank-2.5-lite")
        self.assertGreaterEqual(cal_ok, 0.88)

        # 3. Verify DesignAlternativeProvider protocol and 3-candidate visual repair synthesis
        self.assertIsInstance(default_design_alternative_provider, DesignAlternativeProvider)
        provider = CielabDesignAlternativeProvider()
        alts = provider.suggest_alternatives(
            (119, 119, 119),  # #777777 (4.48:1 fail on white)
            (255, 255, 255),
            brand_palette_hexes=("#0D3B66", "#1A73E8"),
            required_ratio=4.5,
            max_candidates=3,
        )
        self.assertEqual(len(alts), 3)
        for cand in alts:
            self.assertTrue(cand.reverified)
            self.assertGreaterEqual(cand.contrast_ratio, 4.5)

        # 4. Verify Rewriter empty-choices tuple unpacking fix & HMAC Ed25519 key derivation
        rw = ConstrainedRewriter(http_transport=lambda *a, **k: {"choices": []})
        backend = ResolvedRewriterBackend(
            provider="openai",
            model="gpt-4o-mini",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            timeout_s=2.0,
        )
        out_txt, out_model = rw._invoke_configured_backend_sync(backend, "sys", "usr")
        self.assertIsNone(out_txt)
        self.assertEqual(out_model, "gpt-4o-mini")

        k1 = derive_audit_signing_key(42, secret="secret-alpha")
        k2 = derive_audit_signing_key(42, secret="secret-beta")
        self.assertNotEqual(k1.sign(b"audit-head"), k2.sign(b"audit-head"))

    # ── 3. Tier 1.5 SMT Solver (Z3 / SymPy + SciPy HiGHS LP) ──

    def test_smt_constraint_solver_bounds_kfs_validity_expiry_and_drip_pricing(self) -> None:
        """Verify SMT solver on caps, floors, KFS days, expiry, and GST drip pricing."""
        solver = SmtConstraintSolver()

        sat_u, wit_u, sha_u = solver.prove_upper_bound_breach(100_000.0, 50_000.0)
        self.assertTrue(sat_u)
        self.assertGreater(wit_u, 50_000.0)
        self.assertLessEqual(wit_u, 100_000.0)
        self.assertIn(sha_u, ("z3-smt-v4", "sympy-scipy-smt-v2"))

        sat_u_ok, _, _ = solver.prove_upper_bound_breach(40_000.0, 50_000.0)
        self.assertFalse(sat_u_ok)

        sat_l, wit_l, _ = solver.prove_lower_bound_breach(5_000.0, 25_000.0)
        self.assertTrue(sat_l)
        self.assertEqual(wit_l, 15_000.0)

        canon = Canon(
            id="rbi-kfs",
            version="1.0",
            facts=(
                FactClaim(
                    id="f-kfs",
                    text="Personal loan offer requires minimum salary and KFS validity",
                    metric_value="Rs 25,000",
                    comparison_operator=">=",
                    kfs_acceptance_validity_days=7,
                    valid_until="2026-09-30",
                ),
            ),
        )
        alg_check = ClaimAlgebraCheck()
        draft_node = TextNode.from_text(
            "Personal loan offer starting from Rs 10,000 is valid for 3 days until 2026-11-15."
        )
        alg_findings = alg_check.run(draft_node, canon)
        msgs = " | ".join(f.message for f in alg_findings)
        self.assertIn("floor breach", msgs)
        self.assertIn("KFS validity window breach", msgs)
        self.assertIn("Temporal constraint breach", msgs)

        sat_drip, eff_pct, _ = solver.prove_drip_pricing_contradiction(27.0, 12.0)
        self.assertTrue(sat_drip)
        self.assertAlmostEqual(eff_pct, 18.24, places=2)

        # Unit-aware check: duration ("36 months") must not false-match currency ("Rs 25,000")
        cross_unit_node = TextNode.from_text(
            "Personal loan offer requires minimum salary for at least 36 months."
        )
        cross_findings = alg_check.run(cross_unit_node, canon)
        self.assertFalse(any("floor breach" in f.message for f in cross_findings))

        # Multi-variable MRP / Offer / Mandatory Fee contradiction
        mrp_node = TextNode.from_text(
            "MRP ₹2,000 with Flat 50% discount! Pay just ₹1,000 + ₹200 mandatory platform fee."
        )
        mrp_findings = alg_check.run(mrp_node, canon)
        self.assertTrue(any("40.00%" in f.message for f in mrp_findings))

        # Multi-variable Loan / EMI / Tenure / 0% interest contradiction
        emi_node = TextNode.from_text(
            "Borrow ₹1,00,000 at 0% interest for 12 months with EMI of ₹9,500."
        )
        emi_findings = alg_check.run(emi_node, canon)
        self.assertTrue(any("114,000" in f.message for f in emi_findings))

        # Brand guidelines typography hierarchy & 60/30/10 color ratio algebra
        brand_node = TextNode.from_text(
            "Heading font-size: 18pt and body font-size: 16pt. "
            "Palette uses 30% primary, 20% secondary, 50% accent."
        )
        brand_findings = alg_check.run(brand_node, canon)
        self.assertEqual(len(brand_findings), 2)

    # ── 4. Pipeline A Guards 1 & 3 + POS Constraints ──

    def test_spacy_pos_constraints_and_pipeline_a_guards_1_and_3(self) -> None:
        """Verify POS-constrained terminology rules and Guards 1 & 3 bidirectional NLI."""
        canon_noun = Canon(
            id="pos-test",
            version="1.0",
            terminology=(
                TermRule(
                    id="t-guar-noun",
                    pattern_text="guarantee",
                    preferred="limited assurance",
                    pos_constraint="NOUN",
                ),
            ),
        )
        term_check = TerminologyBannedCheck()
        verb_node = TextNode.from_text("We guarantee fast service to every customer.")
        self.assertEqual(len(term_check.run(verb_node, canon_noun)), 0)

        noun_node = TextNode.from_text("Every plan comes with a guarantee of quality.")
        noun_findings = term_check.run(noun_node, canon_noun)
        self.assertEqual(len(noun_findings), 1)
        self.assertEqual(noun_findings[0].evidence.term, "guarantee")

        yaml_str = _canon_to_yaml(canon_noun)
        self.assertIn("pos_constraint: NOUN", yaml_str)

        src_sent = "0% processing fee on loans under Rs 50,000 only within 7 days."
        incomplete_fact = FactClaim(id="f-inc", text="0% processing fee", conditions=())
        repaired, audit = audit_and_repair_fact_claim(incomplete_fact, src_sent)
        self.assertEqual(audit.effective_recall, 1.0)
        self.assertTrue(any("50,000" in c for c in repaired.conditions))
        self.assertTrue(any("7 days" in c for c in repaired.conditions))

        self.assertGreaterEqual(verify_round_trip_nli(repaired, src_sent), 0.90)
        bad_fact = FactClaim(
            id="f-bad",
            text="5% processing fee on loans under Rs 50,000",
            conditions=("on loans under Rs 50,000",),
        )
        self.assertLess(verify_round_trip_nli(bad_fact, src_sent), 0.90)

        good_color = ColorToken(id="c1", hex="#1A73E8", name="Primary Blue")
        self.assertGreaterEqual(verify_round_trip_nli(good_color, "Primary Blue: #1A73E8"), 0.90)
        bad_color = ColorToken(id="c2", hex="#FF0000", name="Primary Blue")
        self.assertLess(verify_round_trip_nli(bad_color, "Primary Blue: #1A73E8"), 0.90)


if __name__ == "__main__":
    unittest.main()
