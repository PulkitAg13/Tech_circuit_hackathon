import { useState, type FormEvent } from "react";
import { useAuth } from "./context";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ShieldCheck,
  Lock,
  User,
  KeyRound,
  ArrowRight,
  Briefcase,
  Play,
} from "lucide-react";

const ROLE_OPTIONS = [
  {
    value: "creator",
    stage: "STAGE 01",
    label: "Creator (Marketing / Agency Author)",
    desc: "Uploads campaign bundles, runs pre-flight checks, fixes Blockers, and documents warning overrides.",
  },
  {
    value: "reviewer",
    stage: "STAGE 02",
    label: "Brand Manager (Playbook & Brand Review)",
    desc: "Manages brand playbooks, reviews revision diffs and warning overrides, and approves brand compliance.",
  },
  {
    value: "admin",
    stage: "STAGE 03",
    label: "Authorised Legal Reviewer (Compliance Sign-Off)",
    desc: "Audits statutory claims and ledger proofs to execute final legal sign-off and release.",
  },
] as const;

const DEMO_ACCOUNTS = [
  {
    username: "creative_lead",
    role: "creator",
    stage: "STAGE 01",
    title: "Creator",
    handle: "@creative_lead",
    summary: "Draft pre-flight & copy repair",
  },
  {
    username: "brand_manager",
    role: "reviewer",
    stage: "STAGE 02",
    title: "Brand Manager",
    handle: "@brand_manager",
    summary: "Playbooks & override review",
  },
  {
    username: "legal_counsel",
    role: "admin",
    stage: "STAGE 03",
    title: "Legal Counsel",
    handle: "@legal_counsel",
    summary: "Statutory sign-off & certificate",
  },
] as const;

export function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedRole = searchParams.get("role");
  const redirectPath = searchParams.get("redirect") || "/";

  const [authMode, setAuthMode] = useState<"signin" | "signup">("signin");

  const matchedDemo = requestedRole
    ? DEMO_ACCOUNTS.find((a) => a.role === requestedRole)
    : undefined;

  const [signInUsername, setSignInUsername] = useState<string>(
    () => matchedDemo?.username ?? "creative_lead",
  );
  const [signInPassword, setSignInPassword] = useState("demoPassword123!");

  const [signUpName, setSignUpName] = useState("");
  const [signUpUsername, setSignUpUsername] = useState("");
  const [signUpPassword, setSignUpPassword] = useState("");
  const [signUpRole, setSignUpRole] = useState<string>(
    () => requestedRole ?? "creator",
  );

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [quickLaunchingUser, setQuickLaunchingUser] = useState<string | null>(
    null,
  );

  const [prevRole, setPrevRole] = useState(requestedRole);
  if (prevRole !== requestedRole) {
    setPrevRole(requestedRole);
    if (requestedRole) {
      const matched = DEMO_ACCOUNTS.find((a) => a.role === requestedRole);
      if (matched) {
        setSignInUsername(matched.username);
        setSignInPassword("demoPassword123!");
      }
      setSignUpRole(requestedRole);
    }
  }

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
      <header className="cg-topbar">
        <div className="cg-topbar-inner">
          <div className="cg-topbar-left">
            <div className="cg-brand">
              <span className="cg-brand-mark" aria-hidden="true">
                <ShieldCheck size={17} strokeWidth={2.2} />
              </span>
              <span className="cg-brand-name">CanonGate</span>
              <span className="cg-brand-version">Console</span>
            </div>
          </div>
        </div>
      </header>

      <main className="cg-auth-main">
        <div className="cg-auth-single-wrap">
          <section className="cg-auth-card">
            <div className="cg-auth-quicklaunch">
              <div className="cg-auth-quicklaunch-top">
                <span className="cg-mono-label">QUICK ROLE LAUNCH</span>
                <span className="cg-auth-quicklaunch-badge">Seeded Accounts</span>
              </div>
              <p className="cg-auth-quicklaunch-desc">
                Select a role to open the governance workspace immediately, or sign in with credentials below.
              </p>

              <div className="cg-auth-persona-grid">
                {DEMO_ACCOUNTS.map((acct) => {
                  const isSelected = signInUsername === acct.username;
                  const isLaunching = quickLaunchingUser === acct.username;
                  return (
                    <button
                      key={acct.username}
                      type="button"
                      data-testid={`quick-login-${acct.username}`}
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
              <span>OR SIGN IN WITH CREDENTIALS</span>
            </div>

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
                Sign In
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
                Create Account
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
                      Demo: <code>demoPassword123!</code>
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
                    {loading ? "Signing in…" : "Sign In"}
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
                  <label htmlFor="signup-role">Role</label>
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
                      placeholder="Create a password"
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
                    {loading ? "Creating account…" : "Create Account"}
                  </span>
                  <ArrowRight size={16} className="cg-arrow-shift" />
                </button>
              </form>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
