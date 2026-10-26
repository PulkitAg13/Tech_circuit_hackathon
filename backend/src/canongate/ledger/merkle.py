"""RFC 9162 (Certificate Transparency v2.0) Binary Merkle Tree & Ed25519 Signed Tree Heads.

Implements the exact cryptographic specification from RFC 9162 §2.1:
- Leaf hash:     MTH({d(0)}) = SHA-256(0x00 || d(0))
- Interior node: MTH(D_n)    = SHA-256(0x01 || MTH(D[0:k]) || MTH(D[k:n]))
  where k is the largest power of 2 strictly less than n.
- Inclusion proof generation (PATH(m, D_n)) and verification (§2.1.3.2).
- Consistency proof generation (SUBPROOF(m, D_n, true)) and verification (§2.1.4.2).
- Ed25519 Signed Tree Head (STH) generation and verification.

Security properties:
1. Domain separation prefixes (0x00 leaf vs 0x01 interior) prevent second-preimage
   tree-height confusion attacks.
2. Unbalanced largest-power-of-two split (k < n) eliminates the Bitcoin CVE-2012-2459
   odd-leaf duplication vulnerability.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
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


def hash_leaf(leaf_bytes: bytes) -> bytes:
    """RFC 9162 §2.1.1: SHA-256(0x00 || leaf_bytes)."""
    return _sha256(LEAF_PREFIX + leaf_bytes)


def hash_children(left: bytes, right: bytes) -> bytes:
    """RFC 9162 §2.1.1: SHA-256(0x01 || left || right)."""
    return _sha256(NODE_PREFIX + left + right)


def _largest_power_of_two_less_than(n: int) -> int:
    """Return the largest power of 2 strictly less than n (for n >= 2) in O(1) time."""
    return 1 << ((n - 1).bit_length() - 1)


def _is_exact_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _mth_range(
    leaves: Sequence[bytes],
    lo: int,
    hi: int,
    memo: dict[tuple[int, int], bytes] | None = None,
) -> bytes:
    """Compute RFC 9162 MTH over `leaves[lo:hi]` without list-slice allocations."""
    if memo is not None and (lo, hi) in memo:
        return memo[(lo, hi)]
    n = hi - lo
    if n == 0:
        res = _sha256(b"")
    elif n == 1:
        res = hash_leaf(leaves[lo])
    else:
        k = _largest_power_of_two_less_than(n)
        left = _mth_range(leaves, lo, lo + k, memo)
        right = _mth_range(leaves, lo + k, hi, memo)
        res = hash_children(left, right)
    if memo is not None:
        memo[(lo, hi)] = res
    return res


def compute_merkle_root(leaves: Sequence[bytes]) -> bytes:
    """Compute the RFC 9162 Merkle Tree Hash (MTH) for `leaves`."""
    return _mth_range(leaves, 0, len(leaves))


def _prove_inclusion_range(
    m: int,
    leaves: Sequence[bytes],
    lo: int,
    hi: int,
    memo: dict[tuple[int, int], bytes],
) -> list[str]:
    n = hi - lo
    if n == 1:
        return []
    k = _largest_power_of_two_less_than(n)
    if m < k:
        path = _prove_inclusion_range(m, leaves, lo, lo + k, memo)
        path.append(_mth_range(leaves, lo + k, hi, memo).hex())
        return path
    path = _prove_inclusion_range(m - k, leaves, lo + k, hi, memo)
    path.append(_mth_range(leaves, lo, lo + k, memo).hex())
    return path


def prove_inclusion(m: int, leaves: Sequence[bytes]) -> list[str]:
    """RFC 9162 §2.1.3.1: Generate O(log n) hex audit path for leaf index `m`."""
    n = len(leaves)
    if not (0 <= m < n):
        raise IndexError(f"Leaf index {m} out of range for tree of size {n}")
    memo: dict[tuple[int, int], bytes] = {}
    return _prove_inclusion_range(m, leaves, 0, n, memo)


def verify_inclusion(
    leaf_entry: bytes,
    leaf_index: int,
    tree_size: int,
    root_hash_hex: str,
    audit_path_hex: Sequence[str],
) -> bool:
    """RFC 9162 §2.1.3.2: Verify a Merkle inclusion proof in O(log n) time."""
    if not (0 <= leaf_index < tree_size):
        return False
    try:
        audit_path = [bytes.fromhex(h) for h in audit_path_hex]
    except ValueError:
        return False

    fn = leaf_index
    sn = tree_size - 1
    r = hash_leaf(leaf_entry)

    for p in audit_path:
        if sn == 0:
            return False
        if (fn & 1) == 1 or fn == sn:
            r = hash_children(p, r)
            while (fn & 1) == 0 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            r = hash_children(r, p)
        fn >>= 1
        sn >>= 1

    return sn == 0 and r.hex() == root_hash_hex


def _subproof_range(
    m: int,
    leaves: Sequence[bytes],
    lo: int,
    hi: int,
    complete: bool,
    memo: dict[tuple[int, int], bytes],
) -> list[bytes]:
    n = hi - lo
    if m == n:
        return [] if complete else [_mth_range(leaves, lo, hi, memo)]
    k = _largest_power_of_two_less_than(n)
    if m <= k:
        path = _subproof_range(m, leaves, lo, lo + k, complete, memo)
        path.append(_mth_range(leaves, lo + k, hi, memo))
        return path
    path = _subproof_range(m - k, leaves, lo + k, hi, False, memo)
    path.append(_mth_range(leaves, lo, lo + k, memo))
    return path


def prove_consistency(first_size: int, leaves: Sequence[bytes]) -> list[str]:
    """RFC 9162 §2.1.4.1: Prove that tree state `first_size` is a prefix of `leaves`."""
    n = len(leaves)
    if not (0 <= first_size <= n):
        raise ValueError(f"Invalid first_size {first_size} for tree size {n}")
    if first_size == 0 or first_size == n:
        return []
    memo: dict[tuple[int, int], bytes] = {}
    return [h.hex() for h in _subproof_range(first_size, leaves, 0, n, True, memo)]


def verify_consistency(
    first_size: int,
    second_size: int,
    first_hash_hex: str,
    second_hash_hex: str,
    consistency_path_hex: Sequence[str],
) -> bool:
    """RFC 9162 §2.1.4.2: Verify consistency between two Merkle Tree Heads.

    Returns True iff the tree of `first_size` with root `first_hash_hex` is an
    exact append-only prefix of the tree of `second_size` with root `second_hash_hex`.
    """
    if not (0 <= first_size <= second_size):
        return False
    if first_size == 0:
        return len(consistency_path_hex) == 0
    if first_size == second_size:
        return first_hash_hex == second_hash_hex and len(consistency_path_hex) == 0
    if not consistency_path_hex:
        return False

    try:
        first_hash = bytes.fromhex(first_hash_hex)
        second_hash = bytes.fromhex(second_hash_hex)
        raw_path = [bytes.fromhex(h) for h in consistency_path_hex]
    except ValueError:
        return False

    path = [first_hash, *raw_path] if _is_exact_power_of_two(first_size) else list(raw_path)

    fn = first_size - 1
    sn = second_size - 1
    while (fn & 1) == 1:
        fn >>= 1
        sn >>= 1

    fr = path[0]
    sr = path[0]

    for c in path[1:]:
        if sn == 0:
            return False
        if (fn & 1) == 1 or fn == sn:
            fr = hash_children(c, fr)
            sr = hash_children(c, sr)
            while (fn & 1) == 0 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            sr = hash_children(sr, c)
        fn >>= 1
        sn >>= 1

    return sn == 0 and fr == first_hash and sr == second_hash


@dataclass(frozen=True, slots=True)
class SignedTreeHead:
    tree_size: int
    timestamp: str
    root_hash: str
    signature_hex: str
    public_key_hex: str

    @property
    def signature(self) -> str:
        return self.signature_hex

    @property
    def public_key(self) -> str:
        return self.public_key_hex

    @property
    def root_hash_hex(self) -> str:
        return self.root_hash

    def canonical_bytes(self) -> bytes:
        payload = {
            "root_hash": self.root_hash,
            "timestamp": self.timestamp,
            "tree_size": self.tree_size,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def to_dict(self) -> dict[str, int | str]:
        return {
            "tree_size": self.tree_size,
            "timestamp": self.timestamp,
            "root_hash": self.root_hash,
            "root_hash_hex": self.root_hash,
            "signature": self.signature_hex,
            "signature_hex": self.signature_hex,
            "public_key": self.public_key_hex,
            "public_key_hex": self.public_key_hex,
        }

    def verify(self) -> bool:
        return verify_tree_head(self)


def sign_tree_head(
    leaves: Sequence[bytes],
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


class MerkleTree:
    """Immutable RFC 9162 Merkle Tree with memoized subtree hashes and Pythonic dunders."""

    __slots__ = ("_leaves", "_memo")

    def __init__(self, leaves: Sequence[bytes] = ()) -> None:
        self._leaves: tuple[bytes, ...] = tuple(leaves)
        self._memo: dict[tuple[int, int], bytes] = {}

    @property
    def root(self) -> bytes:
        return _mth_range(self._leaves, 0, len(self._leaves), self._memo)

    @property
    def root_hex(self) -> str:
        return self.root.hex()

    def __len__(self) -> int:
        return len(self._leaves)

    def __bool__(self) -> bool:
        return len(self._leaves) > 0

    def __iter__(self) -> Iterator[bytes]:
        return iter(self._leaves)

    def __getitem__(self, idx: int) -> bytes:
        return self._leaves[idx]

    def __contains__(self, leaf: object) -> bool:
        return leaf in self._leaves

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MerkleTree):
            return NotImplemented
        return len(self) == len(other) and self.root == other.root

    def __repr__(self) -> str:
        return f"MerkleTree(size={len(self)}, root={self.root_hex[:12]}...)"

    def prove_inclusion(self, index: int) -> list[str]:
        n = len(self._leaves)
        if not (0 <= index < n):
            raise IndexError(f"Leaf index {index} out of range for tree of size {n}")
        return _prove_inclusion_range(index, self._leaves, 0, n, self._memo)

    def prove_consistency(self, first_size: int) -> list[str]:
        n = len(self._leaves)
        if not (0 <= first_size <= n):
            raise ValueError(f"Invalid first_size {first_size} for tree size {n}")
        if first_size == 0 or first_size == n:
            return []
        return [h.hex() for h in _subproof_range(first_size, self._leaves, 0, n, True, self._memo)]

    def sign_head(self, timestamp: str, private_key: Ed25519PrivateKey) -> SignedTreeHead:
        return sign_tree_head(self._leaves, timestamp, private_key)
