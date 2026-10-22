"""RFC 9162 Binary Merkle Transparency Tree and Ed25519 Signed Tree Heads.

Licensing note:
Upstream `fmerg/pymerkle` is licensed under GPL-3.0, which conflicts with
CanonGate's permissive MIT/Apache-2.0/BSD-3 policy. This module implements
RFC 9162 Section 2.1 (Certificate Transparency v2.0 Binary Merkle Hash Trees)
natively using Python's standard library `hashlib` and `pyca/cryptography`
(Apache-2.0/BSD-3).

Security properties:
- Second-preimage resistance via domain-separation prefixes: `0x00` for leaves,
  `0x01` for interior nodes (RFC 9162 §2.1.1).
- Immunity to CVE-2012-2459 lonely-leaf duplication attacks by splitting at the
  largest power of two strictly less than `n` (binary Sakura tree topology).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def hash_leaf(entry: bytes) -> bytes:
    """RFC 9162 §2.1.1: MTH({d(0)}) = SHA-256(0x00 || d(0))."""
    return _sha256(LEAF_PREFIX + entry)


def hash_children(left: bytes, right: bytes) -> bytes:
    """RFC 9162 §2.1.1: MTH(D[n]) = SHA-256(0x01 || MTH(D[0:k]) || MTH(D[k:n]))."""
    return _sha256(NODE_PREFIX + left + right)


def _largest_power_of_two_less_than(n: int) -> int:
    """Return the largest power of 2 strictly less than n (for n >= 2)."""
    k = 1
    while (k << 1) < n:
        k <<= 1
    return k


def compute_merkle_root(leaves: list[bytes]) -> bytes:
    """Compute the RFC 9162 Merkle Tree Hash (MTH) for `leaves`."""
    n = len(leaves)
    if n == 0:
        return _sha256(b"")
    if n == 1:
        return hash_leaf(leaves[0])
    k = _largest_power_of_two_less_than(n)
    return hash_children(
        compute_merkle_root(leaves[:k]),
        compute_merkle_root(leaves[k:]),
    )


def prove_inclusion(m: int, leaves: list[bytes]) -> list[str]:
    """RFC 9162 §2.1.3: Generate O(log n) hex audit path for leaf index `m`."""
    n = len(leaves)
    if not (0 <= m < n):
        raise IndexError(f"Leaf index {m} out of range for tree of size {n}")
    if n == 1:
        return []
    k = _largest_power_of_two_less_than(n)
    if m < k:
        path = prove_inclusion(m, leaves[:k])
        path.append(compute_merkle_root(leaves[k:]).hex())
        return path
    path = prove_inclusion(m - k, leaves[k:])
    path.append(compute_merkle_root(leaves[:k]).hex())
    return path


def verify_inclusion(
    leaf_entry: bytes,
    leaf_index: int,
    tree_size: int,
    root_hash_hex: str,
    audit_path_hex: list[str],
) -> bool:
    """RFC 9162 §2.1.3.2: Verify a Merkle inclusion proof in O(log n) time."""
    if not (0 <= leaf_index < tree_size):
        return False
    fn = leaf_index
    sn = tree_size - 1
    r = hash_leaf(leaf_entry)
    for sibling_hex in audit_path_hex:
        try:
            sibling = bytes.fromhex(sibling_hex)
        except ValueError:
            return False
        if sn == 0:
            return False
        if (fn & 1) == 1 or fn == sn:
            r = hash_children(sibling, r)
            while (fn & 1) == 0 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            r = hash_children(r, sibling)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r.hex() == root_hash_hex


def _subproof(m: int, leaves: list[bytes], complete: bool) -> list[bytes]:
    n = len(leaves)
    if m == n:
        return [] if complete else [compute_merkle_root(leaves)]
    k = _largest_power_of_two_less_than(n)
    if m <= k:
        path = _subproof(m, leaves[:k], complete)
        path.append(compute_merkle_root(leaves[k:]))
        return path
    path = _subproof(m - k, leaves[k:], False)
    path.append(compute_merkle_root(leaves[:k]))
    return path


def prove_consistency(first_size: int, leaves: list[bytes]) -> list[str]:
    """RFC 9162 §2.1.4: Prove that tree state `first_size` is a prefix of `leaves`."""
    n = len(leaves)
    if not (0 <= first_size <= n):
        raise ValueError(f"Invalid first_size {first_size} for tree size {n}")
    if first_size == 0 or first_size == n:
        return []
    return [h.hex() for h in _subproof(first_size, leaves, True)]


@dataclass(frozen=True)
class SignedTreeHead:
    tree_size: int
    timestamp: str
    root_hash: str
    signature_hex: str
    public_key_hex: str

    def canonical_bytes(self) -> bytes:
        payload = {
            "root_hash": self.root_hash,
            "timestamp": self.timestamp,
            "tree_size": self.tree_size,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_tree_head(
    leaves: list[bytes],
    timestamp: str,
    private_key: Ed25519PrivateKey,
) -> SignedTreeHead:
    """Compute Merkle root and sign the Tree Head using Ed25519."""
    root_hex = compute_merkle_root(leaves).hex()
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pub_hex = pub_bytes.hex()
    unsigned = SignedTreeHead(
        tree_size=len(leaves),
        timestamp=timestamp,
        root_hash=root_hex,
        signature_hex="",
        public_key_hex=pub_hex,
    )
    sig_hex = private_key.sign(unsigned.canonical_bytes()).hex()
    return SignedTreeHead(
        tree_size=len(leaves),
        timestamp=timestamp,
        root_hash=root_hex,
        signature_hex=sig_hex,
        public_key_hex=pub_hex,
    )


def verify_tree_head(sth: SignedTreeHead) -> bool:
    """Verify the Ed25519 signature on a SignedTreeHead."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(sth.public_key_hex))
        pub.verify(bytes.fromhex(sth.signature_hex), sth.canonical_bytes())
        return True
    except (ValueError, InvalidSignature):
        return False
