"""Tests for Modern Gemini Multi-Model Cascading Fallback System."""

from __future__ import annotations

import unittest
from typing import Any

from canongate.engine.rewriter import (
    DEFAULT_GEMINI_MODEL_CASCADE,
    ConstrainedRewriter,
    ResolvedRewriterBackend,
)
from canongate.parsers.llm_table import (
    DEFAULT_GEMINI_MODEL_CASCADE as TABLE_GEMINI_CASCADE,
)
from canongate.parsers.llm_table import (
    LLMProviderConfig,
    MultiProviderJsonLLM,
)


class TestGeminiModelCascade(unittest.TestCase):
    def test_01_cascade_model_definitions_modern_and_prioritized(self) -> None:
        """Verify modern Gemini 3.x models are prioritized in descending generation order."""
        self.assertIn("gemini-3.8-flash", DEFAULT_GEMINI_MODEL_CASCADE)
        self.assertIn("gemini-3.6-flash", DEFAULT_GEMINI_MODEL_CASCADE)
        self.assertIn("gemini-3.5-flash", DEFAULT_GEMINI_MODEL_CASCADE)
        self.assertIn("gemini-flash-lite-latest", DEFAULT_GEMINI_MODEL_CASCADE)
        self.assertEqual(DEFAULT_GEMINI_MODEL_CASCADE, TABLE_GEMINI_CASCADE)

        # Primary flagship model is top of cascade
        self.assertEqual(DEFAULT_GEMINI_MODEL_CASCADE[0], "gemini-3.8-flash")
        self.assertEqual(DEFAULT_GEMINI_MODEL_CASCADE[1], "gemini-3.6-flash")

    def test_02_mock_cascade_failover_when_primary_model_unavailable(self) -> None:
        """Verify that when top model returns 503 or 404, it cascades to the next model."""
        attempted_urls: list[str] = []

        def mock_transport(
            url: str,
            payload: dict[str, Any],
            headers: dict[str, str],
            timeout_s: float,
        ) -> dict[str, Any]:
            attempted_urls.append(url)
            # Fail on gemini-3.8-flash (simulate 503 high demand spike)
            if "gemini-3.8-flash" in url:
                raise RuntimeError("HTTP 503: Model experiencing high demand")
            # Succeed on gemini-3.6-flash
            if "gemini-3.6-flash" in url:
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": (
                                            '{"rewritten_text": "Approved loan", '
                                            '"rationale": "fixed"}'
                                        ),
                                        "thoughtSignature": "mock_sig_123",
                                    }
                                ]
                            }
                        }
                    ]
                }
            raise RuntimeError(f"Unexpected model URL: {url}")

        rewriter = ConstrainedRewriter(http_transport=mock_transport)
        backend = ResolvedRewriterBackend(
            provider="gemini",
            model="gemini-3.8-flash",
            api_key="mock-api-key",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            timeout_s=5.0,
        )

        res, effective_model = rewriter._invoke_configured_backend_sync(
            backend,
            system_prompt="Return compliant JSON",
            user_prompt="Rewrite text",
        )

        self.assertIsNotNone(res)
        self.assertEqual(res, "Approved loan")
        # Verified it attempted 3.8 first, then cascaded to 3.6
        self.assertTrue(any("gemini-3.8-flash" in u for u in attempted_urls))
        self.assertTrue(any("gemini-3.6-flash" in u for u in attempted_urls))
        # Effective model returned is the surviving model
        self.assertEqual(effective_model, "gemini-3.6-flash")

    def test_03_table_parser_gemini_cascade_mock(self) -> None:
        """Verify TableGrid parser also cascades through models on failure."""
        attempted_models: list[str] = []

        def mock_table_transport(
            url: str,
            payload: dict[str, Any],
            headers: dict[str, str],
            timeout_s: float,
        ) -> dict[str, Any]:
            for m in DEFAULT_GEMINI_MODEL_CASCADE:
                if f"/models/{m}:generateContent" in url:
                    attempted_models.append(m)
                    break
            if len(attempted_models) == 1:
                raise RuntimeError("503 Service Unavailable")
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"headers": ["Tier", "Rate"], "rows": [["Gold", "10%"]]}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

        cfg = LLMProviderConfig(
            provider="gemini",
            model="gemini-3.8-flash",
            api_key="mock-key",
            base_url="https://generativelanguage.googleapis.com/v1beta",
        )
        llm = MultiProviderJsonLLM(cfg, transport=mock_table_transport)
        out = llm._call_gemini("sys", "user")

        self.assertIsNotNone(out)
        self.assertEqual(out.get("headers"), ["Tier", "Rate"])
        self.assertGreaterEqual(len(attempted_models), 2)
        self.assertEqual(attempted_models[0], "gemini-3.8-flash")
        self.assertEqual(attempted_models[1], "gemini-3.6-flash")


if __name__ == "__main__":
    unittest.main()
