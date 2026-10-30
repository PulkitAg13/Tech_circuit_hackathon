# CanonGate — Product Architecture, Personas & SOTA Compliance UX

## 1. Problem Statement & Core Product Purpose
**CanonGate** is a deterministic **Brand, Accessibility & Regulatory Governance Engine** designed for regulated consumer, financial, healthcare, and e-commerce organizations (e.g., RBI Digital Lending KFS, ASCI Advertising Code, CCPA 2023 Drip Pricing Rules, Drugs & Magic Remedies Act, and WCAG 2.1 Level AA).

In modern marketing and product teams, creative assets, landing pages, CMS entries, and AI-generated copy are produced faster than legal and compliance teams can review them. Existing LLM-only compliance checkers hallucinate citations, miss mathematical contradictions across copy blocks, and cannot issue tamper-evident cryptographic sign-offs.

**CanonGate solves this with a 3-Tier Deterministic + Semantic Verification Pipeline:**
1. **Tier 1 — Deterministic Policy & Accessibility Gate (`< 5ms`)**:
   - Compiled Aho-Corasick / regex terminology scanner (banned superlatives, dark patterns, unapproved medical/financial phrasing).
   - Hex & CSS color palette extraction with **WCAG 2.1 relative luminance contrast calculation** (`4.5:1` Level AA / `7.0:1` Level AAA).
   - Trigger-conditioned mandatory legal disclaimers (e.g., APR / loan triggers requiring RBI Key Fact Statement disclosures).
2. **Tier 1.5 — Z3 SMT Symbolic Arithmetic & Contradiction Prover (`< 25ms`)**:
   - Extracts numeric claims (`APR = 0%`, `Processing Fee = ₹1,500`, `Discount = 50%`, `List Price = ₹1,000`, `Checkout Price = ₹600`) and proves whether copy contains **mathematical contradictions** or illegal drip-pricing under CCPA 2023.
3. **Tier 2 — QASem Predicate-Argument SlotDiff (`< 50ms`)**:
   - Aligns claims in marketing copy against canonical **Approved Facts** and checks whether required **qualifiers** (e.g., *"for a 30-day billing cycle with a 15-day grace period"*, *"in a 12-week clinical trial of 120 adults"*) are present or omitted.

---

## 2. Target Personas & How They Use CanonGate

| Persona | Primary Goal | Expected Workflow in CanonGate |
| :--- | :--- | :--- |
| **1. Marketing Creator / Copywriter (`Stage 1: Creator Studio`)** | Draft campaign copy, upload PDF/Markdown/HTML briefs, and fix violations *before* submitting to Brand & Legal. | 1. Select an active Brand Playbook (or **Import Custom Playbook** in 1 click).<br>2. Paste/upload campaign assets or run a **Pre-Publish Gate Check**.<br>3. Inspect inline highlighted spans (`BLOCKING` vs `WARNING`), click **Apply Deterministic Fix** (`propose_fix`), and click **Submit to Stage 2**. |
| **2. Brand & Governance Lead (`Stage 2: Brand & Governance`)** | Maintain living Brand Playbooks, review Stage 2 campaign submissions, and resolve recurring creator friction. | 1. **Import Custom Playbook** by pasting raw brand guidelines, approved facts, hex colors, and disclaimer triggers—and see compiled rules immediately.<br>2. Review Stage 2 submissions and approve to Stage 3.<br>3. Triage **Playbook Friction Signals** (when creators flag an overly strict rule) and merge `canon.yaml` pull requests. |
| **3. Legal & Regulatory Counsel (`Stage 3: Legal Sign-Off`)** | Perform final regulatory sign-off on high-stakes campaigns and generate audit-ready cryptographic certificates. | 1. Inspect the 3-Tier Audit Matrix (Terminology, Z3 SMT Math Proof, QASem Fact SlotDiff, Required Disclaimers).<br>2. Grant **Stage 3 Final Approval**.<br>3. Issue and export the **RFC 6962 SHA-256 Merkle Audit Certificate** (`.json` / `.pdf`). |
| **4. AI Agent / Developer (`MCP Server & CMS Webhook Gate`)** | Give AI coding/writing assistants (Claude Desktop, Cursor, Windsurf, custom agents) direct access to company brand rules and block non-compliant CMS publishes. | 1. Connect via **Model Context Protocol (`canongate-mcp` stdio or `POST /api/mcp` Streamable HTTP)**.<br>2. Push or query brand rules via MCP (`list_canons`, `compile_canon`, `get_canon_rules`, `canongate://canons/<id>`).<br>3. Run `submit_batch`, `get_findings`, `explain_finding`, and `propose_fix` directly from the AI agent or CMS webhook (`POST /api/gate/webhook/{provider}`). |

---

## 3. Benchmarks from SOTA Governance & Compliance Platforms
Drawing from best-in-class products (Vanta, Linear, Stripe Radar, Writer.com Brand Governance, Figma Tokens Studio):
- **Immediate, Self-Contained Playbook Onboarding**: Importing a custom playbook must work as a standalone action—paste brand guidelines or click a preset template, preview extracted rules live (Terminology, Facts, Hex Tokens, Triggers), and compile into an active Playbook in one click without forcing the user to fill out unrelated campaign fields first.
- **First-Class MCP & Developer Ergonomics**: When a product ships an MCP server (`canongate-mcp`), the UI must expose an interactive **MCP Brand Rule Hub** with copyable `claude_desktop_config.json` / `.cursor/mcp.json` snippets, MCP resource URIs (`canongate://canons/<id>`), and a live in-browser JSON-RPC 2.0 tester so users immediately see how their AI agents receive and enforce brand rules.
- **Explicit, Predictable Authentication**: Sign In, Sign Up (Create Account), and Role Demo Launch must be immediately visible on the home screen; clicking **Sign Out** must deterministically clear session state and return to the Sign In screen without silent background re-authentication loops.
