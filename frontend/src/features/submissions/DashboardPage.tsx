import { useState, useEffect, useCallback, type FormEvent } from "react";
import {
  listSubmissions,
  listCanons,
  createSubmission,
  deleteSubmission,
  getCanonLint,
  getCanonFriction,
  proposeCanonPr,
  applyCanonPr,
  calibrateCanonRule,
  compileBrandCanon,
  type Submission,
  type CanonSummary,
  type CanonRuleItem,
  type BundleAttachmentPayload,
  type CanonLintResponse,
  type CanonFrictionResponse,
  type CanonRevisionPrResponse,
  type CalibrateCanonRuleResponse,
  type CompileCanonResponse,
} from "../../api/client";
import { useAuth } from "../auth/context";
import { useNavigate, Link } from "react-router-dom";

const ROLE_META: Record<
  string,
  {
    label: string;
    shortLabel: string;
    stageOwned: string;
    responsibility: string;
  }
> = {
  creator: {
    label: "Creator (Marketing / Agency)",
    shortLabel: "Creator",
    stageOwned: "Stage 1 · Pre-Flight & Remediation",
    responsibility:
      "Uploads campaign copy, documents, and banners, runs pre-flight checks, resolves blocking issues, and documents context on warning overrides.",
  },
  reviewer: {
    label: "Brand Manager (Playbook Owner)",
    shortLabel: "Brand Manager",
    stageOwned: "Stage 2 · Brand & Playbook Review",
    responsibility:
      "Manages brand playbooks and rule thresholds, reviews revision history and warning overrides, and approves brand compliance.",
  },
  admin: {
    label: "Authorised Legal Reviewer",
    shortLabel: "Legal Sign-Off",
    stageOwned: "Stage 3 · Regulatory & Legal Sign-Off",
    responsibility:
      "Reviews high-risk claims, required disclosures, and overrides to issue final sign-off and generate the release certificate.",
  },
};

function getStageMeta(status: string) {
  switch (status) {
    case "draft":
      return {
        stageNum: 1,
        stageLabel: "Stage 1 · Creator Draft",
        ownerRole: "creator",
        ownerText: "Creator: Review findings & submit for Brand Review",
      };
    case "changes_requested":
      return {
        stageNum: 1,
        stageLabel: "Stage 1 · Changes Requested",
        ownerRole: "creator",
        ownerText: "Creator: Address reviewer feedback & resubmit",
      };
    case "in_review":
      return {
        stageNum: 2,
        stageLabel: "Stage 2 · Brand Review",
        ownerRole: "reviewer",
        ownerText: "Brand Manager: Verify revisions & approve",
      };
    case "approved":
      return {
        stageNum: 3,
        stageLabel: "Stage 3 · Legal Sign-Off",
        ownerRole: "admin",
        ownerText: "Legal Reviewer: Final claim sign-off & release",
      };
    case "published":
      return {
        stageNum: 4,
        stageLabel: "Stage 4 · Approved & Released",
        ownerRole: "published",
        ownerText: "Released · Signed Governance Certificate Ready",
      };
    default:
      return {
        stageNum: 1,
        stageLabel: status,
        ownerRole: "creator",
        ownerText: "In Progress",
      };
  }
}

