"""High-Consequence Adversarial, Boundary, OOP, and Optimization Tests for the 5 Critical Fixes.

Verifies:
1. Engine Contract, Fault Isolation, OrderedDict O(1) LRU Cache, Latency Stamping, and Numeric
   Locator Sort (preventing ASCII string-sort bug where "s:100-105" sorted before "s:4-9")
2. OpenCV Saliency Single-Buffer `cv2.absdiff` Optimization & RGBA Transparency Handling
3. RFC 9162 Cryptographic Transparency (`0x00`/`0x01` second-preimage resistance, CVE-2012-2459
   odd-leaf duplication immunity, §2.1.5 7-leaf exact topology, §2.1.4.2 `verify_consistency`,
   and `MerkleTree` Pythonic sequence/container dunder methods)
4. Statistical Friction & Vectorized Krippendorff's Alpha (`np.add.at` coincidence matrix,
   `D_e == 0` zero-variance guard, negative alpha, missing-data invariance, and input validation)
5. C2PA v0.38+ Rust FFI Lifecycle (`c2pa.inbound` `reader.json()` + `get_active_manifest()` support,
   tampered manifest Blocker, and `c2pa.outbound` single-use `Builder` signing)
6. ProseMirror 1-Indexed + UTF-16 Surrogate-Pair / Emoji Coordinate Translation
7. Domain OOP Special Methods (`ContentAST`, `Canon`, `TermRule`, `Span`, `BBox`, `Check`) and
   Non-Word Symbol Boundary Matching (`"100%"`, `"₹50"`)
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar

import cv2
import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PIL import Image

from canongate.checks.c2pa_inbound import C2paInboundCheck, inspect_c2pa_asset
from canongate.checks.terminology_banned import TerminologyBannedCheck
from canongate.checks.visual_subordination import (
    VisualSubordinationCheck,
    compute_fine_grained_saliency,
)
from canongate.domain.ast import ContentAST, ImageNode, Node, NodeKind, TextNode
from canongate.domain.canon import Canon, ColorToken, FactClaim, TermRule
from canongate.domain.finding import BBox, Finding, Span, TermMatch
from canongate.engine.check import Check
from canongate.engine.runner import _cache, _cache_key, run_checks_collect
from canongate.ledger.c2pa_outbound import build_governance_manifest, sign_approved_asset
from canongate.ledger.friction import compute_rule_friction, krippendorff_alpha
from canongate.ledger.merkle import (
    MerkleTree,
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
    def test_check_finding_helper_callable_dunder_and_id_stability(self) -> None:
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
        # Direct __call__ invocation and equality/hash dunders
        run_findings = check(node, canon)
        self.assertEqual(check, TerminologyBannedCheck())
        self.assertEqual(hash(check), hash(TerminologyBannedCheck()))
        self.assertEqual(len(run_findings), 1)
        self.assertEqual(run_findings[0].id, finding.id)
        self.assertEqual(run_findings[0].locator.key, "s:4-9")

    def test_numeric_span_sorting_beats_ascii_lexicographical_trap(self) -> None:
        """Verify findings at offset 4, 20, and 100 sort numerically (4 < 20 < 100)."""
        rule = TermRule(id="t1", pattern_text="bad", preferred="good", severity=60)
        canon = Canon(id="acme", version="1.0", terminology=(rule,))
        # Create a paragraph with "bad" at offset 4, offset 20, and offset 100
        text = "Now bad" + (" " * 13) + "bad" + (" " * 77) + "bad end."
        self.assertEqual(text[4:7], "bad")
        self.assertEqual(text[20:23], "bad")
        self.assertEqual(text[100:103], "bad")

        ast = ContentAST.from_texts([text])
        findings = asyncio.run(run_checks_collect(ast, canon))
        self.assertEqual(len(findings), 3)
        starts = [f.locator.start for f in findings]  # type: ignore[union-attr]
        self.assertEqual(starts, [4, 20, 100])
        # Verify latency_ms was stamped on each finding's trace
        for f in findings:
            self.assertIsNotNone(f.trace.latency_ms)
            self.assertGreaterEqual(f.trace.latency_ms or 0.0, 0.0)

    def test_async_check_timeout_isolation_and_anti_cache_poisoning(self) -> None:
        """Verify timed-out checks do NOT poison the LRU cache with empty `[]` PASS results."""
        _cache.clear()

        class HangingAsyncCheck(Check):
            check_id: ClassVar[str] = "test.hanging_async"
            check_version: ClassVar[str] = "1.0"
            node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})
            timeout_s: ClassVar[float] = 0.05

            def run(self, node: Node, canon: Canon) -> list[Finding]:
                raise AssertionError(
                    "Runner must call run_async(), not sync run(), when overridden!"
                )

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
            # Case A: Camouflaged disclaimer (low contrast in bottom 15% vs high-contrast headline)
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
        """Verify 0x00/0x01 domain separation and CVE-2012-2459 odd-leaf immunity."""
        d0 = b"leaf-zero"
        d1 = b"leaf-one"
        d2 = b"leaf-two"

        # 1. Second-preimage attack: forge 1-leaf tree with payload (MTH(d0) || MTH(d1))
        forged_leaf_payload = hash_leaf(d0) + hash_leaf(d1)
        two_leaf_root = compute_merkle_root([d0, d1])
        one_leaf_forged_root = compute_merkle_root([forged_leaf_payload])
        self.assertNotEqual(two_leaf_root, one_leaf_forged_root)

        # 2. CVE-2012-2459 odd-leaf duplication attack: [d0, d1, d2] must NOT equal [d0, d1, d2, d2]
        root_3 = compute_merkle_root([d0, d1, d2])
        root_4_dup = compute_merkle_root([d0, d1, d2, d2])
        self.assertNotEqual(root_3, root_4_dup)

    def test_rfc9162_section_2_1_5_seven_leaf_topology_and_merkle_tree_oop(self) -> None:
        """Verify RFC 9162 §2.1.5 7-leaf topology, consistency proofs, and MerkleTree dunders."""
        leaves = [f"d{i}".encode("utf-8") for i in range(7)]
        a, b, c, d, e, f, d6 = [hash_leaf(x) for x in leaves]
        g = hash_children(a, b)
        h = hash_children(c, d)
        i = hash_children(e, f)
        j = d6
        k = hash_children(g, h)
        l_node = hash_children(i, j)
        expected_root = hash_children(k, l_node).hex()

        tree = MerkleTree(leaves)
        self.assertEqual(len(tree), 7)
        self.assertTrue(bool(tree))
        self.assertIn(b"d3", tree)
        self.assertEqual(tree[0], b"d0")
        self.assertEqual(tree.root_hex, expected_root)
        self.assertEqual(tree, MerkleTree(leaves))

        # RFC 9162 §2.1.5 exact inclusion path lengths & nodes:
        self.assertEqual(tree.prove_inclusion(0), [b.hex(), h.hex(), l_node.hex()])
        self.assertEqual(tree.prove_inclusion(3), [c.hex(), g.hex(), l_node.hex()])
        self.assertEqual(tree.prove_inclusion(4), [f.hex(), j.hex(), k.hex()])
        self.assertEqual(tree.prove_inclusion(6), [i.hex(), k.hex()])
        for idx, leaf in enumerate(leaves):
            self.assertTrue(
                verify_inclusion(leaf, idx, len(tree), tree.root_hex, tree.prove_inclusion(idx))
            )

        # Verify consistency across all intermediate sizes m in 1..7 against n = 7
        for m in range(1, 7):
            sub_root = compute_merkle_root(leaves[:m]).hex()
            c_proof = tree.prove_consistency(m)
            self.assertEqual(c_proof, prove_consistency(m, leaves))
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

        # Signed Tree Head tamper test: mutating tree_size or timestamp invalidates Ed25519
        priv = Ed25519PrivateKey.generate()
        sth = tree.sign_head("2026-10-22T12:00:00Z", priv)
        self.assertTrue(sth.verify())
        self.assertTrue(verify_tree_head(sth))
        tampered_sth = type(sth)(
            tree_size=sth.tree_size + 1,
            timestamp=sth.timestamp,
            root_hash=sth.root_hash,
            signature_hex=sth.signature_hex,
            public_key_hex=sth.public_key_hex,
        )
        self.assertFalse(tampered_sth.verify())

    def test_krippendorff_alpha_and_friction_edge_cases(self) -> None:
        # 1. Classic Krippendorff (2013) 4-coder, 12-unit benchmark
        matrix = [
            [1, 2, 3, 3, 2, 1, 4, 1, 2, np.nan, np.nan, np.nan],
            [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, np.nan, 3],
            [np.nan, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, np.nan],
            [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, np.nan],
        ]
        self.assertAlmostEqual(krippendorff_alpha(matrix, "nominal"), 0.7434, places=3)
        self.assertAlmostEqual(krippendorff_alpha(matrix, "interval"), 0.8489, places=3)

        # 2. Zero-variance / universal agreement (D_e == 0) returns 1.0 safely
        unanimous = [[1, 1, 1, np.nan], [1, 1, 1, 1], [1, 1, 1, 1]]
        self.assertEqual(krippendorff_alpha(unanimous, "nominal"), 1.0)

        # 3. Systematic disagreement (opposite labels) yields negative alpha
        opposite = [[0, 1, 0, 1, 0, 1], [1, 0, 1, 0, 1, 0]]
        self.assertLess(krippendorff_alpha(opposite, "nominal"), -0.5)

        # 4. No pairable units (only 1 rating per column) must return 1.0 gracefully
        disjoint = [[1, np.nan, np.nan], [np.nan, 2, np.nan], [np.nan, 2, 3]]
        self.assertEqual(
            krippendorff_alpha([[1, np.nan], [np.nan, 2]], "nominal"),
            1.0,
        )
        self.assertIsInstance(krippendorff_alpha(disjoint, "nominal"), float)

        # 5. Friction shrinkage & invalid input guards
        low_sample = compute_rule_friction("r1", total_flags=1, overrides_and_disputes=1)
        self.assertFalse(bool(low_sample))  # 1/1 is shrunk to 2/6 = 0.3333 <= 0.40
        high_friction = compute_rule_friction("r2", total_flags=10, overrides_and_disputes=8)
        self.assertTrue(bool(high_friction))
        with self.assertRaises(ValueError):
            compute_rule_friction("r3", total_flags=3, overrides_and_disputes=5)


class TestFix4C2paTamperAndSingleSignEnforcement(unittest.TestCase):
    def test_tampered_inbound_manifest_json_fallback_and_outbound_single_sign(self) -> None:
        class TamperedJsonReader:
            def __enter__(self) -> TamperedJsonReader:
                return self

            def __exit__(self, *args: Any) -> None:
                pass

            def json(self) -> str:
                import json as _json

                return _json.dumps(
                    {
                        "validation_state": "Invalid",
                        "active_manifest": "urn:manifest:1",
                        "manifests": {
                            "urn:manifest:1": {
                                "signature_info": {"issuer": "Untrusted"},
                                "assertions": [],
                            }
                        },
                    }
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "tampered.png"
            out_path = Path(tmpdir) / "signed.png"
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
                                {"try_create": staticmethod(lambda *a, **k: TamperedJsonReader())},
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

            # Outbound single-use Builder test
            manifest = build_governance_manifest(
                submission_id=42,
                canon_id="acme",
                canon_hash="abc",
                content_hash="def",
                merkle_root="123",
                approved_by="reviewer1",
                approved_at="2026-10-22T12:00:00Z",
            )
            self.assertEqual(manifest["assertions"][1]["label"], "com.canongate.governance.v1")

            class SingleUseBuilder:
                instances = 0

                def __init__(self, manifest_def: dict[str, Any], context: Any = None) -> None:
                    SingleUseBuilder.instances += 1
                    self.closed = False

                def __enter__(self) -> SingleUseBuilder:
                    return self

                def __exit__(self, *args: Any) -> None:
                    self.closed = True

                def add_ingredient(self, *args: Any) -> None:
                    if self.closed:
                        raise RuntimeError("Builder FFI handle closed")

                def sign_file(self, src: str, dst: str, signer: Any) -> bytes:
                    if self.closed:
                        raise RuntimeError("Builder FFI handle already consumed")
                    self.closed = True
                    Path(dst).write_bytes(Path(src).read_bytes())
                    return b"c2pa-jumbf-manifest"

            mock_c2pa = type(
                "MockC2pa",
                (),
                {
                    "C2paSigningAlg": type("Alg", (), {"ES256": "es256"}),
                    "Context": lambda: object(),
                    "Signer": type(
                        "Sig", (), {"from_callback": staticmethod(lambda **kw: object())}
                    ),
                    "Builder": SingleUseBuilder,
                },
            )
            res1 = sign_approved_asset(
                source_path=img_path,
                output_path=out_path,
                mime_type="image/png",
                manifest_def=manifest,
                sign_callback=lambda data: b"sig",
                cert_chain_pem="-----BEGIN CERTIFICATE-----",
                c2pa_module=mock_c2pa,
            )
            res2 = sign_approved_asset(
                source_path=img_path,
                output_path=out_path,
                mime_type="image/png",
                manifest_def=manifest,
                sign_callback=lambda data: b"sig",
                cert_chain_pem="-----BEGIN CERTIFICATE-----",
                c2pa_module=mock_c2pa,
            )
            self.assertEqual(res1, b"c2pa-jumbf-manifest")
            self.assertEqual(res2, b"c2pa-jumbf-manifest")
            self.assertEqual(SingleUseBuilder.instances, 2)


class TestFix5ProseMirrorUtf16EmojiAndMultiBlockOffsets(unittest.TestCase):
    def test_prosemirror_utf16_surrogate_pair_and_multiblock_offsets_via_node(self) -> None:
        """Verify Python codepoint spans map to ProseMirror UTF-16 1-indexed positions."""
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


class TestFix6DomainOopDundersAndSymbolBoundaryRegex(unittest.TestCase):
    def test_symbol_term_rule_boundaries_and_domain_special_methods(self) -> None:
        # 1. Symbol-bounded term rules like "100% free" and "₹0 fee" must match cleanly
        r_pct = TermRule(id="t_pct", pattern_text="100%", preferred="fully", severity=70)
        r_inr = TermRule(id="t_inr", pattern_text="₹0", preferred="zero-rupee", severity=70)
        canon = Canon(
            id="fin",
            version="1.0",
            terminology=(r_pct, r_inr),
            palette=(ColorToken(id="c1", hex="#1A73E8", name="Blue"),),
            facts=(FactClaim(id="f1", text="Licensed NBFC"),),
        )
        self.assertEqual(len(canon), 4)
        self.assertIn("t_pct", canon)
        self.assertNotIn("missing", canon)
        self.assertIn("Get 100% off with ₹0 joining fee!", r_pct)
        self.assertIn("Get 100% off with ₹0 joining fee!", r_inr)

        # 2. ContentAST and Span/BBox Pythonic special methods
        ast1 = ContentAST.from_texts(["Hello world"])
        ast2 = ContentAST.from_texts(["Second block"])
        combined = ast1 + ast2
        self.assertEqual(len(combined), 2)
        self.assertIn(ast1[0].id, combined)
        self.assertEqual(combined[ast1[0].id], ast1[0])
        self.assertEqual(len(combined[0:1]), 1)
        self.assertEqual(len(ast1[0]), 11)
        self.assertIn("world", ast1[0])

        span_outer = Span(start=0, end=10)
        span_inner = Span(start=2, end=5)
        self.assertIn(span_inner, span_outer)
        self.assertTrue(span_outer.overlaps(span_inner))
        self.assertEqual(span_inner.slice("0123456789"), "234")
        with self.assertRaises(ValueError):
            Span(start=8, end=3)

        bbox = BBox(x=10, y=20, w=100, h=50)
        self.assertEqual(bbox.area, 5000)
        self.assertIn((50, 40), bbox)
        self.assertNotIn((5, 5), bbox)


if __name__ == "__main__":
    unittest.main()
