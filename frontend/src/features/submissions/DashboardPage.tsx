import { useState, useEffect, useMemo, type ChangeEvent, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listSubmissions,
  createSubmission,
  type BundleAttachmentDto,
  listCanons,
  getCanonFriction,
  getCanonLint,
  proposeCanonPr,
  type CanonRevisionPrResponse,
  compileCanon,
  type CompileCanonResponse,
  workflowAction,
  scanSubmission,
  login as apiLogin,
} from "../../api/client";
import { useAuth } from "../auth/AuthContext";

const STATUS_BADGE_CLASS: Record<string, string> = {
  draft: "status-draft",
  in_review: "status-review",
  changes_requested: "status-changes",
  approved: "status-approved",
  published: "status-published",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  in_review: "In Review",
  changes_requested: "Changes Requested",
  approved: "Approved",
  published: "Published",
};

function fileToBase64Attachment(file: File): Promise<BundleAttachmentDto> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const idx = result.indexOf(",");
      const b64 = idx >= 0 ? result.slice(idx + 1) : result;
      resolve({ filename: file.name, content_base64: b64 });
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

const EMPTY_SUBMISSIONS: any[] = [];
const EMPTY_CANONS: any[] = [];

// Realistic test samples grounded in starter canons
const SAMPLE_TEMPLATES = [
  {
    name: "Indian Digital Lending (0% Fee Drop)",
    canonId: "indian-digital-lending",
    title: "Festive Flash Loan Campaign — Draft Copy",
    tagline: "Tests RBI KFS compliance: guaranteed approval & unverified credit checks",
    content:
      "Get a 0% processing fee on loans today! Apply now with no credit check and guaranteed approval for instant cash into your UPI account. Special competitive-rate APR available.",
  },
  {
    name: "Indian D2C Nutra (ASCI Unsubstantiated Claim)",
    canonId: "indian-d2c-nutra",
    title: "Ayurvedic Hair Growth Serum Banner & Ad Copy",
    tagline: "Tests ASCI Health Code: miracle cure, 100% efficacy claims & botanical palette",
    content:
      "Clinically proven hair growth of 23,800 strands in 30 days! 100% cure for hair loss with pure plant extract. Recommended by top doctors across India. Miracle cure for thinning hair.",
  },
  {
    name: "Acme Corp SaaS (Banned Terminology)",
    canonId: "acme-corp",
    title: "Acme Cloud Infrastructure Launch Announcement",
    tagline: "Tests Acme Brand Voice: banned 'cheap' word, formal tone & color drift",
    content:
      "Introducing our cheap new product line! We believe our cutting-edge technology will revolutionize the cloud industry. Buy now and join thousands of happy users.",
  },
];

