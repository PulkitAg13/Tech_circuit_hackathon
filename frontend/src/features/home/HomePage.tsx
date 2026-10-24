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
  Send,
  ArrowRight,
  ChevronRight,
  FileCheck2,
  ScanEye,
  Database,
} from "lucide-react";
import { useAuth } from "../auth/context";

const CAPABILITIES = [
  {
    icon: Database,
    category: "Single Source of Truth",
    title: "Centralised Brand & Claim Playbooks",
    description:
      "Import your brand guidelines, approved product claims, pricing schedules, and visual standards into one structured playbook so every team and agency reviews against the latest rules.",
  },
  {
    icon: Eye,
    category: "Copy, Documents & Banners",
    title: "Multimodal Pre-Publication Review",
    description:
      "Audit campaign copy, Word and PDF brochures, landing pages, and promotional banners — including fine-print disclaimers inside images — before anything goes live.",
  },
  {
    icon: Scale,
    category: "Claim & Disclosure Accuracy",
    title: "Catch Missing Conditions & Expired Offers",
    description:
      "Automatically compare draft claims against your approved fact sheets to flag dropped qualifiers, outdated promotional dates, unverified numbers, and missing disclosures.",
  },
  {
    icon: ScanEye,
    category: "Visual & Accessibility Standards",
    title: "Brand Palette, Logo & Contrast Checks",
    description:
      "Verify brand colour accuracy, logo proportions and clear space, image alt-text completeness, and WCAG contrast legibility across both web copy and ad creatives.",
  },
  {
    icon: Sparkles,
    category: "Contextual Remediation",
    title: "One-Click Brand-Safe Rewrite Suggestions",
    description:
      "Resolve flagged phrases in one click with minimal, context-aware rewrites that preserve your writer's original intent while keeping confidential material private.",
  },
  {
    icon: GitPullRequest,
    category: "Continuous Governance Insights",
    title: "Spot Recurring Mistakes & Unclear Guidelines",
    description:
      "Track which rules trigger the most review friction or overrides over time so brand managers can clarify ambiguous guidelines and reduce review bottlenecks.",
  },
];

const WORKFLOW_STEPS = [
  {
    step: "01",
    role: "Creator (Marketing / Agency)",
    title: "Upload Campaign & Run Pre-Flight Check",
    detail:
      "Upload documents, landing page copy, and promotional banners to get instant, actionable feedback on claims, tone, visuals, and accessibility — and apply one-click fixes.",
    icon: FileSearch,
  },
  {
    step: "02",
    role: "Creator & Brand Manager",
    title: "Collaborate, Review Revisions & Calibrate Rules",
    detail:
      "Creators can document context when overriding non-blocking warnings; Brand Managers review version diffs, fine-tune guideline thresholds, and approve brand readiness.",
    icon: ScanEye,
  },
  {
    step: "03",
    role: "Authorised Legal Reviewer",
    title: "Focused Claim Sign-Off & Release Certificate",
    detail:
      "Legal and compliance reviewers filter directly to high-risk claims, disclosures, and overrides, issuing final sign-off backed by a verifiable audit trail.",
    icon: FileCheck2,
  },
];

const STATUTORY_PACKS = [
  {
    code: "CCPA 2022",
    name: "Misleading Ads & Disclaimer Parity",
    desc: "Checks that disclaimers do not contradict main claims and match the headline's language and visual prominence.",
  },
  {
    code: "RBI 2025 KFS",
    name: "Digital Lending Key Fact Statements",
    desc: "Verifies promotional APR, processing fee caps, and offer validity dates against approved Key Fact Statements.",
  },
  {
    code: "ASCI FY25-26",
    name: "D2C Substantiation & Influencer Disclosures",
    desc: "Distinguishes ingredient studies from finished-product clinical proof and checks upfront partnership disclosures.",
  },
  {
    code: "WCAG 2.1 AA",
    name: "Contrast & Accessibility Compliance",
    desc: "Verifies text legibility (≥ 4.5:1 contrast ratio) and image alt-text across documents, web pages, and banners.",
  },
];

