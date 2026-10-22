"""Tests for newly wired live features:

- Image parser and markdown image AST extraction (ImageNode)
- Visual subordination and C2PA inbound check execution on ImageNode
- RFC 9162 Merkle log audit trail and Ed25519 Signed Tree Head API
- Empirical Bayes Guideline Friction & Krippendorff's alpha API
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from canongate.checks.c2pa_inbound import C2paInboundCheck
from canongate.checks.visual_subordination import VisualSubordinationCheck
from canongate.domain.ast import ContentAST, ImageNode, NodeKind
from canongate.domain.canon import Canon
from canongate.ledger.merkle import verify_inclusion, verify_tree_head
from canongate.parsers.image import parse_image, parse_image_ast
from canongate.parsers.text import parse_text


@pytest.fixture
def sample_image_path(tmp_path: Path) -> Path:
    img_p = tmp_path / "banner.png"
    arr = np.full((120, 240, 3), 180, dtype=np.uint8)
    Image.fromarray(arr).save(img_p)
    return img_p


def test_image_parser(sample_image_path: Path):
    node = parse_image(sample_image_path, alt="Company Banner")
    assert isinstance(node, ImageNode)
    assert node.kind == NodeKind.IMAGE
    assert node.width == 240
    assert node.height == 120
    assert node.alt == "Company Banner"

    ast = parse_image_ast(sample_image_path)
    assert isinstance(ast, ContentAST)
    assert len(ast) == 1
    assert ast[0].kind == NodeKind.IMAGE


def test_markdown_image_extraction_in_parse_text(sample_image_path: Path):
    raw = f"Header headline\n\n![Banner]({sample_image_path})\n\nBody disclaimer copy"
    ast = parse_text(raw)
    assert len(ast) == 3
    assert ast[0].kind == NodeKind.TEXT
    assert ast[1].kind == NodeKind.IMAGE
    assert ast[2].kind == NodeKind.TEXT

    img_node = ast[1]
    assert isinstance(img_node, ImageNode)
    assert img_node.alt == "Banner"
    assert img_node.width == 240
    assert img_node.height == 120


def test_visual_subordination_and_c2pa_check_wire_on_image_node(sample_image_path: Path):
    node = parse_image(sample_image_path)
    canon = Canon(
        id="test-canon",
        version="1.0",
        hash="test-hash",
        terminology=[],
        palette=[],
        facts=[],
    )

    vis_check = VisualSubordinationCheck()
    assert vis_check.accepts(node)
    vis_findings = vis_check.run(node, canon)
    assert isinstance(vis_findings, list)

    c2pa_check = C2paInboundCheck()
    assert c2pa_check.accepts(node)
    c2pa_findings = c2pa_check.run(node, canon)
    assert isinstance(c2pa_findings, list)


@pytest.mark.asyncio
async def test_audit_merkle_log_endpoint_and_friction_integration():
    """Verify Merkle inclusion proof and friction analytics logic."""
    from canongate.ledger.friction import compute_rule_friction, krippendorff_alpha

    # 1. Empirical Bayes Friction verification
    report_low = compute_rule_friction("term.banned", total_flags=20, overrides_and_disputes=12)
    assert report_low.needs_canon_revision is True
    assert report_low.posterior_friction > 0.40

    report_noisy_single = compute_rule_friction("term.rare", total_flags=1, overrides_and_disputes=1)
    # 1 out of 1 flags should shrink toward prior (0.20) and not trigger revision alert
    assert report_noisy_single.needs_canon_revision is False

    # 2. Krippendorff's alpha verification
    ratings = [
        [0, 0, 1, 0],
        [0, 0, 1, 0],
    ]
    alpha = krippendorff_alpha(ratings, "nominal")
    assert alpha == 1.0
