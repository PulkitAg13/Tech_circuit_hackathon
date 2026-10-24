"""Tests for the engine: check registry, terminology check, runner."""

import asyncio
import unittest

try:
    import pytest
except ImportError:
    pytest = None  # type: ignore[assignment]

from canongate.domain.ast import ContentAST, TextNode
from canongate.domain.canon import Canon, TermRule
from canongate.engine.check import Check
from canongate.engine.runner import run_checks_collect


class TestRegistry(unittest.TestCase):
    def test_terminology_check_registered(self):
        assert "terminology.banned" in Check.get_all()

    def test_get_by_id(self):
        cls = Check.get("terminology.banned")
        assert cls is not None
        assert cls.check_id == "terminology.banned"


class TestTerminologyBannedCheck(unittest.TestCase):
    def setUp(self):
        self.canon = Canon(
            id="test",
            version="1",
            terminology=(
                TermRule(id="t1", pattern_text="cheap", preferred="affordable", severity=60),
                TermRule(id="t2", pattern_text="buy", preferred="purchase", severity=40),
            ),
        )
        cls = Check.get("terminology.banned")
        assert cls is not None
        self.check_instance = cls()

    def test_finds_banned_term(self):
        node = TextNode.from_text("This is a cheap product")
        findings = self.check_instance.run(node, self.canon)
        assert len(findings) == 1
        assert findings[0].evidence.term == "cheap"
        assert findings[0].evidence.preferred == "affordable"

    def test_finds_multiple_terms(self):
        node = TextNode.from_text("Buy our cheap stuff")
        findings = self.check_instance.run(node, self.canon)
        assert len(findings) == 2
        terms = {f.evidence.term.lower() for f in findings}
        assert terms == {"buy", "cheap"}

    def test_no_findings_for_clean_text(self):
        node = TextNode.from_text("This is an affordable product")
        findings = self.check_instance.run(node, self.canon)
        assert len(findings) == 0

    def test_case_insensitive(self):
        node = TextNode.from_text("CHEAP and Cheap")
        findings = self.check_instance.run(node, self.canon)
        assert len(findings) == 2

    def test_suggestion_provided(self):
        node = TextNode.from_text("This is cheap")
        findings = self.check_instance.run(node, self.canon)
        assert findings[0].suggestion is not None
        assert findings[0].suggestion.replacements[0].replacement == "affordable"


class TestRunner(unittest.TestCase):
    def test_run_checks_collect(self):
        canon = Canon(
            id="test",
            version="1",
            terminology=(
                TermRule(id="t1", pattern_text="cheap", preferred="affordable", severity=60),
            ),
        )
        ast = ContentAST.from_texts(["This is cheap", "This is fine"])
        findings = asyncio.run(run_checks_collect(ast, canon))
        assert len(findings) == 1
        assert findings[0].check_id == "terminology.banned"

    def test_run_checks_no_findings(self):
        canon = Canon(id="test", version="1")
        ast = ContentAST.from_texts(["All good here"])
        findings = asyncio.run(run_checks_collect(ast, canon))
        assert len(findings) == 0