export function DashboardPage() {
  const { username, role, logout, switchPersona, token } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // TanStack Query for server state
  const { data: submissions = EMPTY_SUBMISSIONS, isLoading: loadingSubmissions } = useQuery({
    queryKey: ["submissions"],
    queryFn: listSubmissions,
  });

  const { data: canons = EMPTY_CANONS } = useQuery({
    queryKey: ["canons"],
    queryFn: listCanons,
  });

  // Local form/UI state
  const [activeTab, setActiveTab] = useState<"submissions" | "governance">("submissions");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [canonId, setCanonId] = useState("");
  const [attachments, setAttachments] = useState<BundleAttachmentDto[]>([]);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [switchLoading, setSwitchLoading] = useState(false);
  const [seedingPipeline, setSeedingPipeline] = useState(false);

  // Canon Governance Studio state
  const [selectedCanonId, setSelectedCanonId] = useState("");
  const [prProposal, setPrProposal] = useState<CanonRevisionPrResponse | null>(null);
  const [compileId, setCompileId] = useState("brand-canon-v1");
  const [compileText, setCompileText] = useState("");
  const [compileResult, setCompileResult] = useState<CompileCanonResponse | null>(null);

  useEffect(() => {
    if (canons.length > 0 && !canonId) {
      setCanonId(canons[0].id);
      setSelectedCanonId(canons[0].id);
    }
  }, [canons, canonId]);

  // Server state for canon governance
  const { data: frictionData = null } = useQuery({
    queryKey: ["canonFriction", selectedCanonId],
    queryFn: () => getCanonFriction(selectedCanonId),
    enabled: !!selectedCanonId && activeTab === "governance",
  });

  const { data: lintData = null } = useQuery({
    queryKey: ["canonLint", selectedCanonId],
    queryFn: () => getCanonLint(selectedCanonId),
    enabled: !!selectedCanonId && activeTab === "governance",
  });

  // Filtered submissions based on tab filter & search
  const filteredSubmissions = useMemo(() => {
    return submissions.filter((sub) => {
      const matchesStatus = statusFilter === "all" || sub.status === statusFilter;
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        sub.title.toLowerCase().includes(q) ||
        sub.canon_id.toLowerCase().includes(q) ||
        (sub.raw_content && sub.raw_content.toLowerCase().includes(q));
      return matchesStatus && matchesSearch;
    });
  }, [submissions, statusFilter, searchQuery]);

  // Status counts for filter pills
  const counts = useMemo(() => {
    const map: Record<string, number> = {
      all: submissions.length,
      draft: 0,
      in_review: 0,
      changes_requested: 0,
      approved: 0,
      published: 0,
    };
    for (const s of submissions) {
      if (map[s.status] !== undefined) {
        map[s.status]++;
      }
    }
    return map;
  }, [submissions]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: (vars: { title: string; rawContent: string; canonId: string; attachments: BundleAttachmentDto[] }) =>
      createSubmission(vars.title, vars.rawContent, vars.canonId, vars.attachments),
    onSuccess: (sub) => {
      queryClient.invalidateQueries({ queryKey: ["submissions"] });
      setShowCreate(false);
      setTitle("");
      setContent("");
      setAttachments([]);
      navigate(`/submissions/${sub.id}`);
    },
    onError: (err: any) => {
      setError(err.message || "Failed to create submission");
    },
  });

  const proposePrMutation = useMutation({
    mutationFn: (cid: string) => proposeCanonPr(cid),
    onSuccess: (pr) => {
      setPrProposal(pr);
    },
    onError: (err: any) => {
      setError(err.message || "Failed to propose Canon PR");
    },
  });

  const compileMutation = useMutation({
    mutationFn: (vars: { compileId: string; compileText: string }) =>
      compileCanon(vars.compileId, vars.compileText, "1.0", [], false),
    onSuccess: (res) => {
      setCompileResult(res);
      queryClient.invalidateQueries({ queryKey: ["canons"] });
    },
    onError: (err: any) => {
      setError(err.message || "Failed to compile Canon");
    },
  });

  async function handleFileSelect(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    try {
      const converted = await Promise.all(files.map(fileToBase64Attachment));
      setAttachments((prev) => [...prev, ...converted]);
    } catch (err: any) {
      setError(err.message || "Failed to read attachment");
    }
  }

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    createMutation.mutate({
      title: title || "Untitled Campaign Draft",
      rawContent: content,
      canonId: canonId || (canons[0]?.id ?? "indian-digital-lending"),
      attachments,
    });
  }

  function loadTemplate(tpl: (typeof SAMPLE_TEMPLATES)[0]) {
    setTitle(tpl.title);
    setContent(tpl.content);
    setCanonId(tpl.canonId);
    setShowCreate(true);
  }

  function loadCanonGovernance(cid: string) {
    setSelectedCanonId(cid);
    setPrProposal(null);
  }

  function handleProposePr() {
    if (!selectedCanonId) return;
    proposePrMutation.mutate(selectedCanonId);
  }

  function handleCompileCanon(e: FormEvent) {
    e.preventDefault();
    compileMutation.mutate({ compileId, compileText });
  }

  /**
   * Fast persona switch in header
   */
  async function handleSwitchPersona(targetUsername: string, targetRole: string) {
    setSwitchLoading(true);
    setError("");
    try {
      await switchPersona(targetUsername, targetRole);
      await queryClient.invalidateQueries({ queryKey: ["submissions"] });
      // When switching to Reviewer or Legal Officer, default to relevant queue filter
      if (targetRole === "reviewer") {
        setStatusFilter("in_review");
      } else if (targetRole === "admin") {
        setStatusFilter("approved");
      } else {
        setStatusFilter("all");
      }
    } catch (err: any) {
      setError(err.message || "Failed to switch persona");
    } finally {
      setSwitchLoading(false);
    }
  }

  /**
   * 1-Click Demo Pipeline Seeder: Creates sample submissions in Draft, In Review, and Approved
   * allowing instant end-to-end evaluation of Creator, Reviewer, and Legal Officer roles.
   */
  async function handleSeedDemoPipeline() {
    setSeedingPipeline(true);
    setError("");
    setSuccessMsg("");

    try {
      // 1. Digital Lending (Draft with findings for Creator)
      const sub1 = await createSubmission(
        "Festive Flash Loan Campaign — Draft Copy",
        "Get a 0% processing fee on loans today! Apply now with no credit check and guaranteed approval for instant cash into your UPI account. Special competitive-rate APR available.",
        "indian-digital-lending"
      );
      // Run scan on sub1 to generate findings
      await scanSubmission(sub1.id, () => {}, () => {});

      // 2. D2C Nutra (In Review for Reviewer)
      const sub2 = await createSubmission(
        "Ayurvedic Hair Growth Serum Banner & Ad Copy",
        "Clinically proven hair growth of 23,800 strands in 30 days! 100% cure for hair loss with pure plant extract. Recommended by top doctors across India. Miracle cure for thinning hair.",
        "indian-d2c-nutra"
      );
      await scanSubmission(sub2.id, () => {}, () => {});
      await workflowAction(sub2.id, "submit", "Submitted for Brand Manager review");

      // 3. Acme Cloud (Approved for Legal Officer)
      const sub3 = await createSubmission(
        "Acme Cloud Infrastructure Launch Announcement",
        "Introducing our affordable new product line! We believe our innovative technology will modernize the cloud industry. Purchase now and join thousands of happy customers.",
        "acme-corp"
      );
      await scanSubmission(sub3.id, () => {}, () => {});
      await workflowAction(sub3.id, "submit", "Submitted for review");

      // Approve sub3 via Reviewer credentials
      try {
        const rev = await apiLogin("pulkit_manager", "demoPassword123!");
        localStorage.setItem("cg_token", rev.token);
        await workflowAction(sub3.id, "approve", "Approved by Brand Manager, ready for Legal sign-off");
      } finally {
        if (token) localStorage.setItem("cg_token", token);
      }

      await queryClient.invalidateQueries({ queryKey: ["submissions"] });
      setSuccessMsg("Demo pipeline seeded successfully! 3 realistic campaigns ready across Draft, In Review, and Approved states.");
      setTimeout(() => setSuccessMsg(""), 6000);
    } catch (err: any) {
      setError(err.message || "Failed to seed demo pipeline");
    } finally {
      setSeedingPipeline(false);
    }
  }

  return (
    <div className="console-layout">
      {/* ── Console Header ── */}
      <div className="console-header-container">
        <header className="console-header-curved">
          <div className="console-brand">
            <Link to="/" className="console-logo-link" title="Return to Product Home">
              <div className="brand-shield-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                  <path d="m9 12 2 2 4-4"/>
                </svg>
              </div>
              <div className="brand-text">
                <span className="brand-title">CanonGate</span>
                <span className="brand-sub">Console</span>
              </div>
            </Link>

            <nav className="console-nav-tabs">
              <button
                className={`console-tab ${activeTab === "submissions" ? "active" : ""}`}
                onClick={() => setActiveTab("submissions")}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                  <line x1="8" y1="21" x2="16" y2="21"/>
                  <line x1="12" y1="17" x2="12" y2="21"/>
                </svg>
                <span>Campaign Queue</span>
                <span className="tab-count">{submissions.length}</span>
              </button>
              <button
                className={`console-tab ${activeTab === "governance" ? "active" : ""}`}
                onClick={() => {
                  setActiveTab("governance");
                  if (selectedCanonId) loadCanonGovernance(selectedCanonId);
                }}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                </svg>
                <span>Canon Governance Studio</span>
                <span className="tab-count">{canons.length}</span>
              </button>
            </nav>
          </div>

          <div className="console-user-controls">
            {/* Persona Switcher for Evaluation */}
            <div className="persona-switcher">
              <span className="persona-label">Persona:</span>
              <button
                className={`role-switch-btn ${role === "creator" ? "active active-creator" : ""}`}
                onClick={() => handleSwitchPersona("creative_lead", "creator")}
                disabled={switchLoading}
                title="Creator: Upload, scan, fix blockers & submit"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 4 }}>
                  <path d="M12 20h9"/>
                  <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                </svg>
                Creator
              </button>
              <button
                className={`role-switch-btn ${role === "reviewer" ? "active active-reviewer" : ""}`}
                onClick={() => handleSwitchPersona("pulkit_manager", "reviewer")}
                disabled={switchLoading}
                title="Reviewer: Adjudicate warnings, approve/request changes"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 4 }}>
                  <path d="M9 11l3 3L22 4"/>
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                </svg>
                Reviewer
              </button>
              <button
                className={`role-switch-btn ${role === "admin" ? "active active-admin" : ""}`}
                onClick={() => handleSwitchPersona("aritra_legal", "admin")}
                disabled={switchLoading}
                title="Legal Officer: Final publish sign-off & C2PA cert"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 4 }}>
                  <circle cx="12" cy="12" r="10"/>
                  <path d="m4.93 4.93 4.24 4.24"/>
                  <path d="m14.83 9.17 4.24-4.24"/>
                  <path d="m14.83 14.83 4.24 4.24"/>
                  <path d="m9.17 14.83-4.24 4.24"/>
                </svg>
                Legal Officer
              </button>
            </div>

            <div className="user-profile-badge">
              <span className="user-name">{username}</span>
              <span className={`role-badge role-${role}`}>{role}</span>
            </div>

            <button className="btn-ghost btn-sm" onClick={logout} title="Sign Out">
              Sign Out
            </button>
          </div>
        </header>
      </div>

      {/* ── Main Content Area ── */}
      <main className="console-main">
        {error && (
          <div className="console-alert error-alert">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <span>{error}</span>
            <button className="alert-close" onClick={() => setError("")}>×</button>
          </div>
        )}

        {successMsg && (
          <div className="console-alert success-alert">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
              <polyline points="22 4 12 14.01 9 11.01"></polyline>
            </svg>
            <span>{successMsg}</span>
            <button className="alert-close" onClick={() => setSuccessMsg("")}>×</button>
          </div>
        )}

        {/* ── Submissions View ── */}
        {activeTab === "submissions" && (
          <div className="submissions-section">
            
            {/* Dynamic Persona Workspace Hub Banner */}
            <div className={`persona-workspace-banner banner-${role || "creator"}`}>
              <div className="banner-left">
                <div className="banner-role-pill">
                  <span className="live-dot" />
                  <span>
                    {role === "creator"
                      ? "CREATOR MODE"
                      : role === "reviewer"
                      ? "REVIEWER MODE (BRAND MANAGER)"
                      : "LEGAL OFFICER MODE (CHIEF COMPLIANCE)"}
                  </span>
                </div>
                <h2 className="banner-title">
                  {role === "creator"
                    ? "Campaign Drafting & Policy Compliance Studio"
                    : role === "reviewer"
                    ? "Adjudication & Brand Governance Queue"
                    : "Executive Regulatory Sign-Off & C2PA Trust Center"}
                </h2>
                <p className="banner-desc">
                  {role === "creator"
                    ? "Author campaign copy, attach raster banners or PDF brochures, and scan against signed brand Canons. Fix blockers before submitting for review."
                    : role === "reviewer"
                    ? "Adjudicate pending campaign submissions. Resolve warnings with mandatory written justification, enforce brand consistency, and approve or request changes."
                    : "Final publication authority. Inspect unbroken SHA-256 hash chains, verify RFC 9162 Merkle tree proofs, issue C2PA cryptographic credentials, and publish."}
                </p>

                {/* Quick Persona Stats */}
                <div className="banner-stats-row">
                  {role === "creator" && (
                    <>
                      <div className="banner-stat-chip">
                        <span className="stat-num">{counts.draft}</span>
                        <span className="stat-label">Active Drafts</span>
                      </div>
                      <div className="banner-stat-chip">
                        <span className="stat-num">{counts.changes_requested}</span>
                        <span className="stat-label">Needs Revision</span>
                      </div>
                      <div className="banner-stat-chip">
                        <span className="stat-num">{submissions.length}</span>
                        <span className="stat-label">Total In Workspace</span>
                      </div>
                    </>
                  )}
                  {role === "reviewer" && (
                    <>
                      <div className="banner-stat-chip highlight-chip">
                        <span className="stat-num">{counts.in_review}</span>
                        <span className="stat-label">Pending In Review</span>
                      </div>
                      <div className="banner-stat-chip">
                        <span className="stat-num">{counts.approved}</span>
                        <span className="stat-label">Approved By You</span>
                      </div>
                      <div className="banner-stat-chip">
                        <span className="stat-num">{canons.length}</span>
                        <span className="stat-label">Monitored Canons</span>
                      </div>
                    </>
                  )}
                  {role === "admin" && (
                    <>
                      <div className="banner-stat-chip highlight-chip-purple">
                        <span className="stat-num">{counts.approved}</span>
                        <span className="stat-label">Ready for Final Sign-Off</span>
                      </div>
                      <div className="banner-stat-chip">
                        <span className="stat-num">{counts.published}</span>
                        <span className="stat-label">Published Live</span>
                      </div>
                      <div className="banner-stat-chip">
                        <span className="stat-num">RFC 9162</span>
                        <span className="stat-label">Merkle Ledger</span>
                      </div>
                    </>
                  )}
                </div>
              </div>

              <div className="banner-actions">
                <button
                  className="btn-primary"
                  onClick={() => setShowCreate(!showCreate)}
                >
                  {showCreate ? "Close Campaign Drawer" : "+ New Campaign Review"}
                </button>
                <button
                  className="btn-secondary btn-seed"
                  onClick={handleSeedDemoPipeline}
                  disabled={seedingPipeline}
                  title="Creates real sample campaigns across Draft, In Review, and Approved states"
                >
                  {seedingPipeline ? (
                    <span>Seeding 3-Persona Pipeline...</span>
                  ) : (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                      </svg>
                      <span>Pre-load Demo Pipeline</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Create Drawer */}
            {showCreate && (
              <div className="create-submission-card">
                <div className="drawer-header">
                  <h3>Submit New Campaign Bundle for Governance Review</h3>
                  <p>Choose an approved brand rulebook or pre-fill a verified test bundle below.</p>
                </div>

                {/* Pre-fill Sample Cards */}
                <div className="sample-bundle-picker">
                  <span className="template-label">Pre-load Verified Test Bundles:</span>
                  <div className="sample-cards-grid">
                    {SAMPLE_TEMPLATES.map((tpl) => (
                      <div
                        key={tpl.name}
                        className={`sample-card ${canonId === tpl.canonId && title === tpl.title ? "selected" : ""}`}
                        onClick={() => loadTemplate(tpl)}
                      >
                        <div className="sample-card-head">
                          <span className="sample-canon-pill">{tpl.canonId}</span>
                        </div>
                        <h4 className="sample-name">{tpl.name}</h4>
                        <p className="sample-desc">{tpl.tagline}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <form onSubmit={handleCreate} className="submission-form">
                  <div className="form-grid-2">
                    <div className="form-group">
                      <label htmlFor="create-title">Campaign Title / Asset Descriptor</label>
                      <input
                        id="create-title"
                        type="text"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder="e.g. Q4 Festive Digital Lending Push"
                        required
                        className="form-input"
                      />
                    </div>

                    <div className="form-group">
                      <label htmlFor="create-canon">Target Brand Canon &amp; Rulebook</label>
                      <select
                        id="create-canon"
                        value={canonId}
                        onChange={(e) => setCanonId(e.target.value)}
                        className="form-select"
                      >
                        {canons.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.id} (v{c.version} · {c.term_count} terms · {c.color_count} colors · {c.fact_count} facts)
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label htmlFor="create-content">
                      Campaign Text Body (Supports Markdown, HTML, KFS APR/Fee Schedules)
                    </label>
                    <textarea
                      id="create-content"
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      placeholder="Paste your ad copy, social post, or disclaimer text here..."
                      rows={5}
                      required={attachments.length === 0}
                      className="form-textarea"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="create-files">
                      Multimodal Attachments (Raster Banners, PDF Brochures, Word Documents)
                    </label>
                    <input
                      id="create-files"
                      type="file"
                      multiple
                      accept=".docx,.pdf,.html,.htm,.md,.txt,.png,.jpg,.jpeg,.webp"
                      onChange={handleFileSelect}
                      className="form-file-input"
                    />
                    {attachments.length > 0 && (
                      <div className="attachments-list">
                        <span className="attachment-badge">
                          Attached ({attachments.length}): {attachments.map((a) => a.filename).join(", ")}
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="form-button-row">
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={createMutation.isPending}
                    >
                      {createMutation.isPending ? "Ingesting & Creating..." : "Create & Launch Review Studio"}
                    </button>
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => setShowCreate(false)}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* Queue Controls & Filter Bar */}
            <div className="queue-controls-bar">
              <div className="status-filter-pills">
                <button
                  className={`filter-pill ${statusFilter === "all" ? "active" : ""}`}
                  onClick={() => setStatusFilter("all")}
                >
                  All ({counts.all})
                </button>
                <button
                  className={`filter-pill ${statusFilter === "draft" ? "active" : ""}`}
                  onClick={() => setStatusFilter("draft")}
                >
                  Drafts ({counts.draft})
                </button>
                <button
                  className={`filter-pill filter-review ${statusFilter === "in_review" ? "active" : ""}`}
                  onClick={() => setStatusFilter("in_review")}
                >
                  In Review ({counts.in_review})
                </button>
                <button
                  className={`filter-pill ${statusFilter === "changes_requested" ? "active" : ""}`}
                  onClick={() => setStatusFilter("changes_requested")}
                >
                  Changes Requested ({counts.changes_requested})
                </button>
                <button
                  className={`filter-pill filter-approved ${statusFilter === "approved" ? "active" : ""}`}
                  onClick={() => setStatusFilter("approved")}
                >
                  Approved ({counts.approved})
                </button>
                <button
                  className={`filter-pill ${statusFilter === "published" ? "active" : ""}`}
                  onClick={() => setStatusFilter("published")}
                >
                  Published ({counts.published})
                </button>
              </div>

              <div className="queue-search-wrap">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="search-icon">
                  <circle cx="11" cy="11" r="8"/>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                <input
                  type="text"
                  placeholder="Filter campaigns by title or canon..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="queue-search-input"
                />
                {searchQuery && (
                  <button className="search-clear-btn" onClick={() => setSearchQuery("")}>×</button>
                )}
              </div>
            </div>

            {/* Submissions List / Table */}
            <div className="submissions-container">
              {loadingSubmissions ? (
                <div className="empty-state-card">
                  <p>Loading campaign verification queue...</p>
                </div>
              ) : filteredSubmissions.length === 0 ? (
                <div className="empty-state-card">
                  <div className="empty-icon-svg">
                    <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                    </svg>
                  </div>
                  <h4>No Campaigns Found in This View</h4>
                  <p>
                    {statusFilter !== "all"
                      ? `There are currently no submissions with status "${STATUS_LABELS[statusFilter] || statusFilter}".`
                      : "Create your first campaign review or load the pre-built demo pipeline to test all 3 personas."}
                  </p>
                  <div className="empty-actions-row">
                    <button
                      className="btn-primary btn-sm"
                      onClick={() => setShowCreate(true)}
                    >
                      + Create Submission
                    </button>
                    <button
                      className="btn-secondary btn-sm"
                      onClick={handleSeedDemoPipeline}
                      disabled={seedingPipeline}
                    >
                      {seedingPipeline ? "Seeding..." : "⚡ Pre-load 3-Persona Demo Pipeline"}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="submissions-grid">
                  {filteredSubmissions.map((sub) => {
                    // Persona-specific action label
                    let actionPrompt = "Open Studio →";
                    if (sub.status === "draft") {
                      actionPrompt = role === "creator" ? "Triage & Scan →" : "Inspect Draft →";
                    } else if (sub.status === "in_review") {
                      actionPrompt = role === "reviewer" || role === "admin" ? "Adjudicate & Review →" : "Awaiting Review →";
                    } else if (sub.status === "approved") {
                      actionPrompt = role === "admin" ? "Publish & Sign C2PA →" : "View Approval →";
                    } else if (sub.status === "published") {
                      actionPrompt = "View Certificate →";
                    }

                    return (
                      <div
                        key={sub.id}
                        className={`submission-card card-status-${sub.status}`}
                        onClick={() => navigate(`/submissions/${sub.id}`)}
                      >
                        <div className="card-top-row">
                          <span className="sub-canon-tag">
                            {sub.canon_id}
                          </span>
                          <span className={`status-pill ${STATUS_BADGE_CLASS[sub.status] || "status-review"}`}>
                            <span className="status-dot" />
                            {STATUS_LABELS[sub.status] || sub.status.replace(/_/g, " ")}
                          </span>
                        </div>

                        <h3 className="sub-title">{sub.title}</h3>

                        <p className="sub-snippet">
                          {sub.raw_content ? sub.raw_content.slice(0, 115) + (sub.raw_content.length > 115 ? "…" : "") : "Multimodal campaign bundle review"}
                        </p>

                        <div className="card-footer-row">
                          <span className="sub-date">
                            Created {new Date(sub.created_at).toLocaleDateString()}
                          </span>
                          <span className="sub-open-link">
                            {actionPrompt}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Governance Studio & Telemetry ── */}
        {activeTab === "governance" && (
          <div className="governance-section">
            <div className="console-hero-banner governance-hero">
              <div className="hero-banner-content">
                <h2>Canon Governance Studio &amp; Telemetry</h2>
                <p>
                  Closed-loop Guideline Friction telemetry, Krippendorff's alpha inter-reviewer agreement,
                  and automated Canon v1.1 PR proposal with historical impact backtesting.
                </p>
              </div>
              <div className="hero-banner-controls">
                <select
                  value={selectedCanonId}
                  onChange={(e) => loadCanonGovernance(e.target.value)}
                  className="form-select select-compact"
                >
                  {canons.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.id} (v{c.version})
                    </option>
                  ))}
                </select>
                <button
                  className="btn-primary btn-sm"
                  onClick={handleProposePr}
                  disabled={proposePrMutation.isPending}
                >
                  {proposePrMutation.isPending ? "Simulating Impact..." : "Auto-Draft v1.1 PR"}
                </button>
              </div>
            </div>

            {/* Static Linter Results */}
            {lintData && (
              <div className="evidence-panel">
                <div className="panel-header">
                  <div className="panel-title-group">
                    <span className="panel-title">
                      Canon Static Linter ({lintData.canon_id} v{lintData.canon_version})
                    </span>
                    <span className="panel-subtitle">
                      Contradiction, overlap, and ungrounded regex boundary audit
                    </span>
                  </div>
                  <span className={`status-pill ${lintData.is_valid ? "status-pass" : "status-blocker"}`}>
                    <span className="status-dot" />
                    {lintData.is_valid ? "Valid: 0 Contradictions" : `${lintData.issues.length} Issues Flagged`}
                  </span>
                </div>
                {lintData.issues.length > 0 && (
                  <ul className="issues-list">
                    {lintData.issues.map((iss, idx: number) => (
                      <li key={idx} className="issue-item">
                        <strong>[{iss.kind}]</strong> {iss.message}{" "}
                        {iss.rule_ids?.length > 0 && <code>({iss.rule_ids.join(", ")})</code>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* Friction Telemetry Table */}
            {frictionData && (
              <div className="evidence-panel">
                <div className="panel-header">
                  <div className="panel-title-group">
                    <span className="panel-title">
                      Empirical Bayes Guideline Friction &amp; Inter-Reviewer Agreement
                    </span>
                    <span className="panel-subtitle">
                      Beta-Binomial shrinkage across creator overrides and reviewer disputes
                    </span>
                  </div>
                  <div className="krippendorff-badge">
                    <span>Krippendorff's alpha: <strong>{frictionData.krippendorff_alpha.toFixed(4)}</strong></span>
                    <span className="kripp-sep">·</span>
                    <span>Total Findings: {frictionData.total_findings}</span>
                  </div>
                </div>

                {frictionData.rules.length > 0 ? (
                  <div className="table-responsive">
                    <table className="clean-data-table">
                      <thead>
                        <tr>
                          <th>Rule ID</th>
                          <th>Total Flags</th>
                          <th>Overrides &amp; Disputes</th>
                          <th>Raw Friction</th>
                          <th>Empirical Bayes Posterior</th>
                          <th>Governance Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {frictionData.rules.map((r) => (
                          <tr key={r.rule_id}>
                            <td><code>{r.rule_id}</code></td>
                            <td>{r.total_flags}</td>
                            <td>{r.overrides_and_disputes}</td>
                            <td>{(r.raw_friction * 100).toFixed(1)}%</td>
                            <td><strong>{(r.posterior_friction * 100).toFixed(1)}%</strong></td>
                            <td>
                              <span className={`status-pill ${r.needs_canon_revision ? "status-changes" : "status-approved"}`}>
                                <span className="status-dot" />
                                {r.needs_canon_revision ? "Needs v1.1 PR (>40%)" : "Healthy"}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="empty-panel-text">No friction data recorded yet for this Canon.</p>
                )}
              </div>
            )}

            {/* Proposed PR Simulation */}
            {prProposal && (
              <div className="evidence-panel pr-panel">
                <div className="panel-header">
                  <span className="panel-title">
                    Proposed Canon PR: {prProposal.canon_id} v{prProposal.base_version} → v{prProposal.proposed_version}
                  </span>
                  <span className="status-pill status-approved">
                    <span className="status-dot" />
                    Impact Backtest Passed
                  </span>
                </div>
                <div className="pr-backtest-summary">
                  <div className="backtest-metric">
                    <span className="metric-title">Bundles Evaluated</span>
                    <span className="metric-val">{prProposal.bundles_evaluated}</span>
                  </div>
                  <div className="backtest-metric">
                    <span className="metric-title">Total Findings</span>
                    <span className="metric-val">{prProposal.before_findings} → {prProposal.after_findings}</span>
                  </div>
                  <div className="backtest-metric">
                    <span className="metric-title">Blockers Reduced</span>
                    <span className="metric-val text-green">{prProposal.before_blockers} → {prProposal.after_blockers}</span>
                  </div>
                  <div className="backtest-metric">
                    <span className="metric-title">Dispute Reduction</span>
                    <span className="metric-val text-blue">{(prProposal.reduction_ratio * 100).toFixed(1)}%</span>
                  </div>
                </div>
                {prProposal.yaml_diff && (
                  <pre className="pr-diff-viewer">
                    {prProposal.yaml_diff}
                  </pre>
                )}
              </div>
            )}

            {/* Pipeline A Compiler Form */}
            <div className="compiler-card">
              <div className="compiler-head">
                <h3>Pipeline A: Compile Brand Book into Grounded Canon</h3>
                <p>
                  Grounded multi-pass compilation with Guard 1 Value-Anchor Audit, Guard 2 Character Grounding,
                  and Guard 3 Round-Trip Entailment (&ge; 0.90).
                </p>
              </div>

              <form onSubmit={handleCompileCanon} className="compiler-form">
                <div className="form-group">
                  <label htmlFor="compile-id">New Canon Unique Identifier</label>
                  <input
                    id="compile-id"
                    type="text"
                    value={compileId}
                    onChange={(e) => setCompileId(e.target.value)}
                    required
                    className="form-input"
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="compile-text">Brand Guidelines / Statutory KFS Source Text</label>
                  <textarea
                    id="compile-text"
                    value={compileText}
                    onChange={(e) => setCompileText(e.target.value)}
                    rows={4}
                    placeholder="e.g.: Never use 'cheap' — prefer 'affordable'. Trust Navy: #0D3B66. 0% processing fee on loans under Rs 50,000 valid until 2026-09-30."
                    required
                    className="form-textarea"
                  />
                </div>

                <button
                  type="submit"
                  className="btn-primary"
                  disabled={compileMutation.isPending}
                >
                  {compileMutation.isPending ? "Executing Guards 1–3..." : "Compile & Ground Canon"}
                </button>
              </form>

              {compileResult && (
                <div className="compile-result-panel">
                  <div className="result-header">
                    <h4>
                      Compiled Canon: <code>{compileResult.canon_id}</code> ({compileResult.hash.slice(0, 16)}…)
                    </h4>
                    <span className="result-counts">
                      {compileResult.term_count} terms · {compileResult.color_count} colors · {compileResult.fact_count} facts
                    </span>
                  </div>
                  <div className="table-responsive">
                    <table className="clean-data-table">
                      <thead>
                        <tr>
                          <th>Rule ID</th>
                          <th>Kind</th>
                          <th>Span [s, e]</th>
                          <th>Guard 1 Anchor Recall</th>
                          <th>Guard 3 Round-Trip NLI</th>
                          <th>Grounding Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {compileResult.provenance.map((p) => (
                          <tr key={p.rule_id}>
                            <td><code>{p.rule_id}</code></td>
                            <td>{p.rule_kind}</td>
                            <td>[{p.start}, {p.end}]</td>
                            <td>{(p.effective_anchor_recall * 100).toFixed(0)}%</td>
                            <td>{(p.round_trip_nli_score * 100).toFixed(0)}%</td>
                            <td>
                              <span className="status-pill status-approved">
                                <span className="status-dot" />
                                {p.alignment_status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
