import { useState, useEffect, type FormEvent } from "react";
import { useAuth } from "./context";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import {
  ShieldCheck,
  Lock,
  User,
  KeyRound,
  ArrowRight,
  Sparkles,
  CheckCircle2,
  Briefcase,
} from "lucide-react";

const ROLE_OPTIONS = [
  {
    value: "creator",
    label: "Creator (Marketing / Agency Author)",
    desc: "Uploads campaign bundles, runs pre-flight checks, fixes Blockers, and justifies Warning overrides.",
  },
  {
    value: "reviewer",
    label: "Brand Manager (Playbook & Brand Review)",
    desc: "Ingests & calibrates Brand Playbooks, reviews revision diffs & overrides, and approves brand compliance.",
  },
  {
    value: "admin",
    label: "Authorised Legal Reviewer (Compliance Sign-Off)",
    desc: "Audits statutory SlotDiff claims & Merkle ledger to execute final legal sign-off and C2PA release.",
  },
] as const;

const DEMO_ACCOUNTS = [
  {
    username: "creative_lead",
    role: "creator",
    label: "1 · Creator Account (@creative_lead)",
    roleBadge: "Creator",
  },
  {
    username: "brand_manager",
    role: "reviewer",
    label: "2 · Brand Manager (@brand_manager)",
    roleBadge: "Brand Manager",
  },
  {
    username: "legal_counsel",
    role: "admin",
    label: "3 · Legal Reviewer (@legal_counsel)",
    roleBadge: "Legal Sign-Off",
  },
] as const;

