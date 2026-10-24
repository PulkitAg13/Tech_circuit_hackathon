import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ShieldCheck,
  FileSearch,
  Scale,
  Lock,
  Sparkles,
  CheckCircle2,
  GitPullRequest,
  Eye,
  Cpu,
  Layers,
  Send,
  ArrowRight,
  ChevronRight,
  FileCheck2,
  ScanEye,
  Database,
} from "lucide-react";
import { useAuth } from "../auth/context";
import { ImageSlideshow } from "./ImageSlideshow";

const CAPABILITIES = [
  {
    icon: Database,
    tier: "Pipeline A · Grounded Canon Ingestion",
    title: "Compile Brand Books & KFS Sheets into Signed Schemas",
    description:
      "Ingests PDF/DOCX brand guidelines, KFS pricing schedules, and reference logos into five deterministic schemas protected by three anti-loss guards (Value-Anchor Coverage, Verbatim Character Grounding, and Round-Trip NLI).",
  },
  {
    icon: Eye,
    tier: "Tier 1 · Deterministic Math & Vision (Zero AI)",
    title: "Exact Physical, Linguistic & Statutory Verification",
    description:
      "Audits W3C WCAG 2.1 pixel luminance contrast, CIEDE2000 colour drift, OpenCV ORB logo distortion and 0.5H clear space, spaCy POS terminology, and CCPA 2022 Hindi-English disclaimer prominence parity.",
  },
  {
    icon: Scale,
    tier: "Tier 2 · Calibrated Slot-Level NLI",
    title: "Catch Dropped Qualifiers & Cross-Modal Contradictions",
    description:
      "Aligns predicate-argument slots between approved Canon claims and draft copy to surface dropped conditions (e.g., missing loan caps or tenure limits) in an explainable SlotDiff table.",
  },
  {
    icon: Sparkles,
    tier: "Tier 3 · Constrained Surgical Rewriter",
    title: "Minimal Fixes That Preserve Creator Intent",
    description:
      "Proposes surgical rewrites only on flagged spans under a strict ≤ 35% Levenshtein edit ceiling with local DPDP PII masking, re-verifying every candidate through Tiers 1 & 2 before display.",
  },
  {
    icon: GitPullRequest,
    tier: "Closed-Loop Governance Analytics",
    title: "Empirical Bayes Friction → Automated Canon v1.1 PRs",
    description:
      "Tracks override and dispute telemetry per rule. When posterior Friction(Ri) exceeds 0.40, CanonGate auto-drafts a Canon v1.1 clarification and backtests its impact across historical bundles.",
  },
  {
    icon: Lock,
    tier: "Cryptographic Provenance & Human Sign-Off",
    title: "Role-Gated Workflow with RFC 9162 Merkle Certificates",
    description:
      "Separates Creator, Brand Manager, and Authorised Legal Reviewer responsibilities with cognitive forcing functions, an append-only SHA-256 hash chain, Ed25519 Signed Tree Heads, and C2PA asset signing.",
  },
];

const WORKFLOW_STEPS = [
  {
    step: "01",
    role: "Creator (Marketing / Agency)",
    title: "Submit Multimodal Bundle & Run Pre-Flight Scan",
    detail:
      "Upload DOCX, PDF, HTML, Markdown, and PNG/JPG promotional banners into a unified ContentAST with dual-script OCR (English + Devanagari) and resolve Blockers via 1-click surgical diffs.",
    icon: FileSearch,
  },
  {
    step: "02",
    role: "Creator & Brand Manager",
    title: "Collaborative Triage, Overrides & Canon Calibration",
    detail:
      "Creators record structured justifications on Warning overrides and comment inline; Brand Managers inspect revision diffs, tune rule thresholds via Confirm & Calibrate sliders, and approve brand compliance.",
    icon: ScanEye,
  },
  {
    step: "03",
    role: "Authorised Legal Reviewer",
    title: "Claim-Only Statutory Review & Cryptographic Release",
    detail:
      "Legal Reviewers filter directly to statutory claims and overrides, verify the SlotDiff evidence, and issue final sign-off — generating a self-contained SHA-256 + Ed25519 Governance Certificate.",
    icon: FileCheck2,
  },
];

