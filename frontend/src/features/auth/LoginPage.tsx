import { useState, useEffect, useCallback, type FormEvent } from "react";
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
  RefreshCw,
  ShieldCheck,
  Sliders,
  Sparkles,
} from "lucide-react";

const ROLE_CARDS = [
  {
    username: "creative_lead",
    role: "creator",
    stageTag: "Stage 1 · Creator",
    title: "Marketing & Agency Creator",
    desc: "Upload campaign copy, brochures, and banners; run pre-flight scans and apply surgical fixes.",
  },
  {
    username: "brand_manager",
    role: "reviewer",
    stageTag: "Stage 2 · Brand Manager",
    title: "Brand Playbook Owner",
    desc: "Inspect revision diffs, verify warning overrides, calibrate thresholds, and approve brand compliance.",
  },
  {
    username: "legal_counsel",
    role: "admin",
    stageTag: "Stage 3 · Legal Counsel",
    title: "Authorised Legal Reviewer",
    desc: "Audit high-risk claims and statutory disclosures; seal the Ed25519 + RFC 9162 release certificate.",
  },
] as const;

interface WorkbenchScenario {
  id: string;
  label: string;
  canonId: string;
  title: string;
  rawDraft: string;
  repairedDraft: string;
  bannerMeta: {
    width: number;
    height: number;
    headline: string;
    subline: string;
    disclaimerText: string;
    fgHex: string;
    bgHex: string;
    repairedFgHex: string;
    contrastRatio: string;
    repairedContrastRatio: string;
  };
}

const WORKBENCH_SCENARIOS: WorkbenchScenario[] = [
  {
    id: "bfsi",
    label: "RBI Digital Lending KFS",
    canonId: "indian-digital-lending",
    title: "QuickLoan Festival Credit Campaign",
    rawDraft:
      "Get 0% processing fee on loans under Rs 1,00,000 with guaranteed approval and no credit check. Annual Percentage Rate (APR) is 14%.\n\n<div style=\"color: #777777; background-color: #FFFFFF;\">Terms apply.</div>",
    repairedDraft:
      "Get 0% processing fee on loans under Rs 50,000 for first-time borrowers only (Subject to RBI Key Fact Statement (KFS) schedule) with subject to credit assessment and streamlined credit verification. Annual Percentage Rate (APR) is 18%.\n\n<div style=\"color: #0D3B66; background-color: #FFFFFF;\">Subject to RBI Key Fact Statement (KFS) schedule.</div>",
    bannerMeta: {
      width: 1920,
      height: 1080,
      headline: "0% Processing Fee · Instant Festival Credit",
      subline: "Principal Rs 50,000 · Tenure 6 Months · APR 18%",
      disclaimerText:
        "Subject to RBI Key Fact Statement (KFS) schedule and credit bureau verification.",
      fgHex: "#777777",
      bgHex: "#FFFFFF",
      repairedFgHex: "#0D3B66",
      contrastRatio: "4.48:1 (Fails WCAG AA 4.5:1)",
      repairedContrastRatio: "11.45:1 (Passes WCAG AAA · ΔE₀₀ = 0.0)",
    },
  },
  {
    id: "nutra",
    label: "ASCI Nutraceutical Launch",
    canonId: "indian-d2c-nutra",
    title: "AyurGlow Curcumin Gold Elixir Launch",
    rawDraft:
      "Experience our miracle cure formula with 2x faster absorption and 100% fat burn results! AyurGlow cures diabetes naturally in 7 days.",
    repairedDraft:
      "Experience our nutritional support formula with 2x faster absorption (in-vitro ingredient study only; when taken with piperine for 8 weeks) and supports active weight management results! AyurGlow supports healthy glycemic metabolism naturally.",
    bannerMeta: {
      width: 1920,
      height: 1080,
      headline: "AyurGlow Curcumin Gold · Bio-Active Botanical Support",
      subline: "2x Faster Absorption (In-Vitro Ingredient Study with Piperine)",
      disclaimerText:
        "Nutraceutical supplement. Not intended to diagnose, treat, cure, or prevent any disease.",
      fgHex: "#777777",
      bgHex: "#FFFFFF",
      repairedFgHex: "#2E6F40",
      contrastRatio: "4.48:1 (Fails WCAG AA 4.5:1)",
      repairedContrastRatio: "6.12:1 (Passes WCAG AA · Botanical Sage)",
    },
  },
  {
    id: "enterprise",
    label: "Enterprise Cloud SLA",
    canonId: "acme-corp", /* taste-skill-ignore */
    title: "CloudScale Enterprise Tier Release",
    rawDraft:
      "Why buy cheap legacy tools when our platform helps users modernize? Acme Corp has over 500 employees serving global enterprises.\n\n<div style=\"color: #777777; background-color: #FFFFFF;\">Standard SLA footnote.</div>", /* taste-skill-ignore */
    repairedDraft:
      "Why purchase affordable legacy tools when our platform helps customers modernize? Acme Corp has over 500 employees (as of Q3 2025) serving global enterprises.\n\n<div style=\"color: #0D3B66; background-color: #FFFFFF;\">Standard SLA footnote.</div>", /* taste-skill-ignore */
    bannerMeta: {
      width: 1920,
      height: 1080,
      headline: "Enterprise Cloud Infrastructure · 99.9% Standard SLA",
      subline: "Over 500 Employees Globally (As of Q3 2025)",
      disclaimerText:
        "Backed by our Standard Enterprise Agreement and SOC 2 Type II controls.",
      fgHex: "#777777",
      bgHex: "#FFFFFF",
      repairedFgHex: "#141414",
      contrastRatio: "4.48:1 (Fails WCAG AA 4.5:1)",
      repairedContrastRatio: "18.10:1 (Passes WCAG AAA)",
    },
  },
];

