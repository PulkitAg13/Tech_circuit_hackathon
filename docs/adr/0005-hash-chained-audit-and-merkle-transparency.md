# ADR 0005: Hash-Chained Audit Ledger and RFC 9162 Merkle Transparency

## Status
Accepted

## Context
Brand compliance and pre-publication claim clearances are subject to legal scrutiny by regulatory bodies (e.g., CCPA, ASCI, RBI, FTC). When compliance violations are alleged, an enterprise must provide non-repudiable evidence proving:
1. Exactly what asset content was submitted and evaluated.
2. Which rules in the brand canon were active at the exact moment of evaluation.
3. Who reviewed the findings, what actions were taken (accept, dismiss, override), and the mandatory rationale provided for overrides.
4. That the audit history has not been altered or backdated after the fact.

Standard database audit rows (e.g. `updated_at` columns or simple relational event logs) provide insufficient integrity because anyone with database administrative access can silently alter or delete records.

## Decision
We implemented a multi-layered cryptographic audit and transparency architecture:

### 1. SHA-256 Hash-Chained Event Ledger
Every workflow state transition (e.g., `submit`, `approve`, `request_changes`, `publish`) generates an immutable event row linked in a deterministic hash chain:
```
event_hash = SHA-256(prev_hash || submission_id || action || actor_id || timestamp)
```
- The initial event links to a standardized `GENESIS_HASH` (`"0" * 64`).
- Any modification to an event's action, actor, timestamp, or sequence breaks the chain and is detected during ledger verification (`repos.verify_submission_chain`).

### 2. RFC 9162 Merkle Tree Transparency Log
The complete sequence of event hashes is indexed into an in-memory RFC 9162 Merkle Tree:
- Enables $O(\log n)$ cryptographic inclusion proofs.
- Produces a deterministic Merkle Root.
- Emits a Signed Tree Head (STH) signed using Ed25519 asymmetric cryptography.

### 3. Cognitive Forcing Functions on Finding Resolutions
To prevent rubber-stamping, override and dismissal actions enforce a cognitive forcing function requiring a justification reason (minimum 3 characters) persisted with the finding resolution.

### 4. Outbound C2PA Cryptographic Provenance
When visual assets are approved and published, CanonGate uses an internal X.509 v3 ECDSA P-256 (`ES256`) certificate generator to produce a C2PA manifest embedding the Merkle Root, content hash, canon hash, and approval metadata directly into the image sidecar.

### 5. Standalone Offline CLI Verifier
A standalone offline command-line tool (`canongate verify cert.json`) enables third-party auditors and regulators to verify governance certificates, Merkle proofs, and Ed25519 signatures completely offline without requiring network access or database credentials.

## Consequences
- **Positive**: Tamper-evident, non-repudiable compliance history with mathematical verification.
- **Positive**: Regulators can independently verify governance claims offline.
- **Positive**: Avoids copyleft licensing traps (e.g., avoiding GPL-3 `pymerkle` in favor of native RFC 9162 implementation).
- **Negative**: All workflow mutations must explicitly compute and commit hash-chain links, preventing bulk batch updates without chain recomputation.

## Alternatives Considered
- *Standard Database Audit Table*: Rejected because it offers no tamper detection against database administrators or compromised credentials.
- *Public Blockchain (Ethereum/Polygon)*: Rejected due to transaction latency, financial cost (gas fees), and confidentiality/privacy requirements under enterprise data protection laws.
