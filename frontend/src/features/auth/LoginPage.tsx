import { useState, type FormEvent } from "react";
import { useAuth } from "./context";
import { useNavigate, Link } from "react-router-dom";
import {
  runGateCheck,
  createSubmission,
  getApiBase,
  type GateCheckResponsePayload,
} from "../../api/client";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Lock,
  ShieldCheck,
  Sliders,
} from "lucide-react";

const ROLE_CARDS = [
  {
    username: "creative_lead",
    role: "creator",
    stageTag: "Stage 1 · Creator",
    title: "Marketing & Agency Creator",
    desc: "Upload your campaign copy, documents, and banners; run pre-flight scans and apply fixes.",
  },
  {
    username: "brand_manager",
    role: "reviewer",
    stageTag: "Stage 2 · Brand Manager",
    title: "Brand Playbook Owner",
    desc: "Manage brand playbooks, calibrate rule thresholds, review revisions, and approve brand readiness.",
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
    desc: "Verifies APR disclosures, processing fee caps, tenure bounds, and mandatory bureau verification clauses.",
  },
  {
    id: "indian-d2c-nutra",
    code: "ASCI & CCPA",
    name: "ASCI & CCPA Advertising Substantiation Baseline",
    desc: "Enforces consumer protection rules against unverified therapeutic claims, drip pricing, and missing qualifiers.",
  },
  {
    id: "acme-corp", /* taste-skill-ignore */
    code: "WCAG 2.1 AA",
    name: "WCAG 2.1 AA Accessibility & Enterprise Baseline",
    desc: "Verifies text contrast ratios (>= 4.5:1), image alt-text completeness, and formal enterprise terminology.",
  },
] as const;

