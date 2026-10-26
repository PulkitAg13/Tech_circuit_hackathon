r"""Standalone CanonGate Command-Line Interface.

Commands:
  - `canongate verify <cert.json>`
  - `canongate benchmark`
  - `canongate gate --canon <id_or_path> --paths <file_or_glob...>`
  - `canongate mcp`

Registered under `[project.scripts]` in `backend/pyproject.toml`:
  `uv run canongate verify cert.json`
  `uv run canongate benchmark`
  `uv run canongate gate --canon indian-digital-lending \`
  `    --paths fixtures/golden_bundle/acme_launch.yaml`
  `uv run canongate mcp`
  `uv run canongate-mcp`
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from canongate.canon.loader import load_canon
from canongate.engine.conformal import default_calibrator, run_redteam_benchmark
from canongate.engine.runner import run_checks_collect
from canongate.ledger.certificate import GovernanceCertificate
from canongate.mcp.batch import resolve_reference_inputs
from canongate.mcp.server import run_stdio_server
from canongate.parsers.bundle import parse_bundle
from canongate.settings import settings as _settings  # noqa: F401


def _cmd_verify(cert_path: Path, *, output_json: bool = False) -> int:
    if not cert_path.is_file():
        msg = f"Certificate file not found: {cert_path}"
        if output_json:
            print(json.dumps({"valid": False, "errors": [msg]}))
        else:
            print(f"[FAIL] {msg}", file=sys.stderr)
        return 1

    try:
        raw_data = json.loads(cert_path.read_text(encoding="utf-8"))
        cert = GovernanceCertificate.from_dict(raw_data)
    except Exception as exc:
        msg = f"Failed to parse certificate JSON: {exc}"
        if output_json:
            print(json.dumps({"valid": False, "errors": [msg]}))
        else:
            print(f"[FAIL] {msg}", file=sys.stderr)
        return 1

    result = cert.verify()
    if output_json:
        print(
            json.dumps(
                {
                    "submission_id": cert.submission_id,
                    "canon_id": cert.canon_id,
                    "canon_hash": cert.canon_hash,
                    "content_hash": cert.content_hash,
                    "tree_size": cert.signed_tree_head.tree_size,
                    "merkle_root": cert.signed_tree_head.root_hash,
                    **result.to_dict(),
                },
                indent=2,
            )
        )
        return 0 if result.valid else 1

    if result.valid:
        print(
            f"[PASS] CanonGate Certificate Verified "
            f"(Submission #{cert.submission_id}: {cert.title!r})\n"
            f"  • Status:          {cert.status}\n"
            f"  • Canon Binding:   {cert.canon_id} ({cert.canon_hash[:16]}...)\n"
            f"  • Content SHA-256: {cert.content_hash[:16]}...\n"
            f"  • Hash Chain:      VALID ({len(cert.events)} sequential event(s))\n"
            f"  • RFC 9162 Merkle: VALID (root={cert.signed_tree_head.root_hash[:16]}...)\n"
            f"  • Ed25519 STH Sig: VALID (pubkey={cert.signed_tree_head.public_key_hex[:16]}...)"
        )
        return 0

    print(
        f"[FAIL] CanonGate Certificate Verification FAILED (Submission #{cert.submission_id}):",
        file=sys.stderr,
    )
    for err in result.errors:
        print(f"  ✗ {err}", file=sys.stderr)
    return 1


def _cmd_benchmark(*, output_json: bool = False) -> int:
    report = run_redteam_benchmark()
    if output_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.to_markdown_table())
    return 0 if (report.overall_recall == 1.0 and report.false_positives == 0) else 1


def _resolve_canon_target(canon_arg: str):
    cand_path = Path(canon_arg)
    if cand_path.is_file():
        return load_canon(cand_path)
    from canongate.api.deps import get_canon

    return get_canon(canon_arg)


def _cmd_gate(
    canon_arg: str,
    paths: Sequence[str],
    *,
    alpha: float = 0.10,
    output_json: bool = False,
) -> int:
    try:
        canon = _resolve_canon_target(canon_arg)
    except Exception as exc:
        msg = f"Failed to load Canon {canon_arg!r}: {exc}"
        if output_json:
            print(json.dumps({"decision": "block", "error": msg}))
        else:
            print(f"[FAIL] {msg}", file=sys.stderr)
        return 1

    resolved_inputs = resolve_reference_inputs(paths=paths)
    file_paths = [
        inp.file_path
        for inp in resolved_inputs
        if inp.file_path is not None and inp.file_path.is_file()
    ]
    if not file_paths:
        msg = f"No valid campaign asset files found for paths: {list(paths)}"
        if output_json:
            print(json.dumps({"decision": "block", "error": msg}))
        else:
            print(f"[FAIL] {msg}", file=sys.stderr)
        return 1

    ast = parse_bundle(*file_paths)
    raw_findings = asyncio.run(run_checks_collect(ast, canon))
    calibrated = default_calibrator.filter_and_calibrate_findings(raw_findings, alpha=alpha)
    blockers = [f for f in calibrated if f.severity >= 50]
    warnings = [f for f in calibrated if f.severity < 50]
    decision = "block" if blockers else ("needs_review" if warnings else "allow")
    lam = round(default_calibrator.threshold(alpha), 4)

    payload = {
        "decision": decision,
        "canon_id": canon.id,
        "canon_version": canon.version,
        "canon_hash": canon.hash,
        "alpha": alpha,
        "conformal_threshold": lam,
        "files_evaluated": [p.name for p in file_paths],
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "total_findings": len(calibrated),
        "findings": [
            {
                "check_id": f.check_id,
                "rule_id": f.rule_ref.rule_id,
                "severity": f.severity,
                "verdict": "BLOCKER" if f.severity >= 50 else "WARNING",
                "message": f.message,
            }
            for f in calibrated
        ],
    }

    if output_json:
        print(json.dumps(payload, indent=2))
    else:
        badge = (
            "PASS (ALLOW)"
            if decision == "allow"
            else ("WARN (NEEDS_REVIEW)" if decision == "needs_review" else "BLOCK")
        )
        print(
            f"[{badge}] CanonGate Pre-Publish Gate — Canon '{canon.id}' v{canon.version} "
            f"(alpha={alpha:.2f}, lambda={lam:.2f})\n"
            f"  • Assets Audited : {', '.join(p.name for p in file_paths)}\n"
            f"  • Findings       : {len(calibrated)} total "
            f"({len(blockers)} Blockers, {len(warnings)} Warnings)"
        )
        for item in payload["findings"][:10]:
            print(
                f"    - [{item['verdict']} · S={item['severity']}] "
                f"{item['check_id']} ({item['rule_id']}): {item['message']}"
            )

    return 1 if decision == "block" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canongate",
        description=(
            "CanonGate offline cryptographic governance verifier, benchmark, CI gate & MCP CLI."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    verify_p = sub.add_parser(
        "verify",
        help="Verify a signed CanonGate governance certificate JSON file offline.",
    )
    verify_p.add_argument(
        "certificate",
        type=Path,
        help="Path to the exported certificate JSON file (e.g. cert.json).",
    )
    verify_p.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON verification output.",
    )

    bench_p = sub.add_parser(
        "benchmark",
        help="Run the 50-case adversarial red-team mutation benchmark suite.",
    )
    bench_p.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON benchmark report.",
    )

    gate_p = sub.add_parser(
        "gate",
        help="Run the pre-publish governance gate on campaign files/globs (exits 1 on Blockers).",
    )
    gate_p.add_argument(
        "--canon",
        required=True,
        help="Canon ID (e.g. indian-digital-lending) or path to a Canon YAML file.",
    )
    gate_p.add_argument(
        "--paths",
        nargs="+",
        required=True,
        help="One or more campaign asset paths, directories, or glob patterns.",
    )
    gate_p.add_argument(
        "--alpha",
        type=float,
        default=0.10,
        help="Split-conformal miscoverage risk level alpha in [0.01, 0.25] (default: 0.10).",
    )
    gate_p.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit machine-readable JSON gate verdict.",
    )

    sub.add_parser(
        "mcp",
        help="Run the CanonGate MCP (2026-07-28) stdio server for Claude Desktop / Cursor.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "verify":
        return _cmd_verify(args.certificate, output_json=args.output_json)
    if args.command == "benchmark":
        return _cmd_benchmark(output_json=args.output_json)
    if args.command == "gate":
        return _cmd_gate(
            args.canon,
            args.paths,
            alpha=args.alpha,
            output_json=args.output_json,
        )
    if args.command == "mcp":
        return run_stdio_server()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
