"""Hash-chained audit ledger.

Each workflow event is chained to the previous via SHA-256:
  event_hash = SHA256(prev_hash + submission_id + action + actor_id + timestamp)

This creates a tamper-evident log — if any row is modified or deleted,
the chain breaks and verification fails.
"""

from __future__ import annotations

import hashlib

GENESIS_HASH = "0" * 64  # the prev_hash of the very first event


def compute_event_hash(
    *,
    prev_hash: str,
    submission_id: int,
    action: str,
    actor_id: int,
    timestamp: str,
) -> str:
    """Compute the hash for a workflow event, chained to the previous event."""
    payload = f"{prev_hash}:{submission_id}:{action}:{actor_id}:{timestamp}"
    return hashlib.sha256(payload.encode()).hexdigest()


def verify_chain(events: list[dict]) -> tuple[bool, int | None]:
    """Verify the integrity of a chain of events.

    Args:
        events: List of event dicts with keys: prev_hash, event_hash,
                submission_id, action, actor_id, created_at

    Returns:
        (is_valid, broken_at_index): True if the chain is intact.
        If broken, broken_at_index is the first invalid event index.
    """
    expected_prev = GENESIS_HASH

    for i, evt in enumerate(events):
        if evt["prev_hash"] != expected_prev:
            return False, i

        computed = compute_event_hash(
            prev_hash=evt["prev_hash"],
            submission_id=evt["submission_id"],
            action=evt["action"],
            actor_id=evt["actor_id"],
            timestamp=evt["created_at"],
        )
        if computed != evt["event_hash"]:
            return False, i

        expected_prev = evt["event_hash"]

    return True, None
