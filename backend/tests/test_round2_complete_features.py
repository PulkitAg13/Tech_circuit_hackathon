"""Comprehensive tests for all Round 2 ("The Build") features and Sprint 1/2 bug fixes."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec

from canongate.canon.impact import _canon_to_yaml, calibrate_canon_rule
from canongate.canon.loader import load_canon
from canongate.checks.accessibility_contrast import AccessibilityContrastCheck
from canongate.checks.trigger_disclaimer import TriggerDisclaimerCheck
from canongate.checks.visual_logo_orb import VisualLogoOrbCheck
from canongate.checks.voice_readability import (
    VoiceReadabilityCheck,
    compute_flesch_kincaid_grade,
)
from canongate.domain.ast import ContentAST, ImageNode, TextNode
from canongate.domain.canon import (
    Canon,
    ColorToken,
    FactClaim,
    LogoToken,
    TermRule,
    TriggerObligation,
    VoiceProfile,
)
from canongate.domain.finding import SlotDiffEvidence
from canongate.domain.pii import default_pii_scrubber
from canongate.domain.workflow import ResolutionError, Role, validate_resolution
from canongate.engine.rewriter import ConstrainedRewriter, compute_edit_distance_ratio
from canongate.engine.runner import run_checks_collect
from canongate.ledger.c2pa_outbound import build_governance_manifest, sign_approved_asset
from canongate.parsers.html import parse_html
from canongate.parsers.llm_table import LLMProviderConfig, MultiProviderJsonLLM


class TestRound2CompleteFeatures(unittest.TestCase):
    def test_five_canon_schemas_yaml_roundtrip_and_calibration(self) -> None:
        canon = Canon(
            id="round2-full-canon",
            version="1.0",
            terminology=(
                TermRule(
                    id="term-cheap",
                    pattern_text="cheap",
                    preferred="affordable",
                    severity=60,
                ),
            ),
            palette=(
                ColorToken(
                    id="brand-blue",
                    hex="#1A73E8",
                    name="Primary Blue",
                    max_delta_e=3.0,
                ),
            ),
            facts=(
                FactClaim(
                    id="loan-cap",
                    text="0% processing fee on loans under Rs 50,000",
                    conditions=("loans under Rs 50,000",),
                    valid_until="2026-12-31",
                ),
            ),
            trigger_obligations=(
                TriggerObligation(
                    id="trig-apr",
                    trigger_pattern=r"0%\s+processing\s+fee",
                    required_disclaimer_id="kfs-apr-disc",
                    required_disclaimer_text="Subject to RBI Key Fact Statement (KFS) schedule",
                    same_language=True,
                ),
            ),
            voice_profile=VoiceProfile(
                id="brand-voice",
                min_sentence_words=3,
                max_sentence_words=22,
                max_passive_voice_pct=20.0,
                max_flesch_kincaid_grade=10.5,
                approved_exemplars=("Clear, transparent digital lending with zero hidden fees.",),
                severity=35,
            ),
            logos=(
                LogoToken(
                    id="primary-logo",
                    name="CanonGate Mark",
                    aspect_ratio=2.0,
                    max_aspect_distortion_pct=2.0,
                    clear_space_ratio_h=0.50,
                    severity=65,
                ),
            ),
            require_image_alt=True,
        )

        yaml_str = _canon_to_yaml(canon)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "canon.yaml"
            p.write_text(yaml_str, encoding="utf-8")
            loaded = load_canon(p)

        self.assertEqual(loaded.id, canon.id)
        self.assertEqual(len(loaded.trigger_obligations), 1)
        self.assertIsNotNone(loaded.voice_profile)
        self.assertEqual(len(loaded.logos), 1)
        self.assertTrue(loaded.require_image_alt)
        self.assertEqual(len(loaded), 6)

        calibrated = calibrate_canon_rule(
            loaded,
            rule_id="term-cheap",
            severity=25,
        )
        self.assertEqual(calibrated.version, "1.1")
        self.assertEqual(calibrated.terminology[0].severity, 25)

    def test_creator_can_override_warning_with_reason_but_cannot_dismiss_or_override_blocker(
        self,
    ) -> None:
        validate_resolution(
            "overridden",
            severity=30,
            role=Role.CREATOR,
            reason="Colloquial tone intentional for campaign quote",
        )
        with self.assertRaises(ResolutionError):
            validate_resolution("overridden", severity=30, role=Role.CREATOR, reason="")
        with self.assertRaises(ResolutionError):
            validate_resolution(
                "dismissed",
                severity=30,
                role=Role.CREATOR,
                reason="Trying to dismiss",
            )
        with self.assertRaises(ResolutionError):
            validate_resolution(
                "overridden",
                severity=70,
                role=Role.CREATOR,
                reason="Creator trying to override blocker",
            )

    def test_c2pa_outbound_replaces_dummy_pem_and_dummy_callback_with_real_es256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "banner.png"
            dst = Path(tmp) / "banner_signed.png"
            img = np.full((64, 64, 3), 200, dtype=np.uint8)
            cv2.imwrite(str(src), img)

            manifest = build_governance_manifest(
                submission_id=42,
                canon_id="test-canon",
                canon_hash="ab" * 32,
                content_hash="cd" * 32,
                merkle_root="ef" * 32,
                approved_by="user_1",
                approved_at="2026-10-24T00:00:00Z",
            )
            sig = sign_approved_asset(
                source_path=src,
                output_path=dst,
                mime_type="image/png",
                manifest_def=manifest,
                sign_callback=lambda _d: b"canongate-c2pa-signature",
                cert_chain_pem="-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
                c2pa_module=None,
            )
            self.assertNotEqual(sig, b"canongate-c2pa-signature")
            sidecar_file = dst.with_suffix(".png.c2pa.json")
            self.assertTrue(sidecar_file.is_file())
            sidecar = json.loads(sidecar_file.read_text(encoding="utf-8"))
            cert = x509.load_pem_x509_certificate(sidecar["certificate_pem"].encode("utf-8"))
            pub_key = cert.public_key()
            self.assertIsInstance(pub_key, ec.EllipticCurvePublicKey)

    def test_wcag_missing_alt_text_check_on_html_images(self) -> None:
        html_bytes = b'<html><body><p>Welcome</p><img src="hero.png" /></body></html>'
        ast = parse_html(html_bytes, source="landing.html")
        canon = Canon(id="wcag-test", version="1.0")
        check = AccessibilityContrastCheck()
        img_nodes = [n for n in ast.nodes if isinstance(n, ImageNode)]
        self.assertEqual(len(img_nodes), 1)
        findings = check.run(img_nodes[0], canon)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_ref.rule_id, "wcag-21-aa-alt-text")

    def test_visual_logo_orb_aspect_distortion_and_clear_space_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ref_img = np.full((60, 120, 3), 255, dtype=np.uint8)
            cv2.rectangle(ref_img, (10, 10), (110, 50), (26, 115, 232), -1)
            cv2.circle(ref_img, (40, 30), 12, (255, 255, 255), -1)
            cv2.line(ref_img, (65, 15), (100, 45), (255, 255, 255), 3)
            cv2.line(ref_img, (65, 45), (100, 15), (255, 255, 255), 3)
            ref_path = Path(tmp) / "ref_logo.png"
            cv2.imwrite(str(ref_path), ref_img)

            banner = np.full((240, 400, 3), 255, dtype=np.uint8)
            stretched = cv2.resize(ref_img, (180, 60))
            banner[80:140, 100:280] = stretched
            cv2.rectangle(banner, (110, 60), (270, 78), (220, 20, 20), -1)
            banner_path = Path(tmp) / "banner.png"
            cv2.imwrite(str(banner_path), banner)

            canon = Canon(
                id="logo-canon",
                version="1.0",
                logos=(
                    LogoToken(
                        id="acme-logo",
                        name="Acme Mark",
                        reference_path=str(ref_path),
                        aspect_ratio=2.0,
                        max_aspect_distortion_pct=2.0,
                        clear_space_ratio_h=0.50,
                        severity=65,
                    ),
                ),
            )
            node = ImageNode.from_bytes(
                banner_path.read_bytes(),
                path=str(banner_path),
                width=400,
                height=240,
                alt="Acme promotional banner",
            )
            findings = VisualLogoOrbCheck().run(node, canon)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].evidence.kind, "logo_geometry")
            self.assertGreater(findings[0].evidence.aspect_distortion_pct, 2.0)
            self.assertGreater(findings[0].evidence.clear_space_intrusion_pct, 5.0)

    def test_voice_readability_check_flags_passive_and_high_fk_grade(self) -> None:
        canon = Canon(
            id="voice-canon",
            version="1.0",
            voice_profile=VoiceProfile(
                id="crisp-voice",
                min_sentence_words=3,
                max_sentence_words=18,
                max_passive_voice_pct=15.0,
                max_flesch_kincaid_grade=9.0,
                approved_exemplars=("Apply in minutes with zero hidden charges.",),
                severity=40,
            ),
        )
        good_node = TextNode.from_text("Apply in minutes with zero hidden charges.")
        self.assertEqual(VoiceReadabilityCheck().run(good_node, canon), [])

        bad_text = (
            "The collateralized documentation was systematically evaluated by the institutional "
            "underwriting department prior to the authorization of preliminary disbursements."
        )
        self.assertGreater(compute_flesch_kincaid_grade(bad_text), 9.0)
        bad_node = TextNode.from_text(bad_text)
        findings = VoiceReadabilityCheck().run(bad_node, canon)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].evidence.kind, "voice_readability")

    def test_trigger_obligation_and_asci_influencer_disclosure(self) -> None:
        canon = Canon(
            id="trig-canon",
            version="1.0",
            trigger_obligations=(
                TriggerObligation(
                    id="zero-fee-disc",
                    trigger_pattern=r"0%\s+processing\s+fee",
                    required_disclaimer_id="kfs-footnote",
                    required_disclaimer_text="Subject to RBI Key Fact Statement schedule",
                    same_language=True,
                    severity=70,
                ),
            ),
        )
        ast_missing = ContentAST(
            nodes=(TextNode.from_text("Get a 0% processing fee on instant loans!"),)
        )
        f_missing = asyncio.run(run_checks_collect(ast_missing, canon))
        trig_findings = [f for f in f_missing if f.check_id == "trigger.disclaimer"]
        self.assertEqual(len(trig_findings), 1)

        ast_present = ContentAST(
            nodes=(
                TextNode.from_text("Get a 0% processing fee on instant loans!", path="text/p[0]"),
                TextNode.from_text(
                    "Disclaimer: Subject to RBI Key Fact Statement schedule.",
                    path="text/p[1]",
                ),
            )
        )
        f_present = asyncio.run(run_checks_collect(ast_present, canon))
        self.assertEqual([f for f in f_present if f.check_id == "trigger.disclaimer"], [])

        inf_node = TextNode.from_text(
            "Loving this serum gifted by GlowLabs! Use my promo code GLOW20 today."
        )
        inf_findings = TriggerDisclaimerCheck().run(inf_node, Canon(id="c", version="1.0"))
        self.assertEqual(len(inf_findings), 1)
        self.assertEqual(inf_findings[0].rule_ref.rule_id, "asci-influencer-upfront-disclosure")

    def test_presidio_dpdp_pii_scrubber_and_cloud_llm_masking(self) -> None:
        raw = (
            "Contact aritra@canongate.in or +91 9876543210 regarding PAN ABCDE1234F, "
            "Aadhaar 2345 6789 0123, and Project Vajra."
        )
        scrubbed = default_pii_scrubber.scrub(raw)
        self.assertGreaterEqual(scrubbed.pii_count, 5)
        self.assertNotIn("aritra@canongate.in", scrubbed.masked_text)
        self.assertNotIn("ABCDE1234F", scrubbed.masked_text)
        self.assertNotIn("2345 6789 0123", scrubbed.masked_text)
        self.assertNotIn("Project Vajra", scrubbed.masked_text)
        self.assertEqual(scrubbed.restore(scrubbed.masked_text), raw)

        captured_prompts: list[str] = []

        def fake_transport(url: str, payload: dict, headers: dict, timeout: float) -> dict:
            user_txt = payload["contents"][0]["parts"][0]["text"]
            captured_prompts.append(user_txt)
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"echo": "' + user_txt.replace('"', '\\"') + '"}'}]
                        }
                    }
                ]
            }

        cfg = LLMProviderConfig(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="test-key",
            base_url="https://example.com",
        )
        client = MultiProviderJsonLLM(cfg, transport=fake_transport)
        resp = client.complete_json(system_prompt="sys", user_prompt=raw)
        self.assertEqual(len(captured_prompts), 1)
        self.assertNotIn("ABCDE1234F", captured_prompts[0])
        self.assertIsNotNone(resp)
        assert resp is not None
        self.assertIn("ABCDE1234F", resp["echo"])

    def test_tier3_constrained_rewriter_enforces_edit_ceiling_and_reverification(self) -> None:
        canon = Canon(
            id="rewrite-canon",
            version="1.0",
            facts=(
                FactClaim(
                    id="loan-cap",
                    text="0% processing fee on loans under Rs 50,000",
                    conditions=("under Rs 50,000",),
                ),
            ),
        )
        node = TextNode.from_text("Get a 0% processing fee on loans today")
        findings = asyncio.run(run_checks_collect(ContentAST(nodes=(node,)), canon))
        nli_finding = next(f for f in findings if isinstance(f.evidence, SlotDiffEvidence))

        rewriter = ConstrainedRewriter(
            max_edit_ratio=0.35,
            llm_rewrite_fn=lambda _m, _msg, _r: (
                "Completely different marketing copy that rewrites the entire "
                "paragraph from scratch!"
            ),
        )
        res = asyncio.run(rewriter.rewrite(node, nli_finding, canon, verify_fn=run_checks_collect))
        self.assertLessEqual(res.edit_distance_ratio, 0.35)
        self.assertIn("under Rs 50,000", res.rewritten_text)
        self.assertTrue(res.reverified)
        self.assertEqual(
            compute_edit_distance_ratio(
                "Get a 0% processing fee on loans today",
                "Get a 0% processing fee on loans under Rs 50,000 today",
                allowed_insertions=("under Rs 50,000",),
            ),
            0.0,
        )

    def test_api_comments_rewrite_calibrate_and_apply_pr_endpoints(self) -> None:
        try:
            from tests.test_full_e2e_routes import _ensure_route_runtime_shims
        except ImportError:
            from test_full_e2e_routes import _ensure_route_runtime_shims

        _ensure_route_runtime_shims()
        from canongate.api.deps import register_canon
        from canongate.api.routes import canons as canons_route
        from canongate.api.routes import submissions as subs_route

        canon = Canon(
            id="api-test-canon",
            version="1.0",
            terminology=(
                TermRule(
                    id="cheap",
                    pattern_text="cheap",
                    preferred="affordable",
                    severity=65,
                ),
            ),
        )
        register_canon(canon, persist_yaml=False)
        cal_res = asyncio.run(
            canons_route.calibrate_canon_endpoint(
                "api-test-canon",
                canons_route.CalibrateCanonRuleRequest(rule_id="cheap", severity=30),
            )
        )
        self.assertEqual(cal_res.new_version, "1.1")

        fake_sub = SimpleNamespace(
            id=1,
            title="Test Sub",
            raw_content="We offer cheap cloud hosting for enterprises.",
            content_hash="11" * 32,
            canon_id="api-test-canon",
            canon_hash=canon.hash,
            status="draft",
            creator_id=1,
        )
        ast = ContentAST(nodes=(TextNode.from_text(fake_sub.raw_content),))
        scan_findings = asyncio.run(run_checks_collect(ast, canon))
        self.assertGreaterEqual(len(scan_findings), 1)
        f0 = scan_findings[0]
        fake_finding_row = SimpleNamespace(
            id=10,
            finding_id=str(f0.id),
            submission_id=1,
            check_id=f0.check_id,
            node_id=str(f0.node_id),
            severity=f0.severity,
            message=f0.message,
            payload_json=f0.model_dump_json(),
            resolution="open",
            resolution_reason="",
            resolved_by=None,
        )
        comments_store: list[SimpleNamespace] = []

        class _FakeRepos:
            async def get_submission(self, _s: object, _sid: int) -> object:
                return fake_sub

            async def get_finding_by_row_id(self, _s: object, _rid: int) -> object:
                return fake_finding_row

            async def update_finding_node_and_payload(
                self, _s: object, _rid: int, **_kw: object
            ) -> object:
                return fake_finding_row

            async def create_comment(self, _s: object, **kw: object) -> object:
                row = SimpleNamespace(
                    id=len(comments_store) + 1, created_at="2026-10-24T00:00:00Z", **kw
                )
                comments_store.append(row)
                return row

            async def list_comments_for_submission(
                self, _s: object, _sid: int, finding_id: int | None = None
            ) -> list[SimpleNamespace]:
                if finding_id is not None:
                    return [c for c in comments_store if c.finding_id == finding_id]
                return list(comments_store)

            async def get_findings_for_canon(self, _s: object, _cid: str) -> list[object]:
                return []

            async def list_submissions(self, _s: object, limit: int = 200) -> list[object]:
                return [fake_sub]

        fake_user = SimpleNamespace(id=1, username="alice", display_name="Alice", role="creator")

        async def _run_endpoint_checks() -> None:
            orig_subs_repos = subs_route.repos
            orig_canons_repos = canons_route.repos
            fake_repos = _FakeRepos()
            subs_route.repos = fake_repos  # type: ignore[assignment]
            canons_route.repos = fake_repos  # type: ignore[assignment]
            try:
                rw = await subs_route.rewrite_finding_span(
                    1,
                    10,
                    None,
                    fake_user,  # type: ignore[arg-type]
                )
                self.assertIn("affordable", rw.rewritten_text)
                self.assertTrue(rw.reverified)

                c_added = await subs_route.add_submission_comment(
                    1,
                    subs_route.CreateCommentRequest(finding_id=10, body="Reviewed surgical diff"),
                    None,  # type: ignore[arg-type]
                    fake_user,  # type: ignore[arg-type]
                )
                self.assertEqual(c_added.body, "Reviewed surgical diff")

                c_list = await subs_route.list_submission_comments(
                    1,
                    None,  # type: ignore[arg-type]
                    fake_user,  # type: ignore[arg-type]
                    finding_id=10,
                )
                self.assertEqual(len(c_list), 1)

                applied = await canons_route.apply_canon_pr(
                    "api-test-canon",
                    None,  # type: ignore[arg-type]
                    canons_route.CanonRevisionPrRequest(),
                )
                self.assertEqual(applied.id, "api-test-canon")
            finally:
                subs_route.repos = orig_subs_repos
                canons_route.repos = orig_canons_repos

        asyncio.run(_run_endpoint_checks())


if __name__ == "__main__":
    unittest.main()
