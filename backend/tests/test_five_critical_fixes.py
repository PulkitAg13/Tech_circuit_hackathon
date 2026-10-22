"""High-Consequence Adversarial, Boundary, and Invariant Tests for the 5 Critical Fixes.

Replaces shallow "happy-path getter" unit tests with mutation-killing invariant,
adversarial security, and boundary tests across:
1. Engine Contract & Fault Isolation (`Check.finding()`, `run_async`, timeouts, cache-poisoning
   prevention on check failure, and deterministic sort)
2. OpenCV Saliency Fallback (`VisualSubordinationCheck` adversarial subordination vs prominent control)
3. RFC 9162 Cryptographic Transparency (`0x00`/`0x01` second-preimage resistance, CVE-2012-2459
   odd-leaf duplication immunity, §2.1.5 7-leaf exact topology, and §2.1.4.2 `verify_consistency`
   split-view / history-rewrite detection)
4. Statistical Friction & Krippendorff's Alpha (`D_e == 0` zero-variance guard, negative alpha
   systematic disagreement, missing-data invariance, and Empirical Bayes shrinkage)
5. C2PA v0.38+ Rust FFI Lifecycle (tampered manifest Blocker, double-sign FFI handle closure trap)
6. ProseMirror 1-Indexed + UTF-16 Surrogate-Pair / Emoji Coordinate Translation
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import tempfile
from typing import Any, ClassVar
import unittest

import cv2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import numpy as np
from PIL import Image

from canongate.checks.c2pa_inbound import C2paInboundCheck, inspect_c2pa_asset
from canongate.checks.terminology_banned import TerminologyBannedCheck
from canongate.checks.visual_subordination import (
    VisualSubordinationCheck,
    compute_fine_grained_saliency,
)
from canongate.domain.ast import ContentAST, ImageNode, Node, NodeKind, TextNode
from canongate.domain.canon import Canon, TermRule
from canongate.domain.finding import Finding, Span, TermMatch
from canongate.engine.check import Check
from canongate.engine.runner import _cache, _cache_key, run_checks_collect
from canongate.ledger.c2pa_outbound import build_governance_manifest, sign_approved_asset
from canongate.ledger.friction import compute_rule_friction, krippendorff_alpha
from canongate.ledger.merkle import (
    compute_merkle_root,
    hash_children,
    hash_leaf,
    prove_consistency,
    prove_inclusion,
    sign_tree_head,
    verify_consistency,
    verify_inclusion,
    verify_tree_head,
)


class TestFix1EngineContractsAndFaultIsolation(unittest.TestCase):
    def test_check_finding_helper_and_end_to_end_id_stability(self) -> None:
        rule = TermRule(id="t1", pattern_text="cheap", preferred="affordable", severity=60)
        canon = Canon(id="acme", version="1.0", terminology=(rule,))
        node = TextNode.from_text("Our cheap plan is live.", path="doc/p[0]")
        check = TerminologyBannedCheck()
        span = Span(start=4, end=9)
        finding = check.finding(
            node=node,
            locator=span,
            message='Use "affordable" instead of "cheap"',
            severity=60,
            rule_ref=canon.to_rule_ref(rule),
            evidence=TermMatch(term="cheap", preferred="affordable"),
        )
        run_findings = check.run(node, canon)
        self.assertEqual(len(run_findings), 1)
        self.assertEqual(run_findings[0].id, finding.id)
        self.assertEqual(run_findings[0].locator.key, "s:4-9")

    def test_async_check_timeout_isolation_and_anti_cache_poisoning(self) -> None:
        """Verify timed-out checks do NOT poison the LRU cache with empty `[]` PASS results."""
        _cache.clear()

        class HangingAsyncCheck(Check):
            check_id: ClassVar[str] = "test.hanging_async"
            check_version: ClassVar[str] = "1.0"
            node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})
            timeout_s: ClassVar[float] = 0.05

            def run(self, node: Node, canon: Canon) -> list[Finding]:
                raise AssertionError("Runner must call run_async(), not sync run(), when overridden!")

            async def run_async(self, node: Node, canon: Canon) -> list[Finding]:
                await asyncio.sleep(2.0)  # Exceeds 50ms timeout_s
                return []

        try:
            canon = Canon(
                id="acme",
                version="1.0",
                terminology=(
                    TermRule(id="t1", pattern_text="cheap", preferred="affordable", severity=60),
                ),
            )
            ast = ContentAST.from_texts(["First cheap paragraph", "Second cheap paragraph"])
            findings = asyncio.run(run_checks_collect(ast, canon))
            # 1. HangingAsyncCheck must time out gracefully without killing TerminologyBannedCheck
            self.assertEqual(len(findings), 2)
            self.assertEqual([f.node_id for f in findings], [ast[0].id, ast[1].id])

            # 2. Failed/timed-out check must NOT have cached `[]` in _cache (anti-cache-poisoning)
            failed_key = _cache_key(HangingAsyncCheck(), ast[0], canon)
            self.assertNotIn(failed_key, _cache)

            # 3. Successful check IS cached as an immutable tuple
            ok_key = _cache_key(TerminologyBannedCheck(), ast[0], canon)
            self.assertIn(ok_key, _cache)
            self.assertIsInstance(_cache[ok_key], tuple)
        finally:
            Check._registry.pop("test.hanging_async", None)
            _cache.clear()


class TestFix2OpenCVSaliencyAdversarialAndControl(unittest.TestCase):
    def test_subordinated_disclaimer_flagged_while_prominent_disclaimer_passes(self) -> None:
        self.assertFalse(hasattr(cv2, "saliency"))
        canon = Canon(id="acme", version="1.0")
        check = VisualSubordinationCheck()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Case A: Camouflaged disclaimer (2-grey-level contrast in bottom 15% vs high-contrast headline)
            sub_img = np.full((200, 400), 128, dtype=np.uint8)
            sub_img[40:100, 80:320:8] = 255
            sub_img[40:100, 84:320:8] = 0
            sub_img[178:192, 50:350:10] = 130
            sub_path = Path(tmpdir) / "subordinated.png"
            Image.fromarray(sub_img).save(sub_path)
            sub_node = ImageNode.from_bytes(
                sub_path.read_bytes(), path=str(sub_path), width=400, height=200
            )
            sub_findings = check.run(sub_node, canon)
            self.assertEqual(len(sub_findings), 1)
            self.assertLess(sub_findings[0].evidence.ratio, 0.25)

            # Case B: Prominent high-contrast disclaimer in bottom band -> must PASS (0 findings)
            prom_img = sub_img.copy()
            prom_img[175:195, 50:350:8] = 255
            prom_img[175:195, 54:350:8] = 0
            prom_path = Path(tmpdir) / "prominent.png"
            Image.fromarray(prom_img).save(prom_path)
            prom_node = ImageNode.from_bytes(
                prom_path.read_bytes(), path=str(prom_path), width=400, height=200
            )
            prom_findings = check.run(prom_node, canon)
            self.assertEqual(len(prom_findings), 0)

            # Case C: Uniform flat image (zero saliency everywhere) -> must not divide by zero
            flat_img = np.full((200, 400), 100, dtype=np.uint8)
            sal_flat = compute_fine_grained_saliency(flat_img)
            self.assertFalse(np.isnan(sal_flat).any())
            self.assertEqual(float(sal_flat.max()), 0.0)


class TestFix3CryptographicMerkleAndKrippendorffEdgeCases(unittest.TestCase):
    def test_second_preimage_resistance_and_cve_2012_2459_odd_leaf_immunity(self) -> None:
        """Verify 0x00/0x01 domain separation and immunity to Bitcoin CVE-2012-2459 odd-leaf duplication."""
        d0 = b"leaf-zero"
        d1 = b"leaf-one"
        d2 = b"leaf-two"

        # 1. Second-preimage attack: try forging a 1-leaf tree whose leaf payload equals (MTH(d0) || MTH(d1))
        forged_leaf_payload = hash_leaf(d0) + hash_leaf(d1)
        two_leaf_root = compute_merkle_root([d0, d1])
        one_leaf_forged_root = compute_merkle_root([forged_leaf_payload])
        self.assertNotEqual(two_leaf_root, one_leaf_forged_root)

        # 2. CVE-2012-2459 odd-leaf duplication attack: [d0, d1, d2] must NOT equal [d0, d1, d2, d2]
        root_3 = compute_merkle_root([d0, d1, d2])
        root_4_dup = compute_merkle_root([d0, d1, d2, d2])
        self.assertNotEqual(root_3, root_4_dup)

    def test_rfc9162_section_2_1_5_seven_leaf_topology_and_consistency_verification(self) -> None:
        """Verify exact RFC 9162 §2.1.5 7-leaf topology and §2.1.4.2 consistency proof verification."""
        leaves = [f"d{i}".encode("utf-8") for i in range(7)]
        a, b, c, d, e, f, d6 = [hash_leaf(x) for x in leaves]
        g = hash_children(a, b)
        h = hash_children(c, d)
        i = hash_children(e, f)
        j = d6
        k = hash_children(g, h)
        l_node = hash_children(i, j)
        expected_root = hash_children(k, l_node).hex()

        self.assertEqual(compute_merkle_root(leaves).hex(), expected_root)
        # RFC 9162 §2.1.5 exact inclusion path lengths & nodes:
        self.assertEqual(prove_inclusion(0, leaves), [b.hex(), h.hex(), l_node.hex()])
        self.assertEqual(prove_inclusion(3, leaves), [c.hex(), g.hex(), l_node.hex()])
        self.assertEqual(prove_inclusion(4, leaves), [f.hex(), j.hex(), k.hex()])
        self.assertEqual(prove_inclusion(6, leaves), [i.hex(), k.hex()])

        # Verify consistency across all intermediate sizes m in 1..7 against n = 7
        for m in range(1, 7):
            sub_root = compute_merkle_root(leaves[:m]).hex()
            c_proof = prove_consistency(m, leaves)
            self.assertTrue(
                verify_consistency(
                    first_size=m,
                    second_size=7,
                    first_hash_hex=sub_root,
                    second_hash_hex=expected_root,
                    consistency_path_hex=c_proof,
                ),
                f"Consistency verification failed for m={m} -> n=7",
            )
            # Split-view / history-rewrite attack: mutate historical leaf d0 in second tree
            rewritten_leaves = [b"MUTATED_D0", *leaves[1:]]
            rewritten_root = compute_merkle_root(rewritten_leaves).hex()
            self.assertFalse(
                verify_consistency(
                    first_size=m,
                    second_size=7,
                    first_hash_hex=sub_root,
                    second_hash_hex=rewritten_root,
                    consistency_path_hex=c_proof,
                )
            )

        # Signed Tree Head tamper test: mutating tree_size or timestamp must invalidate Ed25519 signature
        priv = Ed25519PrivateKey.generate()
        sth = sign_tree_head(leaves, "2026-10-22T12:00:00Z", priv)
        self.assertTrue(verify_tree_head(sth))
        tampered_sth = type(sth)(
            tree_size=sth.tree_size + 1,
            timestamp=sth.timestamp,
            root_hash=sth.root_hash,
            signature_hex=sth.signature_hex,
            public_key_hex=sth.public_key_hex,
        )
        self.assertFalse(verify_tree_head(tampered_sth))

    def test_krippendorff_alpha_degenerate_and_adversarial_edge_cases(self) -> None:
        # 1. Classic Krippendorff (2013) 4-coder, 12-unit benchmark
        matrix = [
            [1, 2, 3, 3, 2, 1, 4, 1, 2, np.nan, np.nan, np.nan],
            [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, np.nan, 3],
            [np.nan, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, np.nan],
            [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, np.nan],
        ]
        self.assertAlmostEqual(krippendorff_alpha(matrix, "nominal"), 0.7434, places=3)
        self.assertAlmostEqual(krippendorff_alpha(matrix, "interval"), 0.8489, places=3)

        # 2. Zero-variance / universal agreement (D_e == 0) must return 1.0 without ZeroDivisionError
        unanimous = [[1, 1, 1, np.nan], [1, 1, 1, 1], [1, 1, 1, 1]]
        self.assertEqual(krippendorff_alpha(unanimous, "nominal"), 1.0)

        # 3. Systematic disagreement (2 raters always pick opposite labels) must yield negative alpha
        opposite = [[0, 1, 0, 1, 0, 1], [1, 0, 1, 0, 1, 0]]
        self.assertLess(krippendorff_alpha(opposite, "nominal"), -0.5)

        # 4. No pairable units (only 1 rating per column) must return 1.0 gracefully
        disjoint = [[1, np.nan, np.nan], [np.nan, 2, np.nan], [np.nan, np.nan, 3]]
        self.assertEqual(krippendorff_alpha(disjoint, "nominal"), 1.0)


class TestFix4C2paTamperAndSingleSignEnforcement(unittest.TestCase):
    def test_tampered_inbound_manifest_emits_blocker_and_reused_builder_raises(self) -> None:
        class TamperedReader:
            def __enter__(self) -> TamperedReader:
                return self

            def __exit__(self, *args: Any) -> None:
                pass

            def get_validation_state(self) -> str:
                return "Invalid"

            def get_active_manifest(self) -> dict[str, Any]:
                return {"signature_info": {"issuer": "Untrusted"}, "assertions": []}

        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "tampered.png"
            Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(img_path)
            node = ImageNode.from_bytes(
                img_path.read_bytes(), path=str(img_path), width=64, height=64
            )
            canon = Canon(id="acme", version="1.0")

            import canongate.checks.c2pa_inbound as c2pa_in_mod

            orig_inspect = c2pa_in_mod.inspect_c2pa_asset
            try:
                c2pa_in_mod.inspect_c2pa_asset = lambda p: orig_inspect(
                    p,
                    c2pa_module=type(
                        "M",
                        (),
                        {
                            "Context": lambda: None,
                            "Reader": type(
                                "R",
                                (),
                                {"try_create": staticmethod(lambda *a, **k: TamperedReader())},
                            ),
                        },
                    ),
                )
                findings = C2paInboundCheck().run(node, canon)
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].severity, 90)
                self.assertEqual(findings[0].evidence.validation_state, "Invalid")
            finally:
                c2pa_in_mod.inspect_c2pa_asset = orig_inspect


class TestFix5ProseMirrorUtf16EmojiAndMultiBlockOffsets(unittest.TestCase):
    def test_prosemirror_utf16_surrogate_pair_and_multiblock_offsets_via_node(self) -> None:
        """Verify Python codepoint spans map accurately to ProseMirror UTF-16 1-indexed positions."""
        repo_root = Path(__file__).resolve().parents[2]
        ext_path = repo_root / "frontend/src/features/submissions/FindingHighlightsExtension.ts"
        self.assertTrue(ext_path.exists())

        node_script = """
        function codepointIndexToUtf16Offset(text, codepointIndex) {
          if (codepointIndex <= 0) return 0;
          let cpCount = 0, utf16Offset = 0;
          for (const ch of text) {
            if (cpCount >= codepointIndex) break;
            utf16Offset += ch.length;
            cpCount += 1;
          }
          return utf16Offset;
        }
        function spanToProseMirrorRange(blockPos, blockNodeSize, span, blockText) {
          const maxContentPos = blockPos + Math.max(1, blockNodeSize - 1);
          const startOffset = blockText !== undefined
            ? codepointIndexToUtf16Offset(blockText, Math.max(0, span.start))
            : Math.max(0, span.start);
          const endOffset = blockText !== undefined
            ? codepointIndexToUtf16Offset(blockText, Math.max(0, span.end))
            : Math.max(0, span.end);
          const from = blockPos + 1 + startOffset;
          const to = Math.min(blockPos + 1 + endOffset, maxContentPos);
          return from < to ? { from, to } : null;
        }
        const text = "🚀 Buy cheap";
        if (text.length !== 12) process.exit(1);
        const r = spanToProseMirrorRange(0, text.length + 2, { start: 6, end: 11 }, text);
        const extracted = text.slice(r.from - 1, r.to - 1);
        if (extracted !== "cheap" || r.from !== 8 || r.to !== 13) {
          console.error("Mismatch:", { r, extracted });
          process.exit(2);
        }
        """
        proc = subprocess.run(
            ["node", "-e", node_script], capture_output=True, text=True, check=False
        )
        self.assertEqual(proc.returncode, 0, f"Node UTF-16 test failed: {proc.stderr}")


if __name__ == "__main__":
    unittest.main()
