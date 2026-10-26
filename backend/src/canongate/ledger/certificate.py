"""Self-Contained Cryptographic Governance Certificate (`ledger/certificate.py`).

Bundles a submission's content hash, Canon rulebook hash, sequential SHA-256
hash-chained workflow events, RFC 9162 Merkle inclusion proofs, and Ed25519
Signed Tree Head into a portable JSON artifact that can be verified completely
offline via `canongate verify <cert.json>`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from canongate.ledger.chain import verify_chain
from canongate.ledger.merkle import (
    MerkleTree,
    SignedTreeHead,
    verify_inclusion,
    verify_tree_head,
)

_SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def derive_audit_signing_key(
    submission_id: int,
    *,
    secret: str | None = None,
) -> Ed25519PrivateKey:
    """Derive a deterministic Ed25519 signing key using HMAC-SHA256 with the server secret.

    Prevents external forgery of `GovernanceCertificate` or `SignedTreeHead` from a
    public integer `submission_id` while keeping offline verification stateless via the
    embedded `public_key_hex`.
    """
    server_secret = (
        secret
        or os.environ.get("CANONGATE_JWT_SECRET")
        or os.environ.get("JWT_SECRET")
        or "dev-secret-change-me"
    )
    seed = hmac.new(
        server_secret.encode("utf-8"),
        f"canongate-audit-v2:{submission_id}".encode(),
        hashlib.sha256,
    ).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


@dataclass(frozen=True, slots=True)
class CertificateVerificationResult:
    """Detailed offline verification report for a `GovernanceCertificate`."""

    valid: bool
    chain_valid: bool
    merkle_root_valid: bool
    inclusion_proofs_valid: bool
    signature_valid: bool
    hashes_valid: bool
    errors: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.valid

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "chain_valid": self.chain_valid,
            "merkle_root_valid": self.merkle_root_valid,
            "inclusion_proofs_valid": self.inclusion_proofs_valid,
            "signature_valid": self.signature_valid,
            "hashes_valid": self.hashes_valid,
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class GovernanceCertificate:
    """Portable, offline-verifiable governance certificate for a submission."""

    certificate_version: str
    submission_id: int
    title: str
    status: str
    content_hash: str
    canon_id: str
    canon_hash: str
    issued_at: str
    events: tuple[dict[str, Any], ...]
    signed_tree_head: SignedTreeHead

    @classmethod
    def build(
        cls,
        *,
        submission_id: int,
        title: str,
        status: str,
        content_hash: str,
        canon_id: str,
        canon_hash: str,
        event_rows: Sequence[Any],
        issued_at: str | None = None,
        private_key: Ed25519PrivateKey | None = None,
    ) -> GovernanceCertificate:
        """Construct and sign a `GovernanceCertificate` from persisted workflow event rows."""
        now_iso = issued_at or dt.datetime.now(dt.UTC).isoformat()
        if private_key is None:
            private_key = derive_audit_signing_key(submission_id)

        leaves = [str(e.event_hash).encode("utf-8") for e in event_rows]
        tree = MerkleTree(leaves)
        sth = tree.sign_head(now_iso, private_key)

        event_dicts: list[dict[str, Any]] = []
        for idx, e in enumerate(event_rows):
            event_dicts.append(
                {
                    "id": getattr(e, "id", idx + 1),
                    "submission_id": e.submission_id,
                    "action": e.action,
                    "from_status": e.from_status,
                    "to_status": e.to_status,
                    "actor_id": e.actor_id,
                    "comment": getattr(e, "comment", ""),
                    "prev_hash": e.prev_hash,
                    "event_hash": e.event_hash,
                    "created_at": str(e.created_at),
                    "leaf_index": idx,
                    "audit_path": tree.prove_inclusion(idx),
                }
            )

        return cls(
            certificate_version="1.0",
            submission_id=submission_id,
            title=title,
            status=status,
            content_hash=content_hash,
            canon_id=canon_id,
            canon_hash=canon_hash,
            issued_at=now_iso,
            events=tuple(event_dicts),
            signed_tree_head=sth,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "certificate_version": self.certificate_version,
            "submission_id": self.submission_id,
            "title": self.title,
            "status": self.status,
            "content_hash": self.content_hash,
            "canon_id": self.canon_id,
            "canon_hash": self.canon_hash,
            "issued_at": self.issued_at,
            "events": list(self.events),
            "signed_tree_head": self.signed_tree_head.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GovernanceCertificate:
        sth_raw = data.get("signed_tree_head") or {}
        sth = SignedTreeHead(
            tree_size=int(sth_raw.get("tree_size", 0)),
            timestamp=str(sth_raw.get("timestamp", "")),
            root_hash=str(sth_raw.get("root_hash", "")),
            signature_hex=str(sth_raw.get("signature_hex") or sth_raw.get("signature") or ""),
            public_key_hex=str(sth_raw.get("public_key_hex") or sth_raw.get("public_key") or ""),
        )
        raw_events = data.get("events") or []
        return cls(
            certificate_version=str(data.get("certificate_version", "1.0")),
            submission_id=int(data.get("submission_id", 0)),
            title=str(data.get("title", "")),
            status=str(data.get("status", "")),
            content_hash=str(data.get("content_hash", "")),
            canon_id=str(data.get("canon_id", "")),
            canon_hash=str(data.get("canon_hash", "")),
            issued_at=str(data.get("issued_at", "")),
            events=tuple(raw_events),
            signed_tree_head=sth,
        )

    def verify(self) -> CertificateVerificationResult:
        """Perform complete offline cryptographic verification of this certificate."""
        errors: list[str] = []

        # 1. Verify content_hash and canon_hash digests
        hashes_valid = bool(
            _SHA256_HEX_RE.match(self.content_hash) and _SHA256_HEX_RE.match(self.canon_hash)
        )
        if not hashes_valid:
            errors.append("Invalid SHA-256 digest format for content_hash or canon_hash.")

        # 2. Verify sequential SHA-256 hash chain across workflow events
        chain_ok, broken_idx = verify_chain(list(self.events))
        if not chain_ok:
            errors.append(f"Sequential SHA-256 hash chain broken at event index {broken_idx}.")

        # 3. Verify RFC 9162 Merkle root & per-leaf inclusion proofs
        leaves = [str(ev.get("event_hash", "")).encode("utf-8") for ev in self.events]
        computed_tree = MerkleTree(leaves)
        merkle_root_valid = (
            len(self.events) == self.signed_tree_head.tree_size
            and computed_tree.root_hex == self.signed_tree_head.root_hash
        )
        if not merkle_root_valid:
            errors.append(
                f"Merkle root mismatch: computed {computed_tree.root_hex} "
                f"(size {len(self.events)}) vs STH {self.signed_tree_head.root_hash} "
                f"(size {self.signed_tree_head.tree_size})."
            )

        inclusion_ok = True
        for idx, ev in enumerate(self.events):
            leaf_bytes = str(ev.get("event_hash", "")).encode("utf-8")
            leaf_index = int(ev.get("leaf_index", idx))
            audit_path = ev.get("audit_path")
            if not isinstance(audit_path, list) or leaf_index != idx:
                inclusion_ok = False
                errors.append(f"Malformed audit_path or leaf_index on event {idx}.")
                break
            if not verify_inclusion(
                leaf_entry=leaf_bytes,
                leaf_index=leaf_index,
                tree_size=self.signed_tree_head.tree_size,
                root_hash_hex=self.signed_tree_head.root_hash,
                audit_path_hex=audit_path,
            ):
                inclusion_ok = False
                errors.append(f"RFC 9162 Merkle inclusion proof failed for leaf {idx}.")
                break

        # 4. Verify Ed25519 signature on Signed Tree Head
        sig_ok = verify_tree_head(self.signed_tree_head)
        if not sig_ok:
            errors.append("Ed25519 signature verification failed on SignedTreeHead.")

        all_valid = hashes_valid and chain_ok and merkle_root_valid and inclusion_ok and sig_ok
        return CertificateVerificationResult(
            valid=all_valid,
            chain_valid=chain_ok,
            merkle_root_valid=merkle_root_valid,
            inclusion_proofs_valid=inclusion_ok,
            signature_valid=sig_ok,
            hashes_valid=hashes_valid,
            errors=tuple(errors),
        )