export function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedRole = searchParams.get("role");
  const redirectPath = searchParams.get("redirect") || "/dashboard";

  // Sign In state
  const [signInUsername, setSignInUsername] = useState("");
  const [signInPassword, setSignInPassword] = useState("");

  // Sign Up state
  const [signUpName, setSignUpName] = useState("");
  const [signUpUsername, setSignUpUsername] = useState("");
  const [signUpPassword, setSignUpPassword] = useState("");
  const [signUpRole, setSignUpRole] = useState<string>("creator");

  // UI state
  const [isRightPanelActive, setIsRightPanelActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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

  function fillDemoAccount(username: string) {
    setIsRightPanelActive(false);
    setSignInUsername(username);
    setSignInPassword("demoPassword123!");
    setError(null);
  }

  return (
    <div className="login-page-sliding">
      {/* Top Navbar */}
      <nav className="sliding-top-nav">
        <Link to="/" className="sliding-brand-link">
          <div className="brand-logo-mark">
            <ShieldCheck size={20} strokeWidth={2.3} />
          </div>
          <div className="sliding-brand-text">
            <span className="sliding-brand-name">CanonGate</span>
            <span className="sliding-brand-tag">Governance Studio</span>
          </div>
        </Link>
        <Link to="/" className="sliding-back-link">
          ← Back to Home
        </Link>
      </nav>

      {/* Main Sliding Container */}
      <div
        className={`sliding-auth-container ${
          isRightPanelActive ? "right-panel-active" : ""
        }`}
      >
        {/* Sign Up Form Container */}
        <div className="sliding-form-container sign-up-container">
          <form className="sliding-auth-form" onSubmit={handleSignUp}>
            <span className="sliding-form-eyebrow">
              <Sparkles size={13} /> Role-Gated Governance Access
            </span>
            <h1 className="sliding-form-title">Create Account</h1>
            <p className="sliding-form-subtitle">
              Register your identity and select your assigned governance role in
              the 4-stage review workflow
            </p>

            {error && isRightPanelActive && (
              <div className="sliding-form-error" role="alert">
                {error}
              </div>
            )}

            <div className="sliding-input-group">
              <div className="sliding-input-wrapper">
                <User size={16} className="sliding-input-icon" />
                <input
                  id="signup-name"
                  type="text"
                  placeholder="Full Name (e.g. Kabir Roy)"
                  value={signUpName}
                  onChange={(e) => setSignUpName(e.target.value)}
                  required
                />
              </div>
              <div className="sliding-input-wrapper">
                <Lock size={16} className="sliding-input-icon" />
                <input
                  id="signup-username"
                  type="text"
                  placeholder="Username (e.g. kabir_roy)"
                  value={signUpUsername}
                  onChange={(e) => setSignUpUsername(e.target.value)}
                  required
                  autoComplete="username"
                />
              </div>
              <div className="sliding-input-wrapper">
                <Briefcase size={16} className="sliding-input-icon" />
                <select
                  id="signup-role"
                  aria-label="Governance Role"
                  value={signUpRole}
                  onChange={(e) => setSignUpRole(e.target.value)}
                  className="sliding-role-select"
                >
                  {ROLE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="sliding-input-wrapper">
                <KeyRound size={16} className="sliding-input-icon" />
                <input
                  id="signup-password"
                  type="password"
                  placeholder="Password"
                  value={signUpPassword}
                  onChange={(e) => setSignUpPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                />
              </div>
            </div>

            <p className="sliding-role-hint">
              {ROLE_OPTIONS.find((r) => r.value === signUpRole)?.desc}
            </p>

            <button
              type="submit"
              className="sliding-submit-btn"
              disabled={loading}
            >
              {loading ? "Creating Account..." : "Register & Enter Studio"}
              <ArrowRight size={16} />
            </button>
          </form>
        </div>

        {/* Sign In Form Container */}
        <div className="sliding-form-container sign-in-container">
          <form className="sliding-auth-form" onSubmit={handleSignIn}>
            <span className="sliding-form-eyebrow">
              <CheckCircle2 size={13} /> Pre-Publication Gate
            </span>
            <h1 className="sliding-form-title">Sign In</h1>
            <p className="sliding-form-subtitle">
              Each account is bound to its assigned role (Creator, Brand
              Manager, or Authorised Legal Reviewer) for tamper-evident RBAC
              accountability
            </p>

            {error && !isRightPanelActive && (
              <div className="sliding-form-error" role="alert">
                {error}
              </div>
            )}

            <div className="sliding-input-group">
              <div className="sliding-input-wrapper">
                <User size={16} className="sliding-input-icon" />
                <input
                  id="username"
                  type="text"
                  placeholder="Username"
                  value={signInUsername}
                  onChange={(e) => setSignInUsername(e.target.value)}
                  required
                  autoComplete="username"
                />
              </div>
              <div className="sliding-input-wrapper">
                <KeyRound size={16} className="sliding-input-icon" />
                <input
                  id="password"
                  type="password"
                  placeholder="Password"
                  value={signInPassword}
                  onChange={(e) => setSignInPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
              </div>
            </div>

            <div className="demo-accounts-bar">
              <span className="demo-accounts-label">
                Select Role Account to Sign In:
              </span>
              <div className="demo-accounts-chips">
                {DEMO_ACCOUNTS.map((acct) => (
                  <button
                    key={acct.username}
                    type="button"
                    className={`demo-account-chip ${
                      signInUsername === acct.username ? "active" : ""
                    }`}
                    onClick={() => fillDemoAccount(acct.username)}
                    title={`Fill credentials for @${acct.username} (${acct.roleBadge})`}
                  >
                    {acct.label}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="submit"
              className="sliding-submit-btn"
              disabled={loading}
            >
              {loading ? "Signing In..." : "Sign In to Console"}
              <ArrowRight size={16} />
            </button>
          </form>
        </div>

        {/* Sliding Overlay Container */}
        <div className="sliding-overlay-container">
          <div className="sliding-overlay">
            {/* Left Overlay Panel (Shown when Sign Up is active) */}
            <div className="sliding-overlay-panel sliding-overlay-left">
              <div className="overlay-badge">EXISTING TEAM MEMBER</div>
              <h2 className="sliding-overlay-title">Welcome Back!</h2>
              <p className="sliding-overlay-text">
                Already have a Creator, Brand Manager, or Legal Reviewer
                account? Sign in with your credentials to access your campaign
                queue and audit ledger.
              </p>
              <button
                type="button"
                className="sliding-ghost-btn"
                onClick={() => {
                  setError(null);
                  setIsRightPanelActive(false);
                }}
              >
                Sign In
              </button>
            </div>

            {/* Right Overlay Panel (Shown when Sign In is active) */}
            <div className="sliding-overlay-panel sliding-overlay-right">
              <div className="overlay-badge">4-STAGE COLLABORATIVE GATE</div>
              <h2 className="sliding-overlay-title">New to CanonGate?</h2>
              <p className="sliding-overlay-text">
                Create an account and choose your assigned role — Creator, Brand
                Manager, or Authorised Legal Reviewer — to collaborate on
                pre-publication governance.
              </p>
              <button
                type="button"
                className="sliding-ghost-btn"
                onClick={() => {
                  setError(null);
                  setIsRightPanelActive(true);
                }}
              >
                Create Account
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
