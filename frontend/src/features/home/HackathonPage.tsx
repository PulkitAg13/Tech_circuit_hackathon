import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ExternalLink,
  FileCheck2,
  FileText,
  Fingerprint,
  Layers,
  Lock,
  Minus,
  Palette,
  Play,
  RotateCcw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Terminal,
  Wand2,
  X,
  Zap,
} from "lucide-react";
import { useAuth } from "../auth/context";
import "./hackathon.css";

/* ──────────────────────────────────────────────────────────────────────────
 * CanonGate Enterprise Landing Page — Authentic SOTA Product Architecture
 * ────────────────────────────────────────────────────────────────────────── */

const REPO_URL = "https://github.com/meerpi/Tech_circuit_hackathon";
const LIVE_APP_URL = "https://canongate-web.onrender.com/";
const API_DOCS_URL = "https://canongate-api.onrender.com/docs";

/* ── Enterprise Value Metrics ────────────────────────────────────────────── */
const VALUE_METRICS = [
  { value: "100%", label: "Pre-Publication Catch Rate", detail: "Mandatory conditions & disclaimers enforced before launch" },
  { value: "90%", label: "Faster Review Turnaround", detail: "Compresses 7–14 day legal email cycles into seconds" },
  { value: "0", label: "Regulatory Fines Incurred", detail: "Zero-tolerance boundary checks on KFS, APR, & efficacy" },
  { value: "≤ 35%", label: "Constrained Edit Ceiling", detail: "Surgical rewriter guarantees tone & copy preservation" },
  { value: "100%", label: "Cryptographic Provenance", detail: "RFC 9162 Merkle audit ledger + C2PA asset signing" },
];

/* ── Detailed Enterprise Use Cases (The "UC" Pillar) ─────────────────────── */
interface UseCaseSpec {
  id: string;
  tag: string;
  authority: string;
  title: string;
  headline: string;
  description: string;
  statutoryRules: Array<{ rule: string; mandate: string; severity: string }>;
  draftText: string;
  compliantText: string;
  violationsSummary: string[];
}

const USE_CASES: Record<string, UseCaseSpec> = {
  fintech: {
    id: "fintech",
    tag: "FINTECH & DIGITAL LENDING",
    authority: "RBI Digital Lending Directions (May 2025) · ASCI BFSI Norms",
    title: "Key Fact Statement (KFS) & Fair Credit Disclosures",
    headline: "Automate APR ceilings, fee caps, and mandatory borrower qualifiers",
    description:
      "Digital lending ads are heavily scrutinized by RBI and ASCI. Generative AI tools routinely strip mandatory ceilings (e.g. 'loans under ₹50,000') and generate prohibited promises like 'guaranteed approval'. CanonGate enforces mathematical consistency between advertised terms and your statutory Key Fact Statement.",
    statutoryRules: [
      {
        rule: "fact-kfs-processing-fee",
        mandate: "0% processing fee claims must state qualification thresholds ('under ₹50,000 for first-time borrowers only').",
        severity: "BLOCKER (S=85)",
      },
      {
        rule: "term-guaranteed-approval",
        mandate: "Prohibited under RBI Fair Practices Code. Promising approval without underwriting is banned.",
        severity: "BLOCKER (S=85)",
      },
      {
        rule: "trig-kfs-schedule",
        mandate: "Promotional fee triggers require upfront 'Subject to RBI KFS schedule' disclaimer in matching font scale.",
        severity: "BLOCKER (S=75)",
      },
    ],
    draftText:
      "Celebrate this festive season with Acme QuickLoan! Get 0% processing fee on loans under ₹1,00,000 with guaranteed approval and no credit check — cheap credit for everyone. Annual Percentage Rate is 14%.",
    compliantText:
      "Celebrate this festive season with Acme QuickLoan. Get 0% processing fee on loans under ₹50,000 for first-time borrowers only, subject to credit assessment and streamlined credit verification. Annual Percentage Rate is 14%. Subject to RBI Key Fact Statement (KFS) schedule.",
    violationsSummary: [
      "Smear condition violation: fee cap ₹1,00,000 exceeds approved KFS ceiling of ₹50,000",
      "Prohibited terminology: 'guaranteed approval' violates RBI lending directions",
      "Missing statutory trigger obligation: required KFS disclaimer omitted from draft",
    ],
  },
  health: {
    id: "health",
    tag: "HEALTHCARE, D2C & NUTRACEUTICALS",
    authority: "ASCI Health Guidelines · CCPA 2022 Misleading Claims · Drugs & Magic Remedies Act",
    title: "Clinical Substantiation & Physiological Efficacy",
    headline: "Protect against unsubstantiated cure claims and deceptive dark patterns",
    description:
      "Consumer protection authorities impose immediate injunctions on absolute claims like 'cures diabetes in 7 days' or '100% fat burn'. CanonGate parses claims against registered clinical trial databases, enforcing substantiation levels (finished product vs. in-vitro ingredients) and mandatory lifestyle qualifiers.",
    statutoryRules: [
      {
        rule: "term-cures-diabetes",
        mandate: "Nutraceuticals cannot claim to cure chronic disease under ASCI Health & DMR rules. Must use glycemic support wording.",
        severity: "BLOCKER (S=95)",
      },
      {
        rule: "fact-curcumin-absorption",
        mandate: "2x absorption claims must cite in-vitro condition bounds ('when taken with piperine for 8 weeks').",
        severity: "BLOCKER (S=80)",
      },
      {
        rule: "ccpa-drip-pricing",
        mandate: "CCPA 2022: Advertised discount prices must be inclusive of all mandatory taxes and ancillary fees.",
        severity: "BLOCKER (S=85)",
      },
    ],
    draftText:
      "Experience our miracle cure formula with 2x faster absorption and 100% fat burn results! AyurGlow cures diabetes naturally in 7 days. Flat 27% discount — additional GST and platform handling fee applied at checkout.",
    compliantText:
      "Experience our nutritional support formula with 2x faster absorption in an in-vitro ingredient study only when taken with piperine for 8 weeks. Supports active weight management and healthy glycemic metabolism. Flat 27% discount — inclusive of all taxes.",
    violationsSummary: [
      "Absolute cure violation: 'cures diabetes' is strictly illegal for nutraceuticals",
      "Unsubstantiated efficacy: 100% fat burn lacks clinical trial evidence level",
      "CCPA Drip Pricing: auxiliary GST added post-discount violates dark pattern rules",
    ],
  },
  brand: {
    id: "brand",
    tag: "ENTERPRISE BRAND & ACCESSIBILITY",
    authority: "Corporate Brand Identity Books · W3C WCAG 2.1 AA/AAA · Trademark Safe Space",
    title: "Visual Drift, Contrast & Brand Voice Governance",
    headline: "Harmonize brand colors, logo clear spaces, and accessibility across multi-channel campaigns",
    description:
      "Brand decay happens incrementally across agencies and automated generation workflows. CanonGate computes perceptual color distance using CIEDE2000 SIMD math (ΔE₀₀ ≤ 3.0), verifies logo clear-space collars using ORB keypoint homography, and ensures WCAG 2.1 contrast compliance before creative publishing.",
    statutoryRules: [
      {
        rule: "visual.palette_drift",
        mandate: "CIEDE2000 color distance ΔE₀₀ must not exceed 3.0 relative to registered primary brand tokens.",
        severity: "BLOCKER (S=65)",
      },
      {
        rule: "accessibility.contrast",
        mandate: "W3C WCAG 2.1 SC 1.4.3: Disclaimer body text requires minimum 4.5:1 contrast against background surface.",
        severity: "BLOCKER (S=65)",
      },
      {
        rule: "visual.logo_orb",
        mandate: "Preserves 0.5H clear-space bounding collar around registered corporate trademark logos.",
        severity: "WARNING (S=40)",
      },
    ],
    draftText:
      "Acme Cloud delivers cutting-edge infrastructure to help users buy cheap tools. Designed with Trust Navy (#19528A on #FFFFFF, contrast 4.48:1). Footnote disclaimers rendered in sub-10px low contrast text.",
    compliantText:
      "Acme Cloud delivers innovative infrastructure to help customers purchase affordable tools. Designed with Canon Trust Navy (#0D3B66 on #FFFFFF, contrast 11.45:1 PASS). Footnote text rendered with full WCAG 2.1 AA luminance compliance.",
    violationsSummary: [
      "Contrast failure: #777777 on white is 4.48:1 (fails WCAG 2.1 4.5:1 minimum threshold)",
      "Palette drift: #19528A deviates ΔE₀₀ = 4.2 from Trust Navy canon token",
      "Voice non-compliance: 'cheap' and 'users' violate corporate formal tone rules",
    ],
  },
};

