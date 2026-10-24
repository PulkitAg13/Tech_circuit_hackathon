"""Standalone CanonGate Command-Line Interface (`canongate verify <cert.json>`).

Registered under `[project.scripts]` in `backend/pyproject.toml`:
  `uv run canongate verify cert.json`

Performs zero-database, completely offline cryptographic verification of an
exported CanonGate governance certificate:
1. Sequential SHA-256 hash chain integrity (`GENESIS_HASH` -> final event).
2. RFC 9162 Binary Merkle Tree root and per-event $O(\\log_2 n)$ inclusion proofs.
3. Ed25519 Signed Tree Head (STH) signature verification.
4. Content & Canon SHA-256 digest binding.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from canongate.ledger.certificate import GovernanceCertificate


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canongate",
        description="CanonGate offline cryptographic governance verifier & CLI.",
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "verify":
        return _cmd_verify(args.certificate, output_json=args.output_json)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
