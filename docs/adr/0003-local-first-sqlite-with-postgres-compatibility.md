# ADR 0003: Local-First SQLite Deployment with PostgreSQL-Compatible Architecture

## Status
Accepted

## Context
CanonGate is designed for brand compliance workflows that span both local developer machines, offline cryptographic CLI verifiers (`canongate verify cert.json`), and multi-tenant enterprise review servers. Requiring an external database daemon (such as PostgreSQL) for local development, pre-commit validation, and automated CI tests increases setup friction, slows test cycles, and breaks standalone offline verification tools. Conversely, relying strictly on SQLite-specific idioms or raw embedded SQLite calls limits scale in concurrent multi-user production environments.

## Decision
We adopted a **Local-First SQLite architecture with seamless PostgreSQL compatibility** powered by SQLAlchemy 2.0 async ORM:

1. **Driver Abstraction**:
   - Local development and test suites use `aiosqlite` with `sqlite+aiosqlite:///canongate.db`.
   - Production deployments configure `postgresql+asyncpg://...` via the `DATABASE_URL` setting.
2. **Standard ANSI SQL Types & Dialect Discipline**:
   - Table schemas use standard SQLAlchemy column definitions (`Integer`, `String`, `DateTime`, `Text`, `JSON`).
   - Autoincrement primary keys and foreign key constraints adhere to cross-engine standards.
   - Timestamps use UTC ISO-8601 formatting across both engines.
3. **Repository Abstraction (`canongate.store.repos`)**:
   - All persistence operations are isolated behind async repository functions accepting an `AsyncSession`.
   - Neither the API route handlers nor the engine checks construct raw SQL strings or inspect dialect internals.

## Consequences
- **Positive**: Zero external services are required to clone and develop the application. Tests run in-memory or on local ephemeral SQLite databases with sub-second setup times.
- **Positive**: Enterprise deployments can switch to a managed PostgreSQL cluster by changing a single environment variable (`DATABASE_URL`).
- **Positive**: The standalone offline verification CLI (`canongate verify`) remains entirely self-contained.
- **Negative**: Certain PostgreSQL-specific extensions (such as `tsvector` full-text search or Postgres enum types) are intentionally avoided in favor of portable database-neutral patterns.

## Alternatives Considered
- *PostgreSQL-only with Docker requirement*: Rejected because it prevents running standalone offline CLI validation and complicates local development on restricted machines.
- *Raw SQLite (sqlite3) without ORM*: Rejected because it creates significant migration rework when scaling to enterprise multi-tenant deployments.