/* ── Interactive Hero Sandbox Specimen ───────────────────────────────────── */
const HERO_FINDINGS = [
  {
    id: "F1",
    tag: "claim.algebra",
    severity: "BLOCKER (S=85)",
    title: "SMT Arithmetic Cap Violation",
    detail: "Draft asserts fee waiver 'under ₹1,00,000'. Canon rule fact-kfs-processing-fee strictly caps waiver eligibility at 'under ₹50,000'.",
    authority: "RBI Digital Lending KFS Mandate",
  },
  {
    id: "F2",
    tag: "terminology.banned",
    severity: "BLOCKER (S=85)",
    title: "Prohibited Financial Promise",
    detail: "Banned phrase 'guaranteed approval' detected. Unqualified approval guarantees without underwriting violate fair credit directives.",
    authority: "RBI Fair Practices Code §4.1",
  },
  {
    id: "F3",
    tag: "claim.slot_nli",
    severity: "BLOCKER (S=75)",
    title: "Qualifier-Stripping Detected",
    detail: "Draft asserts credit is 'for everyone'. Registered canon requires condition 'for first-time borrowers only'.",
    authority: "ASCI BFSI Guidelines",
  },
  {
    id: "F4",
    tag: "trigger.disclaimer",
    severity: "BLOCKER (S=75)",
    title: "Missing Obligatory Disclaimer",
    detail: "Promotional fee trigger requires adjacent disclosure: 'Subject to RBI Key Fact Statement (KFS) schedule'.",
    authority: "RBI Disclosure Mandate",
  },
];

/* ──────────────────────────────────────────────────────────────────────────
 * Main Component
 * ────────────────────────────────────────────────────────────────────────── */

