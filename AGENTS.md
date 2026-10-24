# AGENTS.md — CanonGate AI Agent Guide

## First: Pull Before You Code

```bash
git pull --rebase origin main   # always do this first
```

## Commands

```bash
# Backend
cd backend && uv sync                      # install deps
cd backend && uv run pytest -q             # run tests (must pass)
cd backend && uv run ruff check src/ tests/ # lint
cd backend && uv run ruff format src/ tests/ # format
cd backend && uv run import-linter lint    # import contracts (3 must pass)

# Frontend
cd frontend && npm install && npm run dev  # dev server

# Reset DB (schema change? delete and restart)
rm backend/canongate.db && cd backend && uv run uvicorn canongate.api.app:app
```

## Project Shape

```
backend/src/canongate/
  domain/    # Frozen Pydantic models. NO I/O. No imports from engine/store/api.
  engine/    # Check base + registry + async runner. Imports domain only.
  checks/    # One file per check. Subclass Check. Auto-registered.
  parsers/   # Content → ContentAST. Imports domain only.
  canon/     # YAML → Canon loader.
  store/     # SQLAlchemy tables + async repos. Imports domain + settings.
  ledger/    # Hash-chained audit log, RFC 9162 Merkle tree, friction, C2PA.
  api/       # FastAPI app + routes. The only module that imports everything.
  settings.py
canons/      # YAML brand rule files
frontend/    # Vite + React + TypeScript SPA
```

## Import Boundaries (enforced by import-linter)

domain → nothing internal. engine → domain. checks → domain + engine.
parsers → domain. store → domain + settings. api → everything.

**If `import-linter lint` breaks, your change crosses a boundary. Fix it.**

## Adding a Check

Create `backend/src/canongate/checks/my_check.py`:
```python
from typing import ClassVar
from canongate.domain.ast import Node, NodeKind
from canongate.domain.canon import Canon, Rule
from canongate.domain.finding import Finding, Span, TermMatch
from canongate.engine.check import Check

class MyCheck(Check):
    check_id: ClassVar[str] = "my_domain.my_check"
    check_version: ClassVar[str] = "1.0"
    node_kinds: ClassVar[frozenset[NodeKind]] = frozenset({NodeKind.TEXT})

    def run(self, node: Node, canon: Canon) -> list[Finding]:
        # Use self.finding() helper to avoid boilerplate:
        # return [
        #     self.finding(
        #         node=node,
        #         locator=Span(start=0, end=5),
        #         message="...",
        #         severity=60,
        #         rule_ref=Rule(rule_id="r1", rule_type="term"),
        #         evidence=TermMatch(term="bad", preferred="good"),
        #     )
        # ]
        return []
```
No registration needed — `__init_subclass__` handles it.

## Adding an Evidence Type

1. Add a frozen Pydantic model in `domain/finding.py` with a `kind` literal
2. Add it to the `Evidence` union type
3. Add a React component in `frontend/src/features/findings/evidence/`

## Adding a Workflow State

1. Add the state to `Status` enum in `domain/workflow.py`
2. Add transition rows to `TRANSITIONS` dict — that's it, it's table-driven

## Rules You Must Follow

### Always
- Run `pytest -q` + `ruff check` + `import-linter lint` before committing
- Keep domain models `frozen=True` — never mutate them
- Use `self.finding()` helper in checks (auto-fills IDs)
- Pass `created_at` explicitly to `append_event` (it must match the hash)
- Use deterministic content-hash IDs (SHA-256) for nodes and findings
- Keep checks sync; the runner dispatches them to `asyncio.to_thread`

### Ask First
- Changing the workflow transition table
- Adding new API routes
- Changing the audit ledger hash format
- Modifying the Finding or Canon schema

### Never
- Import store/api/ledger from domain, engine, or checks
- Use mutable Pydantic models
- Skip the hash chain on workflow events
- Bypass `validate_resolution()` when resolving findings
- Commit a failing test or broken import contract

## Architectural & Design References

- **Architecture Diagram (PDF):** [`PulmoTwin_Architecture_Diagram.pdf`](./PulmoTwin_Architecture_Diagram.pdf)
- **Pitch Deck (PDF):** [`PulmoTwin_Pitch_Deck.pdf`](./PulmoTwin_Pitch_Deck.pdf)
- **Architecture Decision Records:** [`docs/adr/`](./docs/adr/)
- **Gap Analysis & Complete Feature Scorecard:** [`gap_analysis.md`](./gap_analysis.md)
