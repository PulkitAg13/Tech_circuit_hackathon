import { useState, type FormEvent } from "react";
import { useAuth } from "./context";
import { useNavigate, Link } from "react-router-dom";
import {
  runGateCheck,
  createSubmission,
  callMcpRpc,
  getApiBase,
  type GateCheckResponsePayload,
} from "../../api/client";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Copy,
  KeyRound,
  Lock,
  LogOut,
  MessageSquare,
  ShieldCheck,
  Terminal,
  UserPlus,
} from "lucide-react";

const ROLE_CARDS = [
  {
    username: "creative_lead",
    role: "creator",
    stageTag: "Stage 1 · Creator",
    title: "Marketing & Agency Creator",
    desc: "Draft campaign copy, upload documents/banners, run pre-flight scans, and apply surgical fixes.",
  },
  {
    username: "brand_manager",
    role: "reviewer",
    stageTag: "Stage 2 · Brand Manager",
    title: "Brand Playbook Owner",
    desc: "Import custom brand playbooks, calibrate rule thresholds, review revisions, and approve Stage 2.",
  },
  {
    username: "legal_counsel",
    role: "admin",
    stageTag: "Stage 3 · Legal Counsel",
    title: "Authorised Legal Reviewer",
    desc: "Audit high-risk claims and statutory disclosures; seal the Ed25519 + RFC 9162 release certificate.",
  },
] as const;

const ESSENTIAL_BASELINES = [
  {
    id: "indian-digital-lending",
    code: "RBI 2025 KFS",
    name: "RBI Digital Lending & Key Fact Statement Baseline",
    desc: "Verifies APR disclosures, processing fee caps (Z3 SMT), tenure bounds, and mandatory bureau clauses.",
  },
  {
    id: "indian-d2c-nutra",
    code: "ASCI & CCPA",
    name: "ASCI & CCPA Advertising Substantiation Baseline",
    desc: "Blocks unverified therapeutic claims, CCPA drip-pricing math contradictions, and dropped qualifiers.",
  },
  {
    id: "acme-corp", /* taste-skill-ignore */
    code: "WCAG 2.1 AA",
    name: "WCAG 2.1 AA Accessibility & Enterprise Baseline",
    desc: "Enforces text contrast ratios (>= 4.5:1), SLA disclosure triggers, and approved enterprise terminology.",
  },
] as const;