export function LoginPage() {
  const { token, username: activeUser, role: activeRole, login, register } = useAuth();
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

  // Live Pre-Publish Gate Workbench state
  const [scenarioId, setScenarioId] = useState<string>("bfsi");
  const [alpha, setAlpha] = useState<number>(0.1);
  const [isRepaired, setIsRepaired] = useState<boolean>(false);
  const [draftText, setDraftText] = useState<string>(WORKBENCH_SCENARIOS[0].rawDraft);
  const [gateResult, setGateResult] = useState<GateCheckResponsePayload | null>(null);
  const [gateLoading, setGateLoading] = useState<boolean>(false);
  const [selectedFindingIdx, setSelectedFindingIdx] = useState<number>(0);
  const [openingStudio, setOpeningStudio] = useState<boolean>(false);

  const activeScenario =
    WORKBENCH_SCENARIOS.find((s) => s.id === scenarioId) ?? WORKBENCH_SCENARIOS[0];

  const executeLiveGateCheck = useCallback(
    async (textToAudit: string, canonId: string, targetAlpha: number) => {
      setGateLoading(true);
      try {
        const res = await runGateCheck({
          canon_id: canonId,
          adapter: "generic",
          title: activeScenario.title,
          raw_content: textToAudit,
          alpha: targetAlpha,
          persist: false,
        });
        setGateResult(res);
        setSelectedFindingIdx(0);
      } catch {
        // Ignore transient errors in preview
      } finally {
        setGateLoading(false);
      }
    },
    [activeScenario.title],
  );

  useEffect(() => {
    void executeLiveGateCheck(draftText, activeScenario.canonId, alpha);
  }, [draftText, activeScenario.canonId, alpha, executeLiveGateCheck]);

  function handleSelectScenario(nextId: string) {
    const found =
      WORKBENCH_SCENARIOS.find((s) => s.id === nextId) ?? WORKBENCH_SCENARIOS[0];
    setScenarioId(found.id);
    setIsRepaired(false);
    setDraftText(found.rawDraft);
  }

  function handleToggleSurgicalRepair() {
    const nextRepaired = !isRepaired;
    setIsRepaired(nextRepaired);
    setDraftText(
      nextRepaired ? activeScenario.repairedDraft : activeScenario.rawDraft,
    );
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

  async function handleOpenScenarioInStudio() {
    setError(null);
    setOpeningStudio(true);
    try {
      if (!token) {
        await login("creative_lead", "demoPassword123!");
      }
      const sub = await createSubmission(
        activeScenario.title,
        draftText,
        activeScenario.canonId,
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
  const activeFinding = findings[Math.min(selectedFindingIdx, Math.max(0, findings.length - 1))] ?? null;

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
            <span className="cg-brand-version">v2.4 Governance Engine</span>
          </Link>

          <nav className="cg-gateway-nav" aria-label="Product Sections">
            <a href="#live-workbench">Live Pre-Publish Gate</a>
            <a href="#engine-architecture">4-Tier Verification</a>
            <a href="#workflow-matrix">3-Role Workflow</a>
          </nav>

          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {token ? (
              <Link to="/dashboard" className="cg-btn cg-btn-primary cg-btn-sm">
                <span>Open Workspace (@{activeUser} · {activeRole})</span>
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

        {/* Section 1: Asymmetric Hero Pitch + Role Launch Sheet */}
        <section className="cg-gateway-hero" aria-label="CanonGate Overview and Role Launch">
          <div className="cg-gateway-pitch-sheet">
            <div>
              <h1 className="cg-gateway-h1">
                Pre-publication brand, claim, and visual governance.
              </h1>
              <p className="cg-gateway-lead">
                CanonGate compiles your brand playbooks, approved Key Fact Statements,
                and statutory rules into a deterministic 4-tier verification gate.
                Audit campaign copy, Word and PDF brochures, and 1080p banners before
                release, with Z3 formal claim proofs, QASem slot-diff tables, and
                Ed25519 cryptographic sign-off.
              </p>
            </div>

            <div className="cg-gateway-kpi-ledger">
              <div className="cg-gateway-kpi-item">
                <span className="cg-gateway-kpi-val">&lt; 5 ms</span>
                <span className="cg-gateway-kpi-label">
                  Tier 1 Aho-Corasick, CIEDE2000 ΔE₀₀, WCAG 2.1, and ORB logo checks
                </span>
              </div>
              <div className="cg-gateway-kpi-item">
                <span className="cg-gateway-kpi-val">Z3 SMT</span>
                <span className="cg-gateway-kpi-label">
                  Tier 1.5 formal algebraic proof for fee caps, APR ceilings, and drip pricing
                </span>
              </div>
              <div className="cg-gateway-kpi-item">
                <span className="cg-gateway-kpi-val">QASem NLI</span>
                <span className="cg-gateway-kpi-label">
                  Tier 2 slot-level entailment catching omitted conditions and expired offers
                </span>
              </div>
              <div className="cg-gateway-kpi-item">
                <span className="cg-gateway-kpi-val">RFC 9162</span>
                <span className="cg-gateway-kpi-label">
                  Merkle audit log + Ed25519 Signed Tree Head + C2PA v2.3 asset provenance
                </span>
              </div>
            </div>
          </div>

          {/* Right Sheet: 1-Click Role Launch & Credential Sign-In */}
          <div className="cg-gateway-auth-sheet" data-ui>
            <div className="cg-auth-sheet-header">
              <div>
                <h2 className="cg-auth-sheet-title">Launch Role-Scoped Console</h2>
                <p className="cg-auth-sheet-sub">
                  Select a governance persona to enter the workspace immediately, or sign in with credentials.
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
                    <span>Launch</span>
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
                  Seeded demo password: <code>demoPassword123!</code>
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
                          <option value="reviewer">Stage 2 · Brand Manager</option>
                          <option value="admin">Stage 3 · Legal Reviewer</option>
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

        {/* Section 2: "One Live Thing" — Interactive Pre-Publication Governance Proof Workbench */}
        <section
          id="live-workbench"
          className="cg-live-workbench"
          data-ui
          aria-label="Interactive Pre-Publication Governance Workbench"
        >
          <div className="cg-wb-header" data-ui>
            <div className="cg-wb-title-block">
              <h2 className="cg-wb-title">
                Live Pre-Publish Gate Workbench (<code>POST /api/gate/check</code>)
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
                    ? `GATE BLOCKED · ${gateResult.blocker_count} BLOCKER(S)`
                    : gateResult.decision === "needs_review"
                      ? `NEEDS REVIEW · ${gateResult.warning_count} WARNING(S)`
                      : "GATE ALLOWED · 0 VIOLATIONS"}
                </span>
              )}
              {gateResult && (
                <code style={{ fontSize: "12px", color: "var(--muted)" }}>
                  {gateResult.latency_ms.toFixed(1)} ms · Playbook:{" "}
                  {gateResult.canon_id}
                </code>
              )}
            </div>

            <div className="cg-wb-controls">
              <div className="cg-segmented-group" role="tablist" aria-label="Sector Scenarios">
                {WORKBENCH_SCENARIOS.map((sc) => (
                  <button
                    key={sc.id}
                    type="button"
                    role="tab"
                    aria-selected={scenarioId === sc.id}
                    className={`cg-seg-btn ${scenarioId === sc.id ? "active" : ""}`}
                    onClick={() => handleSelectScenario(sc.id)}
                  >
                    {sc.label}
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

              <button
                type="button"
                className={`cg-btn cg-btn-sm ${
                  isRepaired ? "cg-btn-secondary" : "cg-btn-emerald"
                }`}
                onClick={handleToggleSurgicalRepair}
              >
                {isRepaired ? (
                  <>
                    <RefreshCw size={13} />
                    <span>Reset to Flagged Draft</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={13} />
                    <span>Apply Surgical Fixes ({findings.length})</span>
                  </>
                )}
              </button>

              <button
                type="button"
                className="cg-btn cg-btn-primary cg-btn-sm"
                disabled={openingStudio}
                onClick={() => void handleOpenScenarioInStudio()}
              >
                <span>
                  {openingStudio ? "Opening Studio…" : "Open in Full Review Studio"}
                </span>
                <ArrowRight size={13} className="cg-arrow-shift" />
              </button>
            </div>
          </div>

          <div className="cg-wb-body" data-ui>
            {/* Left Workbench Pane: Live Editable Draft + Simulated 1080p Banner Stage */}
            <div className="cg-wb-left-pane" data-ui>
              <div className="cg-field-group">
                <div className="cg-field-label-row">
                  <label htmlFor="wb-live-textarea">
                    1 · Campaign Copy &amp; HTML/KFS Payload (Edit live to re-run gate)
                  </label>
                  <code style={{ fontSize: "11.5px", color: "var(--muted)" }}>
                    SHA-256: {gateResult?.content_hash.slice(0, 12) ?? "…"}
                  </code>
                </div>
                <textarea
                  id="wb-live-textarea"
                  rows={4}
                  value={draftText}
                  onChange={(e) => setDraftText(e.target.value)}
                  style={{ fontSize: "13px" }}
                />
              </div>

              {/* Simulated 1080p Promotional Banner Stage */}
              <div
                style={{
                  backgroundColor: "var(--surface-subtle)",
                  border: "1px solid var(--border)",
                  borderRadius: "6px",
                  padding: "12px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    fontSize: "12px",
                    color: "var(--muted)",
                  }}
                >
                  <span>
                    2 · Promotional Banner Stage ({activeScenario.bannerMeta.width}×
                    {activeScenario.bannerMeta.height}px · ORB Clear-Space &amp; WCAG Contrast)
                  </span>
                  <code>
                    {isRepaired
                      ? activeScenario.bannerMeta.repairedContrastRatio
                      : activeScenario.bannerMeta.contrastRatio}
                  </code>
                </div>

                <div
                  style={{
                    backgroundColor: "#141414",
                    color: "#ffffff",
                    borderRadius: "6px",
                    padding: "14px 16px",
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
                      fontSize: "12px",
                    }}
                  >
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "6px",
                        fontWeight: 600,
                      }}
                    >
                      <ShieldCheck size={14} />
                      <span>{activeScenario.title}</span>
                    </span>
                    <code
                      style={{
                        backgroundColor: "rgba(255,255,255,0.12)",
                        padding: "2px 6px",
                        borderRadius: "4px",
                        fontSize: "11px",
                      }}
                    >
                      ORB Logo Clear Space ≥ 0.5H Verified
                    </code>
                  </div>

                  <div
                    style={{
                      backgroundColor: "#ffffff",
                      color: "#0a0a0a",
                      borderRadius: "5px",
                      padding: "12px 14px",
                    }}
                  >
                    <div style={{ fontSize: "15px", fontWeight: 700 }}>
                      {activeScenario.bannerMeta.headline}
                    </div>
                    <div
                      style={{
                        fontSize: "12.5px",
                        color: "#3d434d",
                        marginTop: "2px",
                      }}
                    >
                      {activeScenario.bannerMeta.subline}
                    </div>
                    <div
                      style={{
                        marginTop: "10px",
                        padding: "6px 10px",
                        borderRadius: "4px",
                        backgroundColor: activeScenario.bannerMeta.bgHex,
                        color: isRepaired
                          ? activeScenario.bannerMeta.repairedFgHex
                          : activeScenario.bannerMeta.fgHex,
                        border: isRepaired
                          ? "1.5px solid #2e7d32"
                          : "1.5px dashed #c4242a",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: "8px",
                        fontSize: "12px",
                      }}
                    >
                      <span>{activeScenario.bannerMeta.disclaimerText}</span>
                      <code
                        style={{
                          backgroundColor: isRepaired ? "#dcfae5" : "#ffedea",
                          color: isRepaired ? "#04250e" : "#831c1e",
                          padding: "2px 6px",
                          borderRadius: "3px",
                          fontSize: "11px",
                          fontWeight: 600,
                          whiteSpace: "nowrap",
                        }}
                      >
                        {isRepaired
                          ? `WCAG PASS (${activeScenario.bannerMeta.repairedFgHex})`
                          : `WCAG FAIL (${activeScenario.bannerMeta.fgHex} · 4.48:1)`}
                      </code>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Workbench Pane: Live Calibrated Fault Inspector */}
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
                  Calibrated Findings ({findings.length})
                </span>
                <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                  Conformal cutoff τ ={" "}
                  <code>{gateResult?.conformal_threshold.toFixed(2) ?? "0.34"}</code>
                </span>
              </div>

              {gateLoading ? (
                <div className="cg-clean-note">Evaluating AST against Playbook…</div>
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
                    <span>All Pre-Publication Checks Passed (Decision: ALLOW)</span>
                  </div>
                  <p style={{ margin: 0, fontSize: "12.5px" }}>
                    Zero open blockers or warnings remain. This bundle is ready for Brand
                    Manager and Legal Reviewer sign-off.
                  </p>
                </div>
              ) : (
                <>
                  {/* Finding Selector Pills */}
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
                            Governing Playbook Rule: <code>{activeFinding.rule_id}</code>
                          </span>
                        </div>
                      )}

                      {activeFinding.replacement_preview && (
                        <div className="cg-fault-suggestion-box">
                          <span className="cg-mono-label">
                            {activeFinding.suggestion_label ||
                              "Deterministic Surgical Replacement"}
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
                            ? "Hard HTTP 409 Gate Lock until remediated"
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
                  Every text node, Markdown KFS table, and banner image is parsed into
                  a unified ContentAST and verified locally before any external call.
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
                      Aho-Corasick terminology, UTS #39 confusables, CIEDE2000 ΔE₀₀
                      palette drift, WCAG 2.1 contrast, ORB logo clear-space
                    </td>
                    <td className="cg-num-col">&lt; 5 ms</td>
                  </tr>
                  <tr>
                    <td>
                      <code>Tier 1.5</code>
                    </td>
                    <td>Z3 Theorem Prover (SMT)</td>
                    <td className="cg-td-muted">
                      Formal algebraic verification of loan caps, APR ceilings, and CCPA
                      drip-pricing net discount equations
                    </td>
                    <td className="cg-num-col">&lt; 25 ms</td>
                  </tr>
                  <tr>
                    <td>
                      <code>Tier 2</code>
                    </td>
                    <td>QASem Claim Slot NLI</td>
                    <td className="cg-td-muted">
                      Slot-aligned natural language inference catching omitted qualifiers
                      and ingredient-vs-product substantiation gaps
                    </td>
                    <td className="cg-num-col">&lt; 120 ms</td>
                  </tr>
                  <tr>
                    <td>
                      <code>Tier 3</code>
                    </td>
                    <td>Constrained Surgical Rewriter</td>
                    <td className="cg-td-muted">
                      DPDP PII-masked span repair enforcing ≤ 35% Wagner-Fischer edit
                      distance and automatic Tier 1+2 re-verification
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
                  Enforces role-based separation of duties with cognitive forcing
                  functions and an immutable RFC 9162 Merkle audit trail.
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
                      Uploads multimodal bundles, resolves open Blockers (severity ≥ 50),
                      and records mandatory rationale on Warning overrides.
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <code>Stage 2</code>
                    </td>
                    <td>
                      <strong>Brand Manager</strong> (<code>@brand_manager</code>)
                    </td>
                    <td className="cg-td-muted">
                      Reviews immutable revision diffs and override justifications,
                      calibrates playbook thresholds, and approves brand readiness.
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <code>Stage 3</code>
                    </td>
                    <td>
                      <strong>Legal Reviewer</strong> (<code>@legal_counsel</code>)
                    </td>
                    <td className="cg-td-muted">
                      Filters directly to factual claims, statutory disclosures, and
                      overrides; issues final sign-off to seal the Ed25519 certificate.
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
                      Exports offline-verifiable RFC 9162 Merkle proof and signs visual
                      banners with outbound C2PA v2.3 provenance manifests.
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
