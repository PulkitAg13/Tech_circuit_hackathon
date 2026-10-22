"""Tests for the engine: check registry, terminology check, runner."""

import pytest

from canongate.domain.ast import ContentAST
from canongate.domain.canon import Canon, TermRule
from canongate.engine.check import Check
from canongate.engine.runner import run_checks_collect


class TestRegistry:
    def test_terminology_check_registered(self):
        assert "terminology.banned" in Check.get_all()

    def test_get_by_id(self):
        cls = Check.get("terminology.banned")
        assert cls is not None
        assert cls.check_id == "terminology.banned"


class TestTerminologyBannedCheck:
    @pytest.fixture
    def canon(self):
        return Canon(
            id="test",
            version="1",
            terminology=(
                TermRule(id="t1", pattern_text="cheap", preferred="affordable", severity=60),
                TermRule(id="t2", pattern_text="buy", preferred="purchase", severity=40),
            ),
        )

    @pytest.fixture
    def check_instance(self):
        cls = Check.get("terminology.banned")
        return cls()

    def test_finds_banned_term(self, check_instance, canon):
        from canongate.domain.ast import TextNode

        node = TextNode.from_text("This is a cheap product")
        findings = check_instance.run(node, canon)
        assert len(findings) == 1
        assert findings[0].evidence.term == "cheap"
        assert findings[0].evidence.preferred == "affordable"

    def test_finds_multiple_terms(self, check_instance, canon):
        from canongate.domain.ast import TextNode

        node = TextNode.from_text("Buy our cheap stuff")
        findings = check_instance.run(node, canon)
        assert len(findings) == 2
        terms = {f.evidence.term.lower() for f in findings}
        assert terms == {"buy", "cheap"}

    def test_no_findings_for_clean_text(self, check_instance, canon):
        from canongate.domain.ast import TextNode

        node = TextNode.from_text("This is an affordable product")
        findings = check_instance.run(node, canon)
        assert len(findings) == 0

    def test_case_insensitive(self, check_instance, canon):
        from canongate.domain.ast import TextNode

        node = TextNode.from_text("CHEAP and Cheap")
        findings = check_instance.run(node, canon)
        assert len(findings) == 2

    def test_suggestion_provided(self, check_instance, canon):
        from canongate.domain.ast import TextNode

        node = TextNode.from_text("This is cheap")
        findings = check_instance.run(node, canon)
        assert findings[0].suggestion is not None
        assert findings[0].suggestion.replacements[0].replacement == "affordable"


@pytest.mark.asyncio
class TestRunner:
    async def test_run_checks_collect(self):
        canon = Canon(
            id="test",
            version="1",
            terminology=(
                TermRule(id="t1", pattern_text="cheap", preferred="affordable", severity=60),
            ),
        )
        ast = ContentAST.from_texts(["This is cheap", "This is fine"])
        findings = await run_checks_collect(ast, canon)
        assert len(findings) == 1
        assert findings[0].check_id == "terminology.banned"

    async def test_run_checks_no_findings(self):
        canon = Canon(id="test", version="1")
        ast = ContentAST.from_texts(["All good here"])
        findings = await run_checks_collect(ast, canon)
        assert len(findings) == 0
