import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ImageSlideshow } from "./ImageSlideshow";

const FAQS = [
  {
    q: "What is CanonGate and how does pre-publication governance work?",
    a: "CanonGate is an automated compliance platform that audits marketing campaigns—including ad copy, legal footnotes, and raster banner graphics—against your brand rules and statutory regulations before you spend budget or release campaigns publicly."
  },
  {
    q: "Which regulatory frameworks and statutory standards are supported?",
    a: "CanonGate enforces key Indian and international advertising compliance frameworks, including CCPA 2022 Misleading Advertisements guidelines (PIB 1832906), ASCI FY2025-26 advertising code, RBI Digital Lending Key Fact Statement (KFS) mandates, and W3C WCAG 2.1 AA luminance contrast rules."
  },
  {
    q: "How does the multi-modal inspection check image banners and fine print?",
    a: "Our deterministic vision pipeline extracts rasterized text with pixel bounding boxes, tests contrast ratios with 1-hex precision, verifies logo distortion and 0.5H clear space boundaries, and audits font height against ASCI 26px/1080p prominence and Hindi/English parity guidelines."
  },
  {
    q: "Can marketing and legal teams create custom Brand Canons?",
    a: "Yes. In the Canon Studio, brand stewards can translate brand books, approved product claims, disallowed terminology, and required disclaimers into version-controlled, machine-readable Canons with friction analytics and Krippendorff's alpha calibration."
  },
  {
    q: "How is our campaign data kept confidential and tamper-evident?",
    a: "Evaluations run with local-first, quantized ONNX models ensuring zero neural data leakage. All approvals, overrides, and timestamps are recorded in an append-only SHA-256 audit ledger backed by RFC 9162 Merkle tree transparency proofs."
  },
  {
    q: "How does the role-based workflow work for agencies and creators?",
    a: "Creators receive surgical inline highlights, bounding-box overlays, and suggested copy rewrites under a 35% edit constraint. Compliance reviewers and legal counsel review flagged findings, apply role-gated sign-offs, and export cryptographic Governance Certificates prior to launch."
  }
];