const INTERACTIVE_PREVIEWS = [
  {
    id: "bfsi",
    label: "Digital Lending & BFSI",
    playbook: "Indian Digital Lending Playbook",
    draftSnippet:
      "Get a 0% processing fee on personal loans today with guaranteed approval in 5 minutes!",
    flaggedSpan: "0% processing fee on personal loans today",
    issueType: "BLOCKER · Missing Mandatory Condition",
    approvedFact:
      "0% processing fee applies to personal loans under ₹50,000 for first-time borrowers (valid until 30 Sep 2026).",
    suggestedFix:
      "Get a 0% processing fee on personal loans under ₹50,000 for first-time borrowers today!",
  },
  {
    id: "d2c",
    label: "D2C Personal Care & Wellness",
    playbook: "Indian D2C & ASCI Playbook",
    draftSnippet:
      "Clinically proven to regrow 23,800 hair strands in 30 days with 100% natural Rosemary extract.",
    flaggedSpan: "Clinically proven to regrow 23,800 hair strands",
    issueType: "BLOCKER · Claim Substantiation Mismatch",
    approvedFact:
      "Clinical study applies to the active ingredient in vitro; finished product supports healthier-looking hair with regular use.",
    suggestedFix:
      "Formulated with Rosemary extract shown in ingredient studies to support fuller, healthier-looking hair.",
  },
  {
    id: "saas",
    label: "Enterprise B2B & SaaS",
    playbook: "Acme Enterprise Brand Playbook",
    draftSnippet:
      "Buy our cheap cloud security plan so your users can deploy faster with zero setup.",
    flaggedSpan: "cheap cloud security plan so your users",
    issueType: "WARNING · Brand Voice & Terminology",
    approvedFact:
      "Use 'cost-effective' or 'affordable' instead of 'cheap', and refer to 'customers' or 'teams' rather than 'users'.",
    suggestedFix:
      "Purchase our cost-effective cloud security plan so your teams can deploy faster with zero setup.",
  },
] as const;

