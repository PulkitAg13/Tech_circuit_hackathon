"""Tests for the domain layer: pure logic, no I/O."""

import contextlib
import re
import unittest

try:
    import pytest
except ImportError:

    class _PytestShim:
        @staticmethod
        @contextlib.contextmanager
        def raises(exc_type, match=None):
            try:
                yield
            except exc_type as e:
                if match and not re.search(match, str(e), re.IGNORECASE):
                    raise AssertionError(f"Pattern {match!r} not found in {str(e)!r}") from e
            else:
                raise AssertionError(f"Did not raise {exc_type}")

    pytest = _PytestShim()
from pydantic import ValidationError

from canongate.domain import (
    Action,
    Canon,
    ContentAST,
    NodeKind,
    Role,
    Status,
    TextNode,
    TransitionError,
    next_status,
)
from canongate.domain.canon import TermRule
from canongate.domain.types import stable_finding_id
from canongate.domain.workflow import allowed_actions


class TestContentAST(unittest.TestCase):
    def test_from_texts(self):
        ast = ContentAST.from_texts(["hello", "world"])
        assert len(ast) == 2
        assert ast[0].text == "hello"
        assert ast[1].text == "world"

    def test_node_ids_are_deterministic(self):
        a = TextNode.from_text("hello")
        b = TextNode.from_text("hello")
        assert a.id == b.id

    def test_different_text_different_id(self):
        a = TextNode.from_text("hello")
        b = TextNode.from_text("world")
        assert a.id != b.id

    def test_of_kind(self):
        ast = ContentAST.from_texts(["a", "b"])
        text_nodes = list(ast.of_kind(NodeKind.TEXT))
        assert len(text_nodes) == 2

    def test_frozen(self):
        ast = ContentAST.from_texts(["x"])
        with pytest.raises((ValidationError, TypeError)):
            ast.nodes = ()  # type: ignore


class TestWorkflow(unittest.TestCase):
    def test_submit_draft(self):
        result = next_status(Status.DRAFT, Action.SUBMIT, Role.CREATOR)
        assert result == Status.IN_REVIEW

    def test_approve_in_review(self):
        result = next_status(Status.IN_REVIEW, Action.APPROVE, Role.REVIEWER)
        assert result == Status.APPROVED

    def test_creator_cannot_approve(self):
        with pytest.raises(TransitionError):
            next_status(Status.IN_REVIEW, Action.APPROVE, Role.CREATOR)

    def test_request_changes(self):
        result = next_status(Status.IN_REVIEW, Action.REQUEST_CHANGES, Role.REVIEWER)
        assert result == Status.CHANGES_REQUESTED

    def test_resubmit_after_changes(self):
        result = next_status(Status.CHANGES_REQUESTED, Action.SUBMIT, Role.CREATOR)
        assert result == Status.IN_REVIEW

    def test_publish_requires_admin(self):
        result = next_status(Status.APPROVED, Action.PUBLISH, Role.ADMIN)
        assert result == Status.PUBLISHED

    def test_reviewer_cannot_publish(self):
        with pytest.raises(TransitionError):
            next_status(Status.APPROVED, Action.PUBLISH, Role.REVIEWER)

    def test_allowed_actions_draft_creator(self):
        actions = allowed_actions(Status.DRAFT, Role.CREATOR)
        assert Action.SUBMIT in actions

    def test_allowed_actions_in_review_creator(self):
        actions = allowed_actions(Status.IN_REVIEW, Role.CREATOR)
        assert Action.RECALL in actions
        assert Action.APPROVE not in actions


class TestCanon(unittest.TestCase):
    def test_hash_deterministic(self):
        c1 = Canon(
            id="test",
            version="1",
            terminology=(TermRule(id="t1", pattern_text="bad", preferred="good"),),
        )
        c2 = Canon(
            id="test",
            version="1",
            terminology=(TermRule(id="t1", pattern_text="bad", preferred="good"),),
        )
        assert c1.hash == c2.hash

    def test_rule_lookup(self):
        rule = TermRule(id="t1", pattern_text="bad", preferred="good")
        canon = Canon(id="test", version="1", terminology=(rule,))
        assert canon["t1"] == rule

    def test_rule_lookup_missing(self):
        canon = Canon(id="test", version="1")
        with pytest.raises(KeyError):
            canon["nonexistent"]


class TestFindingId(unittest.TestCase):
    def test_stable(self):
        from canongate.domain.types import NodeId

        a = stable_finding_id("check1", "1.0", NodeId("node1"), "s:0-5")
        b = stable_finding_id("check1", "1.0", NodeId("node1"), "s:0-5")
        assert a == b

    def test_different_inputs(self):
        from canongate.domain.types import NodeId

        a = stable_finding_id("check1", "1.0", NodeId("node1"), "s:0-5")
        b = stable_finding_id("check1", "1.0", NodeId("node2"), "s:0-5")
        assert a != b


class TestResolutionValidation(unittest.TestCase):
    """Tests for validate_resolution — role/severity gating."""

    def test_anyone_can_accept(self):
        from canongate.domain.workflow import Role, validate_resolution

        # Should not raise for any role
        for role in Role:
            validate_resolution("accepted", severity=80, role=role)

    def test_creator_cannot_dismiss(self):
        from canongate.domain.workflow import ResolutionError, Role, validate_resolution

        with pytest.raises(ResolutionError, match="only reviewers"):
            validate_resolution("dismissed", severity=30, role=Role.CREATOR)

    def test_reviewer_can_dismiss_warning(self):
        from canongate.domain.workflow import Role, validate_resolution

        # severity < 50 = warning, reviewer can dismiss
        validate_resolution("dismissed", severity=30, role=Role.REVIEWER)

    def test_reviewer_cannot_dismiss_blocker(self):
        from canongate.domain.workflow import ResolutionError, Role, validate_resolution

        with pytest.raises(ResolutionError, match="blocker"):
            validate_resolution("dismissed", severity=80, role=Role.REVIEWER)

    def test_admin_can_dismiss_warning(self):
        from canongate.domain.workflow import Role, validate_resolution

        validate_resolution("overridden", severity=10, role=Role.ADMIN)

    def test_invalid_resolution(self):
        from canongate.domain.workflow import ResolutionError, Role, validate_resolution

        with pytest.raises(ResolutionError, match="Invalid resolution"):
            validate_resolution("yolo", severity=10, role=Role.ADMIN)
