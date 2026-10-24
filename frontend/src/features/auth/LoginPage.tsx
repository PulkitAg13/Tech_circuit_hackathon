import { useState, useEffect, type FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { login as apiLogin, register as apiRegister } from "../../api/client";

/**
 * CanonGate Logo Component
 * Pixel-accurate shield-governance gate icon + typography
 */
function CanonGateLogo({ variant = "dark" }: { variant?: "dark" | "light" }) {
  const isLight = variant === "light";
  return (
    <div className={`diprella-brand-logo ${isLight ? "logo-light" : "logo-dark"}`}>
      <div className="diprella-logo-box">
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      </div>
      <span className="diprella-logo-text">CanonGate</span>
    </div>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // State: isSignUp toggles the classic sliding container (right-panel-active)
  // When false: Sign In view (State 2 in user images)
  // When true: Create Account / Sign Up view (State 1 in user images)
  const [isSignUp, setIsSignUp] = useState(Boolean((location.state as any)?.signup));

  useEffect(() => {
    if ((location.state as any)?.signup !== undefined) {
      setIsSignUp(Boolean((location.state as any)?.signup));
    }
  }, [location.state]);

  // Sign In form fields
  const [signInEmail, setSignInEmail] = useState("");
  const [signInPassword, setSignInPassword] = useState("");

  // Sign Up form fields
  const [signUpName, setSignUpName] = useState("");
  const [signUpEmail, setSignUpEmail] = useState("");
  const [signUpPassword, setSignUpPassword] = useState("");

  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [loading, setLoading] = useState(false);

  // Lock document body so sign-in page is completely fixed and not movable
  useEffect(() => {
    const originalOverflow = document.body.style.overflow;
    const originalHeight = document.body.style.height;
    document.body.style.overflow = "hidden";
    document.body.style.height = "100vh";
    return () => {
      document.body.style.overflow = originalOverflow;
      document.body.style.height = originalHeight;
    };
  }, []);

  // Handle Sign In submission
  const handleSignIn = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccessMsg("");
    setLoading(true);

    try {
      const username = signInEmail.trim();
      const password = signInPassword;
      const data = await apiLogin(username, password);
      login(data);
      navigate("/dashboard", { replace: true });
    } catch (err: any) {
      setError(err.message || "Invalid email or password");
    } finally {
      setLoading(false);
    }
  };

  // Handle Sign Up submission
  const handleSignUp = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccessMsg("");
    setLoading(true);

    try {
      const username = signUpEmail.trim() || signUpName.trim().toLowerCase().replace(/\s+/g, "_");
      const password = signUpPassword;
      const data = await apiRegister(username, password, "creator", signUpName);
      login(data);
      navigate("/dashboard", { replace: true });
    } catch (err: any) {
      setError(err.message || "Registration failed");
    } finally {
      setLoading(false);
    }
  };


  const handleForgotPassword = () => {
    setSignInEmail("creative_lead");
    setSignInPassword("demoPassword123!");
    setSuccessMsg("Filled demo evaluator credentials! Click SIGN IN to continue.");
  };

  return (
    <div className="diprella-auth-page">
      {/* ── Background Geometric Accents ── */}
      <div className="bg-corner-shape-red" aria-hidden="true" />
      <div className="bg-corner-shape-yellow" aria-hidden="true" />

      {/* ── Main Sliding Card Container ── */}
      <div className={`diprella-card-container ${isSignUp ? "right-panel-active" : ""}`}>
        
        {/* ── Sign In Form (Left on inactive, slides right on active) ── */}
        <div className="diprella-form-panel diprella-sign-in-panel">
          <div className="diprella-top-left-logo" onClick={() => navigate("/")}>
            <CanonGateLogo variant="dark" />
          </div>

          <form onSubmit={handleSignIn} className="diprella-form">
            <h1 className="diprella-heading">Sign in to CanonGate</h1>


            <div className="diprella-input-group">
              <span className="diprella-input-icon">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="4" width="20" height="16" rx="2" />
                  <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
                </svg>
              </span>
              <input
                type="text"
                placeholder="Email"
                value={signInEmail}
                onChange={(e) => setSignInEmail(e.target.value)}
                required
              />
            </div>

            <div className="diprella-input-group">
              <span className="diprella-input-icon">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
              </span>
              <input
                type="password"
                placeholder="Password"
                value={signInPassword}
                onChange={(e) => setSignInPassword(e.target.value)}
                required
              />
            </div>

            {error && !isSignUp && (
              <div className="diprella-error-alert">{error}</div>
            )}
            {successMsg && !isSignUp && (
              <div className="diprella-success-alert">{successMsg}</div>
            )}

            <button
              type="button"
              className="diprella-forgot-link"
              onClick={handleForgotPassword}
            >
              Forgot your password?
            </button>

            <button
              type="submit"
              className="diprella-solid-btn"
              disabled={loading}
            >
              {loading ? "SIGNING IN..." : "SIGN IN"}
            </button>
          </form>
        </div>

        {/* ── Sign Up Form (Behind on inactive, slides to right half on active) ── */}
        <div className="diprella-form-panel diprella-sign-up-panel">
          <form onSubmit={handleSignUp} className="diprella-form">
            <h1 className="diprella-heading">Create Account</h1>


            <div className="diprella-input-group">
              <span className="diprella-input-icon">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              </span>
              <input
                type="text"
                placeholder="Name"
                value={signUpName}
                onChange={(e) => setSignUpName(e.target.value)}
                required
              />
            </div>

            <div className="diprella-input-group">
              <span className="diprella-input-icon">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="4" width="20" height="16" rx="2" />
                  <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
                </svg>
              </span>
              <input
                type="text"
                placeholder="Email"
                value={signUpEmail}
                onChange={(e) => setSignUpEmail(e.target.value)}
                required
              />
            </div>

            <div className="diprella-input-group">
              <span className="diprella-input-icon">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
              </span>
              <input
                type="password"
                placeholder="Password"
                value={signUpPassword}
                onChange={(e) => setSignUpPassword(e.target.value)}
                required
              />
            </div>

            {error && isSignUp && (
              <div className="diprella-error-alert">{error}</div>
            )}

            <button
              type="submit"
              className="diprella-solid-btn"
              disabled={loading}
            >
              {loading ? "CREATING..." : "SIGN UP"}
            </button>
          </form>
        </div>

        {/* ── Overlay Sliding Section ── */}
        <div className="diprella-overlay-container">
          <div className="diprella-overlay">
            
            {/* Geometric Translucent Pattern Elements */}
            <div className="geom-diamond geom-diamond-1" aria-hidden="true" />
            <div className="geom-diamond geom-diamond-2" aria-hidden="true" />
            <div className="geom-circle geom-circle-1" aria-hidden="true" />
            <div className="geom-polygon" aria-hidden="true" />

            {/* Left Overlay (shown when Sign Up is active -> invites to Sign In) */}
            <div className="diprella-overlay-panel diprella-overlay-left">
              <div className="diprella-top-left-logo" onClick={() => navigate("/")}>
                <CanonGateLogo variant="light" />
              </div>

              <h1 className="diprella-overlay-heading">Welcome Back!</h1>
              <p className="diprella-overlay-text">
                To keep connected with us please login with your personal info
              </p>
              <button
                type="button"
                className="diprella-ghost-btn"
                onClick={() => {
                  setIsSignUp(false);
                  setError("");
                  setSuccessMsg("");
                }}
              >
                SIGN IN
              </button>
            </div>

            {/* Right Overlay (shown when Sign In is active -> invites to Sign Up) */}
            <div className="diprella-overlay-panel diprella-overlay-right">
              <h1 className="diprella-overlay-heading">Hello, Friend!</h1>
              <p className="diprella-overlay-text">
                Enter your personal details and start journey with us
              </p>
              <button
                type="button"
                className="diprella-ghost-btn has-ripple-accent"
                onClick={() => {
                  setIsSignUp(true);
                  setError("");
                  setSuccessMsg("");
                }}
              >
                SIGN UP
              </button>
            </div>

          </div>
        </div>

      </div>

    </div>
  );
}