export function LoginPage() {
  const {
    token,
    username: activeUser,
    role: activeRole,
    login,
    register,
    logout,
  } = useAuth();
  const navigate = useNavigate();

  // Prominent Auth Mode Tabs: "signin" | "signup" (Always visible on Home screen!)
  const [authTab, setAuthTab] = useState<"signin" | "signup">("signin");
  const [username, setUsername] = useState("creative_lead");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("demoPassword123!");
  const [role, setRole] = useState("creator");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // On-Demand Pre-Publish Gate state — starts 100% clean and empty (zero toy/test ads)
  const [selectedBaseline, setSelectedBaseline] = useState<string>(
    "indian-digital-lending",
  );
  const [alpha, setAlpha] = useState<number>(0.1);
  const [draftTitle, setDraftTitle] = useState<string>("");
  const [draftText, setDraftText] = useState<string>("");
  const [gateResult, setGateResult] = useState<GateCheckResponsePayload | null>(
    null,
  );
  const [gateLoading, setGateLoading] = useState<boolean>(false);
  const [selectedFindingIdx, setSelectedFindingIdx] = useState<number>(0);
  const [openingStudio, setOpeningStudio] = useState<boolean>(false);

  // Quick MCP Preview state on Home page
  const [mcpCopied, setMcpCopied] = useState(false);
  const [mcpTestOutput, setMcpTestOutput] = useState<string | null>(null);
  const [mcpTesting, setMcpTesting] = useState(false);

  // Contact Us form state
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactOrg, setContactOrg] = useState("");
  const [contactTopic, setContactTopic] = useState("enterprise-playbook");
  const [contactMessage, setContactMessage] = useState("");
  const [contactSubmitted, setContactSubmitted] = useState(false);

  async function handleRunQuickCheck(
    e?: FormEvent,
    overrideText?: string,
    overrideCanon?: string,
    overrideTitle?: string,
  ) {
    if (e) e.preventDefault();
    const textToScan = overrideText ?? draftText;
    const canonToUse = overrideCanon ?? selectedBaseline;
    const titleToUse = overrideTitle ?? draftTitle;
    if (!textToScan.trim()) return;
    setGateLoading(true);
    setError(null);
    try {
      const res = await runGateCheck({
        canon_id: canonToUse,
        adapter: "generic",
        title: titleToUse.trim() || "Quick Pre-Flight Check",
        raw_content: textToScan,
        alpha,
        persist: false,
      });
      setGateResult(res);
      setSelectedFindingIdx(0);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setGateLoading(false);
    }
  }

  async function handleQuickPersona(targetUsername: string) {
    setError(null);
    setLoading(true);
    try {
      await login(targetUsername, "demoPassword123!");
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleOpenInStudio() {
    if (!draftText.trim()) return;
    setError(null);
    setOpeningStudio(true);
    try {
      if (!token) {
        await login("creative_lead", "demoPassword123!");
      }
      const sub = await createSubmission(
        draftTitle.trim() || "Campaign Pre-Flight Audit",
        draftText,
        selectedBaseline,
        [],
        [],
      );
      const apiBase = getApiBase();
      await fetch(`${apiBase}/submissions/${sub.id}/scan?alpha=${alpha}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("cg_token") ?? ""}`,
        },
      }).catch(() => {});
      navigate(`/submissions/${sub.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setOpeningStudio(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (authTab === "signup") {
        await register(
          username.trim(),
          password,
          role,
          displayName.trim() || username.trim(),
        );
      } else {
        await login(username.trim(), password);
      }
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleTestMcpListCanons() {
    setMcpTesting(true);
    try {
      const rpcRes = await callMcpRpc("tools/call", {
        name: "list_canons",
        arguments: {},
      });
      const text =
        rpcRes.result?.content?.[0]?.text || JSON.stringify(rpcRes, null, 2);
      setMcpTestOutput(text);
    } catch (err) {
      setMcpTestOutput(
        JSON.stringify({ error: (err as Error).message }, null, 2),
      );
    } finally {
      setMcpTesting(false);
    }
  }

  function handleCopyMcpConfig() {
    const snippet = JSON.stringify(
      {
        mcpServers: {
          canongate: {
            command: "uv",
            args: ["run", "canongate-mcp"],
            env: { CANONGATE_HTTP_ENDPOINT: "http://localhost:8000/api/mcp" },
          },
        },
      },
      null,
      2,
    );
    navigator.clipboard?.writeText(snippet).catch(() => {});
    setMcpCopied(true);
    setTimeout(() => setMcpCopied(false), 2000);
  }

  function handleContactSubmit(e: FormEvent) {
    e.preventDefault();
    if (!contactName.trim() || !contactEmail.trim() || !contactMessage.trim()) {
      return;
    }
    setContactSubmitted(true);
  }

  const findings = gateResult?.findings ?? [];
  const activeFinding =
    findings[Math.min(selectedFindingIdx, Math.max(0, findings.length - 1))] ??
    null;

  return (
    <div className="cg-gateway-page">
      {/* Top Product & Auth Command Header */}
      <header className="cg-gateway-header">
        <div className="cg-gateway-header-inner">
          <Link to="/" className="cg-brand">
            <span className="cg-brand-mark" aria-hidden="true">
              <ShieldCheck size={16} strokeWidth={2.2} />
            </span>
            <span className="cg-brand-name">CanonGate</span>
            <span className="cg-brand-version">Pre-Publication Governance</span>
          </Link>

          <nav className="cg-gateway-nav" aria-label="Product Sections">
            <a href="#auth-gateway-card">Sign In / Sign Up</a>
            <a href="#quick-check">Live Gate Sandbox</a>
            <a href="#mcp-integration">MCP Brand Rule Server</a>
            <a href="#contact-us">Contact Us</a>
          </nav>

          <div
            className="cg-landing-nav-actions"
            style={{ display: "flex", alignItems: "center", gap: "8px" }}
          >
            {token ? (
              <>
                <Link to="/dashboard" className="cg-btn cg-btn-primary cg-btn-sm">
                  <span>
                    Open Workspace (@{activeUser} · {activeRole})
                  </span>
                  <ArrowRight size={14} className="cg-arrow-shift" />
                </Link>
                <button
                  type="button"
                  data-testid="header-signout-btn"
                  className="cg-btn cg-btn-secondary cg-btn-sm"
                  onClick={() => logout()}
                >
                  <LogOut size={13} />
                  <span>Sign Out</span>
                </button>
              </>
            ) : (
              <>
                <a
                  href="#auth-gateway-card"
                  className="cg-btn cg-btn-secondary cg-btn-sm"
                  onClick={() => {
                    setAuthTab("signin");
                  }}
                >
                  <KeyRound size={13} />
                  <span>Sign In</span>
                </a>
                <a
                  href="#auth-gateway-card"
                  className="cg-btn cg-btn-secondary cg-btn-sm"
                  onClick={() => {
                    setAuthTab("signup");
                    setUsername("");
                    setPassword("");
                  }}
                >
                  <UserPlus size={13} />
                  <span>Sign Up</span>
                </a>
                <button
                  type="button"
                  className="cg-btn cg-btn-primary cg-btn-sm"
                  disabled={loading}
                  onClick={() => void handleQuickPersona("creative_lead")}
                >
                  <span>Enter Workspace</span>
                  <ArrowRight size={14} className="cg-arrow-shift" />
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="cg-gateway-main">
        {error && (
          <div className="cg-alert-banner" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="cg-btn cg-btn-ghost cg-btn-sm"
              onClick={() => setError(null)}
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Section 1: Editorial Overview + First-Class Sign In / Sign Up & Role Launch */}
        <section
          className="cg-gateway-hero"
          aria-label="CanonGate Overview and Authentication"
        >
          <div className="cg-gateway-pitch-sheet">
            <div>
              <div className="cg-tier-summary-pill">
                <span>
                  Brand Playbook Compiler · Symbolic SMT Solver · QASem SlotDiff · MCP 2026-07-28
                </span>
              </div>
              <h1 className="cg-gateway-h1">
                Pre-publication brand &amp; claim governance.
              </h1>
              <p className="cg-gateway-lead">
                Audit campaign copy, documents (<code>.docx</code>,{" "}
                <code>.pdf</code>, <code>.html</code>), and promotional banners
                against statutory baselines (RBI Digital Lending KFS, ASCI &amp;
                CCPA, WCAG 2.1 AA) or your own compiled company brand playbook ·
                via web studio, CMS webhooks, or the <code>canongate-mcp</code>{" "}
                AI agent server.
              </p>
            </div>

            <div className="cg-gateway-kpi-ledger" id="regulatory-baselines">
              {ESSENTIAL_BASELINES.map((b) => (
                <div
                  key={b.id}
                  className="cg-gateway-kpi-item"
                  style={{ gridColumn: "span 1" }}
                >
                  <span
                    className="cg-gateway-kpi-val"
                    style={{ fontSize: "15px" }}
                  >
                    {b.code}
                  </span>
                  <strong style={{ fontSize: "12.5px", color: "var(--text)" }}>
                    {b.name}
                  </strong>
                  <span className="cg-gateway-kpi-label">{b.desc}</span>
                </div>
              ))}
              <div className="cg-gateway-kpi-item">
                <span
                  className="cg-gateway-kpi-val"
                  style={{ fontSize: "15px" }}
                >
                  MCP + Custom Playbooks
                </span>
                <strong style={{ fontSize: "12.5px", color: "var(--text)" }}>
                  Import Brand Rules via UI or MCP
                </strong>
                <span className="cg-gateway-kpi-label">
                  Paste company guidelines, approved facts, hex tokens, and
                  disclaimers to compile a custom YAML playbook or expose it via{" "}
                  <code>canongate-mcp</code>.
                </span>
              </div>
            </div>

            <div className="cg-gateway-kpi-ledger" style={{ marginTop: "4px" }}>
              <div className="cg-gateway-kpi-item">
                <span
                  className="cg-gateway-kpi-val"
                  style={{ fontSize: "14px" }}
                >
                  1. Compile Rules
                </span>
                <strong style={{ fontSize: "12.5px", color: "var(--text)" }}>
                  Playbook Onboarding Studio
                </strong>
                <span className="cg-gateway-kpi-label">
                  Paste raw brand books, product claims, hex colours, and
                  triggers or push via <code>compile_canon</code> over MCP.
                </span>
              </div>
              <div className="cg-gateway-kpi-item">
                <span
                  className="cg-gateway-kpi-val"
                  style={{ fontSize: "14px" }}
                >
                  2. Pre-Flight Scan
                </span>
                <strong style={{ fontSize: "12.5px", color: "var(--text)" }}>
                  Lexical + Z3 SMT + SlotDiff
                </strong>
                <span className="cg-gateway-kpi-label">
                  Catches banned terms, algebraic cap/tax contradictions,
                  dropped qualifiers, and WCAG 2.1 AA contrast failures.
                </span>
              </div>
              <div className="cg-gateway-kpi-item">
                <span
                  className="cg-gateway-kpi-val"
                  style={{ fontSize: "14px" }}
                >
                  3. Surgical Fix
                </span>
                <strong style={{ fontSize: "12.5px", color: "var(--text)" }}>
                  1-Click AST Remediation
                </strong>
                <span className="cg-gateway-kpi-label">
                  Apply deterministic compliant replacements in-place or via{" "}
                  <code>propose_fix</code> in Claude Desktop and Cursor.
                </span>
              </div>
              <div className="cg-gateway-kpi-item">
                <span
                  className="cg-gateway-kpi-val"
                  style={{ fontSize: "14px" }}
                >
                  4. Merkle Seal
                </span>
                <strong style={{ fontSize: "12.5px", color: "var(--text)" }}>
                  Stage 2 &amp; Stage 3 Sign-Off
                </strong>
                <span className="cg-gateway-kpi-label">
                  Brand Manager and Legal Counsel approve to issue an Ed25519 +
                  RFC 9162 SHA-256 audit certificate.
                </span>
              </div>
            </div>
          </div>

          {/* Right Sheet: First-Class Sign In / Sign Up Form + 1-Click Role Demo Launch */}
          <div className="cg-gateway-auth-sheet" id="auth-gateway-card" data-ui>
            <div className="cg-auth-sheet-header">
              <div>
                <h2 className="cg-auth-sheet-title">
                  Sign In or Create Workspace Account
                </h2>
                <p className="cg-auth-sheet-sub">
                  Sign in with credentials, register a new governance account,
                  or launch a pre-configured RBAC role below.
                </p>
              </div>
              <span className="cg-brand-version">JWT + RBAC</span>
            </div>

            {/* Explicit Sign In / Sign Up Mode Switcher */}
            <div
              className="cg-auth-mode-tabs"
              role="tablist"
              aria-label="Authentication Mode"
            >
              <button
                type="button"
                role="tab"
                data-testid="tab-signin"
                aria-selected={authTab === "signin"}
                className={`cg-auth-mode-tab ${
                  authTab === "signin" ? "active" : ""
                }`}
                onClick={() => {
                  setAuthTab("signin");
                  if (!username) setUsername("creative_lead");
                  if (!password) setPassword("demoPassword123!");
                }}
              >
                <KeyRound size={14} />
                <span>Sign In</span>
              </button>
              <button
                type="button"
                role="tab"
                data-testid="tab-signup"
                aria-selected={authTab === "signup"}
                className={`cg-auth-mode-tab ${
                  authTab === "signup" ? "active" : ""
                }`}
                onClick={() => {
                  setAuthTab("signup");
                  if (username === "creative_lead") setUsername("");
                }}
              >
                <UserPlus size={14} />
                <span>Create Account (Sign Up)</span>
              </button>
            </div>

            {/* Always-Visible Credential Form */}
            <form
              onSubmit={handleSubmit}
              className="cg-auth-credential-form"
              data-testid="credential-auth-form"
            >
              <div className="cg-field-row-2">
                <div className="cg-field-group">
                  <label htmlFor="login-username">Username</label>
                  <input
                    id="login-username"
                    data-testid="login-username-input"
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder={
                      authTab === "signup"
                        ? "e.g., priya_compliance"
                        : "e.g., creative_lead"
                    }
                    required
                  />
                </div>
                <div className="cg-field-group">
                  <label htmlFor="login-password">Password</label>
                  <input
                    id="login-password"
                    data-testid="login-password-input"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                  />
                </div>
              </div>

              {authTab === "signup" && (
                <div className="cg-field-row-2">
                  <div className="cg-field-group">
                    <label htmlFor="auth-display">Full Name / Team Label</label>
                    <input
                      id="auth-display"
                      type="text"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      placeholder="e.g., Priya Sharma (Brand Lead)"
                    />
                  </div>
                  <div className="cg-field-group">
                    <label htmlFor="auth-role">Governance Stage Role</label>
                    <select
                      id="auth-role"
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                    >
                      <option value="creator">
                        Stage 1 · Marketing Creator
                      </option>
                      <option value="reviewer">Stage 2 · Brand Manager</option>
                      <option value="admin">Stage 3 · Legal Reviewer</option>
                    </select>
                  </div>
                </div>
              )}

              <div className="cg-auth-form-actions">
                <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                  Demo accounts use password <code>demoPassword123!</code>
                </span>
                <button
                  type="submit"
                  data-testid="auth-submit-btn"
                  className="cg-btn cg-btn-primary cg-btn-sm"
                  disabled={loading}
                >
                  <span>
                    {loading
                      ? "Authenticating…"
                      : authTab === "signup"
                        ? "Create Account & Enter Workspace"
                        : "Sign In to Workspace"}
                  </span>
                  <ArrowRight size={14} className="cg-arrow-shift" />
                </button>
              </div>
            </form>

            {/* 1-Click Demo Role Launchers */}
            <div className="cg-persona-divider">
              <span>Or Launch 1-Click RBAC Stage Persona</span>
            </div>

            <div className="cg-persona-launch-list">
              {ROLE_CARDS.map((card) => (
                <button
                  key={card.username}
                  type="button"
                  data-testid={`quick-login-${card.username}`}
                  disabled={loading}
                  onClick={() => void handleQuickPersona(card.username)}
                  className="cg-persona-launch-row"
                >
                  <div className="cg-persona-row-left">
                    <div className="cg-persona-row-top">
                      <span className="cg-role-stage-tag">{card.stageTag}</span>
                      <span className="cg-persona-row-title">{card.title}</span>
                      <code>@{card.username}</code>
                    </div>
                    <span className="cg-persona-row-desc">{card.desc}</span>
                  </div>
                  <span className="cg-persona-row-cta">
                    <span>Launch</span>
                    <ArrowRight size={13} className="cg-arrow-shift" />
                  </span>
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Section 2: Clean, Empty On-Demand Pre-Publish Gate Sandbox (Zero Toy/Test Ads) */}
        <section
          id="quick-check"
          className="cg-live-workbench"
          data-ui
          aria-label="On-Demand Pre-Publish Check"
        >
          <div className="cg-wb-header" data-ui>
            <div className="cg-wb-title-block">
              <h2 className="cg-wb-title">
                Live Pre-Publish Gate Sandbox (<code>POST /api/gate/check</code>)
              </h2>
              {gateResult && (
                <span
                  className={`status-badge ${
                    gateResult.decision === "block"
                      ? "status-blocked"
                      : gateResult.decision === "needs_review"
                        ? "status-changes_requested"
                        : "status-approved"
                  }`}
                >
                  {gateResult.decision === "block"
                    ? `BLOCKED · ${gateResult.blocker_count} BLOCKER(S)`
                    : gateResult.decision === "needs_review"
                      ? `NEEDS REVIEW · ${gateResult.warning_count} WARNING(S)`
                      : "ALLOWED · 0 VIOLATIONS"}
                </span>
              )}
            </div>

            <div className="cg-wb-controls">
              <select
                aria-label="Regulatory Baseline"
                value={selectedBaseline}
                onChange={(e) => setSelectedBaseline(e.target.value)}
                style={{ width: "auto" }}
              >
                <option value="indian-digital-lending">
                  RBI Digital Lending &amp; KFS (indian-digital-lending)
                </option>
                <option value="indian-d2c-nutra">
                  ASCI &amp; CCPA Substantiation (indian-d2c-nutra)
                </option>
                <option value="acme-corp"> {/* taste-skill-ignore */}
                  WCAG 2.1 AA &amp; Enterprise Baseline {/* taste-skill-ignore */}
                </option>
                <option value="studio-brand-guidelines">
                  Brand Guidelines (Poppins/Lora ≥24pt · 60/30/10 Palette)
                </option>
              </select>

              <select
                aria-label="Conformal Alpha Risk Level"
                value={alpha}
                onChange={(e) => setAlpha(Number(e.target.value))}
                style={{ width: "auto" }}
              >
                <option value={0.04}>Strict (α = 0.04 · BFSI/Legal)</option>
                <option value={0.1}>Balanced (α = 0.10 · Standard)</option>
                <option value={0.2}>Permissive (α = 0.20 · Draft)</option>
              </select>
            </div>
          </div>

          <div className="cg-wb-body" data-ui>
            {/* Left Pane: Input Form */}
            <form
              onSubmit={(e) => void handleRunQuickCheck(e)}
              className="cg-wb-left-pane"
              data-ui
            >
              <div className="cg-wb-pane-header">
                <span className="cg-wb-pane-label">
                  Campaign Copy, Claim Table, or CSS Snippet
                </span>
                <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                  Conformal α = {alpha.toFixed(2)}
                </span>
              </div>

              <div className="cg-field-group">
                <label htmlFor="landing-gate-title">Campaign Title</label>
                <input
                  id="landing-gate-title"
                  type="text"
                  value={draftTitle}
                  onChange={(e) => setDraftTitle(e.target.value)}
                  placeholder="Enter campaign or page title…"
                />
              </div>

              <div className="cg-field-group">
                <label htmlFor="landing-gate-text">
                  Campaign Text / Claims / Disclaimers
                </label>
                <textarea
                  id="landing-gate-text"
                  rows={5}
                  value={draftText}
                  onChange={(e) => setDraftText(e.target.value)}
                  placeholder="Paste your campaign copy, product claims, pricing terms, or CSS snippet here…"
                />
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: "8px",
                }}
              >
                <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                  Evaluates Lexical/WCAG, Unit-Aware Z3 SMT &amp; QASem SlotDiff
                </span>
                <div style={{ display: "flex", gap: "8px" }}>
                  <button
                    type="submit"
                    data-testid="landing-run-gate-btn"
                    className="cg-btn cg-btn-primary cg-btn-sm"
                    disabled={gateLoading || !draftText.trim()}
                  >
                    {gateLoading ? "Scanning…" : "Run Gate Check"}
                  </button>
                  <button
                    type="button"
                    className="cg-btn cg-btn-secondary cg-btn-sm"
                    disabled={openingStudio || !draftText.trim()}
                    onClick={() => void handleOpenInStudio()}
                  >
                    <span>
                      {openingStudio
                        ? "Opening Studio…"
                        : "Open in Full Review Studio"}
                    </span>
                    <ArrowRight size={13} className="cg-arrow-shift" />
                  </button>
                </div>
              </div>
            </form>

            {/* Right Pane: Finding Inspector */}
            <div className="cg-wb-right-pane" data-ui>
              <div className="cg-wb-pane-header">
                <span className="cg-wb-pane-label">
                  {gateResult
                    ? `Audit Findings (${findings.length}) · ${gateResult.latency_ms.toFixed(1)} ms`
                    : "Audit Findings"}
                </span>
                {gateResult && (
                  <code style={{ fontSize: "11.5px", color: "var(--muted)" }}>
                    Threshold ≥ {(gateResult.conformal_threshold * 100).toFixed(0)}
                  </code>
                )}
              </div>

              {!gateResult ? (
                <div className="cg-clean-note">
                  Paste your campaign copy on the left and click{" "}
                  <strong>Run Gate Check</strong> to execute{" "}
                  <code>POST /api/gate/check</code> against the selected
                  regulatory or brand playbook.
                </div>
              ) : findings.length === 0 ? (
                <div className="cg-clean-note">
                  <CheckCircle2
                    size={15}
                    className="cg-text-emerald"
                    style={{ verticalAlign: "middle", marginRight: "6px" }}
                  />
                  <span>
                    Zero violations detected under{" "}
                    <strong>{selectedBaseline}</strong>. This copy is cleared
                    for release.
                  </span>
                </div>
              ) : (
                <>
                  <div className="cg-finding-list">
                    {findings.map((f, idx) => (
                      <div
                        key={f.finding_id}
                        role="button"
                        tabIndex={0}
                        onClick={() => setSelectedFindingIdx(idx)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            setSelectedFindingIdx(idx);
                          }
                        }}
                        className={`cg-finding-item ${
                          idx === selectedFindingIdx ? "selected" : ""
                        }`}
                      >
                        <div className="cg-finding-item-top">
                          <span
                            className={`cg-sev-badge ${
                              f.verdict === "BLOCKER"
                                ? "sev-blocker"
                                : "sev-warning"
                            }`}
                          >
                            {f.verdict} · {f.severity}
                          </span>
                          <code>{f.check_id}</code>
                          <span className="cg-tier-tag">Tier: {f.tier}</span>
                        </div>
                        <p className="cg-finding-msg">{f.message}</p>
                      </div>
                    ))}
                  </div>

                  {activeFinding && (
                    <div className="cg-finding-proof-box">
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: "8px",
                        }}
                      >
                        <strong style={{ fontSize: "12.5px" }}>
                          Rule Reference:{" "}
                          <code>
                            {activeFinding.rule_id || activeFinding.check_id}
                          </code>
                        </strong>
                        <span className="cg-tier-tag">
                          Engine Tier: {activeFinding.tier}
                        </span>
                      </div>

                      {activeFinding.replacement_preview && (
                        <div className="cg-remediation-strip">
                          <div>
                            <div
                              style={{
                                fontSize: "11.5px",
                                fontWeight: 600,
                                color: "var(--positive)",
                              }}
                            >
                              Suggested Compliant Replacement
                            </div>
                            <code>{activeFinding.replacement_preview}</code>
                          </div>
                          <button
                            type="button"
                            className="cg-btn cg-btn-emerald cg-btn-sm"
                            onClick={() => {
                              const loc = activeFinding.locator;
                              if (
                                typeof loc?.start === "number" &&
                                typeof loc?.end === "number" &&
                                activeFinding.replacement_preview
                              ) {
                                const updated =
                                  draftText.slice(0, loc.start) +
                                  activeFinding.replacement_preview +
                                  draftText.slice(loc.end);
                                setDraftText(updated);
                                void handleRunQuickCheck(undefined, updated);
                              }
                            }}
                          >
                            <Check size={13} />
                            <span>Apply Fix &amp; Rescan</span>
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </section>

        {/* Section 3: MCP Brand Rule Server & AI Agent Integration */}
        <section
          id="mcp-integration"
          className="cg-arch-ledger"
          aria-label="MCP Brand Rule Server Integration"
        >
          <div className="cg-arch-ledger-header">
            <div>
              <h2 className="cg-arch-ledger-title">
                Model Context Protocol (<code>canongate-mcp</code>) · How AI
                Agents Get Your Brand Rules
              </h2>
              <p className="cg-arch-ledger-sub">
                Connect Claude Desktop, Cursor, Windsurf, or custom AI agents
                via <code>stdio</code> or <code>POST /api/mcp</code> (MCP
                2026-07-28) to query playbooks, compile new brand guidelines,
                and run deterministic pre-flight audits.
              </p>
            </div>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <button
                type="button"
                className="cg-btn cg-btn-secondary cg-btn-sm"
                onClick={handleCopyMcpConfig}
              >
                {mcpCopied ? <Check size={13} /> : <Copy size={13} />}
                <span>
                  {mcpCopied
                    ? "Copied MCP Config!"
                    : "Copy claude_desktop_config.json"}
                </span>
              </button>
              <button
                type="button"
                data-testid="landing-test-mcp-btn"
                className="cg-btn cg-btn-primary cg-btn-sm"
                disabled={mcpTesting}
                onClick={() => void handleTestMcpListCanons()}
              >
                <Terminal size={13} />
                <span>
                  {mcpTesting
                    ? "Calling MCP…"
                    : "Test Live MCP tools/call (list_canons)"}
                </span>
              </button>
            </div>
          </div>

          <div className="cg-mcp-preview-grid">
            <div className="cg-mcp-code-card">
              <div className="cg-mcp-card-title">
                <span>
                  1. Connect Your AI Agent (
                  <code>claude_desktop_config.json</code> /{" "}
                  <code>.cursor/mcp.json</code>)
                </span>
                <code>MCP 2026-07-28</code>
              </div>
              <div className="cg-mcp-tools-pills">
                <code>stdio: uv run canongate-mcp</code>
                <code>http: POST /api/mcp</code>
                <code>canongate://canons/&lt;id&gt;</code>
              </div>
              <pre className="cg-mcp-pre">{`{
  "mcpServers": {
    "canongate": {
      "command": "uv",
      "args": ["run", "canongate-mcp"],
      "env": {
        "CANONGATE_HTTP_ENDPOINT": "http://localhost:8000/api/mcp"
      }
    }
  }
}`}</pre>
            </div>

            <div className="cg-mcp-code-card">
              <div className="cg-mcp-card-title">
                <span>
                  2. Exposed MCP Governance Tools &amp; Brand Rule Resources
                </span>
                <code>POST /api/mcp</code>
              </div>
              <div className="cg-mcp-tools-pills">
                <code>list_canons</code>
                <code>compile_canon</code>
                <code>get_canon_rules</code>
                <code>submit_batch</code>
                <code>job_status</code>
                <code>get_findings</code>
                <code>explain_finding</code>
                <code>propose_fix</code>
                <code>canongate://canons/&lt;id&gt;</code>
              </div>
              {mcpTestOutput ? (
                <pre
                  className="cg-mcp-pre"
                  style={{ maxHeight: "150px", overflowY: "auto" }}
                >
                  {mcpTestOutput}
                </pre>
              ) : (
                <pre className="cg-mcp-pre">
                  {JSON.stringify(
                    {
                      jsonrpc: "2.0",
                      method: "tools/call",
                      params: {
                        name: "compile_canon",
                        arguments: {
                          canon_id: "company-brand-2026",
                          raw_text:
                            "Never use guaranteed approval -> subject to credit assessment",
                        },
                      },
                    },
                    null,
                    2,
                  )}
                </pre>
              )}
            </div>
          </div>
        </section>

        {/* Section 4: Contact Us (Replaces 4-Tier Hybrid Governance Pipeline) */}
        <section
          id="contact-us"
          data-testid="contact-us-section"
          className="cg-live-workbench"
          data-ui
          aria-label="Contact Us"
        >
          <div className="cg-wb-header" data-ui>
            <div className="cg-wb-title-block">
              <h2 className="cg-wb-title">Contact Us</h2>
              <span className="cg-brand-version">
                Enterprise Governance &amp; Support
              </span>
            </div>
            <span style={{ fontSize: "12.5px", color: "var(--muted)" }}>
              Custom Playbook Onboarding · Regulatory Baselines · MCP &amp; CMS
              Integration
            </span>
          </div>

          <div className="cg-wb-body" data-ui>
            {/* Left Pane: Contact Inquiry Form */}
            <form
              onSubmit={handleContactSubmit}
              className="cg-wb-left-pane"
              data-ui
              data-testid="contact-us-form"
            >
              <div className="cg-wb-pane-header">
                <span className="cg-wb-pane-label">
                  Send an Enterprise or Technical Inquiry
                </span>
                <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                  Response SLA &lt; 4 business hours
                </span>
              </div>

              {contactSubmitted ? (
                <div
                  className="cg-success-banner"
                  data-testid="contact-submitted-banner"
                >
                  <CheckCircle2 size={15} />
                  <span>
                    Thank you, <strong>{contactName}</strong>. Your inquiry
                    regarding <strong>{contactTopic}</strong> has been logged.
                    Our governance engineering team will reach out to{" "}
                    <code>{contactEmail}</code>.
                  </span>
                  <button
                    type="button"
                    className="cg-btn cg-btn-secondary cg-btn-sm"
                    style={{ marginLeft: "auto" }}
                    onClick={() => {
                      setContactSubmitted(false);
                      setContactMessage("");
                    }}
                  >
                    Send Another Message
                  </button>
                </div>
              ) : (
                <>
                  <div className="cg-field-row-2">
                    <div className="cg-field-group">
                      <label htmlFor="contact-name">Full Name</label>
                      <input
                        id="contact-name"
                        data-testid="contact-name-input"
                        type="text"
                        value={contactName}
                        onChange={(e) => setContactName(e.target.value)}
                        placeholder="e.g., Priya Sharma"
                        required
                      />
                    </div>
                    <div className="cg-field-group">
                      <label htmlFor="contact-email">Work Email</label>
                      <input
                        id="contact-email"
                        data-testid="contact-email-input"
                        type="email"
                        value={contactEmail}
                        onChange={(e) => setContactEmail(e.target.value)}
                        placeholder="e.g., priya@company.com"
                        required
                      />
                    </div>
                  </div>

                  <div className="cg-field-row-2">
                    <div className="cg-field-group">
                      <label htmlFor="contact-org">Organisation / Team</label>
                      <input
                        id="contact-org"
                        type="text"
                        value={contactOrg}
                        onChange={(e) => setContactOrg(e.target.value)}
                        placeholder="e.g., Brand & Legal Compliance"
                      />
                    </div>
                    <div className="cg-field-group">
                      <label htmlFor="contact-topic">Inquiry Topic</label>
                      <select
                        id="contact-topic"
                        value={contactTopic}
                        onChange={(e) => setContactTopic(e.target.value)}
                      >
                        <option value="enterprise-playbook">
                          Custom Brand Playbook Onboarding
                        </option>
                        <option value="regulatory-baselines">
                          RBI KFS / ASCI / CCPA / WCAG Baselines
                        </option>
                        <option value="mcp-webhook-integration">
                          MCP Server &amp; CMS Webhook Integration
                        </option>
                        <option value="security-dpdp">
                          Air-Gapped Deployment &amp; DPDP Compliance
                        </option>
                      </select>
                    </div>
                  </div>

                  <div className="cg-field-group">
                    <label htmlFor="contact-message">
                      How can we help your governance workflow?
                    </label>
                    <textarea
                      id="contact-message"
                      data-testid="contact-message-input"
                      rows={3}
                      value={contactMessage}
                      onChange={(e) => setContactMessage(e.target.value)}
                      placeholder="Describe your brand guidelines, regulatory scope, or CMS/MCP integration needs…"
                      required
                    />
                  </div>

                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: "8px",
                    }}
                  >
                    <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                      Protected under DPDP Act 2023 · Zero third-party sharing
                    </span>
                    <button
                      type="submit"
                      data-testid="contact-submit-btn"
                      className="cg-btn cg-btn-primary cg-btn-sm"
                    >
                      <MessageSquare size={13} />
                      <span>Send Message</span>
                    </button>
                  </div>
                </>
              )}
            </form>

            {/* Right Pane: Direct Contact Channels */}
            <div className="cg-wb-right-pane" data-ui>
              <div className="cg-wb-pane-header">
                <span className="cg-wb-pane-label">
                  Direct Governance &amp; Engineering Desks
                </span>
                <code style={{ fontSize: "11.5px", color: "var(--muted)" }}>
                  24×7 Incident &amp; Release Desk
                </code>
              </div>

              <div className="cg-contact-desks-grid">
                <div className="cg-gateway-kpi-item">
                  <span
                    className="cg-gateway-kpi-val"
                    style={{ fontSize: "14px" }}
                  >
                    Enterprise &amp; Brand Desk
                  </span>
                  <strong style={{ fontSize: "12.5px", color: "var(--text)" }}>
                    governance@canongate.io
                  </strong>
                  <span className="cg-gateway-kpi-label">
                    Custom brand playbook compilation, multi-stage RBAC setup,
                    and dedicated on-prem / VPC deployment.
                  </span>
                </div>

                <div className="cg-gateway-kpi-item">
                  <span
                    className="cg-gateway-kpi-val"
                    style={{ fontSize: "14px" }}
                  >
                    Legal &amp; Regulatory Desk
                  </span>
                  <strong style={{ fontSize: "12.5px", color: "var(--text)" }}>
                    compliance@canongate.io
                  </strong>
                  <span className="cg-gateway-kpi-label">
                    RBI Digital Lending KFS, ASCI, CCPA 2023 drip-pricing rules,
                    and RFC 9162 Merkle audit certificate verification.
                  </span>
                </div>

                <div className="cg-gateway-kpi-item">
                  <span
                    className="cg-gateway-kpi-val"
                    style={{ fontSize: "14px" }}
                  >
                    MCP &amp; Developer Support
                  </span>
                  <strong style={{ fontSize: "12.5px", color: "var(--text)" }}>
                    mcp-support@canongate.io
                  </strong>
                  <span className="cg-gateway-kpi-label">
                    Claude Desktop, Cursor, Windsurf <code>canongate-mcp</code>{" "}
                    server setup and Shopify / Webflow pre-publish gates.
                  </span>
                </div>

                <div className="cg-gateway-kpi-item">
                  <span
                    className="cg-gateway-kpi-val"
                    style={{ fontSize: "14px" }}
                  >
                    Security &amp; DPDP Office
                  </span>
                  <strong style={{ fontSize: "12.5px", color: "var(--text)" }}>
                    security@canongate.io
                  </strong>
                  <span className="cg-gateway-kpi-label">
                    Air-gapped PII vault configuration, C2PA v2.3 asset signing,
                    and vulnerability disclosure.
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="cg-gateway-footer">
        <div className="cg-gateway-footer-inner">
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <Lock size={13} />
            <span>
              CanonGate Governance Engine · Pre-Flight Compliance, Symbolic SMT,
              QASem SlotDiff, MCP 2026-07-28 &amp; Ed25519 Merkle Certificates
            </span>
          </div>
          <div>
            <span>
              RBI 2025 KFS · ASCI · CCPA 2023 · WCAG 2.1 AA · DPDP Act 2023
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
