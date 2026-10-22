"""Tests for the text parser."""

from canongate.domain.ast import NodeKind
from canongate.parsers.text import parse_text


class TestTextParser:
    def test_single_paragraph(self):
        ast = parse_text("Hello world")
        assert len(ast) == 1
        assert ast[0].text == "Hello world"

    def test_multiple_paragraphs(self):
        ast = parse_text("Para one\n\nPara two\n\nPara three")
        assert len(ast) == 3

    def test_empty_paragraphs_skipped(self):
        ast = parse_text("Hello\n\n\n\n\nWorld")
        assert len(ast) == 2

    def test_whitespace_stripped(self):
        ast = parse_text("  hello  \n\n  world  ")
        assert ast[0].text == "hello"
        assert ast[1].text == "world"

    def test_all_text_nodes(self):
        ast = parse_text("a\n\nb")
        for node in ast:
            assert node.kind == NodeKind.TEXT

    def test_paths_assigned(self):
        ast = parse_text("a\n\nb", source="doc")
        assert ast[0].path == "doc/p[0]"
        assert ast[1].path == "doc/p[1]"
