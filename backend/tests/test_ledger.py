"""Tests for the hash-chained audit ledger."""

import unittest

from canongate.ledger.chain import GENESIS_HASH, compute_event_hash, verify_chain


class TestLedger(unittest.TestCase):
    def test_genesis_hash(self):
        assert len(GENESIS_HASH) == 64
        assert GENESIS_HASH == "0" * 64

    def test_event_hash_deterministic(self):
        h1 = compute_event_hash(
            prev_hash=GENESIS_HASH,
            submission_id=1,
            action="submit",
            actor_id=1,
            timestamp="2025-01-01T00:00:00",
        )
        h2 = compute_event_hash(
            prev_hash=GENESIS_HASH,
            submission_id=1,
            action="submit",
            actor_id=1,
            timestamp="2025-01-01T00:00:00",
        )
        assert h1 == h2

    def test_chain_verification_valid(self):
        e1_hash = compute_event_hash(
            prev_hash=GENESIS_HASH,
            submission_id=1,
            action="submit",
            actor_id=1,
            timestamp="2025-01-01T00:00:00",
        )
        e2_hash = compute_event_hash(
            prev_hash=e1_hash,
            submission_id=1,
            action="approve",
            actor_id=2,
            timestamp="2025-01-01T01:00:00",
        )

        events = [
            {
                "prev_hash": GENESIS_HASH,
                "event_hash": e1_hash,
                "submission_id": 1,
                "action": "submit",
                "actor_id": 1,
                "created_at": "2025-01-01T00:00:00",
            },
            {
                "prev_hash": e1_hash,
                "event_hash": e2_hash,
                "submission_id": 1,
                "action": "approve",
                "actor_id": 2,
                "created_at": "2025-01-01T01:00:00",
            },
        ]

        valid, broken_at = verify_chain(events)
        assert valid is True
        assert broken_at is None

    def test_chain_verification_tampered(self):
        compute_event_hash(
            prev_hash=GENESIS_HASH,
            submission_id=1,
            action="submit",
            actor_id=1,
            timestamp="2025-01-01T00:00:00",
        )

        events = [
            {
                "prev_hash": GENESIS_HASH,
                "event_hash": "tampered_hash",  # intentionally wrong
                "submission_id": 1,
                "action": "submit",
                "actor_id": 1,
                "created_at": "2025-01-01T00:00:00",
            },
        ]

        valid, broken_at = verify_chain(events)
        assert valid is False
        assert broken_at == 0