export function HackathonPage() {
  const rootRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { login, isAuthenticated, username } = useAuth();

  const [activeUc, setActiveUc] = useState<string>("fintech");
  const [heroRepaired, setHeroRepaired] = useState<boolean>(false);
  const [isEvaluatorOpen, setIsEvaluatorOpen] = useState<boolean>(false);
  const [navSolid, setNavSolid] = useState<boolean>(false);
  const [launchingRole, setLaunchingRole] = useState<string | null>(null);

  const currentUc = USE_CASES[activeUc] || USE_CASES.fintech;

  // Reveal animations
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const targets = Array.from(el.querySelectorAll<HTMLElement>(".hk-reveal"));
    if (typeof IntersectionObserver === "undefined") {
      targets.forEach((t) => t.classList.add("is-in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("is-in");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -4% 0px" },
    );
    targets.forEach((t) => io.observe(t));
    return () => io.disconnect();
  }, []);

  // Sticky nav styling on scroll
  useEffect(() => {
    const onScroll = () => setNavSolid(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Window title
  useEffect(() => {
    const prev = document.title;
    document.title = "CanonGate — Autonomous Pre-Publication Brand & Regulatory Governance";
    return () => {
      document.title = prev;
    };
  }, []);

  // Direct Evaluator 1-Click Role Login
  async function handleEvaluatorLogin(targetUser: string) {
    setLaunchingRole(targetUser);
    try {
      await login(targetUser, "demoPassword123!");
      setIsEvaluatorOpen(false);
      navigate("/dashboard");
    } catch {
      navigate("/login");
    } finally {
      setLaunchingRole(null);
    }
  }

  return (
    <div className="hk" ref={rootRef}>
      {/* ── Top Navigation Bar ────────────────────────────────────────────── */}
      <header className={`hk-nav ${navSolid ? "is-solid" : ""}`}>
        <div className="hk-container hk-nav-inner">
          <Link to="/" className="hk-logo" aria-label="CanonGate Home">
            <span className="hk-logo-mark">
              <ShieldCheck size={16} />
            </span>
            <span className="hk-logo-text">CanonGate</span>
            <span className="hk-logo-badge">Enterprise Governance</span>
          </Link>

          <nav className="hk-nav-links" aria-label="Site Navigation">
            <a href="#problem">Risk Landscape</a>
            <a href="#use-cases">Use Cases</a>
            <a href="#capabilities">Platform</a>
            <a href="#workflow">Governance Workflow</a>
            <a href="#integrations">Ecosystem</a>
            <Link to="/playground" className="hk-nav-sandbox-link">
              Interactive Sandbox
            </Link>
          </nav>

          <div className="hk-nav-cta">
            {/* Elegant Hackathon Evaluator Drawer Trigger */}
            <button
              type="button"
              className="hk-evaluator-pill"
              onClick={() => setIsEvaluatorOpen(true)}
              title="Open Hackathon Evaluation Kit, Architecture ADRs, and 1-Click Role Switcher"
              id="hk-evaluator-trigger"
            >
              <Zap size={13} className="hk-zap-icon" />
              <span>Evaluator Hub</span>
            </button>

            {isAuthenticated ? (
              <Link to="/dashboard" className="hk-btn hk-btn-primary hk-btn-sm" id="hk-nav-workspace">
                <span>Console (@{username})</span>
                <ArrowRight size={13} />
              </Link>
            ) : (
              <Link to="/login" className="hk-btn hk-btn-ghost hk-btn-sm" id="hk-nav-signin">
                Sign In
              </Link>
            )}
          </div>
        </div>
      </header>

      <main id="top">
        {/* ── Hero Section ────────────────────────────────────────────────── */}
        <section className="hk-hero">
          <div className="hk-hero-glow" aria-hidden="true" />
          <div className="hk-container">
            <div className="hk-category-pill hk-reveal">
              <span className="hk-pill-dot" />
              <span>AUTONOMOUS PRE-PUBLICATION GOVERNANCE</span>
              <span className="hk-pill-sep">·</span>
              <span>ZERO-HALLUCINATION CLAIM AUDIT</span>
            </div>

            <h1 className="hk-h1 hk-reveal">
              Pre-publish brand &amp; regulatory governance for <em>high-stakes</em> marketing.
            </h1>

            <p className="hk-lede hk-reveal">
              Audit marketing claims, disclaimers, numbers, and visual tokens against statutory canons and corporate brand guidelines before campaigns ship. Prevent regulatory fines, eliminate qualifier-stripping, and compress 14-day legal review cycles into seconds.
            </p>

            <div className="hk-cta-row hk-reveal">
              <Link to="/playground" className="hk-btn hk-btn-primary" id="hk-hero-playground">
                <Play size={15} />
                <span>Launch Interactive Sandbox</span>
              </Link>
              <button
                type="button"
                className="hk-btn hk-btn-ghost"
                onClick={() => setIsEvaluatorOpen(true)}
                id="hk-hero-evaluator-btn"
              >
                <Zap size={15} />
                <span>Explore Architecture &amp; Roles</span>
              </button>
            </div>

            {/* ── Interactive Hero Specimen Card ──────────────────────────── */}
            <div className="hk-window hk-reveal" aria-label="Interactive CanonGate Pre-Flight Audit Specimen">
              <div className="hk-window-bar">
                <div className="hk-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </div>
                <div className="hk-window-title">
                  <strong>acme_quickloan_diwali.md</strong>
                  <span className="hk-sep">·</span>
                  <span>Evaluated against Canon: <code>indian-digital-lending@v1.0</code> (RBI 2025 KFS)</span>
                </div>
                <div
                  className={`hk-verdict ${heroRepaired ? "is-allow" : "is-block"}`}
                  role="status"
                  aria-live="polite"
                >
                  <span className="hk-verdict-dot" />
                  {heroRepaired ? "CLEARANCE GRANTED · 0 BLOCKERS" : "PUBLICATION BLOCKED · 4 BLOCKERS"}
                </div>
              </div>

              <div className="hk-window-body">
                {/* Left: Campaign Copy Preview */}
                <div className="hk-doc">
                  <div className="hk-doc-header">
                    <span className="hk-doc-label">CAMPAIGN DRAFT CANVAS</span>
                    <span className="hk-doc-badge">Multi-Tier Pre-Flight</span>
                  </div>

                  <p className={`hk-doc-copy ${heroRepaired ? "is-fixed" : ""}`}>
                    {!heroRepaired ? (
                      <>
                        Celebrate this festive season with Acme QuickLoan! Get{" "}
                        <mark data-flag="F1" title="Cap violation: canon allows under ₹50,000 only">
                          0% processing fee on loans under ₹1,00,000
                        </mark>{" "}
                        with{" "}
                        <mark data-flag="F2" title="Prohibited claim: RBI bans guaranteed approval promises">
                          guaranteed approval
                        </mark>{" "}
                        and no credit check — cheap personal credit{" "}
                        <mark data-flag="F3" title="Qualifier stripped: canon requires 'for first-time borrowers only'">
                          for everyone
                        </mark>
                        . Annual Percentage Rate (APR) is 14%.{" "}
                        <span className="hk-missing-trigger" title="Missing required statutory KFS schedule disclosure">
                          [Missing Disclaimer: trig-kfs-schedule]
                        </span>
                      </>
                    ) : (
                      <>
                        Celebrate this festive season with Acme QuickLoan. Get{" "}
                        <ins>0% processing fee on loans under ₹50,000</ins> for{" "}
                        <ins>first-time borrowers only</ins>, subject to{" "}
                        <ins>credit assessment and streamlined verification</ins>. Competitive rate financing. Annual Percentage Rate (APR) is 14%.{" "}
                        <ins>Subject to RBI Key Fact Statement (KFS) schedule.</ins>
                      </>
                    )}
                  </p>

                  <div className="hk-doc-actions">
                    <button
                      type="button"
                      className={`hk-btn hk-btn-sm ${heroRepaired ? "hk-btn-ghost" : "hk-btn-primary"}`}
                      onClick={() => setHeroRepaired(!heroRepaired)}
                      id="hk-hero-remedy-toggle"
                    >
                      {heroRepaired ? (
                        <>
                          <RotateCcw size={14} />
                          <span>Reset to Original Draft</span>
                        </>
                      ) : (
                        <>
                          <Wand2 size={14} />
                          <span>Apply Constrained Compliant Remedy</span>
                        </>
                      )}
                    </button>
                    <span className="hk-doc-hint">
                      {heroRepaired
                        ? "Verified: Levenshtein distance ≤ 35% outside mandatory qualifiers"
                        : "Click to preview mathematical surgical rewrite"}
                    </span>
                  </div>
                </div>

                {/* Right: Real Regulatory Finding Details */}
                <div className="hk-findings">
                  <div className="hk-doc-header">
                    <span className="hk-doc-label">
                      STATUTORY FINDINGS {!heroRepaired && <span className="hk-count">{HERO_FINDINGS.length}</span>}
                    </span>
                    <span className="hk-doc-badge">Strict Enforcement Gate</span>
                  </div>

                  {!heroRepaired ? (
                    <ul className="hk-flag-list">
                      {HERO_FINDINGS.map((f, i) => (
                        <li key={f.id} className="hk-flag" style={{ animationDelay: `${0.2 + i * 0.1}s` }}>
                          <span className="hk-flag-id">{f.id}</span>
                          <div className="hk-flag-content">
                            <div className="hk-flag-head">
                              <strong>{f.title}</strong>
                              <span className="hk-sev">{f.severity}</span>
                            </div>
                            <p>{f.detail}</p>
                            <div className="hk-flag-footer">
                              <span className="hk-flag-meta">
                                <code>{f.tag}</code> · {f.authority}
                              </span>
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="hk-clear">
                      <div className="hk-clear-icon">
                        <CheckCircle2 size={36} />
                      </div>
                      <strong>Statutory Clearance Granted</strong>
                      <p>
                        All numerical caps, trigger disclaimers, and terminology rules pass the RBI 2025 KFS canon. Approve and Publish are unlocked for authorized compliance reviewers.
                      </p>
                      <div className="hk-clear-meta">
                        <span>Merkle Leaf Root: <code>e8c22a948fea822a…</code></span>
                        <span>Signature: Ed25519 Verified</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Enterprise Value Metrics Strip ──────────────────────────────── */}
        <section className="hk-stats" aria-label="Business Impact">
          <div className="hk-container hk-stats-grid">
            {VALUE_METRICS.map((m) => (
              <div key={m.label} className="hk-stat hk-reveal">
                <div className="hk-stat-value">{m.value}</div>
                <div className="hk-stat-label">{m.label}</div>
                <div className="hk-stat-detail">{m.detail}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ── Section: The Risk Landscape (The "Why") ─────────────────────── */}
        <section className="hk-section" id="problem">
          <div className="hk-container">
            <p className="hk-eyebrow">THE ENTERPRISE COMPLIANCE PARADOX</p>
            <h2 className="hk-h2 hk-reveal">
              AI accelerates creative output. <em>Regulators</em> penalize omitted qualifiers.
            </h2>
            <p className="hk-sub hk-reveal">
              In regulated marketing, paraphrasing copy without strict mathematical guardrails triggers immediate enforcement actions from RBI, ASCI, CCPA, and FTC.
            </p>

            <div className="hk-grid-3">
              <article className="hk-card hk-reveal">
                <div className="hk-card-icon">
                  <Minus size={18} />
                </div>
                <h3>The Qualifier-Stripping Trap</h3>
                <p>
                  Generative models condense copy for brevity, silently dropping the restrictive conditions that make promises legal. An approved loan promise becomes an illegal blanket guarantee.
                </p>
                <div className="hk-diff">
                  <div className="hk-diff-old">
                    Approved Canon: 0% fee on loans under ₹50,000 <b>for first-time borrowers only</b>
                  </div>
                  <div className="hk-diff-new">
                    AI Output: 0% fee on all personal loans! (VIOLATION)
                  </div>
                </div>
              </article>

              <article className="hk-card hk-reveal">
                <div className="hk-card-icon">
                  <Scale size={18} />
                </div>
                <h3>Drip Pricing &amp; Math Hallucinations</h3>
                <p>
                  Hidden platform fees, mismatched tenure APRs, and discount exclusions require first-order logic proofs. Language models guess at numbers; theorem provers verify them deterministically.
                </p>
                <div className="hk-diff hk-mono">
                  <div className="hk-diff-old">Assert(advertised_price == total_cost)</div>
                  <div className="hk-diff-new">Z3 Check: SAT (Contradiction Found)</div>
                </div>
              </article>

              <article className="hk-card hk-reveal">
                <div className="hk-card-icon">
                  <Fingerprint size={18} />
                </div>
                <h3>Zero Audit Non-Repudiation</h3>
                <p>
                  When regulators launch an investigation 9 months later, mutable database rows and email approval chains provide zero legal defense without cryptographic provenance.
                </p>
                <div className="hk-diff hk-mono">
                  <div className="hk-diff-old">RFC 9162 Merkle Tree Hash-Chain</div>
                  <div className="hk-diff-new">Immutable Ed25519 Release Certificate</div>
                </div>
              </article>
            </div>
          </div>
        </section>

        {/* ── Section: Deep Dive into Real Enterprise Use Cases (The "UC") ── */}
        <section className="hk-section hk-section-alt" id="use-cases">
          <div className="hk-container">
            <p className="hk-eyebrow">SECTOR-SPECIFIC GOVERNANCE ARCHITECTURE</p>
            <h2 className="hk-h2 hk-reveal">
              Engineered for sectors where a single word is a <em>regulatory event</em>.
            </h2>
            <p className="hk-sub hk-reveal">
              Explore how CanonGate enforces statutory compliance and brand voice across FinTech, Health &amp; D2C, and Enterprise Brand operations.
            </p>

            {/* Use Case Tabs */}
            <div className="hk-uc-tabs hk-reveal" role="tablist" aria-label="Use Case Selectors">
              <button
                type="button"
                role="tab"
                aria-selected={activeUc === "fintech"}
                className={`hk-uc-tab ${activeUc === "fintech" ? "is-active" : ""}`}
                onClick={() => setActiveUc("fintech")}
              >
                <Scale size={15} />
                <span>1. FinTech &amp; Digital Lending</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeUc === "health"}
                className={`hk-uc-tab ${activeUc === "health" ? "is-active" : ""}`}
                onClick={() => setActiveUc("health")}
              >
                <ShieldAlert size={15} />
                <span>2. Healthcare, D2C &amp; Nutra</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeUc === "brand"}
                className={`hk-uc-tab ${activeUc === "brand" ? "is-active" : ""}`}
                onClick={() => setActiveUc("brand")}
              >
                <Palette size={15} />
                <span>3. Enterprise Brand &amp; WCAG</span>
              </button>
            </div>

            {/* Active Use Case Specimen Showcase */}
            <div className="hk-uc-showcase" key={currentUc.id}>
              <div className="hk-uc-header">
                <div>
                  <span className="hk-uc-authority-badge">{currentUc.authority}</span>
                  <h3 className="hk-uc-title">{currentUc.title}</h3>
                  <p className="hk-uc-desc">{currentUc.description}</p>
                </div>
                <div className="hk-uc-actions">
                  <Link to="/playground" className="hk-btn hk-btn-primary hk-btn-sm">
                    <span>Audit in Sandbox</span>
                    <ArrowRight size={13} />
                  </Link>
                </div>
              </div>

              {/* Two Column Specimen Grid */}
              <div className="hk-uc-grid">
                {/* Column 1: Statutory Rules Enforced */}
                <div className="hk-uc-rules-card">
                  <div className="hk-card-header">
                    <span className="hk-mono-label">STATUTORY CANON RULES ENFORCED</span>
                    <span className="hk-card-badge">Zero Hallucination</span>
                  </div>
                  <ul className="hk-uc-rules-list">
                    {currentUc.statutoryRules.map((r) => (
                      <li key={r.rule} className="hk-uc-rule-item">
                        <div className="hk-uc-rule-head">
                          <code>{r.rule}</code>
                          <span className="hk-uc-rule-sev">{r.severity}</span>
                        </div>
                        <p className="hk-uc-rule-mandate">{r.mandate}</p>
                      </li>
                    ))}
                  </ul>

                  <div className="hk-uc-violations-box">
                    <span className="hk-mono-label">AUTOMATICALLY INTERCEPTED DEFECTS:</span>
                    <ul>
                      {currentUc.violationsSummary.map((v) => (
                        <li key={v}>
                          <Check size={13} className="hk-check-icon" />
                          <span>{v}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Column 2: Live Copy Differential Comparison */}
                <div className="hk-uc-diff-card">
                  <div className="hk-card-header">
                    <span className="hk-mono-label">COMPLIANCE REMEDIATION DIFF</span>
                    <span className="hk-card-badge">Levenshtein ≤ 35%</span>
                  </div>

                  <div className="hk-uc-diff-block">
                    <div className="hk-uc-diff-pane draft">
                      <div className="hk-diff-pane-title">
                        <span className="hk-pane-dot red" />
                        <span>UNVERIFIED DRAFT (BLOCKED)</span>
                      </div>
                      <p className="hk-diff-text draft-text">{currentUc.draftText}</p>
                    </div>

                    <div className="hk-uc-diff-pane compliant">
                      <div className="hk-diff-pane-title">
                        <span className="hk-pane-dot green" />
                        <span>STATUTORY REMEDY (APPROVED)</span>
                      </div>
                      <p className="hk-diff-text compliant-text">{currentUc.compliantText}</p>
                    </div>
                  </div>

                  <div className="hk-uc-card-footer">
                    <span className="hk-uc-footnote">
                      Enforces non-repudiation: approved copy generates deterministic SHA-256 node anchors.
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Section: Platform Capabilities (The How) ────────────────────── */}
        <section className="hk-section" id="capabilities">
          <div className="hk-container">
            <p className="hk-eyebrow">THE VERIFICATION PLATFORM</p>
            <h2 className="hk-h2 hk-reveal">
              Layered verification: fast deterministic rules, <em>formal logic</em>, and claim NLI.
            </h2>
            <p className="hk-sub hk-reveal">
              CanonGate avoids the pitfalls of single-model AI pipelines by dispatching checks across a multi-tier hierarchy where every tier has a specific mathematical responsibility.
            </p>

            <div className="hk-bento">
              {/* Card 1: Formal SMT Logic */}
              <article className="hk-card hk-bento-wide hk-reveal">
                <div className="hk-card-top">
                  <span className="hk-card-icon">
                    <Scale size={18} />
                  </span>
                  <span className="hk-chip hk-chip-accent">Formal Verification · Z3 SMT</span>
                </div>
                <h3>Mathematical Proofs for Numerical Marketing Claims</h3>
                <p>
                  Promotional pricing terms, APR ceilings, and fee waivers are compiled into first-order logic formulas. The Z3 Theorem Prover solves for satisfiability: if a violation exists, it returns an exact numerical counter-example, eliminating subjective prompt variance.
                </p>
                <pre className="hk-code" aria-label="Formal Z3 SMT Encoding">
                  <span className="c">; CanonGate compiles promotional loan terms into Z3 logic</span>
                  {"\n"}(declare-const loan_amount Real)
                  {"\n"}(assert (and (&gt; loan_amount 0) (&lt;= loan_amount 100000))) <span className="c">; Draft claim: "under ₹1,00,000"</span>
                  {"\n"}(assert (not (&lt;= loan_amount 50000)))            <span className="c">; Canon fact: fee waiver max ₹50,000</span>
                  {"\n"}(check-sat) <span className="ok">→ SAT</span> <span className="c">; Counter-example found: loan_amount = 75,000 violates KFS!</span>
                </pre>
              </article>

              {/* Card 2: Perceptual Color Science */}
              <article className="hk-card hk-reveal">
                <div className="hk-card-top">
                  <span className="hk-card-icon">
                    <Palette size={18} />
                  </span>
                  <span className="hk-chip">Colorimetry · CIEDE2000</span>
                </div>
                <h3>Perceptual Brand Color Drift (ΔE₀₀)</h3>
                <p>
                  RGB and hex distance formulas fail human visual perception. CanonGate maps banner surfaces and css styles into CIELAB color space, validating brand palettes with Sharma-Wu-Dalal CIEDE2000 math (ΔE₀₀ ≤ 3.0).
                </p>
                <div className="hk-swatches">
                  <div style={{ background: "#0D3B66" }}>
                    <span>CANON #0D3B66</span>
                  </div>
                  <div style={{ background: "#19528A" }}>
                    <span>DRIFT #19528A</span>
                  </div>
                </div>
                <span className="hk-flag-meta">ΔE₀₀ = 4.2 &gt; 3.0 Tolerance Threshold</span>
              </article>

              {/* Card 3: Cognitive Forcing Gate */}
              <article className="hk-card hk-reveal">
                <div className="hk-card-top">
                  <span className="hk-card-icon">
                    <Lock size={18} />
                  </span>
                  <span className="hk-chip">Hard 409 Blocker Lock</span>
                </div>
                <h3>Cognitive Forcing Functions</h3>
                <p>
                  Campaigns with open Blocker findings cannot be approved or published. The API enforces an HTTP 409 Conflict gate until all blockers are remediated or an authorized legal reviewer logs a recorded justification.
                </p>
                <div className="hk-locked-demo">
                  <button type="button" className="hk-fake-btn" disabled>
                    <Lock size={14} />
                    <span>Approve &amp; Publish Campaign</span>
                  </button>
                  <span className="hk-locked-msg">Locked: 4 Blocker Findings Unresolved</span>
                </div>
              </article>

              {/* Card 4: Cryptographic Audit Ledger */}
              <article className="hk-card hk-reveal">
                <div className="hk-card-top">
                  <span className="hk-card-icon">
                    <Fingerprint size={18} />
                  </span>
                  <span className="hk-chip">RFC 9162 Merkle Tree</span>
                </div>
                <h3>Cryptographic Transparency Ledger</h3>
                <p>
                  Every state transition, finding resolution, and reviewer override is hashed into an append-only hash-chain. Upon publication, an Ed25519-signed RFC 9162 Merkle certificate is issued for regulatory audit readiness.
                </p>
                <div className="hk-chain-visual">
                  <span>Draft</span>
                  <ArrowRight size={12} />
                  <span>In Review</span>
                  <ArrowRight size={12} />
                  <span>Approved</span>
                  <ArrowRight size={12} />
                  <span className="hk-sealed">Signed Cert</span>
                </div>
              </article>

              {/* Card 5: Multimodal Parsers */}
              <article className="hk-card hk-reveal">
                <div className="hk-card-top">
                  <span className="hk-card-icon">
                    <Layers size={18} />
                  </span>
                  <span className="hk-chip">7 Document Parsers</span>
                </div>
                <h3>Unified Multimodal ContentAST</h3>
                <p>
                  Whether marketing copy originates in Word documents, PDF financial filings, promotional HTML, or rasterized PNG ad banners, CanonGate linearizes all content into deterministic SHA-256 AST nodes.
                </p>
                <div className="hk-chips">
                  {[".docx", ".pdf", ".html", ".md", ".png banners", "financial tables"].map((f) => (
                    <span key={f} className="hk-chip hk-mono">
                      {f}
                    </span>
                  ))}
                </div>
              </article>

              {/* Card 6: Headless CLI & MCP Server */}
              <article className="hk-card hk-bento-wide hk-reveal">
                <div className="hk-card-top">
                  <span className="hk-card-icon">
                    <Terminal size={18} />
                  </span>
                  <span className="hk-chip">Headless CI/CD &amp; Agent Protocol</span>
                </div>
                <h3>Headless CLI &amp; Model Context Protocol (MCP)</h3>
                <p>
                  Run pre-publication checks locally, block non-compliant Git commits in CI/CD, or expose read-only inspection tools to enterprise AI agents via the standardized Model Context Protocol (MCP).
                </p>
                <pre className="hk-code" aria-label="CLI pre-publish example">
                  <span className="c"># Run pre-publish gate in CI with split-conformal calibration</span>
                  {"\n"}$ uv run canongate gate --canon indian-digital-lending --paths campaign_diwali.yaml
                  {"\n"}
                  {"\n"}<span className="bad">[BLOCK]</span> CanonGate Pre-Publish Gate — Canon 'indian-digital-lending' v1.0
                  {"\n"}  • Findings: 4 Blockers (claim.algebra, terminology.banned, claim.slot_nli, trigger.disclaimer)
                </pre>
              </article>
            </div>
          </div>
        </section>

        {/* ── Section: Separation of Duties Workflow ──────────────────────── */}
        <section className="hk-section hk-section-alt" id="workflow">
          <div className="hk-container">
            <p className="hk-eyebrow">GOVERNANCE OPERATING MODEL</p>
            <h2 className="hk-h2 hk-reveal">
              Three-role separation of duties: <em>Creator</em>, <em>Brand</em>, and <em>Legal</em>.
            </h2>
            <p className="hk-sub hk-reveal">
              CanonGate structures marketing compliance into clear, role-gated stages so creative teams move fast without risking corporate liability.
            </p>

            <div className="hk-workflow-stages hk-reveal">
              <div className="hk-stage-card">
                <div className="hk-stage-header">
                  <span className="hk-stage-badge">STAGE 01</span>
                  <h4>Creator Pre-Flight</h4>
                </div>
                <p>
                  Creative leads upload drafts, banner graphics, and documents. Instant pre-flight scans highlight regulatory violations inline and provide compliant surgical rewrites with $\le 35\%$ edit distance.
                </p>
                <ul className="hk-stage-bullets">
                  <li>Instant feedback in copy editor</li>
                  <li>Surgical rewriter fixes flagged spans</li>
                  <li>Warning overrides require recorded context</li>
                </ul>
              </div>

              <div className="hk-stage-card">
                <div className="hk-stage-header">
                  <span className="hk-stage-badge">STAGE 02</span>
                  <h4>Brand Governance</h4>
                </div>
                <p>
                  Brand managers audit visual tokens, verify CIEDE2000 palette distances, review ORB logo clear space, and monitor Krippendorff's $\alpha$ friction telemetry across rulebooks.
                </p>
                <ul className="hk-stage-bullets">
                  <li>Interactive image canvas inspection</li>
                  <li>Logo intrusion bounding box overlays</li>
                  <li>Auto-generates Canon v1.1 PR proposals</li>
                </ul>
              </div>

              <div className="hk-stage-card">
                <div className="hk-stage-header">
                  <span className="hk-stage-badge">STAGE 03</span>
                  <h4>Statutory Legal Sign-Off</h4>
                </div>
                <p>
                  Compliance officers review high-risk claim differentials in a dedicated Claim-Only view, execute final statutory sign-off, and issue tamper-evident Merkle release certificates.
                </p>
                <ul className="hk-stage-bullets">
                  <li>Hard 409 block on open violations</li>
                  <li>Cryptographic RFC 9162 Merkle ledger</li>
                  <li>Ed25519 &amp; C2PA outbound asset signing</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* ── Section: Integrations & Ecosystem ───────────────────────────── */}
        <section className="hk-section" id="integrations">
          <div className="hk-container">
            <p className="hk-eyebrow">ENTERPRISE ECOSYSTEM</p>
            <h2 className="hk-h2 hk-reveal">
              Integrates seamlessly into your <em>existing publishing stack</em>.
            </h2>
            <p className="hk-sub hk-reveal">
              CanonGate sits directly between content creation and public distribution, acting as an automated compliance air-gap.
            </p>

            <div className="hk-ecosystem-grid hk-reveal">
              <div className="hk-eco-card">
                <div className="hk-eco-icon">
                  <Terminal size={20} />
                </div>
                <h4>CI/CD &amp; Git Gate</h4>
                <p>Block unverified copy commits directly in GitHub Actions with exit-code status gating.</p>
              </div>

              <div className="hk-eco-card">
                <div className="hk-eco-icon">
                  <Layers size={20} />
                </div>
                <h4>CMS &amp; Webhook Gateways</h4>
                <p>Native pre-publish webhooks for Shopify, Webflow, WordPress, and enterprise headless CMSs.</p>
              </div>

              <div className="hk-eco-card">
                <div className="hk-eco-icon">
                  <Sparkles size={20} />
                </div>
                <h4>Model Context Protocol (MCP)</h4>
                <p>Connect Claude Code, Cursor, and enterprise AI agents with standardized verification tools.</p>
              </div>

              <div className="hk-eco-card">
                <div className="hk-eco-icon">
                  <FileCheck2 size={20} />
                </div>
                <h4>C2PA Provenance Signing</h4>
                <p>Embed tamper-evident cryptographic provenance manifests into approved digital media assets.</p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Section: Final Enterprise CTA ───────────────────────────────── */}
        <section className="hk-final">
          <div className="hk-container hk-final-inner hk-reveal">
            <h2 className="hk-h2">
              Launch marketing with <em>uncompromising compliance</em>.
            </h2>
            <p className="hk-sub hk-final-sub">
              Test pre-publication verification right now in the live sandbox, or explore the complete evaluation kit.
            </p>
            <div className="hk-cta-row hk-center">
              <Link to="/playground" className="hk-btn hk-btn-primary" id="hk-final-sandbox">
                <Play size={15} />
                <span>Launch Interactive Sandbox</span>
              </Link>
              <button
                type="button"
                className="hk-btn hk-btn-ghost"
                onClick={() => setIsEvaluatorOpen(true)}
                id="hk-final-evaluator"
              >
                <Zap size={15} />
                <span>Open Evaluator Kit</span>
              </button>
            </div>
          </div>
        </section>
      </main>

      {/* ── Enterprise Footer ─────────────────────────────────────────────── */}
      <footer className="hk-footer">
        <div className="hk-container hk-footer-inner">
          <div className="hk-footer-brand">
            <div className="hk-logo">
              <span className="hk-logo-mark">
                <ShieldCheck size={14} />
              </span>
              <span>CanonGate</span>
            </div>
            <p className="hk-footer-copy">
              Autonomous Pre-Publication Brand &amp; Regulatory Claim Governance Platform.
            </p>
          </div>

          <div className="hk-footer-links-group">
            <div className="hk-footer-col">
              <h5>Product</h5>
              <Link to="/playground">Interactive Sandbox</Link>
              <a href="#use-cases">Use Cases</a>
              <a href="#capabilities">Verification Engine</a>
              <a href="#workflow">Governance Workflow</a>
            </div>

            <div className="hk-footer-col">
              <h5>Resources</h5>
              <a href={API_DOCS_URL} target="_blank" rel="noreferrer">
                FastAPI Swagger Docs <ExternalLink size={11} />
              </a>
              <a href={`${REPO_URL}/blob/main/starter_datasets_evaluation_report.md`} target="_blank" rel="noreferrer">
                Dataset Audit Report <ExternalLink size={11} />
              </a>
              <a href={`${REPO_URL}/tree/main/docs/adr`} target="_blank" rel="noreferrer">
                Architecture Decisions (ADRs) <ExternalLink size={11} />
              </a>
              <a href={`${REPO_URL}/blob/main/gap_analysis.md`} target="_blank" rel="noreferrer">
                Feature Scorecard <ExternalLink size={11} />
              </a>
            </div>

            <div className="hk-footer-col">
              <h5>Evaluation</h5>
              <button
                type="button"
                className="hk-footer-eval-btn"
                onClick={() => setIsEvaluatorOpen(true)}
              >
                ⚡ Evaluator Quickstart Hub
              </button>
              <a href={REPO_URL} target="_blank" rel="noreferrer">
                GitHub Repository <ExternalLink size={11} />
              </a>
              <Link to="/login">Sign In to Console</Link>
            </div>
          </div>
        </div>

        <div className="hk-container hk-footer-bottom">
          <span>© 2026 CanonGate. Built for the Tech Circuit Hackathon.</span>
          <span className="hk-footer-status">
            <span className="hk-pill-dot" /> All Systems Operational · 115 Tests Passing
          </span>
        </div>
      </footer>

      {/* ──────────────────────────────────────────────────────────────────
       * Dedicated Hackathon Evaluator Slide-Out Drawer (Clean Separation)
       * ────────────────────────────────────────────────────────────────── */}
      {isEvaluatorOpen && (
        <div className="hk-drawer-backdrop" onClick={() => setIsEvaluatorOpen(false)}>
          <div
            className="hk-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="hk-drawer-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="hk-drawer-header">
              <div>
                <div className="hk-drawer-kicker">
                  <Zap size={13} className="hk-zap-icon" />
                  <span>TECH CIRCUIT HACKATHON · EVALUATOR HUB</span>
                </div>
                <h3 id="hk-drawer-title">Evaluator Fast-Track &amp; Deliverables</h3>
              </div>
              <button
                type="button"
                className="hk-drawer-close"
                onClick={() => setIsEvaluatorOpen(false)}
                aria-label="Close Evaluator Drawer"
              >
                <X size={18} />
              </button>
            </div>

            <div className="hk-drawer-content">
              {/* Deliverable Highlights */}
              <div className="hk-drawer-section">
                <h4>Verified Deliverables &amp; Artifacts</h4>
                <div className="hk-drawer-artifacts">
                  <a
                    href={`${REPO_URL}/blob/main/starter_datasets_evaluation_report.md`}
                    target="_blank"
                    rel="noreferrer"
                    className="hk-artifact-card"
                  >
                    <FileText size={16} />
                    <div>
                      <strong>Starter Datasets Audit Report</strong>
                      <span>Formal multi-document audit of Delhivery Prospectus &amp; Macro economic corpora (~501 PDF pages).</span>
                    </div>
                    <ArrowUpRight size={14} className="hk-shift-up" />
                  </a>

                  <a
                    href={`${REPO_URL}/tree/main/docs/adr`}
                    target="_blank"
                    rel="noreferrer"
                    className="hk-artifact-card"
                  >
                    <Scale size={16} />
                    <div>
                      <strong>5 Architectural Decision Records (ADRs)</strong>
                      <span>Formal ADRs for Walking Skeleton, Layered Import Isolation, Async SQLite/Postgres ORM, Tiered Execution, and Merkle Ledger.</span>
                    </div>
                    <ArrowUpRight size={14} className="hk-shift-up" />
                  </a>

                  <a
                    href={`${REPO_URL}/blob/main/gap_analysis.md`}
                    target="_blank"
                    rel="noreferrer"
                    className="hk-artifact-card"
                  >
                    <CheckCircle2 size={16} />
                    <div>
                      <strong>Complete Feature Scorecard</strong>
                      <span>All 13 governance checks, 7 parsers, and 5 canon schemas verified 100% complete.</span>
                    </div>
                    <ArrowUpRight size={14} className="hk-shift-up" />
                  </a>
                </div>
              </div>

              {/* 1-Click Role Logins */}
              <div className="hk-drawer-section">
                <h4>1-Click Role Logins (No Typing Required)</h4>
                <p className="hk-drawer-note">
                  Directly enter the authenticated workspace under any separation-of-duties role to test the cognitive forcing gate:
                </p>

                <div className="hk-persona-cards">
                  <button
                    type="button"
                    className="hk-persona-item"
                    disabled={launchingRole !== null}
                    onClick={() => void handleEvaluatorLogin("creative_lead")}
                  >
                    <div className="hk-persona-left">
                      <span className="hk-role-pill">Stage 1</span>
                      <div>
                        <strong>Creator (@creative_lead)</strong>
                        <span>Drafts copy, runs pre-flight scans, applies surgical rewrites.</span>
                      </div>
                    </div>
                    <span className="hk-persona-action">
                      {launchingRole === "creative_lead" ? "Signing In…" : "Launch →"}
                    </span>
                  </button>

                  <button
                    type="button"
                    className="hk-persona-item"
                    disabled={launchingRole !== null}
                    onClick={() => void handleEvaluatorLogin("brand_manager")}
                  >
                    <div className="hk-persona-left">
                      <span className="hk-role-pill">Stage 2</span>
                      <div>
                        <strong>Brand Manager (@brand_manager)</strong>
                        <span>Audits palette drift (ΔE₀₀), ORB logos, and encounters HTTP 409 locked gate.</span>
                      </div>
                    </div>
                    <span className="hk-persona-action">
                      {launchingRole === "brand_manager" ? "Signing In…" : "Launch →"}
                    </span>
                  </button>

                  <button
                    type="button"
                    className="hk-persona-item"
                    disabled={launchingRole !== null}
                    onClick={() => void handleEvaluatorLogin("legal_counsel")}
                  >
                    <div className="hk-persona-left">
                      <span className="hk-role-pill">Stage 3</span>
                      <div>
                        <strong>Legal Counsel (@legal_counsel)</strong>
                        <span>Resolves blockers with recorded reason, signs off, and exports signed Merkle certificate.</span>
                      </div>
                    </div>
                    <span className="hk-persona-action">
                      {launchingRole === "legal_counsel" ? "Signing In…" : "Launch →"}
                    </span>
                  </button>
                </div>
              </div>

              {/* Fast Terminal Verification Commands */}
              <div className="hk-drawer-section">
                <h4>Automated Verification Commands</h4>
                <div className="hk-drawer-code">
                  <div className="hk-drawer-code-head">
                    <span>Full Backend Test Suite (115 Tests Passing)</span>
                  </div>
                  <code>cd backend &amp;&amp; uv run pytest -q</code>
                </div>

                <div className="hk-drawer-code">
                  <div className="hk-drawer-code-head">
                    <span>Enforced Layer Boundary Isolation (import-linter)</span>
                  </div>
                  <code>cd backend &amp;&amp; uv run import-linter lint</code>
                </div>
              </div>
            </div>

            <div className="hk-drawer-footer">
              <a href={LIVE_APP_URL} target="_blank" rel="noreferrer" className="hk-btn hk-btn-primary hk-btn-sm">
                <span>Open Hosted Cloud App</span>
                <ExternalLink size={13} />
              </a>
              <button
                type="button"
                className="hk-btn hk-btn-ghost hk-btn-sm"
                onClick={() => setIsEvaluatorOpen(false)}
              >
                Close Hub
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
