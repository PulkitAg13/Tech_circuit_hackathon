import { useState, useEffect, useCallback, type FormEvent } from "react";
import {
  listSubmissions,
  listCanons,
  createSubmission,
  getCanonLint,
  getCanonFriction,
  proposeCanonPr,
  applyCanonPr,
  calibrateCanonRule,
  compileBrandCanon,
  getFindings,
  resolveFinding,
  workflowAction,
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

const SAMPLE_CAMPAIGNS: Record<
  string,
  { title: string; content: string; badge: string }
> = {
  "indian-digital-lending": {
    title: "Q3 Instant Digital Loan — Rapido & FirstCry Red-Team Bundle",
    badge: "RBI 2025 KFS + CCPA 2022",
    content: `Get a 0% processing fee on personal loans today with instant approval in 5 minutes!

Buy our cheap credit protection plan for users who want cutting-edge financial freedom.

| Loan Slab | Interest Rate (p.a.) | Processing Fee |
| --- | --- | --- |
| Personal Loan | 10.5% | 0% |
| *T&C Apply: GST and additional charges may apply on discounted fee | | |

color: #FFFFFF; background-color: #777777; Muted grey footnote disclaimer text failing WCAG 2.1 AA contrast.`,
  },
  "indian-d2c-nutra": {
    title: "Monsoon Hair & Immunity D2C Influencer Campaign",
    badge: "ASCI FY25-26 + Influencer Disclosure",
    content: `Clinically proven to regrow 23,800 hair strands in 30 days with 100% natural Rosemary extract!

Partnering with @GlowWithMe for this monsoon transformation routine — buy our cheap starter kit today and cure hair fall permanently.`,
  },
  "acme-corp": {
    title: "Acme Cloud Enterprise Launch Announcement",
    badge: "B2B SaaS Brand Canon",
    content: `Acme Corp was founded in 2018 and serves over 500 enterprise customers worldwide.

Buy our cheap cutting-edge cloud governance suite so your users can deploy faster.`,
  },
};

const SAMPLE_BRAND_BOOK_SPEC = `Brand Voice Guideline: Never use 'cheap', prefer 'affordable'. Never use 'guaranteed', prefer 'designed to'.
Approved Palette — Primary Royal Blue: #1A73E8
Approved KFS Claim: 0% processing fee on personal loans under Rs 50,000 valid until 2026-09-30.`;

const ROLE_META: Record<
  string,
  { label: string; shortLabel: string; stageOwned: string; responsibility: string }
> = {
  creator: {
    label: "Creator (Marketing / Agency)",
    shortLabel: "Creator",
    stageOwned: "Stage 1 · Pre-Flight & Remediation",
    responsibility:
      "Authors multimodal campaign bundles, runs Tier 1+2 pre-flight scans, resolves Blockers, and records justifications on Warning overrides.",
  },
  reviewer: {
    label: "Brand Manager (Canon Owner)",
    shortLabel: "Brand Manager",
    stageOwned: "Stage 2 · Brand & Canon Review",
    responsibility:
      "Ingests & calibrates Brand Canons, reviews revision diffs & Creator overrides, and approves brand compliance to forward to Legal.",
  },
  admin: {
    label: "Authorised Legal Reviewer",
    shortLabel: "Legal Sign-Off",
    stageOwned: "Stage 3 · Statutory & Legal Sign-Off",
    responsibility:
      "Audits statutory SlotDiff claims (RBI KFS, CCPA, ASCI) and Merkle ledger to execute final legal sign-off and C2PA release.",
  },
};

function getStageMeta(status: string) {
  switch (status) {
    case "draft":
      return {
        stageNum: 1,
        stageLabel: "Stage 1 · Creator Draft",
        ownerRole: "creator",
        ownerText: "Creator Action: Run Scan & Fix Blockers",
      };
    case "changes_requested":
      return {
        stageNum: 1,
        stageLabel: "Stage 1 · Changes Requested",
        ownerRole: "creator",
        ownerText: "Creator Action: Address Reviewer Feedback",
      };
    case "in_review":
      return {
        stageNum: 2,
        stageLabel: "Stage 2 · Brand Review",
        ownerRole: "reviewer",
        ownerText: "Brand Manager Gate: Verify Diffs & Overrides",
      };
    case "approved":
      return {
        stageNum: 3,
        stageLabel: "Stage 3 · Legal Sign-Off",
        ownerRole: "admin",
        ownerText: "Legal Reviewer Gate: Final Statutory Sign-Off",
      };
    case "published":
      return {
        stageNum: 4,
        stageLabel: "Stage 4 · Sealed & Released",
        ownerRole: "published",
        ownerText: "Released · SHA-256 + Ed25519 Certificate Ready",
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

  // New submission form
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [rawContent, setRawContent] = useState("");
  const [selectedCanon, setSelectedCanon] = useState("");
  const [imagePathsInput, setImagePathsInput] = useState("");
  const [uploadedAttachments, setUploadedAttachments] = useState<
    BundleAttachmentPayload[]
  >([]);
  const [submitting, setSubmitting] = useState(false);
  const [seedingDemo, setSeedingDemo] = useState(false);
  const [switchingRole, setSwitchingRole] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Canon Governance & Closed-Loop PR Studio state
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

  // Brand Manager Confirm & Calibrate Sliders state (populated dynamically from selected Canon)
  const [calRuleId, setCalRuleId] = useState<string>("");
  const [calSeverity, setCalSeverity] = useState<number>(40);
  const [calMaxDeltaE, setCalMaxDeltaE] = useState<number>(5.0);
  const [calMaxWords, setCalMaxWords] = useState<number>(28);
  const [calMaxFkGrade, setCalMaxFkGrade] = useState<number>(11.0);
  const [calibrating, setCalibrating] = useState(false);
  const [calibrationResult, setCalibrationResult] =
    useState<CalibrateCanonRuleResponse | null>(null);

  // Pipeline A Compile-to-Schema Onboarding state (no hardcoded Canon ID)
  const [compileId, setCompileId] = useState<string>("");
  const [compileText, setCompileText] = useState<string>("");
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
              "Practitioners repeatedly disputed strict threshold on promotional copy; clarify scope and calibrate tolerance in v1.1.";
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
        `Merged Canon ${updated.id} v${updated.version} (SHA-256: ${updated.hash.slice(0, 12)}…) into active governance registry.`,
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
    if (!targetId || !compileText.trim()) {
      setError(
        "Please provide both a target Canon ID and brand guideline text to compile.",
      );
      return;
    }
    setCompiling(true);
    setError(null);
    try {
      const res = await compileBrandCanon(
        targetId,
        compileText,
        [],
        "1.0",
        false,
      );
      setCompileResult(res);
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
    setSubmitting(true);
    setError(null);
    try {
      const imagePaths = imagePathsInput
        .split(",")
        .map((p) => p.trim())
        .filter(Boolean);
      const sub = await createSubmission(
        title,
        rawContent,
        selectedCanon,
        imagePaths,
        uploadedAttachments,
      );
      setShowForm(false);
      setTitle("");
      setRawContent("");
      setImagePathsInput("");
      setUploadedAttachments([]);
      navigate(`/submissions/${sub.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  function handleLoadSampleTemplate(canonId: string) {
    const sample =
      SAMPLE_CAMPAIGNS[canonId] ?? SAMPLE_CAMPAIGNS["indian-digital-lending"];
    setSelectedCanon(canonId);
    setTitle(sample.title);
    setRawContent(sample.content);
    setShowForm(true);
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

  async function handleSeedDemoPipeline() {
    setSeedingDemo(true);
    setError(null);
    const originalRole = role || "creator";
    try {
      const sample = SAMPLE_CAMPAIGNS["indian-digital-lending"];
      const sub = await createSubmission(
        "RBI 2025 KFS & CCPA Pre-Flight — Instant Personal Loan Bundle",
        sample.content,
        "indian-digital-lending",
        [],
        [],
      );

      await fetch(`/api/submissions/${sub.id}/scan?alpha=0.1`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("cg_token") ?? ""}`,
        },
      });

      const findings = await getFindings(sub.id);
      for (const f of findings) {
        if (f.severity >= 50) {
          await resolveFinding(
            sub.id,
            f.row_id,
            "accepted",
            "Accepted canon-grounded qualifier & WCAG contrast fix",
          );
        } else {
          await resolveFinding(
            sub.id,
            f.row_id,
            "overridden",
            "Approved promotional phrasing per Q3 BFSI campaign brief",
          );
        }
      }

      if (role !== "creator") {
        await switchRole("creator");
      }
      await workflowAction(
        sub.id,
        "submit",
        "Creator pre-flight scan complete; all blockers remediated and warnings documented.",
      );

      await switchRole("reviewer");
      await workflowAction(
        sub.id,
        "approve",
        "Brand Manager verified KFS SlotDiff alignment, voice profile, and warning override rationale.",
      );

      if (originalRole !== "reviewer") {
        await switchRole(originalRole);
      }

      await refresh();
      navigate(`/submissions/${sub.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSeedingDemo(false);
    }
  }

  async function handleFileSelect(files: FileList | null) {
    if (!files || files.length === 0) return;
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
    setUploadedAttachments((prev) => [...prev, ...loaded]);
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
      {/* Curved Console Header */}
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
              Canon Governance & v1.1 PR Studio
            </button>
          </nav>
        </div>

        <div className="header-right">
          {/* Authenticated User Identity Badge (Never hijacked on role switch) */}
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

          {/* RBAC Role Mode Switcher (Updates current user's role without changing username) */}
          <div
            className="persona-switcher-group"
            title="Switch your active RBAC role in the 4-stage workflow (preserves your signed-in account)"
          >
            <span className="persona-switcher-label">Active Role:</span>
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
            {/* 4-Stage SOTA Collaborative Governance Pipeline Overview */}
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
                    Active Workspace: {currentRoleMeta.label} —{" "}
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
                    className="btn-secondary"
                    disabled={seedingDemo}
                    onClick={handleSeedDemoPipeline}
                    title="Seeds a complete Indian Digital Lending campaign bundle, resolves findings, and advances it through Brand Review so Legal Sign-Off & Certificate export can be inspected immediately."
                  >
                    {seedingDemo
                      ? "Seeding Demo Workflow..."
                      : "⚡ Seed End-to-End Demo Bundle"}
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => setShowForm(!showForm)}
                  >
                    {showForm ? "Cancel" : "+ New Campaign Bundle"}
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
                    <span className="stage-pill-count">{stageCounts.stage1}</span>
                  </div>
                  <div className="stage-pill-name">
                    Creator Pre-Flight & Fixes
                  </div>
                  <div className="stage-pill-owner">
                    Owner: Creator · Fix Blockers & Override Warnings
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
                    <span className="stage-pill-count">{stageCounts.stage2}</span>
                  </div>
                  <div className="stage-pill-name">
                    Brand Manager Review
                  </div>
                  <div className="stage-pill-owner">
                    Owner: Brand Manager · Audit Diffs & Approve
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
                    <span className="stage-pill-count">{stageCounts.stage3}</span>
                  </div>
                  <div className="stage-pill-name">
                    Authorised Legal Sign-Off
                  </div>
                  <div className="stage-pill-owner">
                    Owner: Legal Reviewer · Claim-Only Gate & Release
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
                    <span className="stage-pill-count">{stageCounts.stage4}</span>
                  </div>
                  <div className="stage-pill-name">
                    Cryptographically Released
                  </div>
                  <div className="stage-pill-owner">
                    SHA-256 Chain + Ed25519 STH + C2PA Assets
                  </div>
                </button>
              </div>
            </section>

            {/* Quick-load starter templates bar */}
            <div className="template-quickstart-bar">
              <span className="template-bar-label">
                Quick-Load Red-Team Campaign Bundle:
              </span>
              <button
                type="button"
                className="template-chip"
                onClick={() =>
                  handleLoadSampleTemplate("indian-digital-lending")
                }
              >
                🏦 Indian Digital Lending (RBI KFS + CCPA)
              </button>
              <button
                type="button"
                className="template-chip"
                onClick={() => handleLoadSampleTemplate("indian-d2c-nutra")}
              >
                🌿 D2C Personal Care & Nutra (ASCI FY25-26)
              </button>
              <button
                type="button"
                className="template-chip"
                onClick={() => handleLoadSampleTemplate("acme-corp")}
              >
                ☁️ Acme Enterprise Cloud (B2B SaaS)
              </button>
            </div>

            {showForm && (
              <form className="submission-form card" onSubmit={handleCreate}>
                <h3>Submit Multimodal Campaign Bundle for Governance Check</h3>
                <div className="form-row">
                  <div className="form-group flex-1">
                    <label htmlFor="sub-title">Campaign Title</label>
                    <input
                      id="sub-title"
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="e.g. Q3 Instant Loan Promotional Landing Page"
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="sub-canon">Governing Brand Canon</label>
                    <select
                      id="sub-canon"
                      value={selectedCanon}
                      onChange={(e) => setSelectedCanon(e.target.value)}
                    >
                      {canons.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.id} (v{c.version} — {c.term_count} terms,{" "}
                          {c.fact_count} facts, {c.color_count} colours)
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="form-group">
                  <label htmlFor="sub-content">
                    Campaign Copy / Markdown Table / HTML Snippet (double
                    newline between blocks)
                  </label>
                  <textarea
                    id="sub-content"
                    rows={8}
                    value={rawContent}
                    onChange={(e) => setRawContent(e.target.value)}
                    placeholder="Paste your marketing copy, KFS pricing table, or HTML snippet here..."
                  />
                </div>
                <div className="form-row">
                  <div className="form-group flex-1">
                    <label htmlFor="sub-files">
                      Upload Multimodal Files (`.docx`, `.pdf`, `.html`, `.md`,
                      `.png`, `.jpg` Banners)
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
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="form-group flex-1">
                    <label htmlFor="sub-images">
                      Server Image / Banner Asset Paths (optional,
                      comma-separated)
                    </label>
                    <input
                      id="sub-images"
                      type="text"
                      value={imagePathsInput}
                      onChange={(e) => setImagePathsInput(e.target.value)}
                      placeholder="e.g. /assets/banners/monsoon_promo.png"
                    />
                  </div>
                </div>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={submitting}
                >
                  {submitting
                    ? "Parsing ContentAST & Creating Bundle..."
                    : "Create & Open in Split-Screen Review Studio →"}
                </button>
              </form>
            )}

            {/* Queue Filter Tabs */}
            <div className="queue-filter-bar">
              <div className="queue-filter-tabs">
                <button
                  type="button"
                  className={`filter-pill ${stageFilter === "all" ? "active" : ""}`}
                  onClick={() => setStageFilter("all")}
                >
                  All Bundles ({submissions.length})
                </button>
                <button
                  type="button"
                  className={`filter-pill ${stageFilter === "mine" ? "active" : ""}`}
                  onClick={() => setStageFilter("mine")}
                >
                  Action Required for {currentRoleMeta.shortLabel}
                </button>
                <button
                  type="button"
                  className={`filter-pill ${stageFilter === "stage1" ? "active" : ""}`}
                  onClick={() => setStageFilter("stage1")}
                >
                  Stage 1: Draft / Revisions ({stageCounts.stage1})
                </button>
                <button
                  type="button"
                  className={`filter-pill ${stageFilter === "stage2" ? "active" : ""}`}
                  onClick={() => setStageFilter("stage2")}
                >
                  Stage 2: Brand Review ({stageCounts.stage2})
                </button>
                <button
                  type="button"
                  className={`filter-pill ${stageFilter === "stage3" ? "active" : ""}`}
                  onClick={() => setStageFilter("stage3")}
                >
                  Stage 3: Legal Sign-Off ({stageCounts.stage3})
                </button>
                <button
                  type="button"
                  className={`filter-pill ${stageFilter === "stage4" ? "active" : ""}`}
                  onClick={() => setStageFilter("stage4")}
                >
                  Stage 4: Released ({stageCounts.stage4})
                </button>
              </div>
            </div>

            {loading ? (
              <div className="loading-state">Loading campaign bundles...</div>
            ) : filteredSubmissions.length === 0 ? (
              <div className="empty-state card">
                <p>
                  {submissions.length === 0
                    ? "No campaign bundles in the queue yet. Click one of the Quick-Load Red-Team Campaign Bundles above or click + New Campaign Bundle to get started."
                    : "No campaign bundles match the selected workflow stage filter."}
                </p>
                {stageFilter !== "all" && (
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ marginTop: "0.75rem" }}
                    onClick={() => setStageFilter("all")}
                  >
                    Show All Bundles ({submissions.length})
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
                        <span className="sub-canon-tag">{s.canon_id}</span>
                      </div>
                      <h3 className="sub-card-title">{s.title}</h3>
                      <div
                        className={`sub-card-stage-owner ${
                          isMyTurn ? "owner-active" : ""
                        }`}
                      >
                        <span>
                          {isMyTurn ? "● Action Required: " : "Next Step: "}
                          {stageInfo.ownerText}
                        </span>
                      </div>
                      <div className="sub-card-meta">
                        <span>Bundle #{s.id}</span>
                        <span>SHA-256: {s.content_hash.slice(0, 10)}…</span>
                        {s.image_nodes && s.image_nodes.length > 0 && (
                          <span>🖼 {s.image_nodes.length} banner(s)</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        ) : (
          /* Canon Governance, Empirical Bayes Friction & Closed-Loop v1.1 PR Studio */
          <div className="governance-studio">
            <div className="toolbar">
              <div>
                <h2>Canon Governance, Friction Telemetry & v1.1 PR Studio</h2>
                <p className="gov-subtitle">
                  Closed-loop Empirical Bayes Beta-Binomial guideline friction (
                  <code>Friction(R_i) &gt; 0.40</code>) → automated Canon v1.1
                  PR generator & historical bundle backtest
                </p>
              </div>
              <div className="form-group" style={{ minWidth: "280px" }}>
                <label htmlFor="gov-canon-select">Active Brand Canon</label>
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

            {/* Canon Schema Summary Strip */}
            {activeCanonSummary && (
              <div className="canon-summary-strip">
                <div className="canon-metric-box">
                  <span className="canon-metric-val">
                    v{activeCanonSummary.version}
                  </span>
                  <span className="canon-metric-lbl">Canon Version</span>
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
                  <span className="canon-metric-lbl">
                    Palette Tokens (ΔE00)
                  </span>
                </div>
                <div className="canon-metric-box">
                  <span className="canon-metric-val">
                    {frictionReport
                      ? frictionReport.krippendorff_alpha.toFixed(3)
                      : "1.000"}
                  </span>
                  <span className="canon-metric-lbl">
                    Krippendorff&apos;s α Agreement
                  </span>
                </div>
              </div>
            )}

            {govLoading ? (
              <div className="loading-state">
                Computing Empirical Bayes friction telemetry and linting
                Canon...
              </div>
            ) : (
              <div className="gov-panels-grid">
                {/* Panel 1: Static Canon Linter */}
                <div className="card gov-panel">
                  <div className="gov-panel-header">
                    <h3>1. Static Canon Integrity Linter</h3>
                    {lintReport && (
                      <span
                        className={`status-badge ${
                          lintReport.is_valid
                            ? "status-approved"
                            : "status-changes_requested"
                        }`}
                      >
                        {lintReport.is_valid
                          ? "VALID SCHEMA"
                          : `${lintReport.issues.length} ISSUE(S)`}
                      </span>
                    )}
                  </div>
                  <p className="gov-panel-desc">
                    Checks for duplicate rule IDs, circular terminology
                    replacements (<code>A → B → A</code>), and uncalibrated
                    CIEDE2000 colour collisions.
                  </p>
                  {lintReport && lintReport.issues.length === 0 ? (
                    <div className="gov-clean-box">
                      ✓ Zero circular terminology rules, duplicate IDs, or
                      palette collisions detected in{" "}
                      <strong>{lintReport.canon_id}</strong> (v
                      {lintReport.canon_version}).
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

                {/* Panel 2: Empirical Bayes Guideline Friction */}
                <div className="card gov-panel">
                  <div className="gov-panel-header">
                    <h3>2. Empirical Bayes Guideline Friction</h3>
                    <span className="sub-canon-tag">
                      {frictionReport?.total_findings ?? 0} historical flags
                    </span>
                  </div>
                  <p className="gov-panel-desc">
                    Applies Beta(1, 4) shrinkage so single-flag noise shrinks
                    toward the prior while systematically disputed rules (
                    <code>posterior &gt; {prThreshold.toFixed(2)}</code>)
                    trigger a Canon v1.1 revision.
                  </p>

                  {frictionReport && frictionReport.rules.length > 0 ? (
                    <table className="slot-diff-table">
                      <thead>
                        <tr>
                          <th>Rule ID</th>
                          <th>Flags</th>
                          <th>Overrides / Disputes</th>
                          <th>Posterior Friction</th>
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
                                ? "NEEDS v1.1 PR"
                                : "CALIBRATED"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="gov-clean-box">
                      No historical overrides recorded yet for{" "}
                      <strong>{govCanonId}</strong>. Run a scan on a submission
                      and override a Warning to populate live friction
                      telemetry, or click{" "}
                      <strong>Simulate &amp; Propose Canon v1.1 PR</strong>{" "}
                      below.
                    </div>
                  )}

                  <div className="gov-pr-controls">
                    <label className="threshold-label">
                      <span>
                        Friction Trigger Threshold:{" "}
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
                        ? "Simulating Historical Bundles..."
                        : "Simulate & Propose Canon v1.1 PR"}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Panel 3: Proposed Canon v1.1 PR Diff & Backtest Impact */}
            {prProposal && (
              <div className="card gov-pr-card">
                <div className="gov-panel-header">
                  <div>
                    <h3>
                      3. Auto-Drafted Canon PR: {prProposal.canon_id} v
                      {prProposal.base_version} → v{prProposal.proposed_version}
                    </h3>
                    <p className="gov-panel-desc">
                      Historical Backtest across{" "}
                      <strong>{prProposal.bundles_evaluated}</strong> campaign
                      bundle(s): Total Findings{" "}
                      <strong>{prProposal.before_findings}</strong> →{" "}
                      <strong>{prProposal.after_findings}</strong> (
                      {(prProposal.reduction_ratio * 100).toFixed(1)}% noise
                      reduction)
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
                        ? "Merging v1.1..."
                        : `✓ Merge & Activate v${prProposal.proposed_version}`}
                    </button>
                  )}
                </div>

                {prProposal.revisions.length > 0 ? (
                  <>
                    <table className="slot-diff-table">
                      <thead>
                        <tr>
                          <th>Rule ID</th>
                          <th>Action</th>
                          <th>Before (v{prProposal.base_version})</th>
                          <th>After (v{prProposal.proposed_version})</th>
                          <th>Rationale</th>
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
                          Unified Canon YAML Diff
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
                    exceed the {(prThreshold * 100).toFixed(0)}% posterior
                    friction threshold. Override or dispute a finding in the
                    Review Studio (or lower the slider threshold) to generate a
                    v1.1 rule relaxation diff.
                  </div>
                )}
              </div>
            )}

            {/* Panel 4 & 5: Brand Manager Confirm & Calibrate Sliders + Pipeline A Compiler */}
            <div
              className="gov-panels-grid"
              style={{ marginTop: "1.25rem" }}
            >
              {/* Panel 4: Confirm & Calibrate Sliders (Dynamic Rule Dropdown) */}
              <div className="card gov-panel">
                <div className="gov-panel-header">
                  <h3>4. Confirm &amp; Calibrate Rule Sliders</h3>
                  <span className="sub-canon-tag">Guard 3 · Brand Manager</span>
                </div>
                <p className="gov-panel-desc">
                  Select any rule from <strong>{govCanonId}</strong> to tune its
                  severity (Warning <code>1–49</code> vs Blocker{" "}
                  <code>50–100</code>), CIEDE2000 colour tolerance (
                  <code>ΔE00</code>), and readability bounds in real time.
                </p>
                <form
                  onSubmit={handleCalibrateRule}
                  className="gov-calibrate-form"
                >
                  <div className="form-group">
                    <label htmlFor="cal-rule-select">
                      Select Rule from <code>{govCanonId}</code> to Calibrate
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
                        placeholder="Enter rule ID"
                      />
                    )}
                  </div>

                  {selectedCalRule?.source_text && (
                    <div
                      className="gov-clean-box"
                      style={{ marginBottom: "0.75rem", fontSize: "0.78rem" }}
                    >
                      <strong>Source Rule Grounding:</strong>{" "}
                      {selectedCalRule.source_text}
                    </div>
                  )}

                  <div className="slider-grid">
                    <label className="threshold-label">
                      <span>
                        Rule Severity S: <strong>{calSeverity}</strong> (
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
                        Palette Max ΔE00:{" "}
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
                        Voice Max Sentence Words: <strong>{calMaxWords}</strong>
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
                        Max Flesch-Kincaid Grade:{" "}
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
                      ? "Calibrating Canon..."
                      : `Confirm & Calibrate '${calRuleId}'`}
                  </button>
                </form>

                {calibrationResult && (
                  <div
                    className="gov-clean-box"
                    style={{ marginTop: "0.75rem" }}
                  >
                    ✓ Calibrated <strong>{calibrationResult.canon_id}</strong>{" "}
                    (v{calibrationResult.previous_version} → v
                    {calibrationResult.new_version}, SHA-256:{" "}
                    <code>{calibrationResult.new_hash.slice(0, 12)}…</code>)
                  </div>
                )}
              </div>

              {/* Panel 5: Pipeline A Compile-to-Schema Onboarding */}
              <div className="card gov-panel">
                <div className="gov-panel-header">
                  <h3>5. Pipeline A: Compile-to-Schema Onboarding</h3>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
                    onClick={() => {
                      setCompileId("fintech-kfs-canon");
                      setCompileText(SAMPLE_BRAND_BOOK_SPEC);
                    }}
                  >
                    Load Sample Brand Book Excerpt
                  </button>
                </div>
                <p className="gov-panel-desc">
                  Compile raw brand guidelines and KFS fact sheets into a signed
                  Canon behind Guard 1 (Value-Anchor Recall = 1.0), Guard 2
                  (Verbatim Character Grounding), and Guard 3 (Round-Trip NLI ≥
                  0.90).
                </p>
                <form
                  onSubmit={handleCompileCanon}
                  className="gov-compile-form"
                >
                  <div className="form-group">
                    <label htmlFor="compile-canon-id">New Canon ID</label>
                    <input
                      id="compile-canon-id"
                      type="text"
                      value={compileId}
                      onChange={(e) => setCompileId(e.target.value)}
                      placeholder="e.g. fintech-kfs-canon"
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="compile-raw-text">
                      Brand Book / KFS Fact Sheet Specification
                    </label>
                    <textarea
                      id="compile-raw-text"
                      rows={4}
                      value={compileText}
                      onChange={(e) => setCompileText(e.target.value)}
                      placeholder="Paste brand voice rules, hex palette tokens, and approved KFS claims..."
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={compiling}
                  >
                    {compiling
                      ? "Running Guards 1–3..."
                      : "Compile & Sign Brand Canon"}
                  </button>
                </form>

                {compileResult && (
                  <div
                    className="gov-clean-box"
                    style={{ marginTop: "0.75rem" }}
                  >
                    <div>
                      ✓ Compiled <strong>{compileResult.canon_id}</strong> (
                      {compileResult.term_count} terms,{" "}
                      {compileResult.color_count} colours,{" "}
                      {compileResult.fact_count} facts · SHA-256:{" "}
                      <code>{compileResult.hash.slice(0, 12)}…</code>)
                    </div>
                    {compileResult.provenance.map((p) => (
                      <div
                        key={p.rule_id}
                        style={{ fontSize: "0.78rem", marginTop: "0.25rem" }}
                      >
                        • <code>{p.rule_id}</code> [{p.start}:{p.end}] · Guard 1
                        Recall:{" "}
                        <strong>
                          {(p.effective_anchor_recall * 100).toFixed(0)}%
                        </strong>{" "}
                        · Guard 3 Round-Trip NLI:{" "}
                        <strong>
                          {(p.round_trip_nli_score * 100).toFixed(0)}%
                        </strong>{" "}
                        ({p.alignment_status})
                      </div>
                    ))}
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
