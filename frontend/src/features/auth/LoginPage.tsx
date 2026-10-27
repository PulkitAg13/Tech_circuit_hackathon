import { useState, useEffect, type FormEvent } from "react";
import { useAuth } from "./context";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import {
  ShieldCheck,
  Lock,
  User,
  KeyRound,
  ArrowRight,
  CheckCircle2,
  Briefcase,
  Cpu,
  FileCheck2,
  Layers,
  Play,
} from "lucide-react";

const ROLE_OPTIONS = [
  {
    value: "creator",
    stage: "STAGE 01",
    label: "Creator (Marketing / Agency Author)",
    desc: "Uploads campaign bundles, runs pre-flight checks, fixes Blockers, and documents context on Warning overrides.",
  },
  {
    value: "reviewer",
    stage: "STAGE 02",
    label: "Brand Manager (Playbook & Brand Review)",
    desc: "Ingests & calibrates Brand Playbooks, reviews revision diffs & overrides, and approves brand compliance.",
  },
  {
    value: "admin",
    stage: "STAGE 03",
    label: "Authorised Legal Reviewer (Compliance Sign-Off)",
    desc: "Audits statutory SlotDiff claims & Merkle ledger to execute final legal sign-off and C2PA release.",
  },
] as const;

const DEMO_ACCOUNTS = [
  {
    username: "creative_lead",
    role: "creator",
    stage: "STAGE 01",
    title: "Creator Workspace",
    handle: "@creative_lead",
    summary: "Draft pre-flight, surgical copy repair & WCAG swatch fixes",
  },
  {
    username: "brand_manager",
    role: "reviewer",
    stage: "STAGE 02",
    title: "Brand Manager Console",
    handle: "@brand_manager",
    summary: "Playbook calibration, override review & v1.1 PR generation",
  },
  {
    username: "legal_counsel",
    role: "admin",
    stage: "STAGE 03",
    title: "Legal Counsel Sign-Off",
    handle: "@legal_counsel",
    summary: "Statutory KFS/ASCI audit, final release & Merkle certificate",
  },
] as const;

