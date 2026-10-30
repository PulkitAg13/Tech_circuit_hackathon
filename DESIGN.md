# CanonGate — Design System & Engineering Specification (`DESIGN.md`)

Distilled from `@ui-ux-pro-max`, `@design-taste-frontend` (`workspace` archetype), `@emil-design-eng`, `@impeccable`, and `@vibe-security`.

## 1. Aesthetic Direction & Surface Palette (`open-plane` Workspace)
- **Archetype**: High-craft light mode (`daylight-default`) engineered for dense legal, compliance, and brand audit workflows.
- **Surface Hierarchy** (Whisper-quiet luxury; borders instead of heavy drop-shadows):
  - `--bg-canvas` / `--ground`: `#ffffff` (Primary workspace plane)
  - `--bg-surface` / `--surface`: `#f9f9f9` (Sidebar, subtle wells, secondary panels)
  - `--bg-elevated` / `--raised`: `#ffffff` (Interactive cards, modals, inspector sheets)
  - `--bg-subtle`: `#f2f3f0` (Hover states, active nav pills, inline code pills)
- **Ink Hierarchy**:
  - `--ink-primary` / `--text`: `#1f201d` (Warm charcoal ink — high contrast without harsh `#000000` glare)
  - `--ink-secondary`: `#474844` (Body copy, rule explanations)
  - `--ink-muted` / `--muted`: `#636361` (Captions, metadata labels — WCAG AA `5.7:1` on `#ffffff`)
- **Accent & Semantic Verdicts**:
  - `--accent`: `#1b6e66` (Deep compliance teal — primary actions, active focus rings, verified Merkle states)
  - `--accent-hover`: `#145650`
  - `--accent-soft`: `rgba(27, 110, 102, 0.08)`
  - `--status-pass-fg`: `#166534` / `--status-pass-bg`: `#f0fdf4` / `--status-pass-border`: `#bbf7d0`
  - `--status-warn-fg`: `#92400e` / `--status-warn-bg`: `#fffbeb` / `--status-warn-border`: `#fde68a`
  - `--status-fail-fg`: `#991b1b` / `--status-fail-bg`: `#fef2f2` / `--status-fail-border`: `#fecaca`
- **Hairline Borders**:
  - `--line`: `rgba(31, 32, 29, 0.09)` (`1px solid` structural dividers)
  - `--line-strong`: `rgba(31, 32, 29, 0.18)` (Active inputs, emphasized cards)

## 2. Typography & Scannable Hierarchy
- **Display / Editorial Serif (`--font-display`)**: `'Instrument Serif', Georgia, serif`
  - Used selectively for the Home editorial greeting and Merkle Audit Certificate title (`clamp(1.75rem, 2.6vw, 2.35rem)`, `line-height: 1.12`, `letter-spacing: -0.02em`).
- **UI & Analytical Sans (`--font-sans`)**: `'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif`
  - Body `14px` (`0.875rem`) / `1.55` line-height; Section titles `16px–18px` (`font-weight: 600`, `letter-spacing: -0.015em`).
- **Technical & Cryptographic Mono (`--font-mono`)**: `'Geist Mono', ui-monospace, SFMono-Regular, monospace`
  - Used for rule IDs (`TERM-001`, `FACT-002`), Z3 SMT expressions, SHA-256 Merkle hashes, latency metrics (`18ms`), and JSON-RPC 2.0 payloads.
- **Numeric Discipline**:
  - `font-variant-numeric: tabular-nums` enforced across all KPI counters, pass rates, contrast ratios (`4.5:1`), latency badges, and audit tables.

## 3. Interactive Polish (`@emil-design-eng`)
- **Custom Easing Curves**:
  - `--ease-out`: `cubic-bezier(0.23, 1, 0.32, 1)` for hover, tab switches, and drawer/modal entrances (`160ms–200ms`).
  - `--ease-in-out`: `cubic-bezier(0.77, 0, 0.175, 1)` for layout state morphing.
- **Tactile Press Feedback**:
  - Every interactive button (`button:not(:disabled):active`, `.cg-btn:active`) uses `transform: scale(0.97)` so actions feel physically responsive.
- **Zero Layout Shift on Dynamic Text**:
  - Status notes (`.cg-clean-note`), inline code badges, and findings use `display: block` with inline elements or properly wrapped flex containers so `<strong>` and `<code>` children never fragment into vertical columns.

## 4. Layout & Responsive Breakpoints
- **Desktop (`1440px`)**: `240px` fixed left workspace rail + fluid main canvas (`max-width: 1320px`) with master-detail split panels.
- **Tablet (`768px`)**: Top horizontal navigation bar + 2-column adaptive grid; zero horizontal overflow.
- **Mobile (`390px`)**: Compact header + scrollable nav pills + stacked single-column cards with `>= 40px` touch targets and zero text overlap.
