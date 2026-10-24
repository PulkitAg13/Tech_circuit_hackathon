# ADR 0002: Layered Import Boundaries Enforced by Import-Linter

## Status
Accepted

## Context
In Python governance engines, domain logic easily becomes coupled to storage mechanisms, API frameworks, or concrete check execution details. Unchecked dependencies lead to circular imports, fragile tests requiring deep mock hierarchies, and untestable business logic. To maintain long-term architectural integrity as teams scale, architectural boundaries must be enforced mechanically rather than rely on documentation or code reviews alone.

## Decision
We enforce strict unidirectional layered import boundaries using `import-linter` contracts configured directly in `pyproject.toml`:

```
domain → (nothing internal)
parsers → domain
engine → domain
checks → domain + engine
store → domain + settings
ledger → domain
api → everything
```

### Module Responsibilities & Constraints
1. **`canongate.domain`**:
   - Contains pure data models (`ContentAST`, `Canon`, `Finding`, `Workflow`).
   - All models use `frozen=True` Pydantic models.
   - **Contract**: Zero imports from internal modules (`engine`, `checks`, `parsers`, `store`, `api`, `ledger`). Absolutely NO I/O or network calls.
2. **`canongate.engine`**:
   - Contains `Check` base class, registry, conformal risk controller, and async runner.
   - **Contract**: Imports `domain` only. Forbidden from importing `store`, `api`, or `ledger`.
3. **`canongate.checks`**:
   - Concrete check implementations (regex, CIEDE2000, WCAG contrast, Z3 SMT arithmetic, NLI slot alignment).
   - Auto-registers via `Check.__init_subclass__`.
   - **Contract**: Imports `domain` and `engine` only. Forbidden from importing `store`, `api`, or `ledger`.
4. **`canongate.parsers`**:
   - Converts raw multimodal files (`.docx`, `.pdf`, `.html`, `.png`) into `ContentAST`.
   - **Contract**: Imports `domain` only.
5. **`canongate.store`**:
   - SQLAlchemy tables and async repositories for SQLite/PostgreSQL persistence.
   - **Contract**: Imports `domain` and `settings`. Forbidden from importing `api`.
6. **`canongate.api`**:
   - FastAPI application, route handlers, dependency injection, and SSE streaming.
   - The composition root: the only module authorized to import across all layers.

### CI Enforcement
The build pipeline and pre-commit checks run:
```bash
uv run import-linter lint
```
A pull request cannot merge if an unauthorized dependency is introduced.

## Consequences
- **Positive**: Core checks and domain logic remain pure and can be tested instantaneously without spinning up databases, mocking ORM sessions, or initializing FastAPI test clients.
- **Positive**: Eliminates circular dependency deadlocks completely.
- **Negative**: Developers must carefully place shared types in `domain` rather than co-locating them in feature folders.

## Alternatives Considered
- *Convention and PR Reviews*: Rejected because architectural leakage silently accumulates over time under delivery pressure.
- *Separate Multi-Repo Packages*: Rejected due to monorepo maintenance simplicity and fast local iteration speed.