export function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedRole = searchParams.get("role");
  const redirectPath = searchParams.get("redirect") || "/dashboard";

  // Mode: Sign In vs Create Account
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signin");

  // Sign In state
  const [signInUsername, setSignInUsername] = useState("creative_lead");
  const [signInPassword, setSignInPassword] = useState("demoPassword123!");

  // Sign Up state
  const [signUpName, setSignUpName] = useState("");
  const [signUpUsername, setSignUpUsername] = useState("");
  const [signUpPassword, setSignUpPassword] = useState("");
  const [signUpRole, setSignUpRole] = useState<string>("creator");

  // UI state
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [quickLaunchingUser, setQuickLaunchingUser] = useState<string | null>(
    null,
  );

  useEffect(() => {
    if (requestedRole) {
      const matched = DEMO_ACCOUNTS.find((a) => a.role === requestedRole);
      if (matched) {
        setSignInUsername(matched.username);
        setSignInPassword("demoPassword123!");
      }
      setSignUpRole(requestedRole);
    }
  }, [requestedRole]);

  async function handleSignIn(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(signInUsername.trim(), signInPassword);
      navigate(redirectPath);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSignUp(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await register(
        signUpUsername.trim(),
        signUpPassword,
        signUpRole,
        signUpName.trim() || signUpUsername.trim(),
      );
      navigate(redirectPath);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleInstantDemoLaunch(acctUsername: string) {
    setError(null);
    setSignInUsername(acctUsername);
    setSignInPassword("demoPassword123!");
    setQuickLaunchingUser(acctUsername);
    try {
      await login(acctUsername, "demoPassword123!");
      navigate(redirectPath);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setQuickLaunchingUser(null);
    }
  }

  return (
    <div className="cg-auth-shell">
      {/* Top Architectural Bar */}
      <header className="cg-topbar">
        <div className="cg-topbar-inner">
          <div className="cg-topbar-left">
            <Link to="/" className="cg-brand">
              <span className="cg-brand-mark" aria-hidden="true">
                <ShieldCheck size={17} strokeWidth={2.2} />
              </span>
              <span className="cg-brand-name">CanonGate</span>
              <span className="cg-brand-version">RBAC Gateway</span>
            </Link>
          </div>
          <div className="cg-topbar-right">
            <Link to="/" className="cg-btn cg-btn-ghost">
              ← Back to Product Overview
            </Link>
          </div>
        </div>
      </header>

      {/* Main Split Gateway */}
      <main className="cg-auth-main">
        <div className="cg-auth-grid">
          {/* Left Column: 1-Click Role Sandbox + Credential Form */}
          <section className="cg-auth-card">
            {/* 1-Click Role Persona Quick-Launch Section */}
            <div className="cg-auth-quicklaunch">
              <div className="cg-auth-quicklaunch-top">
                <span className="cg-mono-label">
                  INSTANT DEMO WORKSPACE ACCESS (1-CLICK LAUNCH)
                </span>
                <span className="cg-auth-quicklaunch-badge">
                  Zero-Config Seeded Accounts
                </span>
              </div>
              <p className="cg-auth-quicklaunch-desc">
                Select any role below to enter the live governance console
                immediately, or use the credential form underneath.
              </p>

              <div className="cg-auth-persona-grid">
                {DEMO_ACCOUNTS.map((acct) => {
                  const isSelected = signInUsername === acct.username;
                  const isLaunching = quickLaunchingUser === acct.username;
                  return (
                    <button
                      key={acct.username}
                      type="button"
                      disabled={loading || quickLaunchingUser !== null}
                      className={`cg-auth-persona-card ${
                        isSelected ? "active" : ""
                      }`}
                      onClick={() =>
                        void handleInstantDemoLaunch(acct.username)
                      }
                    >
                      <div className="cg-auth-persona-header">
                        <span className="cg-role-stage-tag">{acct.stage}</span>
                        <code>{acct.handle}</code>
                      </div>
                      <div className="cg-auth-persona-title">
                        <span>
                          {isLaunching ? "Signing in…" : acct.title}
                        </span>
                        <Play size={12} className="cg-arrow-shift" />
                      </div>
                      <p className="cg-auth-persona-sub">{acct.summary}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="cg-auth-divider">
              <span>OR SIGN IN / REGISTER WITH CREDENTIALS</span>
            </div>

            {/* Segmented Mode Switcher */}
            <div className="cg-auth-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={authMode === "signin"}
                className={`cg-auth-tab ${
                  authMode === "signin" ? "active" : ""
                }`}
                onClick={() => {
                  setError(null);
                  setAuthMode("signin");
                }}
              >
                Sign In to Existing Account
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={authMode === "signup"}
                className={`cg-auth-tab ${
                  authMode === "signup" ? "active" : ""
                }`}
                onClick={() => {
                  setError(null);
                  setAuthMode("signup");
                }}
              >
                Create New Role Account
              </button>
            </div>

            {error && (
              <div className="cg-auth-error" role="alert">
                <span>{error}</span>
              </div>
            )}

            {authMode === "signin" ? (
              <form
                key="signin-form"
                className="cg-auth-form cg-animate-swap"
                onSubmit={handleSignIn}
              >
                <div className="cg-field-group">
                  <label htmlFor="username">Username</label>
                  <div className="cg-input-with-icon">
                    <User size={15} className="cg-field-icon" />
                    <input
                      id="username"
                      type="text"
                      value={signInUsername}
                      onChange={(e) => setSignInUsername(e.target.value)}
                      placeholder="e.g. creative_lead"
                      required
                      autoComplete="username"
                    />
                  </div>
                </div>

                <div className="cg-field-group">
                  <div className="cg-field-label-row">
                    <label htmlFor="password">Password</label>
                    <span className="cg-field-hint">
                      Demo password: <code>demoPassword123!</code>
                    </span>
                  </div>
                  <div className="cg-input-with-icon">
                    <KeyRound size={15} className="cg-field-icon" />
                    <input
                      id="password"
                      type="password"
                      value={signInPassword}
                      onChange={(e) => setSignInPassword(e.target.value)}
                      placeholder="Enter your password"
                      required
                      autoComplete="current-password"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  className="cg-btn cg-btn-primary cg-btn-full cg-btn-lg"
                  disabled={loading || quickLaunchingUser !== null}
                >
                  <span>
                    {loading ? "Authenticating…" : "Sign In to Governance Console"}
                  </span>
                  <ArrowRight size={16} className="cg-arrow-shift" />
                </button>
              </form>
            ) : (
              <form
                key="signup-form"
                className="cg-auth-form cg-animate-swap"
                onSubmit={handleSignUp}
              >
                <div className="cg-field-row-2">
                  <div className="cg-field-group">
                    <label htmlFor="signup-name">Full Name</label>
                    <div className="cg-input-with-icon">
                      <User size={15} className="cg-field-icon" />
                      <input
                        id="signup-name"
                        type="text"
                        placeholder="e.g. Kabir Roy"
                        value={signUpName}
                        onChange={(e) => setSignUpName(e.target.value)}
                        required
                      />
                    </div>
                  </div>

                  <div className="cg-field-group">
                    <label htmlFor="signup-username">Username</label>
                    <div className="cg-input-with-icon">
                      <Lock size={15} className="cg-field-icon" />
                      <input
                        id="signup-username"
                        type="text"
                        placeholder="e.g. kabir_roy"
                        value={signUpUsername}
                        onChange={(e) => setSignUpUsername(e.target.value)}
                        required
                        autoComplete="username"
                      />
                    </div>
                  </div>
                </div>

                <div className="cg-field-group">
                  <label htmlFor="signup-role">Assigned Governance Role</label>
                  <div className="cg-input-with-icon">
                    <Briefcase size={15} className="cg-field-icon" />
                    <select
                      id="signup-role"
                      aria-label="Governance Role"
                      value={signUpRole}
                      onChange={(e) => setSignUpRole(e.target.value)}
                    >
                      {ROLE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.stage} · {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <p className="cg-field-help">
                    {ROLE_OPTIONS.find((r) => r.value === signUpRole)?.desc}
                  </p>
                </div>

                <div className="cg-field-group">
                  <label htmlFor="signup-password">Password</label>
                  <div className="cg-input-with-icon">
                    <KeyRound size={15} className="cg-field-icon" />
                    <input
                      id="signup-password"
                      type="password"
                      placeholder="Create a strong password"
                      value={signUpPassword}
                      onChange={(e) => setSignUpPassword(e.target.value)}
                      required
                      autoComplete="new-password"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  className="cg-btn cg-btn-primary cg-btn-full cg-btn-lg"
                  disabled={loading}
                >
                  <span>
                    {loading
                      ? "Creating Account…"
                      : "Register & Enter Governance Studio"}
                  </span>
                  <ArrowRight size={16} className="cg-arrow-shift" />
                </button>
              </form>
            )}
          </section>

          {/* Right Column: Architectural RBAC & Cryptographic Workflow Spec */}
          <aside className="cg-auth-spec-panel">
            <div className="cg-auth-spec-top">
              <span className="cg-mono-label" style={{ color: "#38BDF8" }}>
                TAMPER-EVIDENT ROLE SEPARATION
              </span>
              <h2>4-Stage Collaborative Pre-Publish Gate</h2>
              <p>
                Every action in CanonGate is bound to an authenticated RBAC
                identity and recorded in an append-only RFC 9162 SHA-256 Merkle
                audit tree.
              </p>
            </div>

            <div className="cg-auth-stage-list">
              <div className="cg-auth-stage-item">
                <span className="cg-auth-stage-num">01</span>
                <div>
                  <strong>Creator Pre-Flight (@creative_lead)</strong>
                  <p>
                    Runs Tier 1–2 checks, applies ≤35% surgical rewrites and
                    WCAG contrast swatches, and documents warning overrides.
                  </p>
                </div>
              </div>

              <div className="cg-auth-stage-item">
                <span className="cg-auth-stage-num">02</span>
                <div>
                  <strong>Brand Governance (@brand_manager)</strong>
                  <p>
                    Reviews inline ProseMirror diffs and banner bounding boxes,
                    calibrates rule thresholds, and approves brand compliance.
                  </p>
                </div>
              </div>

              <div className="cg-auth-stage-item">
                <span className="cg-auth-stage-num">03</span>
                <div>
                  <strong>Legal &amp; Statutory Sign-Off (@legal_counsel)</strong>
                  <p>
                    Verifies QASem SlotDiff claims, Z3 KFS APR math, and
                    mandatory statutory disclosures to issue final release.
                  </p>
                </div>
              </div>

              <div className="cg-auth-stage-item">
                <span className="cg-auth-stage-num">04</span>
                <div>
                  <strong>Cryptographic Release Seal (Ed25519 + C2PA 2.2)</strong>
                  <p>
                    Generates a self-contained JSON certificate verifiable
                    offline via <code>uv run canongate verify cert.json</code>.
                  </p>
                </div>
              </div>
            </div>

            <div className="cg-auth-spec-footer">
              <div className="cg-auth-spec-pill">
                <Cpu size={14} />
                <span>100% Local Tier 1 &amp; 1.5 Math</span>
              </div>
              <div className="cg-auth-spec-pill">
                <Layers size={14} />
                <span>DPDP 2023 PII Vault</span>
              </div>
              <div className="cg-auth-spec-pill">
                <FileCheck2 size={14} />
                <span>In-Session Role Switcher Ready</span>
              </div>
              <div className="cg-auth-spec-pill">
                <CheckCircle2 size={14} />
                <span>RFC 9162 Merkle Proofs</span>
              </div>
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