export function HomePage() {
  const { token, username, displayName, role } = useAuth();
  const [activePreviewId, setActivePreviewId] = useState<string>("bfsi");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactOrg, setContactOrg] = useState("");
  const [contactMessage, setContactMessage] = useState("");
  const [contactSubmitted, setContactSubmitted] = useState(false);
  const [ticketRef, setTicketRef] = useState("");

  const activePreview =
    INTERACTIVE_PREVIEWS.find((p) => p.id === activePreviewId) ??
    INTERACTIVE_PREVIEWS[0];

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
              <span className="brand-tag">Pre-Publication Brand Governance</span>
            </div>
          </Link>

          <nav className="home-nav-links" aria-label="Primary Navigation">
            <a href="#problem">Why CanonGate</a>
            <a href="#capabilities">Capabilities</a>
            <a href="#workflow">Workflow</a>
            <a href="#statutory">Regulatory Packs</a>
            <a href="#contact">Contact</a>
          </nav>

          <div className="home-nav-actions">
            {token ? (
              <Link to="/dashboard" className="btn-primary home-cta-btn">
                <span>
                  Open Workspace ({displayName || username} · {role})
                </span>
                <ArrowRight size={16} />
              </Link>
            ) : (
              <>
                <Link to="/login" className="home-signin-link">
                  Sign In
                </Link>
                <Link to="/login" className="btn-primary home-cta-btn">
                  <span>Start Campaign Review</span>
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
            <ShieldCheck size={14} />
            <span>
              Pre-Publication Brand, Claim &amp; Visual Governance for Modern
              Teams
            </span>
          </div>

          <h1 className="hero-headline">
            Catch Off-Brand Visuals &amp; Unverified Claims{" "}
            <span className="hero-highlight">Before You Publish.</span>
          </h1>

          <p className="hero-subheadline">
            CanonGate checks your marketing copy, brochures, landing pages, and
            promotional banners against your approved brand guidelines, product
            facts, and regulatory disclosures — explaining every issue and
            suggesting brand-safe fixes while keeping every approval in human
            hands.
          </p>

          <div className="hero-cta-group">
            <Link
              to={token ? "/dashboard" : "/login"}
              className="btn-primary hero-primary-btn"
            >
              <span>
                {token ? "Go to Campaign Workspace" : "Launch Governance Studio"}
              </span>
              <ChevronRight size={18} />
            </Link>
            <a href="#workflow" className="hero-secondary-btn">
              <span>See How Teams Collaborate</span>
            </a>
          </div>

          {/* Interactive Live Product Preview Window (replaces broken static slides) */}
          <div className="hero-studio-preview">
            <div className="hero-preview-topbar">
              <div className="preview-window-dots">
                <span className="win-dot dot-red" />
                <span className="win-dot dot-amber" />
                <span className="win-dot dot-green" />
                <span className="preview-window-title">
                  Live Pre-Publication Review Preview — {activePreview.playbook}
                </span>
              </div>
              <div className="preview-sector-tabs">
                {INTERACTIVE_PREVIEWS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`preview-sector-tab ${
                      activePreviewId === item.id ? "active" : ""
                    }`}
                    onClick={() => setActivePreviewId(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="hero-preview-body">
              <div className="preview-draft-col">
                <div className="preview-col-label">
                  1 · Campaign Draft Submitted by Creator
                </div>
                <div className="preview-draft-box">
                  <p>
                    {activePreview.draftSnippet
                      .split(activePreview.flaggedSpan)
                      .map((part, idx, arr) => (
                        <span key={idx}>
                          {part}
                          {idx < arr.length - 1 && (
                            <mark className="preview-highlight-mark">
                              {activePreview.flaggedSpan}
                            </mark>
                          )}
                        </span>
                      ))}
                  </p>
                </div>
                <div className="preview-fix-box">
                  <span className="preview-fix-badge">
                    ✓ Suggested Brand-Safe Fix
                  </span>
                  <p>{activePreview.suggestedFix}</p>
                </div>
              </div>

              <div className="preview-finding-col">
                <div className="preview-col-label">
                  2 · Explainable Governance Finding &amp; Source Rule
                </div>
                <div className="preview-finding-card">
                  <div className="preview-finding-badge">
                    {activePreview.issueType}
                  </div>
                  <div className="preview-rule-box">
                    <strong>Approved Source Guideline:</strong>{" "}
                    {activePreview.approvedFact}
                  </div>
                  <div className="preview-actions-row">
                    <span className="preview-action-pill primary">
                      ✓ Accept &amp; Apply Fix
                    </span>
                    <span className="preview-action-pill">
                      💬 Add Review Note
                    </span>
                    <span className="preview-action-pill">
                      Forward to Brand &amp; Legal Sign-Off →
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Empirical Industry Evidence Strip */}
          <div className="hero-metrics-grid" id="problem">
            <div className="hero-metric-card">
              <span className="metric-number">11,581</span>
              <span className="metric-label">
                ASCI ad complaint cases in FY2025-26 (+21% YoY) across digital
                and D2C campaigns
              </span>
            </div>
            <div className="hero-metric-card">
              <span className="metric-number">95.9%</span>
              <span className="metric-label">
                of audited web pages fail WCAG 2.2 A/AA; low text contrast is
                the #1 failure
              </span>
            </div>
            <div className="hero-metric-card">
              <span className="metric-number">₹10L–₹50L</span>
              <span className="metric-label">
                Statutory CCPA penalties for misleading claims and unreadable
                fine-print disclaimers
              </span>
            </div>
            <div className="hero-metric-card">
              <span className="metric-number">100% Private</span>
              <span className="metric-label">
                Self-hostable local execution that keeps pre-launch campaigns
                and pricing sheets inside your workspace
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Platform Capabilities Section */}
      <section className="home-section" id="capabilities">
        <div className="home-section-inner">
          <div className="section-header">
            <span className="section-eyebrow">PLATFORM CAPABILITIES</span>
            <h2 className="section-title">
              Everything You Need to Govern Brand &amp; Claims Before Launch
            </h2>
            <p className="section-desc">
              Instead of rejecting creative work late in the cycle, CanonGate
              gives writers, designers, brand managers, and legal reviewers
              clear explanations and one-click fixes across every format.
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
                  <div className="capability-tier">{cap.category}</div>
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
              sign-off teams — with clear stage ownership and full revision
              history.
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
              Ready for Indian D2C, BFSI &amp; Enterprise SaaS
            </h2>
            <p className="section-desc">
              Ships with starter Brand Playbooks for Digital Lending, D2C
              Personal Care &amp; Nutraceuticals, and Enterprise SaaS alongside
              four enforceable statutory packs out of the box.
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
              Have questions about onboarding your brand guidelines, KFS fact
              sheets, or setting up role-based pre-publication review for your
              team? Send us a note below.
            </p>

            <div className="contact-highlights">
              <div className="contact-highlight-item">
                <ShieldCheck size={18} />
                <span>
                  Self-hosted local execution by default — confidential
                  pre-launch materials stay in your environment
                </span>
              </div>
              <div className="contact-highlight-item">
                <Lock size={18} />
                <span>
                  Automatic PII protection and tamper-evident approval
                  certificates for every released campaign
                </span>
              </div>
              <div className="contact-highlight-item">
                <Sparkles size={18} />
                <span>
                  Onboard PDF/DOCX brand books, colour palettes, and product
                  fact sheets in minutes
                </span>
              </div>
            </div>
          </div>

          <div className="contact-card card">
            <form onSubmit={handleContactSubmit} className="contact-form">
              <h3 className="contact-form-title">
                Request Enterprise Onboarding &amp; Product Walkthrough
              </h3>
              <p className="contact-form-subtitle">
                Tell us about your team and content workflow, and we&apos;ll
                prepare a tailored brand playbook setup.
              </p>

              <div className="form-group">
                <label htmlFor="contact-name">Full Name</label>
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
                  Organisation &amp; Industry (D2C, BFSI, Enterprise, Agency)
                </label>
                <input
                  id="contact-org"
                  type="text"
                  required
                  placeholder="e.g. FinTrust Digital Lending"
                  value={contactOrg}
                  onChange={(e) => setContactOrg(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="contact-message">
                  What content formats or guidelines do you want to govern?
                </label>
                <textarea
                  id="contact-message"
                  rows={4}
                  required
                  placeholder="Tell us about your brand guidelines, product fact sheets, or pre-publication review workflow..."
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
                  Inquiry registered ({ticketRef}) for{" "}
                  {contactOrg || "your team"}. You can also test the live
                  workspace right now via the Start Campaign Review button
                  above.
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
              Intelligent Pre-Publication Brand &amp; Claim Governance Platform
            </p>
          </div>
          <div className="footer-links">
            <a href="#capabilities">Capabilities</a>
            <a href="#workflow">Workflow</a>
            <a href="#statutory">Regulatory Packs</a>
            <Link to="/login">Sign In</Link>
            <Link to="/dashboard">Governance Workspace</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