export function HomePage() {
  const navigate = useNavigate();
  const { isAuthenticated, username, role } = useAuth();

  // Contact Form State
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactSubject, setContactSubject] = useState("");
  const [contactMessage, setContactMessage] = useState("");
  const [contactSent, setContactSent] = useState(false);
  const [openFaqIndex, setOpenFaqIndex] = useState<number | null>(0);

  function scrollToContact() {
    const el = document.getElementById("contact");
    if (el) {
      el.scrollIntoView({ behavior: "smooth" });
    }
  }

  function handleContactSubmit(e: FormEvent) {
    e.preventDefault();
    const recipient = "tejas.23bce10419@vitbhopal.ac.in";
    const subject = encodeURIComponent(`[CanonGate Inquiry] ${contactSubject || "New Contact Message"}`);
    const body = encodeURIComponent(
      `Name: ${contactName}\nEmail: ${contactEmail}\nTopic: ${contactSubject}\n\nMessage:\n${contactMessage}`
    );

    window.open(`mailto:${recipient}?subject=${subject}&body=${body}`, "_blank");

    setContactSent(true);
    setContactName("");
    setContactEmail("");
    setContactSubject("");
    setContactMessage("");
  }

  return (
    <div className="home-layout">
      {/* ── Background Geometric Accents (Matching Login Page Theme) ── */}
      <div className="bg-corner-shape-red" aria-hidden="true" />

      {/* ── Curved Floating Header ── */}
      <header className="home-nav-floating nav-slide-in">
        <div className="home-nav-floating-inner">
          <div className="brand-logo" onClick={() => navigate("/")}>
            <div className="brand-shield-icon">
              <svg
                width="20"
                height="20"
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
            <div className="brand-title-wrap">
              <span className="brand-title">CanonGate</span>
              <span className="brand-badge">Governance</span>
            </div>
          </div>

          <div className="nav-actions">
            {isAuthenticated ? (
              <div className="auth-user-bar">
                <span className="user-greeting">
                  <strong>{username}</strong> <span className="role-chip">{role}</span>
                </span>
                <button
                  type="button"
                  className="btn-primary btn-sm"
                  onClick={() => navigate("/dashboard")}
                >
                  Go to Console
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                    <polyline points="12 5 19 12 12 19"></polyline>
                  </svg>
                </button>
              </div>
            ) : (
              <>
                <button
                  type="button"
                  className="btn-ghost btn-sm"
                  onClick={() => navigate("/login", { state: { signup: false } })}
                >
                  Sign In
                </button>
                <button
                  type="button"
                  className="btn-primary btn-sm"
                  onClick={() => navigate("/login", { state: { signup: true } })}
                >
                  Sign Up
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                    <polyline points="12 5 19 12 12 19"></polyline>
                  </svg>
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ── Main Content Container ── */}
      <main className="home-main-content">
        {/* ── Hero Presentation Section ── */}
        <section className="hero-section" id="overview">
          <div className="hero-geom-diamond hero-diamond-1" aria-hidden="true" />
          <div className="hero-geom-diamond hero-diamond-2" aria-hidden="true" />

          <div className="hero-container">
            <div className="hero-pill-badge anim-fade-up-1">
              <span className="sonar-beacon"></span>
              <span>Pre-Publication Brand &amp; Claim Governance Platform</span>
            </div>

            <h1 className="hero-title anim-fade-up-2">
              Automated brand and claim compliance before spend.
            </h1>

            <p className="hero-subtitle anim-fade-up-3">
              CanonGate compiles brand guidelines, approved facts, and statutory rules into machine-readable Canons, 
              auditing campaign bundles across copy, fine print, and raster banners before public release.
            </p>

            <div className="hero-cta-group anim-fade-up-4">
              <button
                className="btn-primary btn-lg"
                onClick={() => navigate(isAuthenticated ? "/dashboard" : "/login")}
              >
                <span>{isAuthenticated ? "Open Governance Console" : "Launch CanonGate"}</span>
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="5" y1="12" x2="19" y2="12"></line>
                  <polyline points="12 5 19 12 12 19"></polyline>
                </svg>
              </button>
              <button
                className="btn-secondary btn-lg"
                onClick={scrollToContact}
              >
                Contact Our Team
              </button>
            </div>
          </div>
        </section>

        {/* ── Visual Showcase Slideshow (Centered in Card Motif) ── */}
        <section className="slideshow-card-wrap">
          <div className="slideshow-outer-card">
            <div className="slideshow-card-header">
              <div className="slideshow-header-title">
                <span className="live-dot" />
                <span>Live Pre-Publication Visual Inspection Studio</span>
              </div>
              <span className="slideshow-header-meta">5s Real-Time Inspection Carousel</span>
            </div>
            <ImageSlideshow />
          </div>
        </section>

        {/* ── Frequently Asked Questions (FAQ) Section ── */}
        <section className="faq-section" id="faq">
          <div className="faq-container">
            <div className="faq-header">
              <div className="faq-pill-badge">
                <span className="sonar-beacon"></span>
                <span>Frequently Asked Questions</span>
              </div>
              <h2 className="faq-title">Everything You Need to Know About CanonGate</h2>
              <p className="faq-subtitle">
                Clear answers to common questions about pre-publication governance, statutory compliance checks, and team workflows.
              </p>
            </div>

            <div className="faq-accordion">
              {FAQS.map((faq, index) => {
                const isOpen = openFaqIndex === index;
                return (
                  <div
                    key={index}
                    className={`faq-item ${isOpen ? "open" : ""}`}
                  >
                    <button
                      type="button"
                      className="faq-question-btn"
                      onClick={() => setOpenFaqIndex(isOpen ? null : index)}
                      aria-expanded={isOpen}
                    >
                      <span className="faq-question-text">{faq.q}</span>
                      <span className="faq-toggle-icon">
                        <svg
                          width="18"
                          height="18"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                      </span>
                    </button>
                    {isOpen && (
                      <div className="faq-answer-panel">
                        <p className="faq-answer-text">{faq.a}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* ── Dedicated Contact Our Team Form Section ── */}
        <section className="contact-section" id="contact">
          <div className="contact-card">
            <div className="contact-card-header">
              <div className="contact-icon-pill">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m22 2-7 20-4-9-9-4Z"/>
                  <path d="M22 2 11 13"/>
                </svg>
              </div>
              <h2 className="contact-title">Contact Our Team</h2>
              <p className="contact-desc">
                Have questions regarding CanonGate pre-publication compliance, custom brand Canons, or enterprise integration? Send our team a message below.
              </p>
            </div>

            {contactSent ? (
              <div className="contact-success-box">
                <div className="success-icon-circle">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </div>
                <h3>Message Sent Successfully!</h3>
                <p>
                  Thank you for reaching out. Your message has been received by our engineering and compliance team. We will get back to you shortly.
                </p>
                <button
                  type="button"
                  className="btn-primary btn-sm"
                  onClick={() => setContactSent(false)}
                >
                  Send Another Message
                </button>
              </div>
            ) : (
              <form className="contact-form" onSubmit={handleContactSubmit}>
                <div className="contact-form-grid">
                  <div className="contact-field-group">
                    <label htmlFor="c-name">Your Full Name</label>
                    <input
                      id="c-name"
                      type="text"
                      required
                      placeholder="e.g. Alex Johnson"
                      value={contactName}
                      onChange={(e) => setContactName(e.target.value)}
                    />
                  </div>
                  <div className="contact-field-group">
                    <label htmlFor="c-email">Work Email</label>
                    <input
                      id="c-email"
                      type="email"
                      required
                      placeholder="e.g. alex@company.com"
                      value={contactEmail}
                      onChange={(e) => setContactEmail(e.target.value)}
                    />
                  </div>
                </div>

                <div className="contact-field-group">
                  <label htmlFor="c-subject">Subject / Inquiry Topic</label>
                  <input
                    id="c-subject"
                    type="text"
                    required
                    placeholder="e.g. Campaign Governance & Pre-Flight Integration"
                    value={contactSubject}
                    onChange={(e) => setContactSubject(e.target.value)}
                  />
                </div>

                <div className="contact-field-group">
                  <label htmlFor="c-msg">Message</label>
                  <textarea
                    id="c-msg"
                    rows={4}
                    required
                    placeholder="How can our governance team assist you?"
                    value={contactMessage}
                    onChange={(e) => setContactMessage(e.target.value)}
                  />
                </div>

                <div className="contact-form-footer">
                  <button type="submit" className="btn-primary btn-lg">
                    <span>Send Message to Team</span>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="22" y1="2" x2="11" y2="13"/>
                      <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                    </svg>
                  </button>
                  <span className="contact-note">
                    Directly received by our team · Response within 24 business hours
                  </span>
                </div>
              </form>
            )}
          </div>
        </section>
      </main>

      {/* ── Clean Thematic Footer ── */}
      <footer className="home-footer">
        <div className="bg-corner-shape-yellow" aria-hidden="true" />

        <div className="footer-inner">
          <div className="footer-col brand-col">
            <div className="brand-logo" onClick={() => navigate("/")}>
              <div className="brand-shield-icon">
                <svg
                  width="20"
                  height="20"
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
              <span className="brand-title">CanonGate</span>
            </div>
            <p className="footer-tagline">
              Pre-publication brand &amp; claim governance platform. Automated compliance before marketing spend.
            </p>
            <p className="team-credit">
              TechCircuit Hackathon · Team <strong>Decisionsparalysis</strong>
            </p>
          </div>

          <div className="footer-col">
            <h4>Statutory Frameworks</h4>
            <ul>
              <li>CCPA 2022 Misleading Ads (PIB 1832906)</li>
              <li>RBI Digital Lending 2025 KFS Mandate</li>
              <li>ASCI FY2025-26 Code &amp; Guidelines</li>
              <li>W3C WCAG 2.1 AA Luminance Math</li>
            </ul>
          </div>

          <div className="footer-col contact-col">
            <h4>Contact Our Team</h4>
            <ul>
              <li>
                <button
                  type="button"
                  className="footer-contact-link-btn"
                  onClick={() => document.getElementById("faq")?.scrollIntoView({ behavior: "smooth" })}
                >
                  Frequently Asked Questions
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className="footer-contact-link-btn"
                  onClick={scrollToContact}
                >
                  Send a Message to Team
                </button>
              </li>
              <li>Pre-Publication Governance Support</li>
              <li>Enterprise Canon Setup</li>
              <li>TechCircuit Hackathon 2026</li>
            </ul>
          </div>
        </div>

        <div className="footer-bottom">
          <span>&copy; 2026 CanonGate. All rights reserved.</span>
          <span>Self-hostable, local-first pre-publication governance.</span>
        </div>
      </footer>
    </div>
  );
}