export function DashboardPage() {
  const { username, displayName, role, switchRole, logout } = useAuth();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<"submissions" | "governance">(
    "submissions",
  );
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [canons, setCanons] = useState<CanonSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [stageFilter, setStageFilter] = useState<string>("all");

  // New submission form — automatically shown when queue is empty
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [rawContent, setRawContent] = useState("");
  const [selectedCanon, setSelectedCanon] = useState("");
  const [uploadedAttachments, setUploadedAttachments] = useState<
    BundleAttachmentPayload[]
  >([]);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [switchingRole, setSwitchingRole] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Brand Playbook (Canon) Studio state
  const [govCanonId, setGovCanonId] = useState<string>("");
  const [lintReport, setLintReport] = useState<CanonLintResponse | null>(null);
  const [frictionReport, setFrictionReport] =
    useState<CanonFrictionResponse | null>(null);
  const [prProposal, setPrProposal] = useState<CanonRevisionPrResponse | null>(
    null,
  );
  const [govLoading, setGovLoading] = useState(false);
  const [prLoading, setPrLoading] = useState(false);
  const [applyingPr, setApplyingPr] = useState(false);
  const [prAppliedBanner, setPrAppliedBanner] = useState<string | null>(null);
  const [prThreshold, setPrThreshold] = useState<number>(0.35);

  // Rule Calibration Sliders state (populated dynamically from selected Canon)
  const [calRuleId, setCalRuleId] = useState<string>("");
  const [calSeverity, setCalSeverity] = useState<number>(40);
  const [calMaxDeltaE, setCalMaxDeltaE] = useState<number>(5.0);
  const [calMaxWords, setCalMaxWords] = useState<number>(28);
  const [calMaxFkGrade, setCalMaxFkGrade] = useState<number>(11.0);
  const [calibrating, setCalibrating] = useState(false);
  const [calibrationResult, setCalibrationResult] =
    useState<CalibrateCanonRuleResponse | null>(null);

  // Playbook Import state
  const [compileId, setCompileId] = useState<string>("");
  const [compileText, setCompileText] = useState<string>("");
  const [compileAttachments, setCompileAttachments] = useState<
    BundleAttachmentPayload[]
  >([]);
  const [compiling, setCompiling] = useState(false);
  const [compileResult, setCompileResult] =
    useState<CompileCanonResponse | null>(null);

  const syncRuleSliders = useCallback((rule: CanonRuleItem | undefined) => {
    if (!rule) return;
    setCalRuleId(rule.id);
    if (typeof rule.severity === "number") {
      setCalSeverity(rule.severity);
    }
    if (typeof rule.max_delta_e === "number") {
      setCalMaxDeltaE(rule.max_delta_e);
    }
    if (typeof rule.max_sentence_words === "number") {
      setCalMaxWords(rule.max_sentence_words);
    }
    if (typeof rule.max_flesch_kincaid_grade === "number") {
      setCalMaxFkGrade(rule.max_flesch_kincaid_grade);
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [subs, cans] = await Promise.all([listSubmissions(), listCanons()]);
      setSubmissions(subs);
      if (subs.length === 0) {
        setShowForm(true);
      }
      setCanons(cans);
      if (cans.length > 0) {
        const defaultCanon =
          cans.find((c) => c.id === "indian-digital-lending")?.id ?? cans[0].id;
        setSelectedCanon((prev) => prev || defaultCanon);
        setGovCanonId((prev) => {
          const resolvedGovId = prev || defaultCanon;
          const activeObj =
            cans.find((c) => c.id === resolvedGovId) ?? cans[0];
          if (activeObj?.rules && activeObj.rules.length > 0) {
            setCalRuleId((currRuleId) => {
              const existingMatch = activeObj.rules?.find(
                (r) => r.id === currRuleId,
              );
              const picked = existingMatch ?? activeObj.rules![0];
              syncRuleSliders(picked);
              return picked.id;
            });
          }
          return resolvedGovId;
        });
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [syncRuleSliders]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const loadGovernanceTelemetry = useCallback(async (canonId: string) => {
    if (!canonId) return;
    setGovLoading(true);
    setPrProposal(null);
    try {
      const [lint, friction] = await Promise.all([
        getCanonLint(canonId),
        getCanonFriction(canonId),
      ]);
      setLintReport(lint);
      setFrictionReport(friction);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setGovLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === "governance" && govCanonId) {
      loadGovernanceTelemetry(govCanonId);
    }
  }, [activeTab, govCanonId, loadGovernanceTelemetry]);

  function handleSelectGovCanon(newCanonId: string) {
    setGovCanonId(newCanonId);
    setCalibrationResult(null);
    const found = canons.find((c) => c.id === newCanonId);
    if (found?.rules && found.rules.length > 0) {
      syncRuleSliders(found.rules[0]);
    } else {
      setCalRuleId("");
    }
  }

  function handleSelectCalRule(newRuleId: string) {
    setCalRuleId(newRuleId);
    const foundCanon = canons.find((c) => c.id === govCanonId);
    const rule = foundCanon?.rules?.find((r) => r.id === newRuleId);
    if (rule) {
      syncRuleSliders(rule);
    }
  }

  async function handleProposePr() {
    if (!govCanonId) return;
    setPrLoading(true);
    setPrAppliedBanner(null);
    try {
      const notes: Record<string, string> = {};
      if (frictionReport) {
        for (const r of frictionReport.rules) {
          if (r.needs_canon_revision) {
            notes[r.rule_id] =
              "Rule frequently overridden during campaign reviews; clarify scope and calibrate threshold in v1.1.";
          }
        }
      }
      const res = await proposeCanonPr(govCanonId, notes, prThreshold, 1);
      setPrProposal(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPrLoading(false);
    }
  }

  async function handleApplyPr() {
    if (!govCanonId || !prProposal) return;
    setApplyingPr(true);
    setError(null);
    try {
      const updated = await applyCanonPr(govCanonId, {}, prThreshold, 1, false);
      setPrAppliedBanner(
        `Activated Playbook ${updated.id} v${updated.version} (${updated.hash.slice(0, 12)}…).`,
      );
      await refresh();
      await loadGovernanceTelemetry(govCanonId);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setApplyingPr(false);
    }
  }

  async function handleCalibrateRule(e: FormEvent) {
    e.preventDefault();
    if (!govCanonId || !calRuleId.trim()) return;
    setCalibrating(true);
    setError(null);
    try {
      const res = await calibrateCanonRule(govCanonId, {
        rule_id: calRuleId.trim(),
        severity: calSeverity,
        max_delta_e: calMaxDeltaE,
        max_sentence_words: calMaxWords,
        max_flesch_kincaid_grade: calMaxFkGrade,
        persist: false,
      });
      setCalibrationResult(res);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCalibrating(false);
    }
  }

  async function handleCompileCanon(e: FormEvent) {
    e.preventDefault();
    const targetId = compileId.trim();
    if (
      !targetId ||
      (!compileText.trim() && compileAttachments.length === 0)
    ) {
      setError(
        "Please provide a Playbook ID and either guideline text or an uploaded document.",
      );
      return;
    }
    setCompiling(true);
    setError(null);
    try {
      const res = await compileBrandCanon(
        targetId,
        compileText,
        compileAttachments,
        "1.0",
        false,
      );
      setCompileResult(res);
      setCompileId("");
      setCompileText("");
      setCompileAttachments([]);
      await refresh();
      handleSelectGovCanon(res.canon_id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCompiling(false);
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!rawContent.trim() && uploadedAttachments.length === 0) {
      setError(
        "Please enter campaign copy or attach at least one document or banner image.",
      );
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const sub = await createSubmission(
        title.trim() || "Untitled Campaign",
        rawContent,
        selectedCanon,
        [],
        uploadedAttachments,
      );
      // Automatically run pre-flight scan before opening Review Studio
      await fetch(`/api/submissions/${sub.id}/scan?alpha=0.1`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("cg_token") ?? ""}`,
        },
      }).catch(() => {});

      setShowForm(false);
      setTitle("");
      setRawContent("");
      setUploadedAttachments([]);
      navigate(`/submissions/${sub.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeleteSubmission(
    e: React.MouseEvent,
    submissionId: number,
  ) {
    e.stopPropagation();
    setDeletingId(submissionId);
    setError(null);
    try {
      await deleteSubmission(submissionId);
      setSubmissions((prev) => prev.filter((s) => s.id !== submissionId));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setDeletingId(null);
    }
  }

  async function handleSwitchRoleMode(
    targetRole: "creator" | "reviewer" | "admin",
  ) {
    if (role === targetRole) return;
    setSwitchingRole(true);
    setError(null);
    try {
      await switchRole(targetRole);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSwitchingRole(false);
    }
  }

  async function readFilesAsBase64(
    files: FileList | null,
  ): Promise<BundleAttachmentPayload[]> {
    if (!files || files.length === 0) return [];
    const loaded: BundleAttachmentPayload[] = [];
    for (const file of Array.from(files)) {
      const buf = await file.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let binary = "";
      for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
      }
      loaded.push({
        filename: file.name,
        content_base64: btoa(binary),
      });
    }
    return loaded;
  }

  async function handleFileSelect(files: FileList | null) {
    const loaded = await readFilesAsBase64(files);
    if (loaded.length > 0) {
      setUploadedAttachments((prev) => [...prev, ...loaded]);
    }
  }

  async function handleCompileFileSelect(files: FileList | null) {
    const loaded = await readFilesAsBase64(files);
    if (loaded.length > 0) {
      setCompileAttachments((prev) => [...prev, ...loaded]);
    }
  }

  const activeCanonSummary = canons.find((c) => c.id === govCanonId);
  const currentRoleMeta = ROLE_META[role || "creator"] ?? ROLE_META.creator;
  const selectedCalRule = activeCanonSummary?.rules?.find(
    (r) => r.id === calRuleId,
  );

  const stageCounts = {
    stage1: submissions.filter(
      (s) => s.status === "draft" || s.status === "changes_requested",
    ).length,
    stage2: submissions.filter((s) => s.status === "in_review").length,
    stage3: submissions.filter((s) => s.status === "approved").length,
    stage4: submissions.filter((s) => s.status === "published").length,
  };

  const filteredSubmissions = submissions.filter((s) => {
    if (stageFilter === "all") return true;
    if (stageFilter === "mine") {
      if (role === "creator")
        return s.status === "draft" || s.status === "changes_requested";
      if (role === "reviewer") return s.status === "in_review";
      if (role === "admin") return s.status === "approved";
      return true;
    }
    if (stageFilter === "stage1")
      return s.status === "draft" || s.status === "changes_requested";
    if (stageFilter === "stage2") return s.status === "in_review";
    if (stageFilter === "stage3") return s.status === "approved";
    if (stageFilter === "stage4") return s.status === "published";
    return true;
  });

  return (
    <div className="dashboard-page">
      {/* Console Header */}
      <header className="console-header-curved">
        <div className="header-left">
          <Link
            to="/"
            style={{
              textDecoration: "none",
              display: "flex",
              alignItems: "center",
              gap: "0.55rem",
            }}
          >
            <span className="logo-icon">⛨</span>
            <h1>CanonGate</h1>
          </Link>
          <nav className="console-nav-tabs" aria-label="Workspace Views">
            <button
              type="button"
              className={`nav-tab-btn ${
                activeTab === "submissions" ? "active" : ""
              }`}
              onClick={() => setActiveTab("submissions")}
            >
              Campaign Queue ({submissions.length})
            </button>
            <button
              type="button"
              className={`nav-tab-btn ${
                activeTab === "governance" ? "active" : ""
              }`}
              onClick={() => setActiveTab("governance")}
            >
              Brand Playbooks &amp; Rule Studio
            </button>
          </nav>
        </div>

        <div className="header-right">
          {/* Authenticated User Identity Pill */}
          <div
            className="user-identity-pill"
            title={`Signed in as ${displayName || username} (@${username})`}
          >
            <span className="user-identity-avatar">
              {(displayName || username || "U").slice(0, 1).toUpperCase()}
            </span>
            <div className="user-identity-text">
              <span className="user-identity-name">
                {displayName || username}
              </span>
              <span className="user-identity-handle">@{username}</span>
            </div>
          </div>

          {/* RBAC Role Switcher (Preserves signed-in username) */}
          <div
            className="persona-switcher-group"
            title="Switch your active role in the 4-stage review workflow (keeps your signed-in identity)"
          >
            <span className="persona-switcher-label">Role View:</span>
            <button
              type="button"
              disabled={switchingRole}
              className={`persona-chip ${role === "creator" ? "active" : ""}`}
              onClick={() => handleSwitchRoleMode("creator")}
            >
              1 · Creator
            </button>
            <button
              type="button"
              disabled={switchingRole}
              className={`persona-chip ${role === "reviewer" ? "active" : ""}`}
              onClick={() => handleSwitchRoleMode("reviewer")}
            >
              2 · Brand Manager
            </button>
            <button
              type="button"
              disabled={switchingRole}
              className={`persona-chip ${role === "admin" ? "active" : ""}`}
              onClick={() => handleSwitchRoleMode("admin")}
            >
              3 · Legal Sign-Off
            </button>
          </div>

          <button type="button" onClick={logout} className="btn-ghost">
            Sign out
          </button>
        </div>
      </header>

      <main className="dashboard-main">
        {error && (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="btn-ghost"
              style={{ padding: "0.15rem 0.5rem", fontSize: "0.75rem" }}
              onClick={() => setError(null)}
            >
              Dismiss
            </button>
          </div>
        )}

        {activeTab === "submissions" ? (
          <>
            {/* 4-Stage Collaborative Governance Pipeline Banner */}
            <section
              className="workflow-pipeline-banner"
              aria-label="4-Stage Governance Workflow"
            >
              <div className="workflow-pipeline-header">
                <div>
                  <span className="workflow-pipeline-eyebrow">
                    4-STAGE COLLABORATIVE GOVERNANCE WORKFLOW
                  </span>
                  <h2 className="workflow-pipeline-title">
                    {currentRoleMeta.label} —{" "}
                    <span className="workflow-pipeline-highlight">
                      {currentRoleMeta.stageOwned}
                    </span>
                  </h2>
                  <p className="workflow-pipeline-subtitle">
                    {currentRoleMeta.responsibility}
                  </p>
                </div>
                <div className="toolbar-actions-group">
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => setShowForm(!showForm)}
                  >
                    {showForm ? "Hide Submission Form" : "+ New Campaign Bundle"}
                  </button>
                </div>
              </div>

              <div className="workflow-stage-cards">
                <button
                  type="button"
                  className={`workflow-stage-pill ${
                    stageFilter === "stage1" ? "selected" : ""
                  } ${role === "creator" ? "owned-by-me" : ""}`}
                  onClick={() =>
                    setStageFilter(stageFilter === "stage1" ? "all" : "stage1")
                  }
                >
                  <div className="stage-pill-top">
                    <span className="stage-pill-num">STAGE 1</span>
                    <span className="stage-pill-count">
                      {stageCounts.stage1}
                    </span>
                  </div>
                  <div className="stage-pill-name">
                    Creator Pre-Flight &amp; Fixes
                  </div>
                  <div className="stage-pill-owner">
                    Owner: Creator · Fix Blockers &amp; Document Overrides
                  </div>
                </button>

                <button
                  type="button"
                  className={`workflow-stage-pill ${
                    stageFilter === "stage2" ? "selected" : ""
                  } ${role === "reviewer" ? "owned-by-me" : ""}`}
                  onClick={() =>
                    setStageFilter(stageFilter === "stage2" ? "all" : "stage2")
                  }
                >
                  <div className="stage-pill-top">
                    <span className="stage-pill-num">STAGE 2</span>
                    <span className="stage-pill-count">
                      {stageCounts.stage2}
                    </span>
                  </div>
                  <div className="stage-pill-name">Brand Manager Review</div>
                  <div className="stage-pill-owner">
                    Owner: Brand Manager · Verify Diffs &amp; Approve
                  </div>
                </button>

                <button
                  type="button"
                  className={`workflow-stage-pill ${
                    stageFilter === "stage3" ? "selected" : ""
                  } ${role === "admin" ? "owned-by-me" : ""}`}
                  onClick={() =>
                    setStageFilter(stageFilter === "stage3" ? "all" : "stage3")
                  }
                >
                  <div className="stage-pill-top">
                    <span className="stage-pill-num">STAGE 3</span>
                    <span className="stage-pill-count">
                      {stageCounts.stage3}
                    </span>
                  </div>
                  <div className="stage-pill-name">
                    Authorised Legal Sign-Off
                  </div>
                  <div className="stage-pill-owner">
                    Owner: Legal Reviewer · Claim Sign-Off &amp; Release
                  </div>
                </button>

                <button
                  type="button"
                  className={`workflow-stage-pill ${
                    stageFilter === "stage4" ? "selected" : ""
                  }`}
                  onClick={() =>
                    setStageFilter(stageFilter === "stage4" ? "all" : "stage4")
                  }
                >
                  <div className="stage-pill-top">
                    <span className="stage-pill-num">STAGE 4</span>
                    <span className="stage-pill-count">
                      {stageCounts.stage4}
                    </span>
                  </div>
                  <div className="stage-pill-name">Approved &amp; Released</div>
                  <div className="stage-pill-owner">
                    Signed Audit Certificate &amp; Provenance Ready
                  </div>
                </button>
              </div>
            </section>

            {/* New Campaign Submission Form */}
            {showForm && (
              <form className="submission-form card" onSubmit={handleCreate}>
                <div className="gov-panel-header">
                  <div>
                    <h3>Submit Campaign Content for Pre-Publication Review</h3>
                    <p className="gov-panel-desc" style={{ marginBottom: 0 }}>
                      Enter your marketing copy, pricing table, or HTML below,
                      or attach `.docx`, `.pdf`, `.html`, `.md`, `.png`, or
                      `.jpg` files to scan against your chosen Brand Playbook.
                    </p>
                  </div>
                </div>

                <div className="form-row" style={{ marginTop: "0.75rem" }}>
                  <div className="form-group flex-1">
                    <label htmlFor="sub-title">Campaign Title</label>
                    <input
                      id="sub-title"
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="e.g. Q3 Product Launch Landing Page & Banner"
                      required
                    />
                  </div>
                  <div className="form-group flex-1">
                    <label htmlFor="sub-canon">Governing Brand Playbook</label>
                    <select
                      id="sub-canon"
                      value={selectedCanon}
                      onChange={(e) => setSelectedCanon(e.target.value)}
                    >
                      {canons.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.id} (v{c.version} — {c.term_count} terms,{" "}
                          {c.fact_count} approved facts, {c.color_count} brand
                          colours)
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="sub-content">
                    Campaign Copy / Markdown Pricing Table / HTML Content
                  </label>
                  <textarea
                    id="sub-content"
                    rows={6}
                    value={rawContent}
                    onChange={(e) => setRawContent(e.target.value)}
                    placeholder="Write or paste your campaign copy, claims, disclaimers, or Markdown table here..."
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="sub-files">
                    Attach Documents or Promotional Banners (`.docx`, `.pdf`,
                    `.html`, `.md`, `.png`, `.jpg`)
                  </label>
                  <input
                    id="sub-files"
                    type="file"
                    multiple
                    accept=".docx,.pdf,.html,.htm,.md,.txt,.png,.jpg,.jpeg,.webp"
                    onChange={(e) => handleFileSelect(e.target.files)}
                  />
                  {uploadedAttachments.length > 0 && (
                    <div className="uploaded-files-pills">
                      {uploadedAttachments.map((att, idx) => (
                        <span
                          key={`${att.filename}-${idx}`}
                          className="file-pill"
                        >
                          📎 {att.filename}
                          <button
                            type="button"
                            style={{
                              marginLeft: "0.4rem",
                              border: "none",
                              background: "transparent",
                              cursor: "pointer",
                              color: "inherit",
                              fontWeight: 800,
                            }}
                            onClick={() =>
                              setUploadedAttachments((prev) =>
                                prev.filter((_, i) => i !== idx),
                              )
                            }
                          >
                            ✕
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div
                  style={{
                    display: "flex",
                    justifyContent: "flex-end",
                    gap: "0.75rem",
                    marginTop: "0.5rem",
                  }}
                >
                  {submissions.length > 0 && (
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => setShowForm(false)}
                    >
                      Cancel
                    </button>
                  )}
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={submitting}
                  >
                    {submitting
                      ? "Scanning & Opening Review Studio..."
                      : "Create & Open in Split-Screen Review Studio →"}
                  </button>
                </div>
              </form>
            )}

            {/* Queue Filter Tabs */}
            <div className="queue-filter-bar">
              <div className="queue-filter-tabs">
                <button
                  type="button"
                  className={`filter-pill ${
                    stageFilter === "all" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("all")}
                >
                  All Campaigns ({submissions.length})
                </button>
                <button
                  type="button"
                  className={`filter-pill ${
                    stageFilter === "mine" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("mine")}
                >
                  Action Required for {currentRoleMeta.shortLabel}
                </button>
                <button
                  type="button"
                  className={`filter-pill ${
                    stageFilter === "stage1" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("stage1")}
                >
                  Stage 1: Draft / Revisions ({stageCounts.stage1})
                </button>
                <button
                  type="button"
                  className={`filter-pill ${
                    stageFilter === "stage2" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("stage2")}
                >
                  Stage 2: Brand Review ({stageCounts.stage2})
                </button>
                <button
                  type="button"
                  className={`filter-pill ${
                    stageFilter === "stage3" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("stage3")}
                >
                  Stage 3: Legal Sign-Off ({stageCounts.stage3})
                </button>
                <button
                  type="button"
                  className={`filter-pill ${
                    stageFilter === "stage4" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("stage4")}
                >
                  Stage 4: Released ({stageCounts.stage4})
                </button>
              </div>
            </div>

            {loading ? (
              <div className="loading-state">Loading campaign queue...</div>
            ) : filteredSubmissions.length === 0 ? (
              <div className="empty-state card">
                <p>
                  {submissions.length === 0
                    ? "Your campaign queue is currently empty. Use the form above to submit your first campaign copy, document, or banner for pre-publication review."
                    : "No campaigns match the selected workflow stage filter."}
                </p>
                {stageFilter !== "all" && (
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ marginTop: "0.75rem" }}
                    onClick={() => setStageFilter("all")}
                  >
                    Show All Campaigns ({submissions.length})
                  </button>
                )}
              </div>
            ) : (
              <div className="submissions-grid">
                {filteredSubmissions.map((s) => {
                  const stageInfo = getStageMeta(s.status);
                  const isMyTurn = stageInfo.ownerRole === role;
                  return (
                    <div
                      key={s.id}
                      className={`submission-card card ${
                        isMyTurn ? "submission-card-my-turn" : ""
                      }`}
                      onClick={() => navigate(`/submissions/${s.id}`)}
                    >
                      <div className="sub-card-header">
                        <span className={`status-badge status-${s.status}`}>
                          {stageInfo.stageLabel}
                        </span>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.45rem",
                          }}
                        >
                          <span className="sub-canon-tag">{s.canon_id}</span>
                          <button
                            type="button"
                            className="btn-ghost"
                            style={{
                              padding: "0.18rem 0.45rem",
                              fontSize: "0.72rem",
                              color: "#64748b",
                            }}
                            disabled={deletingId === s.id}
                            onClick={(e) => handleDeleteSubmission(e, s.id)}
                            title="Delete this campaign bundle from queue"
                          >
                            {deletingId === s.id ? "…" : "✕"}
                          </button>
                        </div>
                      </div>
                      <h3 className="sub-card-title">{s.title}</h3>
                      <div
                        className={`sub-card-stage-owner ${
                          isMyTurn ? "owner-active" : ""
                        }`}
                      >
                        <span>
                          {isMyTurn ? "● Action Required — " : ""}
                          {stageInfo.ownerText}
                        </span>
                      </div>
                      <div
                        className="sub-card-meta"
                        style={{
                          justifyContent: "space-between",
                          alignItems: "center",
                          marginTop: "0.65rem",
                        }}
                      >
                        <span>
                          Bundle #{s.id} ·{" "}
                          {s.image_nodes && s.image_nodes.length > 0
                            ? `${s.image_nodes.length} banner(s)`
                            : `${s.text_blocks?.length ?? 1} text block(s)`}
                        </span>
                        <span
                          style={{
                            fontWeight: 700,
                            color: "#0f766e",
                            fontFamily: "var(--font-sans)",
                          }}
                        >
                          Open Review Studio →
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        ) : (
          /* Brand Playbooks & Rule Studio */
          <div className="governance-studio">
            <div className="toolbar">
              <div>
                <h2>Brand Playbooks, Rule Calibration &amp; Friction Insights</h2>
                <p className="gov-subtitle">
                  Inspect active brand playbooks, calibrate rule severities and
                  visual tolerances, and review automated v1.1 rule improvements
                  based on team override patterns.
                </p>
              </div>
              <div className="form-group" style={{ minWidth: "280px" }}>
                <label htmlFor="gov-canon-select">Active Brand Playbook</label>
                <select
                  id="gov-canon-select"
                  value={govCanonId}
                  onChange={(e) => handleSelectGovCanon(e.target.value)}
                >
                  {canons.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.id} (v{c.version})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {prAppliedBanner && (
              <div className="pr-applied-banner card">{prAppliedBanner}</div>
            )}

            {/* Playbook Summary Strip */}
            {activeCanonSummary && (
              <div className="canon-summary-strip">
                <div className="canon-metric-box">
                  <span className="canon-metric-val">
                    v{activeCanonSummary.version}
                  </span>
                  <span className="canon-metric-lbl">Playbook Version</span>
                </div>
                <div className="canon-metric-box">
                  <span className="canon-metric-val">
                    {activeCanonSummary.term_count}
                  </span>
                  <span className="canon-metric-lbl">Terminology Rules</span>
                </div>
                <div className="canon-metric-box">
                  <span className="canon-metric-val">
                    {activeCanonSummary.fact_count}
                  </span>
                  <span className="canon-metric-lbl">Approved Fact Claims</span>
                </div>
                <div className="canon-metric-box">
                  <span className="canon-metric-val">
                    {activeCanonSummary.color_count}
                  </span>
                  <span className="canon-metric-lbl">Brand Colour Tokens</span>
                </div>
                <div className="canon-metric-box">
                  <span className="canon-metric-val">
                    {frictionReport
                      ? `${(frictionReport.krippendorff_alpha * 100).toFixed(0)}%`
                      : "100%"}
                  </span>
                  <span className="canon-metric-lbl">Reviewer Consistency</span>
                </div>
              </div>
            )}

            {govLoading ? (
              <div className="loading-state">
                Loading playbook rules and review insights...
              </div>
            ) : (
              <div className="gov-panels-grid">
                {/* Panel 1: Guideline Consistency Check */}
                <div className="card gov-panel">
                  <div className="gov-panel-header">
                    <h3>1. Playbook Consistency Check</h3>
                    {lintReport && (
                      <span
                        className={`status-badge ${
                          lintReport.is_valid
                            ? "status-approved"
                            : "status-changes_requested"
                        }`}
                      >
                        {lintReport.is_valid
                          ? "VALID PLAYBOOK"
                          : `${lintReport.issues.length} ISSUE(S)`}
                      </span>
                    )}
                  </div>
                  <p className="gov-panel-desc">
                    Verifies that your playbook has no duplicate rule IDs,
                    contradictory terminology replacements, or overlapping brand
                    colours.
                  </p>
                  {lintReport && lintReport.issues.length === 0 ? (
                    <div className="gov-clean-box">
                      ✓ All terminology rules, approved claims, and colour
                      tokens in <strong>{lintReport.canon_id}</strong> (v
                      {lintReport.canon_version}) are consistent and conflict-free.
                    </div>
                  ) : (
                    <ul className="gov-issue-list">
                      {lintReport?.issues.map((iss, idx) => (
                        <li key={idx} className="gov-issue-item">
                          <strong>[{iss.kind.toUpperCase()}]</strong>{" "}
                          {iss.message} (<code>{iss.rule_ids.join(", ")}</code>)
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Panel 2: Guideline Friction Insights */}
                <div className="card gov-panel">
                  <div className="gov-panel-header">
                    <h3>2. Guideline Friction &amp; Override Insights</h3>
                    <span className="sub-canon-tag">
                      {frictionReport?.total_findings ?? 0} total flags
                    </span>
                  </div>
                  <p className="gov-panel-desc">
                    Identifies which brand rules are repeatedly overridden by
                    creators or reviewers so you can clarify ambiguous wording
                    or adjust severity.
                  </p>

                  {frictionReport && frictionReport.rules.length > 0 ? (
                    <table className="slot-diff-table">
                      <thead>
                        <tr>
                          <th>Rule ID</th>
                          <th>Flags</th>
                          <th>Overrides</th>
                          <th>Friction Rate</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {frictionReport.rules.map((r) => (
                          <tr key={r.rule_id}>
                            <td>
                              <code>{r.rule_id}</code>
                            </td>
                            <td>{r.total_flags}</td>
                            <td>{r.overrides_and_disputes}</td>
                            <td>{(r.posterior_friction * 100).toFixed(1)}%</td>
                            <td
                              className={
                                r.needs_canon_revision
                                  ? "slot-dropped"
                                  : "slot-match"
                              }
                            >
                              {r.needs_canon_revision
                                ? "REVIEW RULE"
                                : "HEALTHY"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="gov-clean-box">
                      No rule overrides recorded yet for{" "}
                      <strong>{govCanonId}</strong>. As your team reviews
                      campaigns and records overrides, rule friction metrics
                      will appear here automatically.
                    </div>
                  )}

                  <div className="gov-pr-controls">
                    <label className="threshold-label">
                      <span>
                        Friction Alert Threshold:{" "}
                        <strong>{(prThreshold * 100).toFixed(0)}%</strong>
                      </span>
                      <input
                        type="range"
                        min="0.15"
                        max="0.60"
                        step="0.05"
                        value={prThreshold}
                        onChange={(e) => setPrThreshold(Number(e.target.value))}
                      />
                    </label>
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={handleProposePr}
                      disabled={prLoading}
                    >
                      {prLoading
                        ? "Analysing Past Reviews..."
                        : "Draft Playbook v1.1 Improvement"}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Panel 3: Proposed Playbook v1.1 Diff */}
            {prProposal && (
              <div className="card gov-pr-card">
                <div className="gov-panel-header">
                  <div>
                    <h3>
                      3. Proposed Playbook Update: {prProposal.canon_id} v
                      {prProposal.base_version} → v{prProposal.proposed_version}
                    </h3>
                    <p className="gov-panel-desc">
                      Simulated impact across{" "}
                      <strong>{prProposal.bundles_evaluated}</strong> past
                      campaign(s): Total Flags{" "}
                      <strong>{prProposal.before_findings}</strong> →{" "}
                      <strong>{prProposal.after_findings}</strong> (
                      {(prProposal.reduction_ratio * 100).toFixed(1)}% reduction
                      in false alarms)
                    </p>
                  </div>
                  {prProposal.has_changes && (
                    <button
                      type="button"
                      className="btn-action btn-action-approve"
                      onClick={handleApplyPr}
                      disabled={applyingPr}
                    >
                      {applyingPr
                        ? "Activating v1.1..."
                        : `✓ Approve & Activate v${prProposal.proposed_version}`}
                    </button>
                  )}
                </div>

                {prProposal.revisions.length > 0 ? (
                  <>
                    <table className="slot-diff-table">
                      <thead>
                        <tr>
                          <th>Rule ID</th>
                          <th>Recommended Change</th>
                          <th>Current Rule (v{prProposal.base_version})</th>
                          <th>Updated Rule (v{prProposal.proposed_version})</th>
                          <th>Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {prProposal.revisions.map((rev) => (
                          <tr key={rev.rule_id}>
                            <td>
                              <code>{rev.rule_id}</code>
                            </td>
                            <td>
                              <span className="tier-badge">{rev.action}</span>
                            </td>
                            <td>{rev.before_summary}</td>
                            <td>
                              <strong>{rev.after_summary}</strong>
                            </td>
                            <td>{rev.rationale}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                    {prProposal.yaml_diff && (
                      <div className="yaml-diff-box">
                        <div className="yaml-diff-title">
                          Playbook Diff Preview
                        </div>
                        <pre className="yaml-diff-pre">
                          {prProposal.yaml_diff}
                        </pre>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="gov-clean-box">
                    No rules in <strong>{prProposal.canon_id}</strong> currently
                    exceed the {(prThreshold * 100).toFixed(0)}% friction
                    threshold.
                  </div>
                )}
              </div>
            )}

            {/* Panel 4 & 5: Calibrate Rule Thresholds + Import New Playbook */}
            <div className="gov-panels-grid" style={{ marginTop: "1.25rem" }}>
              {/* Panel 4: Calibrate Rule Thresholds */}
              <div className="card gov-panel">
                <div className="gov-panel-header">
                  <h3>4. Calibrate Rule Thresholds</h3>
                  <span className="sub-canon-tag">Brand Manager Controls</span>
                </div>
                <p className="gov-panel-desc">
                  Select any rule in <strong>{govCanonId}</strong> to adjust
                  whether it acts as a non-blocking Warning (<code>1–49</code>)
                  or a hard Blocker (<code>50–100</code>), or fine-tune colour
                  and readability limits.
                </p>
                <form
                  onSubmit={handleCalibrateRule}
                  className="gov-calibrate-form"
                >
                  <div className="form-group">
                    <label htmlFor="cal-rule-select">
                      Select Rule from <code>{govCanonId}</code>
                    </label>
                    {activeCanonSummary?.rules &&
                    activeCanonSummary.rules.length > 0 ? (
                      <select
                        id="cal-rule-select"
                        value={calRuleId}
                        onChange={(e) => handleSelectCalRule(e.target.value)}
                      >
                        {activeCanonSummary.rules.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        id="cal-rule-select"
                        type="text"
                        value={calRuleId}
                        onChange={(e) => setCalRuleId(e.target.value)}
                        placeholder="Select a rule ID"
                      />
                    )}
                  </div>

                  {selectedCalRule?.source_text && (
                    <div
                      className="gov-clean-box"
                      style={{ marginBottom: "0.75rem", fontSize: "0.78rem" }}
                    >
                      <strong>Source Guideline:</strong>{" "}
                      {selectedCalRule.source_text}
                    </div>
                  )}

                  <div className="slider-grid">
                    <label className="threshold-label">
                      <span>
                        Rule Severity: <strong>{calSeverity}</strong> (
                        {calSeverity >= 50 ? "BLOCKER" : "WARNING"})
                      </span>
                      <input
                        type="range"
                        min="10"
                        max="95"
                        step="5"
                        value={calSeverity}
                        onChange={(e) => setCalSeverity(Number(e.target.value))}
                      />
                    </label>
                    <label className="threshold-label">
                      <span>
                        Colour Drift Tolerance (ΔE):{" "}
                        <strong>{calMaxDeltaE.toFixed(1)}</strong>
                      </span>
                      <input
                        type="range"
                        min="1.0"
                        max="12.0"
                        step="0.5"
                        value={calMaxDeltaE}
                        onChange={(e) =>
                          setCalMaxDeltaE(Number(e.target.value))
                        }
                      />
                    </label>
                    <label className="threshold-label">
                      <span>
                        Max Sentence Length: <strong>{calMaxWords} words</strong>
                      </span>
                      <input
                        type="range"
                        min="15"
                        max="45"
                        step="1"
                        value={calMaxWords}
                        onChange={(e) => setCalMaxWords(Number(e.target.value))}
                      />
                    </label>
                    <label className="threshold-label">
                      <span>
                        Max Reading Grade Level:{" "}
                        <strong>{calMaxFkGrade.toFixed(1)}</strong>
                      </span>
                      <input
                        type="range"
                        min="6.0"
                        max="16.0"
                        step="0.5"
                        value={calMaxFkGrade}
                        onChange={(e) =>
                          setCalMaxFkGrade(Number(e.target.value))
                        }
                      />
                    </label>
                  </div>

                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={calibrating || !calRuleId}
                    style={{ marginTop: "0.75rem" }}
                  >
                    {calibrating
                      ? "Saving Rule Settings..."
                      : `Save Calibration for '${calRuleId}'`}
                  </button>
                </form>

                {calibrationResult && (
                  <div
                    className="gov-clean-box"
                    style={{ marginTop: "0.75rem" }}
                  >
                    ✓ Updated <strong>{calibrationResult.canon_id}</strong> (v
                    {calibrationResult.previous_version} → v
                    {calibrationResult.new_version})
                  </div>
                )}
              </div>

              {/* Panel 5: Import New Brand Playbook */}
              <div className="card gov-panel">
                <div className="gov-panel-header">
                  <h3>5. Import New Brand Playbook</h3>
                  <span className="sub-canon-tag">PDF / DOCX / Text</span>
                </div>
                <p className="gov-panel-desc">
                  Create a new enforceable Brand Playbook from your brand
                  guidelines, approved product fact sheets, and hex colour
                  palette.
                </p>
                <form
                  onSubmit={handleCompileCanon}
                  className="gov-compile-form"
                >
                  <div className="form-group">
                    <label htmlFor="compile-canon-id">Playbook Identifier</label>
                    <input
                      id="compile-canon-id"
                      type="text"
                      value={compileId}
                      onChange={(e) => setCompileId(e.target.value)}
                      placeholder="e.g. my-brand-playbook"
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="compile-raw-text">
                      Brand Rules, Approved Claims &amp; Colour Hex Codes
                    </label>
                    <textarea
                      id="compile-raw-text"
                      rows={4}
                      value={compileText}
                      onChange={(e) => setCompileText(e.target.value)}
                      placeholder="Example: Never use 'cheap', prefer 'affordable'. Primary Blue: #1A73E8. Approved Claim: 0% processing fee on loans under Rs 50,000 valid until 2026-09-30."
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="compile-files">
                      Or Upload Brand Book / Fact Sheet (`.pdf`, `.docx`, `.md`)
                    </label>
                    <input
                      id="compile-files"
                      type="file"
                      multiple
                      accept=".pdf,.docx,.md,.txt"
                      onChange={(e) => handleCompileFileSelect(e.target.files)}
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={compiling}
                  >
                    {compiling
                      ? "Compiling Brand Playbook..."
                      : "Import & Activate Playbook"}
                  </button>
                </form>

                {compileResult && (
                  <div
                    className="gov-clean-box"
                    style={{ marginTop: "0.75rem" }}
                  >
                    <div>
                      ✓ Imported Playbook{" "}
                      <strong>{compileResult.canon_id}</strong> (
                      {compileResult.term_count} terms,{" "}
                      {compileResult.color_count} colours,{" "}
                      {compileResult.fact_count} approved facts)
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
