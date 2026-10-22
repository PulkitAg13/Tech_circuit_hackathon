"""C2PA Inbound Provenance Check (`c2pa.inbound`).

Upstream `contentauth/c2pa-python` v0.38+ lifecycle notes:
1. Legacy thread-local settings and bare `Reader(path)` exception-driven probes
   are superseded by `c2pa.Context()` and `c2pa.Reader.try_create(path, context=ctx)`,
   which returns `None` cleanly when an image has no JUMBF manifest box.
2. Inspects `reader.get_validation_state()` (`"Valid"`, `"Trusted"`, `"Invalid"`)
   and checks `c2pa.actions` / `c2pa.actions.v2` assertions for IPTC AI-generated
   `digitalSourceType` URIs (`trainedAlgorithmicMedia`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from canongate.domain.ast import ImageNode, Node, NodeKind
from canongate.domain.canon import Canon, Rule
from canongate.domain.finding import BBox, C2paEvidence, Finding, Tier, Trace
from canongate.engine.check import Check

_AI_SOURCE_TYPES = (
    "trainedAlgorithmicMedia",
    "compositeWithTrainedAlgorithmicMedia",
    "algorithmicMedia",
)


def inspect_c2pa_asset(asset_path: str | Path, c2pa_module: Any = None) -> C2paEvidence:
    """Inspect an image asset for C2PA JUMBF Content Credentials using v0.38+ API."""
    if c2pa_module is None:
        try:
            import c2pa as c2pa_mod  # type: ignore[import-not-found]

            c2pa_module = c2pa_mod
        except ImportError:
            return C2paEvidence(
                has_manifest=False,
                validation_state="Unavailable",
                issuer=None,
                digital_source_type=None,
            )

    path_str = str(asset_path)
    ctx_cls = getattr(c2pa_module, "Context", None)
    reader_cls = getattr(c2pa_module, "Reader", None)
    if reader_cls is None:
        return C2paEvidence(has_manifest=False, validation_state="Unavailable")

    ctx = ctx_cls() if ctx_cls is not None else None
    try_create = getattr(reader_cls, "try_create", None)
    if callable(try_create):
        reader = try_create(path_str, context=ctx) if ctx is not None else try_create(path_str)
    else:
        try:
            reader = reader_cls(path_str)
        except Exception:
            reader = None

    if reader is None:
        return C2paEvidence(
            has_manifest=False,
            validation_state="Missing",
            issuer=None,
            digital_source_type=None,
        )

    with reader:
        val_state = (
            reader.get_validation_state()
            if hasattr(reader, "get_validation_state")
            else "Valid"
        )
        active: dict[str, Any] = (
            reader.get_active_manifest()
            if hasattr(reader, "get_active_manifest")
            else {}
        ) or {}

        sig_info = active.get("signature_info") or {}
        issuer = sig_info.get("issuer")
        digital_source_type: str | None = None

        for assertion in active.get("assertions") or []:
            label = str(assertion.get("label", ""))
            if label.startswith("c2pa.actions"):
                data = assertion.get("data") or {}
                for act in data.get("actions") or []:
                    dst = act.get("digitalSourceType")
                    if dst:
                        digital_source_type = str(dst)
                        break

        return C2paEvidence(
            has_manifest=True,
            validation_state=str(val_state),
            issuer=str(issuer) if issuer else None,
            digital_source_type=digital_source_type,
        )


class C2paInboundCheck(Check):
    check_id: ClassVar[str] = "c2pa.inbound"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.IMAGE})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        assert isinstance(node, ImageNode)
        path = Path(node.asset_path)
        if not path.exists():
            return []

        ev = inspect_c2pa_asset(path)
        if ev.validation_state == "Unavailable":
            return []

        bbox = BBox(x=0, y=0, w=max(1, node.width), h=max(1, node.height))
        rule_ref = Rule(
            rule_id="c2pa-provenance",
            rule_type="provenance",
            source_text="Visual assets must carry valid C2PA Content Credentials provenance",
        )

        if ev.has_manifest and ev.validation_state == "Invalid":
            return [
                self.finding(
                    node=node,
                    locator=bbox,
                    severity=90,
                    message="C2PA Content Credentials signature or data hash is INVALID (tampered asset).",
                    rule_ref=rule_ref,
                    evidence=ev,
                    trace=Trace(tier=Tier.DETERMINISTIC),
                )
            ]

        if ev.digital_source_type and any(t in ev.digital_source_type for t in _AI_SOURCE_TYPES):
            return [
                self.finding(
                    node=node,
                    locator=bbox,
                    severity=45,
                    message=f"Asset carries AI-generated C2PA provenance ({ev.digital_source_type}); verify disclosure.",
                    rule_ref=rule_ref,
                    evidence=ev,
                    trace=Trace(tier=Tier.DETERMINISTIC),
                )
            ]

        return []
