"""Pure, table-driven state machine for the review workflow.

No I/O. No side effects. Just computes the next state.

States: DRAFT → IN_REVIEW → CHANGES_REQUESTED → APPROVED → PUBLISHED
Actions: SUBMIT, APPROVE, REQUEST_CHANGES, PUBLISH, RECALL

The transitions table is the single source of truth. Adding a new role or
state is just one row in the dict.
"""

from __future__ import annotations

from enum import StrEnum


class Status(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    PUBLISHED = "published"


class Action(StrEnum):
    SUBMIT = "submit"
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    PUBLISH = "publish"
    RECALL = "recall"


class Role(StrEnum):
    CREATOR = "creator"
    REVIEWER = "reviewer"
    ADMIN = "admin"


# ── Transition Table ─────────────────────────────────────────────────

# (current_status, action) → {allowed_roles, next_status}

_Entry = tuple[frozenset[Role], Status]

TRANSITIONS: dict[tuple[Status, Action], _Entry] = {
    (Status.DRAFT, Action.SUBMIT): (
        frozenset({Role.CREATOR, Role.ADMIN}),
        Status.IN_REVIEW,
    ),
    (Status.IN_REVIEW, Action.APPROVE): (
        frozenset({Role.REVIEWER, Role.ADMIN}),
        Status.APPROVED,
    ),
    (Status.IN_REVIEW, Action.REQUEST_CHANGES): (
        frozenset({Role.REVIEWER, Role.ADMIN}),
        Status.CHANGES_REQUESTED,
    ),
    (Status.IN_REVIEW, Action.RECALL): (
        frozenset({Role.CREATOR, Role.ADMIN}),
        Status.DRAFT,
    ),
    (Status.CHANGES_REQUESTED, Action.SUBMIT): (
        frozenset({Role.CREATOR, Role.ADMIN}),
        Status.IN_REVIEW,
    ),
    (Status.APPROVED, Action.PUBLISH): (
        frozenset({Role.ADMIN}),
        Status.PUBLISHED,
    ),
    (Status.APPROVED, Action.RECALL): (
        frozenset({Role.ADMIN}),
        Status.IN_REVIEW,
    ),
}


class TransitionError(Exception):
    """Raised when a workflow transition is not allowed."""

    def __init__(self, status: Status, action: Action, role: Role) -> None:
        self.status = status
        self.action = action
        self.role = role
        super().__init__(f"Transition ({status}, {action}) not allowed for role {role}")


def next_status(current: Status, action: Action, role: Role) -> Status:
    """Compute the next status or raise TransitionError.

    This is a pure function. All side effects (persistence, events)
    live in the API layer.
    """
    key = (current, action)
    entry = TRANSITIONS.get(key)
    if entry is None:
        raise TransitionError(current, action, role)

    allowed_roles, target = entry
    if role not in allowed_roles:
        raise TransitionError(current, action, role)

    return target


def allowed_actions(status: Status, role: Role) -> list[Action]:
    """Return the actions available to `role` in the given `status`."""
    actions: list[Action] = []
    for (s, a), (roles, _) in TRANSITIONS.items():
        if s == status and role in roles:
            actions.append(a)
    return actions


# ── Finding Resolution Rules ─────────────────────────────────────────


class ResolutionError(Exception):
    """Raised when a finding resolution is not allowed."""


def validate_resolution(
    resolution: str,
    *,
    severity: int,
    role: Role,
) -> None:
    """Check whether `role` may apply `resolution` to a finding of `severity`.

    Rules:
    - "accepted": any role (creator accepts the suggestion).
    - "dismissed": reviewer/admin only, warnings only (severity < 50).
    - "overridden": reviewer/admin only, warnings only.
    - Blockers (severity >= 50) can only be "accepted".

    Raises ResolutionError if the combination is disallowed.
    """
    if resolution not in ("accepted", "dismissed", "overridden"):
        raise ResolutionError(f"Invalid resolution: {resolution!r}")

    if resolution == "accepted":
        return  # anyone can accept a suggestion

    # dismissed / overridden require reviewer or admin
    if role not in (Role.REVIEWER, Role.ADMIN):
        raise ResolutionError(
            f"Role {role} cannot {resolution} a finding — only reviewers and admins can"
        )

    if severity >= 50:
        raise ResolutionError(
            f"Cannot {resolution} a blocker (severity={severity}). "
            "Blockers must be accepted (fix applied) or the content must be changed."
        )
