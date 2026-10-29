"""Tests for strict account and workflow-stage isolation, access control, and PDF safeguards."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from canongate.api.routes.submissions import _can_user_access_submission
from canongate.parsers.pdf import _MAX_PDF_EMBEDDED_IMAGES


class TestIsolationAndAccessControl(unittest.TestCase):
    def test_pdf_embedded_image_safeguard_constants(self) -> None:
        """Verify the PDF safeguard prevents excessive embedded media extraction."""
        self.assertEqual(_MAX_PDF_EMBEDDED_IMAGES, 6)

    def test_creator_strict_account_isolation(self) -> None:
        """Creator accounts should only ever see their own campaigns."""
        creator_1 = SimpleNamespace(id=1, username="alice", role="creator")
        creator_2 = SimpleNamespace(id=2, username="bob", role="creator")

        own_draft = SimpleNamespace(id=10, creator_id=1, status="draft")
        other_draft = SimpleNamespace(id=11, creator_id=2, status="draft")
        other_in_review = SimpleNamespace(id=12, creator_id=2, status="in_review")
        other_approved = SimpleNamespace(id=13, creator_id=2, status="approved")

        self.assertTrue(_can_user_access_submission(creator_1, own_draft))
        self.assertFalse(_can_user_access_submission(creator_1, other_draft))
        self.assertFalse(_can_user_access_submission(creator_1, other_in_review))
        self.assertFalse(_can_user_access_submission(creator_1, other_approved))

        self.assertTrue(_can_user_access_submission(creator_2, other_draft))
        self.assertFalse(_can_user_access_submission(creator_2, own_draft))

    def test_unsubmitted_drafts_private_to_creator(self) -> None:
        """Unsubmitted drafts must never leak to Reviewers or Admins until submitted."""
        creator = SimpleNamespace(id=1, username="alice", role="creator")
        reviewer = SimpleNamespace(id=3, username="carol", role="reviewer")
        admin = SimpleNamespace(id=4, username="dave", role="admin")

        draft = SimpleNamespace(id=20, creator_id=1, status="draft")
        changes_req = SimpleNamespace(id=21, creator_id=1, status="changes_requested")

        # Creator sees own draft
        self.assertTrue(_can_user_access_submission(creator, draft))
        self.assertTrue(_can_user_access_submission(creator, changes_req))

        # Reviewer and Admin cannot see unsubmitted drafts of others
        self.assertFalse(_can_user_access_submission(reviewer, draft))
        self.assertFalse(_can_user_access_submission(reviewer, changes_req))
        self.assertFalse(_can_user_access_submission(admin, draft))
        self.assertFalse(_can_user_access_submission(admin, changes_req))

    def test_submitted_and_published_visible_to_reviewers_and_admins(self) -> None:
        """Once in_review, approved, or published, campaigns appear in Reviewer/Admin queues."""
        reviewer = SimpleNamespace(id=3, username="carol", role="reviewer")
        admin = SimpleNamespace(id=4, username="dave", role="admin")

        in_review = SimpleNamespace(id=30, creator_id=1, status="in_review")
        approved = SimpleNamespace(id=31, creator_id=1, status="approved")
        published = SimpleNamespace(id=32, creator_id=1, status="published")

        for sub in (in_review, approved, published):
            self.assertTrue(_can_user_access_submission(reviewer, sub))
            self.assertTrue(_can_user_access_submission(admin, sub))

    def test_admin_and_reviewer_own_campaigns(self) -> None:
        """Reviewers and Admins can always see campaigns they personally authored."""
        reviewer = SimpleNamespace(id=3, username="carol", role="reviewer")
        admin = SimpleNamespace(id=4, username="dave", role="admin")

        reviewer_draft = SimpleNamespace(id=40, creator_id=3, status="draft")
        admin_draft = SimpleNamespace(id=41, creator_id=4, status="draft")

        self.assertTrue(_can_user_access_submission(reviewer, reviewer_draft))
        self.assertTrue(_can_user_access_submission(admin, admin_draft))