export function LoginPage() {
  const {
    token,
    username: activeUser,
    role: activeRole,
    login,
    register,
  } = useAuth();
  const navigate = useNavigate();

  // Auth form state
  const [showCustomForm, setShowCustomForm] = useState(false);
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("creator");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // On-Demand Pre-Publish Gate state (starts 100% clean and empty — no fake ads)
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

  async function handleRunQuickCheck(e: FormEvent) {
    e.preventDefault();
    if (!draftText.trim()) return;
    setGateLoading(true);
    setError(null);
    try {
      const res = await runGateCheck({
        canon_id: selectedBaseline,
        adapter: "generic",
        title: draftTitle.trim() || "Quick Pre-Flight Check",
        raw_content: draftText,
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
      if (isRegister) {
        await register(username, password, role, displayName || username);
      } else {
        await login(username, password);
      }
      navigate("/dashboard");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const findings = gateResult?.findings ?? [];
  const activeFinding =
    findings[Math.min(selectedFindingIdx, Math.max(0, findings.length - 1))] ??
    null;

  return (
    <div className="cg-gateway-page">
      {/* Top Product & Role Launch Command Header */}
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
            <a href="#regulatory-baselines">Regulatory Baselines</a>
            <a href="#quick-check">On-Demand Check</a>
            <a href="#engine-architecture">4-Tier Architecture</a>
          </nav>

          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {token ? (
              <Link to="/dashboard" className="cg-btn cg-btn-primary cg-btn-sm">
                <span>
                  Open Workspace (@{activeUser} · {activeRole})
                </span>
                <ArrowRight size={14} className="cg-arrow-shift" />
              </Link>
            ) : (
              <button
                type="button"
                className="cg-btn cg-btn-primary cg-btn-sm"
                disabled={loading}
                onClick={() => void handleQuickPersona("creative_lead")}
              >
                <span>Enter Workspace</span>
                <ArrowRight size={14} className="cg-arrow-shift" />
              </button>
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

        {/* Section 1: Clean Overview + Role-Scoped Workspace Entry */}
        <section
          className="cg-gateway-hero"
          aria-label="CanonGate Overview and Role Launch"
        >
          <div className="cg-gateway-pitch-sheet">
            <div>
              <h1 className="cg-gateway-h1">
                Pre-publication brand, claim, and regulatory governance.
              </h1>
              <p className="cg-gateway-lead">
                Verify campaign copy, documents (`.docx`, `.pdf`, `.html`), and
                promotional banners against essential statutory baselines (RBI
                Digital Lending KFS, ASCI &amp; CCPA, WCAG 2.1 AA) or your own
                compiled company brand guidelines before anything goes live.
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
                  Custom Canon
                </span>
                <strong style={{ fontSize: "12.5px", color: "var(--text)" }}>
                  Your Own Brand Playbooks
                </strong>
                <span className="cg-gateway-kpi-label">
                  Upload your own PDF/Word brand books, CSV fact sheets, and
                  reference logos inside the workspace.
                </span>
              </div>
            </div>
          </div>

          {/* Right Sheet: 1-Click Role Launch & Credential Sign-In */}
          <div className="cg-gateway-auth-sheet" data-ui>
            <div className="cg-auth-sheet-header">
              <div>
                <h2 className="cg-auth-sheet-title">
                  Enter Governance Workspace
                </h2>
                <p className="cg-auth-sheet-sub">
                  Select your role to open a clean workspace, or sign in with
                  your account credentials.
                </p>
              </div>
              <span className="cg-brand-version">RBAC Active</span>
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
                    <span>Open</span>
                    <ArrowRight size={13} className="cg-arrow-shift" />
                  </span>
                </button>
              ))}
            </div>

            <div
              style={{
                borderTop: "1px solid var(--rule)",
                paddingTop: "12px",
                display: "flex",
                flexDirection: "column",
                gap: "10px",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                  Role accounts use password <code>demoPassword123!</code>
                </span>
                <button
                  type="button"
                  className="cg-link-btn"
                  onClick={() => setShowCustomForm(!showCustomForm)}
                >
                  {showCustomForm
                    ? "Hide Credential Form"
                    : "Sign In / Register Custom Account"}
                </button>
              </div>

              {showCustomForm && (
                <form
                  onSubmit={handleSubmit}
                  className="cg-animate-swap"
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "10px",
                    backgroundColor: "var(--surface-subtle)",
                    padding: "12px",
                    borderRadius: "6px",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="cg-field-row-2">
                    <div className="cg-field-group">
                      <label htmlFor="auth-username">Username</label>
                      <input
                        id="auth-username"
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        placeholder="e.g., creative_lead"
                        required
                      />
                    </div>
                    <div className="cg-field-group">
                      <label htmlFor="auth-password">Password</label>
                      <input
                        id="auth-password"
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        required
                      />
                    </div>
                  </div>

                  {isRegister && (
                    <div className="cg-field-row-2">
                      <div className="cg-field-group">
                        <label htmlFor="auth-display">Display Name</label>
                        <input
                          id="auth-display"
                          type="text"
                          value={displayName}
                          onChange={(e) => setDisplayName(e.target.value)}
                          placeholder="e.g., Priya Sharma"
                        />
                      </div>
                      <div className="cg-field-group">
                        <label htmlFor="auth-role">Governance Role</label>
                        <select
                          id="auth-role"
                          value={role}
                          onChange={(e) => setRole(e.target.value)}
                        >
                          <option value="creator">Stage 1 · Creator</option>
                          <option value="reviewer">
                            Stage 2 · Brand Manager
                          </option>
                          <option value="admin">
                            Stage 3 · Legal Reviewer
                          </option>
                        </select>
                      </div>
                    </div>
                  )}

                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: "8px",
                    }}
                  >
                    <button
                      type="button"
                      className="cg-link-btn"
                      onClick={() => setIsRegister(!isRegister)}
                    >
                      {isRegister
                        ? "Already have an account? Sign In"
                        : "Need a new account? Register"}
                    </button>
                    <button
                      type="submit"
                      className="cg-btn cg-btn-primary cg-btn-sm"
                      disabled={loading}
                    >
                      {loading
                        ? "Authenticating…"
                        : isRegister
                          ? "Create Account"
                          : "Sign In"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </section>

        {/* Section 2: Clean, Empty On-Demand Pre-Flight Check (Zero pre-filled fake ads) */}
        <section
          id="quick-check"
          className="cg-live-workbench"
          data-ui
          aria-label="On-Demand Pre-Publish Check"
        >
          <div className="cg-wb-header" data-ui>
            <div className="cg-wb-title-block">
              <h2 className="cg-wb-title">
                On-Demand Pre-Publish Check (<code>POST /api/gate/check</code>)
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
              <div
                className="cg-segmented-group"
                role="tablist"
                aria-label="Regulatory Baseline"
              >
                {ESSENTIAL_BASELINES.map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    role="tab"
                    aria-selected={selectedBaseline === b.id}
                    className={`cg-seg-btn ${
                      selectedBaseline === b.id ? "active" : ""
                    }`}
                    onClick={() => setSelectedBaseline(b.id)}
                  >
                    {b.code}
                  </button>
                ))}
              </div>

              <div
                className="cg-segmented-group"
                title="Distribution-free Conformal Risk Control (alpha)"
              >
                <span
                  style={{
                    fontSize: "11.5px",
                    color: "var(--muted)",
                    padding: "0 6px",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "4px",
                  }}
                >
                  <Sliders size={12} /> α:
                </span>
                {[0.04, 0.1, 0.2].map((val) => (
                  <button
                    key={val}
                    type="button"
                    className={`cg-seg-btn ${alpha === val ? "active" : ""}`}
                    onClick={() => setAlpha(val)}
                  >
                    {val.toFixed(2)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="cg-wb-body" data-ui>
            <form
              onSubmit={handleRunQuickCheck}
              className="cg-wb-left-pane"
              data-ui
            >
              <div className="cg-field-group">
                <label htmlFor="wb-title-input">
                  Asset or Campaign Title (optional)
                </label>
                <input
                  id="wb-title-input"
                  type="text"
                  value={draftTitle}
                  onChange={(e) => setDraftTitle(e.target.value)}
                  placeholder="Enter your campaign or document title…"
                />
              </div>

              <div className="cg-field-group">
                <label htmlFor="wb-live-textarea">
                  Your Copy, Claims, or HTML Content
                </label>
                <textarea
                  id="wb-live-textarea"
                  rows={4}
                  value={draftText}
                  onChange={(e) => setDraftText(e.target.value)}
                  placeholder="Paste your own marketing copy, product claims, pricing terms, or HTML snippet here to verify against the selected regulatory baseline…"
                />
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "8px",
                  flexWrap: "wrap",
                }}
              >
                <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                  Evaluated locally with DPDP PII protection.
                </span>
                <div style={{ display: "flex", gap: "8px" }}>
                  {gateResult && (
                    <button
                      type="button"
                      className="cg-btn cg-btn-secondary cg-btn-sm"
                      onClick={() => {
                        setDraftText("");
                        setDraftTitle("");
                        setGateResult(null);
                      }}
                    >
                      Clear
                    </button>
                  )}
                  <button
                    type="submit"
                    className="cg-btn cg-btn-primary cg-btn-sm"
                    disabled={gateLoading || !draftText.trim()}
                  >
                    <span>
                      {gateLoading ? "Checking…" : "Run Pre-Publish Check"}
                    </span>
                    <ArrowRight size={13} className="cg-arrow-shift" />
                  </button>
                </div>
              </div>
            </form>

            <div className="cg-wb-right-pane" data-ui>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "8px",
                }}
              >
                <span style={{ fontSize: "13px", fontWeight: 600 }}>
                  Verification Result
                </span>
                {gateResult && (
                  <button
                    type="button"
                    className="cg-btn cg-btn-secondary cg-btn-sm"
                    disabled={openingStudio}
                    onClick={() => void handleOpenInStudio()}
                  >
                    <span>
                      {openingStudio
                        ? "Opening Studio…"
                        : "Open in Full Review Studio"}
                    </span>
                    <ArrowRight size={13} />
                  </button>
                )}
              </div>

              {!gateResult ? (
                <div
                  className="cg-clean-note"
                  style={{
                    padding: "24px 16px",
                    justifyContent: "center",
                    textAlign: "center",
                  }}
                >
                  Paste your copy on the left and click{" "}
                  <strong>Run Pre-Publish Check</strong>, or enter the workspace
                  above to upload full documents (`.docx`, `.pdf`), banners
                  (`.png`, `.jpg`), and custom brand playbooks.
                </div>
              ) : findings.length === 0 ? (
                <div
                  className="cg-success-banner"
                  style={{
                    flexDirection: "column",
                    alignItems: "flex-start",
                    gap: "6px",
                    padding: "16px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      fontWeight: 600,
                    }}
                  >
                    <CheckCircle2 size={16} />
                    <span>
                      All Pre-Publication Checks Passed (Decision: ALLOW)
                    </span>
                  </div>
                  <p style={{ margin: 0, fontSize: "12.5px" }}>
                    Zero violations detected against{" "}
                    <code>{gateResult.canon_id}</code>.
                  </p>
                </div>
              ) : (
                <>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                    {findings.map((f, idx) => (
                      <button
                        key={f.finding_id || idx}
                        type="button"
                        onClick={() => setSelectedFindingIdx(idx)}
                        className={`cg-btn cg-btn-sm ${
                          selectedFindingIdx === idx
                            ? "cg-btn-primary"
                            : "cg-btn-secondary"
                        }`}
                      >
                        <span>#{idx + 1}</span>
                        <code>{f.check_id}</code>
                        <span
                          className={`cg-sev-badge ${
                            f.severity >= 50 ? "sev-blocker" : "sev-warning"
                          }`}
                        >
                          {f.severity}
                        </span>
                      </button>
                    ))}
                  </div>

                  {activeFinding && (
                    <div
                      className={`cg-fault-card ${
                        activeFinding.severity >= 50
                          ? "fault-blocker"
                          : "fault-warning"
                      }`}
                      style={{ cursor: "default" }}
                    >
                      <div className="cg-fault-card-top">
                        <span
                          className={`cg-sev-badge ${
                            activeFinding.severity >= 50
                              ? "sev-blocker"
                              : "sev-warning"
                          }`}
                        >
                          {activeFinding.verdict} · {activeFinding.severity}
                        </span>
                        <code>{activeFinding.check_id}</code>
                        <span className="cg-fault-tier-pill">
                          Tier: {activeFinding.tier.toUpperCase()}
                        </span>
                      </div>

                      <p className="cg-fault-message">{activeFinding.message}</p>

                      {activeFinding.rule_id && (
                        <div className="cg-fault-rule-box">
                          <span className="cg-mono-label">
                            Governing Rule: <code>{activeFinding.rule_id}</code>
                          </span>
                        </div>
                      )}

                      {activeFinding.replacement_preview && (
                        <div className="cg-fault-suggestion-box">
                          <span className="cg-mono-label">
                            {activeFinding.suggestion_label ||
                              "Suggested Remediation"}
                          </span>
                          <div className="cg-replacement-diff">
                            <Check size={14} />
                            <code>{activeFinding.replacement_preview}</code>
                          </div>
                        </div>
                      )}

                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          paddingTop: "6px",
                          fontSize: "12px",
                          color: "var(--muted)",
                        }}
                      >
                        <span>
                          <Lock size={12} style={{ verticalAlign: "middle" }} />{" "}
                          {activeFinding.severity >= 50
                            ? "Blocker: Requires remediation before sign-off"
                            : "Warning: Can be remediated or overridden with justification"}
                        </span>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </section>

        {/* Section 3: 4-Tier Verification Architecture & 3-Role Governance Ledger */}
        <section
          id="engine-architecture"
          className="cg-gov-two-col"
          aria-label="Verification Architecture and Role Matrix"
        >
          <div className="cg-gov-card">
            <div className="cg-gov-card-header">
              <div>
                <h3>Four-Tier Pre-Publication Verification Cascade</h3>
                <p>
                  Every text node, Markdown KFS table, and banner image is
                  parsed into a unified ContentAST and verified locally.
                </p>
              </div>
            </div>
            <div className="cg-table-scroll">
              <table className="cg-data-table">
                <thead>
                  <tr>
                    <th>Tier</th>
                    <th>Verification Engine</th>
                    <th>Enforced Checks</th>
                    <th className="cg-num-col">Latency</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>
                      <code>Tier 1</code>
                    </td>
                    <td>Deterministic AST &amp; Vision</td>
                    <td className="cg-td-muted">
                      Aho-Corasick terminology, UTS #39 confusables, CIEDE2000
                      ΔE₀₀ palette drift, WCAG 2.1 contrast, ORB logo
                      clear-space
                    </td>
                    <td className="cg-num-col">&lt; 5 ms</td>
                  </tr>
                  <tr>
                    <td>
                      <code>Tier 1.5</code>
                    </td>
                    <td>Z3 Theorem Prover (SMT)</td>
                    <td className="cg-td-muted">
                      Formal algebraic verification of loan caps, APR ceilings,
                      and CCPA drip-pricing net discount equations
                    </td>
                    <td className="cg-num-col">&lt; 25 ms</td>
                  </tr>
                  <tr>
                    <td>
                      <code>Tier 2</code>
                    </td>
                    <td>QASem Claim Slot NLI</td>
                    <td className="cg-td-muted">
                      Slot-aligned natural language inference catching omitted
                      qualifiers and substantiation gaps
                    </td>
                    <td className="cg-num-col">&lt; 120 ms</td>
                  </tr>
                  <tr>
                    <td>
                      <code>Tier 3</code>
                    </td>
                    <td>Constrained Surgical Rewriter</td>
                    <td className="cg-td-muted">
                      DPDP PII-masked span repair enforcing ≤ 35% Wagner-Fischer
                      edit distance and automatic Tier 1+2 re-verification
                    </td>
                    <td className="cg-num-col">&lt; 250 ms</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="cg-gov-card" id="workflow-matrix">
            <div className="cg-gov-card-header">
              <div>
                <h3>Three-Role Collaborative Sign-Off &amp; Audit Ledger</h3>
                <p>
                  Enforces role-based separation of duties with cognitive
                  forcing functions and an immutable RFC 9162 Merkle audit
                  trail.
                </p>
              </div>
            </div>
            <div className="cg-table-scroll">
              <table className="cg-data-table">
                <thead>
                  <tr>
                    <th>Stage</th>
                    <th>Role Owner</th>
                    <th>Governance Responsibilities &amp; Gate Rules</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>
                      <code>Stage 1</code>
                    </td>
                    <td>
                      <strong>Creator</strong> (<code>@creative_lead</code>)
                    </td>
                    <td className="cg-td-muted">
                      Uploads multimodal bundles, resolves open Blockers
                      (severity ≥ 50), and records mandatory rationale on
                      Warning overrides.
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <code>Stage 2</code>
                    </td>
                    <td>
                      <strong>Brand Manager</strong> (
                      <code>@brand_manager</code>)
                    </td>
                    <td className="cg-td-muted">
                      Reviews immutable revision diffs and override
                      justifications, calibrates playbook thresholds, and
                      approves brand readiness.
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <code>Stage 3</code>
                    </td>
                    <td>
                      <strong>Legal Reviewer</strong> (
                      <code>@legal_counsel</code>)
                    </td>
                    <td className="cg-td-muted">
                      Filters directly to factual claims, statutory disclosures,
                      and overrides; issues final sign-off to seal the Ed25519
                      certificate.
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <code>Stage 4</code>
                    </td>
                    <td>
                      <strong>Released &amp; Sealed</strong>
                    </td>
                    <td className="cg-td-muted">
                      Exports offline-verifiable RFC 9162 Merkle proof and signs
                      visual banners with outbound C2PA v2.3 provenance
                      manifests.
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