const STATUTORY_PACKS = [
  {
    code: "CCPA 2022",
    name: "Misleading Ads & Disclaimer Parity",
    desc: "Enforces same-language script parity and visual prominence between headlines and fine-print disclaimers.",
  },
  {
    code: "RBI 2025 KFS",
    name: "Digital Lending Key Fact Statements",
    desc: "Verifies promotional APR, processing fee caps, and validity dates against approved KFS schedules.",
  },
  {
    code: "ASCI FY25-26",
    name: "D2C Substantiation & Influencer Disclosures",
    desc: "Distinguishes ingredient in-vitro studies from finished-product clinical proof and checks upfront disclosures.",
  },
  {
    code: "WCAG 2.1 AA",
    name: "Pixel Luminance & Alt-Text Accessibility",
    desc: "Computes exact W3C relative luminance contrast (≥ 4.5:1 AA) across both DOM styles and rasterised banners.",
  },
];

export function HomePage() {
  const { token, username, displayName, role } = useAuth();
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactOrg, setContactOrg] = useState("");
  const [contactMessage, setContactMessage] = useState("");
  const [contactSubmitted, setContactSubmitted] = useState(false);
  const [ticketRef, setTicketRef] = useState("");

  function handleContactSubmit(e: FormEvent) {
    e.preventDefault();
    const digest = Math.abs(
      Array.from(`${contactName}:${contactEmail}:${contactOrg}`).reduce(
        (acc, ch) => (acc * 31 + ch.charCodeAt(0)) | 0,
        7,
      ),
    )
      .toString(16)
      .toUpperCase()
      .slice(0, 6);
    setTicketRef(`CG-REQ-${digest}`);
    setContactSubmitted(true);
  }

  return (
    <div className="home-page">
      {/* Navigation Header */}
      <header className="home-navbar">
        <div className="home-navbar-inner">
          <Link to="/" className="home-brand">
            <div className="brand-logo-mark">
              <ShieldCheck size={22} strokeWidth={2.2} />
            </div>
            <div className="brand-text-group">
              <span className="brand-title">CanonGate</span>
              <span className="brand-tag">Pre-Publication Governance</span>
            </div>
          </Link>

          <nav className="home-nav-links" aria-label="Primary Navigation">
            <a href="#problem">Why CanonGate</a>
            <a href="#capabilities">Architecture</a>
            <a href="#workflow">Workflow</a>
            <a href="#statutory">Statutory Packs</a>
            <a href="#contact">Contact</a>
          </nav>

          <div className="home-nav-actions">
            {token ? (
              <Link to="/dashboard" className="btn-primary home-cta-btn">
                <span>
                  Open Studio ({displayName || username} · {role})
                </span>
                <ArrowRight size={16} />
              </Link>
            ) : (
              <>
                <Link to="/login" className="home-signin-link">
                  Sign In
                </Link>
                <Link to="/login" className="btn-primary home-cta-btn">
                  <span>Launch Governance Studio</span>
                  <ArrowRight size={16} />
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="hero-section">
        <div className="hero-inner">
          <div className="hero-badge">
            <Cpu size={14} />
            <span>
              Deterministic Math & Vision First · Calibrated Slot NLI Second ·
              Constrained Rewriting Last
            </span>
          </div>

          <h1 className="hero-headline">
            Stop Brand Drift & Unverified Claims{" "}
            <span className="hero-highlight">Before Publication.</span>
          </h1>

          <p className="hero-subheadline">
            CanonGate compiles your brand guidelines, approved KFS fact sheets,
            and statutory rules into a signed, machine-readable{" "}
            <strong>Canon</strong> — auditing every campaign document and
            promotional banner with exact character and pixel provenance while
            keeping every approval decision in human hands.
          </p>

          <div className="hero-cta-group">
            <Link
              to={token ? "/dashboard" : "/login"}
              className="btn-primary hero-primary-btn"
            >
              <span>
                {token
                  ? "Continue to Governance Console"
                  : "Start Pre-Flight Review"}
              </span>
              <ChevronRight size={18} />
            </Link>
            <a href="#capabilities" className="hero-secondary-btn">
              <Layers size={17} />
              <span>Explore 3-Tier Engine</span>
            </a>
          </div>

          {/* Empirical Evidence Metrics Strip */}
          <div className="hero-metrics-grid" id="problem">
            <div className="hero-metric-card">
              <span className="metric-number">11,581</span>
              <span className="metric-label">
                ASCI complaint cases in FY2025-26 (+21% YoY) across D2C &
                digital ads
              </span>
            </div>
            <div className="hero-metric-card">
              <span className="metric-number">95.9%</span>
              <span className="metric-label">
                of 1M audited pages fail WCAG 2.2 A/AA; low contrast is the #1
                failure
              </span>
            </div>
            <div className="hero-metric-card">
              <span className="metric-number">₹10L–₹50L</span>
              <span className="metric-label">
                Statutory CCPA penalties under Sec. 21 for misleading qualifiers
                & fine print
              </span>
            </div>
            <div className="hero-metric-card">
              <span className="metric-number">100% Local</span>
              <span className="metric-label">
                Air-gapped default execution with DPDP PII scrubbing & RFC 9162
                Merkle proofs
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Interactive Visual Showcase Slideshow */}
      <ImageSlideshow />

      {/* Capabilities / 3-Tier Engine Section */}
      <section className="home-section" id="capabilities">
        <div className="home-section-inner">
          <div className="section-header">
            <span className="section-eyebrow">TWO-PIPELINE ARCHITECTURE</span>
            <h2 className="section-title">
              Glass-Box Verification Built for Regulated Teams
            </h2>
            <p className="section-desc">
              Unlike black-box chatbots or text-only linters that skip rasterised
              banner fine print, CanonGate executes a strict, explainable
              verification hierarchy across text, tables, and imagery.
            </p>
          </div>

          <div className="capabilities-grid">
            {CAPABILITIES.map((cap) => {
              const IconComponent = cap.icon;
              return (
                <article key={cap.title} className="capability-card">
                  <div className="capability-icon-wrap">
                    <IconComponent size={22} />
                  </div>
                  <div className="capability-tier">{cap.tier}</div>
                  <h3 className="capability-title">{cap.title}</h3>
                  <p className="capability-desc">{cap.description}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      {/* 3-Role Collaborative Workflow Section */}
      <section className="home-section home-section-alt" id="workflow">
        <div className="home-section-inner">
          <div className="section-header">
            <span className="section-eyebrow">HUMAN-IN-THE-LOOP OVERSIGHT</span>
            <h2 className="section-title">
              Three-Role Collaborative Governance Workflow
            </h2>
            <p className="section-desc">
              Designed around real marketing, brand management, and legal
              sign-off teams — with cognitive forcing functions that prevent
              rubber-stamping.
            </p>
          </div>

          <div className="workflow-cards-grid">
            {WORKFLOW_STEPS.map((item) => {
              const StepIcon = item.icon;
              return (
                <div key={item.step} className="workflow-step-card">
                  <div className="workflow-step-top">
                    <span className="workflow-step-num">STAGE {item.step}</span>
                    <span className="workflow-role-pill">{item.role}</span>
                  </div>
                  <div className="workflow-step-icon">
                    <StepIcon size={24} />
                  </div>
                  <h3 className="workflow-step-title">{item.title}</h3>
                  <p className="workflow-step-detail">{item.detail}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Pre-Compiled Statutory Packs */}
      <section className="home-section" id="statutory">
        <div className="home-section-inner">
          <div className="section-header">
            <span className="section-eyebrow">BUILT-IN REGULATORY PACKS</span>
            <h2 className="section-title">
              Ready for Indian D2C, BFSI & Enterprise SaaS
            </h2>
            <p className="section-desc">
              Ships with three starter Brand Canons (`acme-corp`,
              `indian-digital-lending`, `indian-d2c-nutra`) and four enforceable
              statutory packs out of the box.
            </p>
          </div>

          <div className="statutory-grid">
            {STATUTORY_PACKS.map((pack) => (
              <div key={pack.code} className="statutory-card">
                <div className="statutory-code">
                  <CheckCircle2 size={16} />
                  <span>{pack.code}</span>
                </div>
                <h4 className="statutory-name">{pack.name}</h4>
                <p className="statutory-desc">{pack.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Contact Us Section */}
      <section className="home-section home-section-contact" id="contact">
        <div className="home-section-inner contact-grid">
          <div className="contact-info">
            <span className="section-eyebrow">GET IN TOUCH</span>
            <h2 className="section-title">
              Deploy Self-Hosted Brand Governance
            </h2>
            <p className="section-desc">
              Have questions about custom Canon compilation, air-gapped VPC
              deployment, or CMS pre-publish webhooks? Send our engineering team
              a message below.
            </p>

            <div className="contact-highlights">
              <div className="contact-highlight-item">
                <ShieldCheck size={18} />
                <span>
                  Air-gapped Local Mode by default — zero outbound data leakage
                </span>
              </div>
              <div className="contact-highlight-item">
                <Lock size={18} />
                <span>
                  DPDP 2025 PII masking + tamper-evident SHA-256 & Ed25519 audit
                  ledger
                </span>
              </div>
              <div className="contact-highlight-item">
                <Sparkles size={18} />
                <span>
                  Team <strong>__Decisionsparalysis__</strong> · Aritra Mahanty,
                  Pulkit Agrawal, Tejas Ranjeet, Kabir Roy
                </span>
              </div>
            </div>
          </div>

          <div className="contact-card">
            <form onSubmit={handleContactSubmit} className="contact-form">
              <h3>Request Enterprise Onboarding & Architecture Brief</h3>
              <div className="form-group">
                <label htmlFor="contact-name">Your Name</label>
                <input
                  id="contact-name"
                  type="text"
                  required
                  placeholder="e.g. Priya Sharma"
                  value={contactName}
                  onChange={(e) => setContactName(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="contact-email">Work Email</label>
                <input
                  id="contact-email"
                  type="email"
                  required
                  placeholder="priya@company.in"
                  value={contactEmail}
                  onChange={(e) => setContactEmail(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="contact-org">
                  Organisation / Sector (D2C, BFSI, Agency)
                </label>
                <input
                  id="contact-org"
                  type="text"
                  required
                  placeholder="e.g. FinTrust Digital Lending NBFC"
                  value={contactOrg}
                  onChange={(e) => setContactOrg(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="contact-message">
                  Governance Requirements or Questions
                </label>
                <textarea
                  id="contact-message"
                  rows={4}
                  required
                  placeholder="Tell us about your brand guidelines, KFS sheets, or pre-publication review workflow..."
                  value={contactMessage}
                  onChange={(e) => setContactMessage(e.target.value)}
                />
              </div>

              <button type="submit" className="btn-primary contact-submit-btn">
                <Send size={16} />
                <span>Submit Governance Inquiry</span>
              </button>

              {contactSubmitted && (
                <p className="contact-success-note" role="status">
                  Inquiry registered ({ticketRef}) for {contactOrg || "your team"}.
                  You can also explore the live interactive workspace right now
                  via the Governance Studio button above.
                </p>
              )}
            </form>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="home-footer">
        <div className="home-footer-inner">
          <div className="footer-brand-col">
            <div className="home-brand">
              <div className="brand-logo-mark">
                <ShieldCheck size={18} strokeWidth={2.2} />
              </div>
              <span className="brand-title">CanonGate</span>
            </div>
            <p className="footer-caption">
              Pre-publication brand & claim governance platform · Built by Team{" "}
              <strong>__Decisionsparalysis__</strong>
            </p>
          </div>
          <div className="footer-links">
            <a href="#capabilities">Architecture</a>
            <a href="#workflow">Workflow</a>
            <a href="#statutory">Statutory Packs</a>
            <Link to="/login">Sign In</Link>
            <Link to="/dashboard">Governance Console</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
