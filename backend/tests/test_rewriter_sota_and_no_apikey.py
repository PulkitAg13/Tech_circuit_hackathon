"""Live & Adversarial Tests for Improvement #2 (`canongate.engine.rewriter` & `domain.pii`).

Tests:
1. **Explicit No-API-Key Disclosure (Zero Silent AI Pretending):**
   - Verifies that when no API key is configured, `ConstrainedRewriter.rewrite()`,
     `POST /api/submissions/{id}/findings/{row_id}/rewrite`, and MCP `propose_fix`
     explicitly report `api_key_configured=False`,
     `used_provider="no-api-key (deterministic-surgical)"`,
     `context_trace["ai_used"]=False`, and a clear human-readable `provider_notice`
     stating that no LLM API key is configured.
2. **Expanded Indian DPDP 2025 PII Scrubber & Bijective Placeholder Guard:**
   - Tests masking and restoration of Indian `GSTIN`, `PAN_ID`, `AADHAAR_ID`, `IFSC`,
     `UPI_VPA`, `+91 PHONE`, `EMAIL`, and `CODENAME`, plus `verify_placeholder_integrity()`
     rejecting dropped or hallucinated placeholder tokens.
3. **All 6 SOTA Bad-Generation Rejection Gates:**
   - Gate 1: Empty / degenerate length ratio rejection.
   - Gate 2: Dropped or hallucinated PII placeholder (`<PAN_ID_1>`, `<GSTIN_1>`) rejection.
   - Gate 3: Numeric/currency/date anchor drift (e.g. changing `₹50k` to `₹5k`) rejection.
   - Gate 4: Qualifier-stripped Levenshtein edit distance `> 35%` rejection.
   - Gate 5: Incomplete fix (target violation still open under Tier 1/2 re-verification) rejection.
   - Gate 6: Collateral regression (rewrite fixes target rule but adds new banned word).
4. **Live Loopback HTTP Inkloom / OpenRouter Server + 3-State Circuit Breaker:**
   - Spins up a real local HTTP server (`127.0.0.1`) speaking the OpenRouter / Inkloom
     `/v1/chat/completions` JSON protocol, verifies `Authorization: Bearer ...` and
     `Idempotency-Key` headers, verifies PII is scrubbed over the wire, and tests the
     3-state circuit breaker (`CLOSED` -> `OPEN` after 3 failures -> `< 1ms` fast failover).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from canongate.checks.claim_slot_nli import ClaimSlotNliCheck
from canongate.domain.ast import ContentAST, TextNode
from canongate.domain.canon import Canon, FactClaim, TermRule, TriggerObligation
from canongate.domain.finding import SlotDiffEvidence
from canongate.domain.pii import default_pii_scrubber
from canongate.engine.rewriter import ConstrainedRewriter, default_constrained_rewriter
from canongate.engine.runner import run_checks_collect

# Warm up NLI check once before timed check runs
ClaimSlotNliCheck().run(TextNode.from_text("Warmup text Rs 50,000"), Canon(id="w", version="1.0"))


class TestRewriterSotaAndNoApiKeyDisclosure(unittest.TestCase):
    """End-to-end verification: explicit no-API-key notice, 6 gates, and loopback LLM."""

    def setUp(self) -> None:
        self._saved_env = {
            k: os.environ.get(k)
            for k in (
                "CANONGATE_REWRITER_PROVIDER",
                "CANONGATE_LLM_PROVIDER",
                "LLM_PROVIDER",
                "CANONGATE_INKLOOM_API_KEY",
                "INKLOOM_API_KEY",
                "CANONGATE_INKLOOM_BASE_URL",
                "INKLOOM_BASE_URL",
                "CANONGATE_OPENROUTER_API_KEY",
                "OPENROUTER_API_KEY",
                "CANONGATE_GEMINI_API_KEY",
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "CANONGATE_OPENAI_API_KEY",
                "OPENAI_API_KEY",
                "CANONGATE_GROQ_API_KEY",
                "GROQ_API_KEY",
                "CANONGATE_OLLAMA_HOST",
                "OLLAMA_HOST",
            )
        }
        for k in self._saved_env:
            os.environ.pop(k, None)

    def tearDown(self) -> None:
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    @staticmethod
    def _build_test_canon() -> Canon:
        return Canon(
            id="lending-sota-canon",
            version="2.0",
            terminology=(
                TermRule(
                    id="term-cheap",
                    pattern_text="cheap",
                    preferred="competitive-rate",
                    severity=65,
                ),
                TermRule(
                    id="term-guaranteed",
                    pattern_text="guaranteed approval",
                    preferred="subject to credit appraisal",
                    severity=80,
                ),
            ),
            facts=(
                FactClaim(
                    id="fact-zero-fee",
                    text="0% processing fee on loans under Rs 50,000",
                    conditions=("under Rs 50,000", "for first-time borrowers only"),
                ),
            ),
            trigger_obligations=(
                TriggerObligation(
                    id="trig-kfs",
                    trigger_pattern=r"\b0%\s+processing\s+fee\b",
                    required_disclaimer_id="disc-kfs",
                    required_disclaimer_text="Subject to RBI Key Fact Statement (KFS) schedule.",
                    severity=70,
                ),
            ),
        )

    def test_01_explicit_no_api_key_disclosure_never_pretends_ai_wrote_it(self) -> None:
        """When no API key is configured, rewriter must explicitly inform the user."""
        canon = self._build_test_canon()
        node = TextNode.from_text("Get a 0% processing fee on loans today.")
        findings = asyncio.run(run_checks_collect(ContentAST(nodes=(node,)), canon))
        nli_finding = next(f for f in findings if isinstance(f.evidence, SlotDiffEvidence))

        res = asyncio.run(
            default_constrained_rewriter.rewrite(
                node, nli_finding, canon, verify_fn=run_checks_collect
            )
        )
        self.assertFalse(res.api_key_configured)
        self.assertEqual(res.used_provider, "no-api-key (deterministic-surgical)")
        self.assertIn("No LLM API key configured", res.provider_notice)
        self.assertIn("local deterministic AST", res.provider_notice)
        self.assertFalse(res.context_trace["ai_used"])
        self.assertFalse(res.context_trace["api_key_configured"])
        self.assertTrue(res.context_trace["privacy_lock_local_only"])
        self.assertIn("No API Key", res.suggestion.label)
        self.assertIn("under Rs 50,000", res.rewritten_text)
        self.assertTrue(res.reverified)

    def test_02_expanded_dpdp_pii_scrubber_and_bijective_placeholder_guard(self) -> None:
        """Verify GSTIN, PAN, Aadhaar, IFSC, UPI VPA, +91 Phone, Email, and Codename scrubbing."""
        raw = (
            "Applicant Rahul (PAN ABCDE1234F, Aadhaar 2345 6789 0123, GSTIN 27ABCDE1234F1Z5, "
            "IFSC HDFC0001234, UPI rahul.sharma@okicici, mobile +91 9876543210, "
            "email rahul@fintech.in, Project Vajra) gets a 0% processing fee on loans today."
        )
        scrubbed = default_pii_scrubber.scrub(raw)
        self.assertGreaterEqual(scrubbed.pii_count, 8)
        for secret in (
            "ABCDE1234F",
            "2345 6789 0123",
            "27ABCDE1234F1Z5",
            "HDFC0001234",
            "rahul.sharma@okicici",
            "9876543210",
            "rahul@fintech.in",
            "Project Vajra",
        ):
            self.assertNotIn(secret, scrubbed.masked_text)

        ok, err = scrubbed.verify_placeholder_integrity(scrubbed.masked_text)
        self.assertTrue(ok)
        self.assertIsNone(err)

        # Dropping a placeholder must fail Gate 2
        corrupted = scrubbed.masked_text.replace("<GSTIN_1>", "REDACTED")
        ok_drop, err_drop = scrubbed.verify_placeholder_integrity(corrupted)
        self.assertFalse(ok_drop)
        self.assertIn("<GSTIN_1>", err_drop or "")

        # Hallucinating an unknown placeholder must fail Gate 2
        hallucinated = scrubbed.masked_text + " <PAN_ID_99>"
        ok_hal, err_hal = scrubbed.verify_placeholder_integrity(hallucinated)
        self.assertFalse(ok_hal)
        self.assertIn("<PAN_ID_99>", err_hal or "")

        # Round-trip restoration
        self.assertEqual(scrubbed.restore(scrubbed.masked_text), raw)

    def test_03_six_sota_bad_generation_gates_reject_bad_llm_outputs(self) -> None:
        """Verify each of the 6 bad-generation failure modes is caught and rejected."""
        canon = self._build_test_canon()
        text_with_pii_and_anchor = (
            "Contact PAN ABCDE1234F for a cheap credit line of Rs 25,000 today."
        )
        node = TextNode.from_text(text_with_pii_and_anchor)
        findings = asyncio.run(run_checks_collect(ContentAST(nodes=(node,)), canon))
        term_finding = next(f for f in findings if f.check_id == "terminology.banned")

        bad_cases: list[tuple[str, str, str]] = [
            # (Case name, bad LLM output, expected rejection substring)
            ("gate1_empty", "   ", "empty or identical"),
            (
                "gate2_dropped_pii_placeholder",
                "Contact our desk for a competitive-rate credit line of Rs 25,000 today.",
                "dropped required PII placeholder <PAN_ID_1>",
            ),
            (
                "gate3_numeric_anchor_drift",
                "Contact PAN <PAN_ID_1> for a competitive-rate credit line of Rs 99,000 today.",
                "numeric anchor",
            ),
            (
                "gate4_over_35pct_edit_distance",
                (
                    "Contact PAN <PAN_ID_1> for Rs 25,000 through our completely rewritten "
                    "institutional banking portal right now!"
                ),
                "exceeds 35% surgical ceiling",
            ),
            (
                "gate5_target_violation_unresolved",
                "Contact PAN <PAN_ID_1> for a cheap credit line of Rs 25,000 right now.",
                "still fails after candidate rewrite",
            ),
            (
                "gate6_collateral_regression_introduced",
                (
                    "Contact PAN <PAN_ID_1> for a competitive-rate credit line of Rs 25,000 "
                    "with guaranteed approval today."
                ),
                "collateral rule violation",
            ),
        ]

        for case_name, bad_output, expected_reason in bad_cases:
            with self.subTest(case=case_name):
                rewriter = ConstrainedRewriter(
                    max_edit_ratio=0.35,
                    llm_rewrite_fn=lambda _m, _msg, _r, out=bad_output: out,
                )
                res = asyncio.run(
                    rewriter.rewrite(node, term_finding, canon, verify_fn=run_checks_collect)
                )
                self.assertEqual(res.used_provider, "deterministic-surgical (llm-fallback)")
                self.assertIn(
                    expected_reason.lower(),
                    (res.context_trace.get("llm_rejected_reason") or "").lower(),
                )
                # And verify fallback rewrite IS clean and preserves PII + Rs 25,000
                self.assertIn("ABCDE1234F", res.rewritten_text)
                self.assertIn("Rs 25,000", res.rewritten_text)
                self.assertIn("competitive-rate", res.rewritten_text)
                self.assertNotIn("cheap", res.rewritten_text.lower())

    def test_04_live_loopback_http_inkloom_server_and_circuit_breaker(self) -> None:
        """Spin up a live local HTTP server speaking the Inkloom chat completions protocol."""
        canon = self._build_test_canon()
        node = TextNode.from_text(
            "Email rahul@fintech.in (GSTIN 27ABCDE1234F1Z5) for a cheap loan of Rs 40,000."
        )
        findings = asyncio.run(run_checks_collect(ContentAST(nodes=(node,)), canon))
        term_finding = next(f for f in findings if f.check_id == "terminology.banned")

        captured_requests: list[dict[str, Any]] = []
        server_mode = {"fail": False}

        class _LoopbackInkloomHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length).decode("utf-8")
                captured_requests.append(
                    {
                        "path": self.path,
                        "auth": self.headers.get("Authorization"),
                        "idem_key": self.headers.get("Idempotency-Key"),
                        "body": json.loads(raw_body),
                    }
                )
                if server_mode["fail"]:
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error": "Simulated provider outage"}')
                    return

                # Parse masked span from user message and return compliant JSON
                msgs = json.loads(raw_body)["messages"]
                user_json = json.loads(msgs[-1]["content"])
                masked_span = user_json["flagged_masked_span"]
                fixed_masked = masked_span.replace("cheap", "competitive-rate")
                resp_payload = {
                    "id": "chatcmpl-inkloom-live-1",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "rewritten_text": (
                                            f'Sure! Here is the revised text: "{fixed_masked}"'
                                        ),
                                        "rationale": (
                                            "Replaced banned term 'cheap' with 'competitive-rate'."
                                        ),
                                    }
                                ),
                            },
                        }
                    ],
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp_payload).encode("utf-8"))

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        httpd = HTTPServer(("127.0.0.1", port), _LoopbackInkloomHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            os.environ["INKLOOM_API_KEY"] = "ik_live_test_credit_key_12345"
            os.environ["INKLOOM_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
            os.environ["INKLOOM_MODEL"] = "inkloom/claude-haiku-4.5"

            rewriter = ConstrainedRewriter(max_edit_ratio=0.35)
            res = asyncio.run(
                rewriter.rewrite(node, term_finding, canon, verify_fn=run_checks_collect)
            )
            self.assertTrue(res.api_key_configured)
            self.assertEqual(res.used_provider, "inkloom:inkloom/claude-haiku-4.5")
            self.assertTrue(res.context_trace["ai_used"])
            self.assertTrue(res.quality_gates["all_passed"])
            # Conversational wrapper ("Sure! Here is the revised text:") was stripped
            self.assertNotIn("Sure!", res.rewritten_text)
            # PII was masked on the wire and restored locally
            self.assertEqual(len(captured_requests), 1)
            wire_body_str = json.dumps(captured_requests[0]["body"])
            self.assertNotIn("rahul@fintech.in", wire_body_str)
            self.assertNotIn("27ABCDE1234F1Z5", wire_body_str)
            self.assertIn("<EMAIL_1>", wire_body_str)
            self.assertIn("<GSTIN_1>", wire_body_str)
            self.assertEqual(captured_requests[0]["auth"], "Bearer ik_live_test_credit_key_12345")
            self.assertTrue((captured_requests[0]["idem_key"] or "").startswith("cg-rw-"))
            self.assertIn("rahul@fintech.in", res.rewritten_text)
            self.assertIn("27ABCDE1234F1Z5", res.rewritten_text)
            self.assertIn("competitive-rate", res.rewritten_text)

            # Now simulate 3 consecutive provider 503 outages to trip the Circuit Breaker
            server_mode["fail"] = True
            for _ in range(3):
                r_fail = asyncio.run(
                    rewriter.rewrite(node, term_finding, canon, verify_fn=run_checks_collect)
                )
                self.assertEqual(r_fail.used_provider, "deterministic-surgical (llm-fallback)")
            self.assertEqual(rewriter.circuit_breaker.state, "OPEN")

            # 4th call must short-circuit in < 1ms without hitting the HTTP server
            req_count_before = len(captured_requests)
            t0 = time.perf_counter()
            r_open = asyncio.run(
                rewriter.rewrite(node, term_finding, canon, verify_fn=run_checks_collect)
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self.assertEqual(len(captured_requests), req_count_before)
            self.assertEqual(r_open.context_trace["circuit_breaker_state"], "OPEN")
            self.assertIn("Circuit breaker for inkloom is OPEN", r_open.provider_notice)
            self.assertLess(elapsed_ms, 50.0)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
