"""Unit tests verifying the 5 high-priority upstream & codebase fixes.

1. Check.finding() base helper in `canongate.engine.check`
2. Montabone & Soto integral-image saliency fallback in `canongate.checks.visual_subordination`
3. Zero-GPL RFC 9162 Merkle trees (`canongate.ledger.merkle`) and vectorized
   Krippendorff's alpha (`canongate.ledger.friction`)
4. C2PA v0.38+ Rust FFI lifecycle (`Context`, `Reader.try_create`, single-sign `Builder`)
5. ProseMirror 1-indexed token position coordinate translation (`FindingHighlightsExtension.ts`)
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any
import unittest

import cv2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import numpy as np
from PIL import Image

from canongate.checks.c2pa_inbound import inspect_c2pa_asset
from canongate.checks.terminology_banned import TerminologyBannedCheck
from canongate.checks.visual_subordination import (
    VisualSubordinationCheck,
    compute_fine_grained_saliency,
)
from canongate.domain.ast import ImageNode, TextNode
from canongate.domain.canon import Canon, TermRule
from canongate.domain.finding import Span, TermMatch
from canongate.ledger.c2pa_outbound import build_governance_manifest, sign_approved_asset
from canongate.ledger.friction import compute_rule_friction, krippendorff_alpha
from canongate.ledger.merkle import (
    compute_merkle_root,
    prove_consistency,
    prove_inclusion,
    sign_tree_head,
    verify_inclusion,
    verify_tree_head,
)


class TestFix1CheckFindingHelper(unittest.TestCase):
    def test_check_finding_helper_constructs_valid_finding(self) -> None:
        rule = TermRule(id="t1", pattern_text="cheap", preferred="affordable", severity=60)
        canon = Canon(
            id="acme",
            version="1.0",
            terminology=(rule,),
        )
        node = TextNode.from_text("Our cheap plan is live.", path="doc/p[0]")
        check = TerminologyBannedCheck()
        span = Span(start=4, end=9)
        rule_ref = canon.to_rule_ref(rule)
        finding = check.finding(
            node=node,
            locator=span,
            message='Use "affordable" instead of "cheap"',
            severity=60,
            rule_ref=rule_ref,
            evidence=TermMatch(term="cheap", preferred="affordable"),
        )
        self.assertEqual(finding.check_id, "terminology.banned")
        self.assertEqual(finding.locator, span)
        self.assertEqual(finding.rule_ref.rule_id, "t1")
        self.assertEqual(finding.evidence.kind, "term_match")
        self.assertEqual(finding.trace.tier.value, "deterministic")

        # Also verify TerminologyBannedCheck.run() exercises self.finding() end-to-end
        run_findings = check.run(node, canon)
        self.assertEqual(len(run_findings), 1)
        self.assertEqual(run_findings[0].id, finding.id)


class TestFix2OpenCVSaliencyFallback(unittest.TestCase):
    def test_integral_box_filter_saliency_without_opencv_contrib(self) -> None:
        # Standard opencv-python does not ship cv2.saliency
        self.assertFalse(hasattr(cv2, "saliency"))

        # Create a 200x400 synthetic banner with high-contrast headline and camouflaged bottom band
        img = np.full((200, 400), 128, dtype=np.uint8)
        # High-salience white & black stripes in headline zone (y: 40..100)
        img[40:100, 80:320:8] = 255
        img[40:100, 84:320:8] = 0
        # Very faint 2-unit delta in bottom disclaimer band (y: 178..192)
        img[178:192, 50:350:10] = 130

        sal_map = compute_fine_grained_saliency(img)
        self.assertEqual(sal_map.shape, (200, 400))
        self.assertGreaterEqual(float(sal_map.min()), 0.0)
        self.assertLessEqual(float(sal_map.max()), 1.0 + 1e-6)

        with tempfile.TemporaryDirectory() as tmpdir:
            banner_path = Path(tmpdir) / "banner.png"
            Image.fromarray(img).save(banner_path)
            raw_bytes = banner_path.read_bytes()
            node = ImageNode.from_bytes(
                raw_bytes,
                path=str(banner_path),
                width=400,
                height=200,
            )
            canon = Canon(id="acme", version="1.0")
            findings = VisualSubordinationCheck().run(node, canon)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].check_id, "visual.subordination")
            self.assertEqual(findings[0].evidence.kind, "saliency")
            self.assertLess(findings[0].evidence.ratio, 0.25)


class TestFix3ZeroGPLMerkleAndKrippendorff(unittest.TestCase):
    def test_rfc9162_merkle_inclusion_and_ed25519_sth(self) -> None:
        leaves = [f"event-{i}".encode("utf-8") for i in range(11)]
        root_hex = compute_merkle_root(leaves).hex()

        for idx, leaf in enumerate(leaves):
            proof = prove_inclusion(idx, leaves)
            self.assertTrue(
                verify_inclusion(
                    leaf_entry=leaf,
                    leaf_index=idx,
                    tree_size=len(leaves),
                    root_hash_hex=root_hex,
                    audit_path_hex=proof,
                )
            )
            # Tampered leaf must fail verification
            self.assertFalse(
                verify_inclusion(
                    leaf_entry=b"tampered-leaf",
                    leaf_index=idx,
                    tree_size=len(leaves),
                    root_hash_hex=root_hex,
                    audit_path_hex=proof,
                )
            )

        consistency = prove_consistency(5, leaves)
        self.assertGreater(len(consistency), 0)

        priv_key = Ed25519PrivateKey.generate()
        sth = sign_tree_head(leaves, "2026-10-22T12:00:00Z", priv_key)
        self.assertTrue(verify_tree_head(sth))

    def test_vectorized_krippendorff_alpha_and_beta_binomial_friction(self) -> None:
        # Classic Krippendorff (2013) 4-coder, 12-unit reliability matrix
        matrix = [
            [1, 2, 3, 3, 2, 1, 4, 1, 2, np.nan, np.nan, np.nan],
            [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, np.nan, 3],
            [np.nan, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, np.nan],
            [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, np.nan],
        ]
        alpha_nom = krippendorff_alpha(matrix, level_of_measurement="nominal")
        self.assertAlmostEqual(alpha_nom, 0.7434, places=3)

        alpha_int = krippendorff_alpha(matrix, level_of_measurement="interval")
        self.assertAlmostEqual(alpha_int, 0.8489, places=3)

        # Single override (1/1) has raw=1.0 but Beta(1,4) posterior=2/6=0.3333 (no false alarm)
        low_sample = compute_rule_friction("rule-1", total_flags=1, overrides_and_disputes=1)
        self.assertAlmostEqual(low_sample.raw_friction, 1.0)
        self.assertAlmostEqual(low_sample.posterior_friction, 0.3333, places=3)
        self.assertFalse(low_sample.needs_canon_revision)

        # High-volume overridden rule (8/10) has posterior=9/15=0.60 -> triggers revision
        high_friction = compute_rule_friction("rule-2", total_flags=10, overrides_and_disputes=8)
        self.assertGreater(high_friction.posterior_friction, 0.40)
        self.assertTrue(high_friction.needs_canon_revision)


class TestFix4C2paRustFfiLifecycle(unittest.TestCase):
    def test_c2pa_inbound_try_create_and_outbound_single_use_builder(self) -> None:
        calls: list[str] = []

        class FakeReader:
            def __init__(self, state: str, dst: str | None = None) -> None:
                self._state = state
                self._dst = dst

            def __enter__(self) -> FakeReader:
                calls.append("reader_enter")
                return self

            def __exit__(self, *args: Any) -> None:
                calls.append("reader_exit")

            def get_validation_state(self) -> str:
                return self._state

            def get_active_manifest(self) -> dict[str, Any]:
                return {
                    "signature_info": {"issuer": "CanonGate Authority"},
                    "assertions": [
                        {
                            "label": "c2pa.actions.v2",
                            "data": {
                                "actions": [
                                    {"digitalSourceType": self._dst} if self._dst else {}
                                ]
                            },
                        }
                    ],
                }

        class FakeC2paModule:
            class C2paSigningAlg:
                ES256 = "es256"

            class Context:
                def __enter__(self) -> Any:
                    calls.append("context_enter")
                    return self

                def __exit__(self, *args: Any) -> None:
                    calls.append("context_exit")

            class Reader:
                @staticmethod
                def try_create(path: str, context: Any = None) -> FakeReader | None:
                    calls.append(f"try_create:{Path(path).name}")
                    if "unsigned" in path:
                        return None
                    return FakeReader(
                        "Valid",
                        "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
                    )

            class Signer:
                @staticmethod
                def from_callback(
                    callback: Any, alg: Any, certs: Any, tsa_url: Any = None
                ) -> Any:
                    class _S:
                        def __enter__(self) -> Any:
                            calls.append("signer_enter")
                            return self

                        def __exit__(self, *args: Any) -> None:
                            calls.append("signer_exit")

                    return _S()

            class Builder:
                def __init__(self, manifest_def: dict[str, Any], context: Any = None) -> None:
                    self.manifest_def = manifest_def
                    self.closed = False

                def __enter__(self) -> Any:
                    calls.append("builder_enter")
                    return self

                def __exit__(self, *args: Any) -> None:
                    self.closed = True
                    calls.append("builder_exit")

                def add_ingredient(self, ingredient_json: str, mime: str, stream: Any) -> None:
                    calls.append("add_ingredient")

                def sign_file(self, src: str, dst: str, signer: Any) -> bytes:
                    if self.closed:
                        raise RuntimeError("Builder already closed after single sign!")
                    calls.append("sign_file")
                    return b"c2pa-manifest-bytes"

        with tempfile.TemporaryDirectory() as tmpdir:
            unsigned_file = Path(tmpdir) / "unsigned.png"
            signed_file = Path(tmpdir) / "signed.png"
            unsigned_file.write_bytes(b"fake-png-bytes")
            signed_file.write_bytes(b"fake-png-bytes")

            ev_missing = inspect_c2pa_asset(unsigned_file, c2pa_module=FakeC2paModule)
            self.assertFalse(ev_missing.has_manifest)
            self.assertEqual(ev_missing.validation_state, "Missing")

            ev_ai = inspect_c2pa_asset(signed_file, c2pa_module=FakeC2paModule)
            self.assertTrue(ev_ai.has_manifest)
            self.assertEqual(ev_ai.validation_state, "Valid")
            self.assertIn("trainedAlgorithmicMedia", ev_ai.digital_source_type or "")

            manifest = build_governance_manifest(
                submission_id=42,
                canon_id="acme",
                canon_hash="abc1234",
                content_hash="def5678",
                merkle_root="00" * 32,
                approved_by="reviewer_1",
                approved_at="2026-10-22T12:00:00Z",
            )
            out_bytes = sign_approved_asset(
                source_path=unsigned_file,
                output_path=signed_file,
                mime_type="image/png",
                manifest_def=manifest,
                sign_callback=lambda data: b"sig",
                cert_chain_pem="-----BEGIN CERTIFICATE-----...",
                c2pa_module=FakeC2paModule,
            )
            self.assertEqual(out_bytes, b"c2pa-manifest-bytes")
            self.assertIn("builder_enter", calls)
            self.assertIn("add_ingredient", calls)
            self.assertIn("sign_file", calls)
            self.assertIn("builder_exit", calls)


if __name__ == "__main__":
    unittest.main()
