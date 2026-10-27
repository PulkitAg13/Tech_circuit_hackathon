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
  getApiBase,
  type Submission,
  type CanonSummary,
  type CanonRuleItem,
  type BundleAttachmentPayload,
  type CanonLintResponse,
  type CanonFrictionResponse,
  type CanonRevisionPrResponse,
  type CalibrateCanonRuleResponse,
  type CompileCanonResponse,
  type CustomTermInput,
  type CustomFactInput,
  type CustomColorInput,
  type CustomTriggerInput,
} from "../../api/client";
import { useAuth } from "../auth/context";
import { useNavigate, Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FilePlus2,
  FileText,
  Filter,
  GitPullRequest,
  Image as ImageIcon,
  Layers,
  LogOut,
  Plus,
  Search,
  ShieldCheck,
  Sliders,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";

const CUSTOM_PLAYBOOK_VALUE = "__custom__";

const ROLE_META: Record<
  string,
  {
    label: string;
    shortLabel: string;
    stageOwned: string;
    stageNum: number;
    responsibility: string;
  }
> = {
  creator: {
    label: "Creator (Marketing / Agency)",
    shortLabel: "Creator",
    stageOwned: "Stage 01 · Pre-Flight & Remediation",
    stageNum: 1,
    responsibility:
      "Uploads campaign copy, documents, and banners, runs pre-flight checks, resolves blocking issues, and documents context on warning overrides.",
  },
  reviewer: {
    label: "Brand Manager (Playbook Owner)",
    shortLabel: "Brand Manager",
    stageOwned: "Stage 02 · Brand & Playbook Review",
    stageNum: 2,
    responsibility:
      "Manages brand playbooks and rule thresholds, reviews revision history and warning overrides, and approves brand compliance.",
  },
  admin: {
    label: "Authorised Legal Reviewer",
    shortLabel: "Legal Sign-Off",
    stageOwned: "Stage 03 · Regulatory & Legal Sign-Off",
    stageNum: 3,
    responsibility:
      "Reviews high-risk claims, required disclosures, and overrides to issue final sign-off and generate the release certificate.",
  },
};

const QUICK_SAMPLE_PRESETS = [
  {
    label: "RBI Digital Lending Ad",
    canonId: "indian-digital-lending",
    title: "Acme QuickLoan Diwali Festival Campaign",
    content:
      "Celebrate this festive season with Acme QuickLoan! Get 0% interest on all personal loans with guaranteed instant approval in 60 seconds.\n\nPrincipal: ₹50,000 | Processing Fee: ₹1,500 | Total Interest: ₹3,500 | Tenure: 6 Months | Stated APR: 14.00%.",
  },
  {
    label: "ASCI Nutraceutical Launch",
    canonId: "indian-d2c-nutra",
    title: "VitalGlow Marine Peptides Instagram Launch",
    content:
      "Transform your skin overnight: VitalGlow Marine Peptides are clinically proven to permanently reverse skin aging in 7 days with 100% doctor-endorsed zero side effects.",
  },
  {
    label: "Enterprise Cloud Keynote",
    canonId: "acme-corp",
    title: "Acme Cloud Shield Enterprise Launch Copy",
    content:
      "Deploy Acme Cloud Shield for 100% unhackable zero-downtime infrastructure backed by unlimited SLA payouts on every tier across 24 global regions.",
  },
] as const;

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
  const [govSubTab, setGovSubTab] = useState<
    "rules" | "friction" | "calibrate" | "compile"
  >("rules");

  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [canons, setCanons] = useState<CanonSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [ruleSearchQuery, setRuleSearchQuery] = useState<string>("");

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
  const [error, setError] = useState<string | null>(null);

  // Inline Custom Company Guidelines / Documents onboarding inside Campaign Submission Form
  const [inlineCanonId, setInlineCanonId] = useState<string>("");
  const [inlineCanonText, setInlineCanonText] = useState<string>("");
  const [inlineCanonFiles, setInlineCanonFiles] = useState<
    BundleAttachmentPayload[]
  >([]);
  const [inlineTerms, setInlineTerms] = useState<CustomTermInput[]>([]);
  const [inlineFacts, setInlineFacts] = useState<CustomFactInput[]>([]);
  const [inlineColors, setInlineColors] = useState<CustomColorInput[]>([]);
  const [inlineTriggers, setInlineTriggers] = useState<CustomTriggerInput[]>(
    [],
  );

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

  // Playbook Studio Import state (Tab 4)
  const [compileId, setCompileId] = useState<string>("");
  const [compileText, setCompileText] = useState<string>("");
  const [compileAttachments, setCompileAttachments] = useState<
    BundleAttachmentPayload[]
  >([]);
  const [studioTerms, setStudioTerms] = useState<CustomTermInput[]>([]);
  const [studioFacts, setStudioFacts] = useState<CustomFactInput[]>([]);
  const [studioColors, setStudioColors] = useState<CustomColorInput[]>([]);
  const [studioTriggers, setStudioTriggers] = useState<CustomTriggerInput[]>(
    [],
  );
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
    let active = true;
    void Promise.resolve().then(() => {
      if (active) {
        setSubmissions([]);
        refresh();
      }
    });
    return () => {
      active = false;
    };
  }, [refresh, username, role]);

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
      let active = true;
      void Promise.resolve().then(() => {
        if (active) {
          loadGovernanceTelemetry(govCanonId);
        }
      });
      return () => {
        active = false;
      };
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
    const hasCustomRules =
      studioTerms.length > 0 ||
      studioFacts.length > 0 ||
      studioColors.length > 0 ||
      studioTriggers.length > 0;
    if (
      !targetId ||
      (!compileText.trim() &&
        compileAttachments.length === 0 &&
        !hasCustomRules)
    ) {
      setError(
        "Please provide a Playbook ID and either company guideline text, an uploaded document/logo, or structured rules.",
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
        {
          custom_terms: studioTerms,
          custom_facts: studioFacts,
          custom_colors: studioColors,
          custom_triggers: studioTriggers,
        },
      );
      setCompileResult(res);
      setCompileId("");
      setCompileText("");
      setCompileAttachments([]);
      setStudioTerms([]);
      setStudioFacts([]);
      setStudioColors([]);
      setStudioTriggers([]);
      await refresh();
      handleSelectGovCanon(res.canon_id);
      setGovSubTab("rules");
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
      let targetCanonId = selectedCanon;

      if (selectedCanon === CUSTOM_PLAYBOOK_VALUE) {
        const cleanId =
          inlineCanonId
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9-_]+/g, "-") || "company-custom-playbook";
        const hasInlineRules =
          inlineTerms.length > 0 ||
          inlineFacts.length > 0 ||
          inlineColors.length > 0 ||
          inlineTriggers.length > 0;
        if (
          !inlineCanonText.trim() &&
          inlineCanonFiles.length === 0 &&
          !hasInlineRules
        ) {
          setError(
            "Please upload your company guideline/fact-sheet files, paste your company rules/facts, or add structured rules below.",
          );
          setSubmitting(false);
          return;
        }
        const compiled = await compileBrandCanon(
          cleanId,
          inlineCanonText,
          inlineCanonFiles,
          "1.0",
          false,
          {
            custom_terms: inlineTerms,
            custom_facts: inlineFacts,
            custom_colors: inlineColors,
            custom_triggers: inlineTriggers,
          },
        );
        targetCanonId = compiled.canon_id;
      }

      const sub = await createSubmission(
        title.trim() || "Untitled Campaign",
        rawContent,
        targetCanonId,
        [],
        uploadedAttachments,
      );
      const apiBase = getApiBase();
      await fetch(`${apiBase}/submissions/${sub.id}/scan?alpha=0.1`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("cg_token") ?? ""}`,
        },
      }).catch(() => {});

      setShowForm(false);
      setTitle("");
      setRawContent("");
      setUploadedAttachments([]);
      setInlineCanonId("");
      setInlineCanonText("");
      setInlineCanonFiles([]);
      setInlineTerms([]);
      setInlineFacts([]);
      setInlineColors([]);
      setInlineTriggers([]);
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

  async function handleInlineCanonFileSelect(files: FileList | null) {
    const loaded = await readFilesAsBase64(files);
    if (loaded.length > 0) {
      setInlineCanonFiles((prev) => [...prev, ...loaded]);
    }
  }

  async function handleCompileFileSelect(files: FileList | null) {
    const loaded = await readFilesAsBase64(files);
    if (loaded.length > 0) {
      setCompileAttachments((prev) => [...prev, ...loaded]);
    }
  }

  function applySamplePreset(preset: (typeof QUICK_SAMPLE_PRESETS)[number]) {
    setTitle(preset.title);
    setRawContent(preset.content);
    const matchingCanon = canons.find((c) => c.id === preset.canonId);
    if (matchingCanon) {
      setSelectedCanon(matchingCanon.id);
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

  const myActionCount = submissions.filter((s) => {
    if (role === "creator")
      return s.status === "draft" || s.status === "changes_requested";
    if (role === "reviewer") return s.status === "in_review";
    if (role === "admin") return s.status === "approved";
    return false;
  }).length;

  const filteredSubmissions = submissions.filter((s) => {
    if (stageFilter === "mine") {
      if (role === "creator" && s.status !== "draft" && s.status !== "changes_requested")
        return false;
      if (role === "reviewer" && s.status !== "in_review") return false;
      if (role === "admin" && s.status !== "approved") return false;
    } else if (stageFilter === "stage1") {
      if (s.status !== "draft" && s.status !== "changes_requested") return false;
    } else if (stageFilter === "stage2") {
      if (s.status !== "in_review") return false;
    } else if (stageFilter === "stage3") {
      if (s.status !== "approved") return false;
    } else if (stageFilter === "stage4") {
      if (s.status !== "published") return false;
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchTitle = s.title.toLowerCase().includes(q);
      const matchCanon = s.canon_id.toLowerCase().includes(q);
      const matchId = `#${s.id}`.includes(q) || String(s.id) === q;
      return matchTitle || matchCanon || matchId;
    }
    return true;
  });

  const filteredRules = (activeCanonSummary?.rules ?? []).filter((r) => {
    if (!ruleSearchQuery.trim()) return true;
    const q = ruleSearchQuery.toLowerCase();
    return (
      r.id.toLowerCase().includes(q) ||
      r.rule_type.toLowerCase().includes(q) ||
      r.label.toLowerCase().includes(q) ||
      (r.source_text ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="cg-app-shell">
      {/* ── Architectural Application Command Bar ── */}
      <header className="cg-app-topbar">
        <div className="cg-app-topbar-inner">
          <div className="cg-app-topbar-left">
            <Link to="/" className="cg-brand">
              <span className="cg-brand-mark" aria-hidden="true">
                <ShieldCheck size={17} strokeWidth={2.2} />
              </span>
              <span className="cg-brand-name">CanonGate</span>
              <span className="cg-brand-version">Console</span>
            </Link>

            <nav className="cg-workspace-switcher" aria-label="Workspace Views">
              <button
                type="button"
                className={`cg-ws-tab ${
                  activeTab === "submissions" ? "active" : ""
                }`}
                onClick={() => setActiveTab("submissions")}
              >
                <Layers size={14} />
                <span>Campaign Queue</span>
                <span className="cg-ws-count">{submissions.length}</span>
              </button>
              <button
                type="button"
                className={`cg-ws-tab ${
                  activeTab === "governance" ? "active" : ""
                }`}
                onClick={() => setActiveTab("governance")}
              >
                <BookOpen size={14} />
                <span>Playbooks &amp; Rule Studio</span>
                <span className="cg-ws-count">{canons.length}</span>
              </button>
            </nav>
          </div>

          <div className="cg-app-topbar-right">
            {/* In-Session RBAC Role Switcher */}
            <label
              className="cg-role-Select-pill"
              title="Switch active RBAC role in-session (POST /api/auth/switch-role)"
            >
              <span className="cg-role-dot" />
              <span className="cg-role-select-prefix">Role:</span>
              <select
                aria-label="Active Governance Role"
                value={role || "creator"}
                onChange={(e) => {
                  void switchRole(e.target.value);
                }}
              >
                <option value="creator">Stage 1 · Creator</option>
                <option value="reviewer">Stage 2 · Brand Manager</option>
                <option value="admin">Stage 3 · Legal Reviewer</option>
              </select>
            </label>

            {/* Authenticated Identity Pill */}
            <div
              className="cg-user-pill"
              title={`Authenticated as ${displayName || username} (@${username})`}
            >
              <span className="cg-user-avatar">
                {(displayName || username || "U").slice(0, 1).toUpperCase()}
              </span>
              <span className="cg-user-handle">@{username}</span>
            </div>

            <button
              type="button"
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="cg-btn cg-btn-ghost cg-btn-sm"
              title="Sign out or switch account"
            >
              <LogOut size={14} />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </header>

      <main className="cg-app-main">
        {error && (
          <div className="cg-alert-banner" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="cg-btn cg-btn-ghost cg-btn-sm"
              onClick={() => setError(null)}
            >
              <X size={14} />
              <span>Dismiss</span>
            </button>
          </div>
        )}

        {activeTab === "submissions" ? (
          <div key="tab-submissions" className="cg-animate-swap">
            {/* ── Role Context Header & Primary Actions ── */}
            <section className="cg-console-hero-bar">
              <div className="cg-console-hero-left">
                <div className="cg-console-eyebrow">
                  <span className="cg-role-stage-tag">
                    {currentRoleMeta.stageOwned}
                  </span>
                  <span>Active Role: {currentRoleMeta.label}</span>
                  {myActionCount > 0 && (
                    <span className="cg-action-needed-pill">
                      ● {myActionCount} awaiting your action
                    </span>
                  )}
                </div>
                <h2 className="cg-console-title">
                  Pre-Publication Campaign Triage &amp; Governance Queue
                </h2>
                <p className="cg-console-subtitle">
                  {currentRoleMeta.responsibility}
                </p>
              </div>

              <div className="cg-console-hero-actions">
                <button
                  type="button"
                  className="cg-btn cg-btn-secondary"
                  onClick={() => {
                    setShowForm(true);
                    setSelectedCanon(CUSTOM_PLAYBOOK_VALUE);
                  }}
                >
                  <Upload size={14} />
                  <span>Onboard Company Guidelines</span>
                </button>
                <button
                  type="button"
                  className="cg-btn cg-btn-primary"
                  onClick={() => setShowForm(!showForm)}
                >
                  {showForm ? (
                    <>
                      <X size={15} />
                      <span>Close Composer</span>
                    </>
                  ) : (
                    <>
                      <Plus size={15} />
                      <span>New Campaign Bundle</span>
                    </>
                  )}
                </button>
              </div>
            </section>

            {/* ── 4-Stage Interactive Pipeline Filter Strip ── */}
            <section
              className="cg-pipeline-strip"
              aria-label="4-Stage Governance Workflow"
            >
              {[
                {
                  key: "stage1",
                  num: "01",
                  title: "Creator Pre-Flight",
                  sub: "Draft & Surgical Fixes",
                  count: stageCounts.stage1,
                  owned: role === "creator",
                },
                {
                  key: "stage2",
                  num: "02",
                  title: "Brand Review",
                  sub: "Diffs & Overrides",
                  count: stageCounts.stage2,
                  owned: role === "reviewer",
                },
                {
                  key: "stage3",
                  num: "03",
                  title: "Legal Sign-Off",
                  sub: "Statutory & KFS Claims",
                  count: stageCounts.stage3,
                  owned: role === "admin",
                },
                {
                  key: "stage4",
                  num: "04",
                  title: "Released & Sealed",
                  sub: "Merkle + C2PA Cert",
                  count: stageCounts.stage4,
                  owned: false,
                },
              ].map((st) => {
                const isSelected = stageFilter === st.key;
                return (
                  <button
                    key={st.key}
                    type="button"
                    className={`cg-pipeline-card ${
                      isSelected ? "selected" : ""
                    } ${st.owned ? "owned-by-me" : ""}`}
                    onClick={() =>
                      setStageFilter(isSelected ? "all" : st.key)
                    }
                  >
                    <div className="cg-pipeline-card-top">
                      <span className="cg-pipeline-step-tag">
                        STAGE {st.num}
                      </span>
                      {st.owned && (
                        <span className="cg-pipeline-your-stage">
                          YOUR STAGE
                        </span>
                      )}
                      <span className="cg-pipeline-count">{st.count}</span>
                    </div>
                    <div className="cg-pipeline-name">{st.title}</div>
                    <div className="cg-pipeline-sub">{st.sub}</div>
                  </button>
                );
              })}
            </section>

            {/* ── Campaign Bundle Composer (Collapsible / Drawer Card) ── */}
            {showForm && (
              <form
                className="cg-composer-card cg-animate-swap"
                onSubmit={handleCreate}
              >
                <div className="cg-composer-header">
                  <div>
                    <span className="cg-mono-label">
                      MULTI-MODAL BUNDLE COMPOSER · PIPELINE B PRE-FLIGHT
                    </span>
                    <h3>Submit Campaign Content for Pre-Publication Audit</h3>
                  </div>
                  <div className="cg-composer-presets">
                    <span className="cg-mono-label">1-Click Sample Fill:</span>
                    {QUICK_SAMPLE_PRESETS.map((preset) => (
                      <button
                        key={preset.label}
                        type="button"
                        className="cg-preset-chip"
                        onClick={() => applySamplePreset(preset)}
                      >
                        <Sparkles size={12} />
                        <span>{preset.label}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="cg-composer-body">
                  <div className="cg-field-row-2">
                    <div className="cg-field-group">
                      <label htmlFor="sub-title">Campaign Bundle Title</label>
                      <input
                        id="sub-title"
                        type="text"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder="e.g. Q3 Product Launch Landing Page & Banner"
                        required
                      />
                    </div>

                    <div className="cg-field-group">
                      <div className="cg-field-label-row">
                        <label htmlFor="sub-canon">
                          Governing Brand Playbook
                        </label>
                        <button
                          type="button"
                          className="cg-link-btn"
                          onClick={() =>
                            setSelectedCanon(
                              selectedCanon === CUSTOM_PLAYBOOK_VALUE
                                ? canons[0]?.id || "indian-digital-lending"
                                : CUSTOM_PLAYBOOK_VALUE,
                            )
                          }
                        >
                          {selectedCanon === CUSTOM_PLAYBOOK_VALUE
                            ? "← Use Existing Playbook"
                            : "+ Parse Custom Company Docs / Rules"}
                        </button>
                      </div>
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
                        <option value={CUSTOM_PLAYBOOK_VALUE}>
                          + Upload / Define Custom Company Guidelines, Facts
                          &amp; Logos
                        </option>
                      </select>
                    </div>
                  </div>

                  {/* Progressive Disclosure: Inline Custom Playbook Onboarding */}
                  {selectedCanon === CUSTOM_PLAYBOOK_VALUE && (
                    <div className="cg-custom-canon-box cg-animate-swap">
                      <div className="cg-custom-canon-header">
                        <div>
                          <h4>
                            Compile Custom Company Brand Playbook (Pipeline A)
                          </h4>
                          <p>
                            Upload your brand book (`.pdf`, `.docx`, `.md`),
                            approved KFS/product fact sheets (`.csv`, `.json`,
                            `.yaml`), or reference logo (`.png`, `.jpg`), or
                            define rules below.
                          </p>
                        </div>
                        <span className="cg-brand-version">
                          Guards 1–3 Protected
                        </span>
                      </div>

                      <div className="cg-field-row-2">
                        <div className="cg-field-group">
                          <label htmlFor="inline-canon-id">
                            Company Playbook Identifier
                          </label>
                          <input
                            id="inline-canon-id"
                            type="text"
                            value={inlineCanonId}
                            onChange={(e) => setInlineCanonId(e.target.value)}
                            placeholder="e.g. my-company-brand-v1"
                            required
                          />
                        </div>

                        <div className="cg-field-group">
                          <label htmlFor="inline-canon-files">
                            Upload Guideline Docs, Fact Sheets or Reference
                            Logos
                          </label>
                          <input
                            id="inline-canon-files"
                            type="file"
                            multiple
                            accept=".pdf,.docx,.csv,.json,.yaml,.yml,.md,.txt,.html,.png,.jpg,.jpeg,.webp"
                            onChange={(e) =>
                              handleInlineCanonFileSelect(e.target.files)
                            }
                          />
                          {inlineCanonFiles.length > 0 && (
                            <div className="uploaded-files-pills">
                              {inlineCanonFiles.map((att, idx) => (
                                <span
                                  key={`${att.filename}-${idx}`}
                                  className="file-pill"
                                >
                                  {att.filename}
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setInlineCanonFiles((prev) =>
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
                      </div>

                      <div className="cg-field-group">
                        <label htmlFor="inline-canon-text">
                          Paste Company Brand Guidelines, Approved Facts,
                          Disclaimers &amp; Hex Colours
                        </label>
                        <textarea
                          id="inline-canon-text"
                          rows={3}
                          value={inlineCanonText}
                          onChange={(e) => setInlineCanonText(e.target.value)}
                          placeholder={
                            "• Never use 'guaranteed returns', prefer 'historical target yield'.\n" +
                            "• Approved Fact: 0% processing fee on loans under Rs 50,000 valid until 2026-12-31.\n" +
                            "• Trigger: 'loan' -> Disclaimer: 'Subject to credit assessment and RBI KFS terms.'"
                          }
                        />
                      </div>

                      <div className="cg-rule-builder-toolbar">
                        <button
                          type="button"
                          className="cg-btn cg-btn-secondary cg-btn-sm"
                          onClick={() =>
                            setInlineTerms((prev) => [
                              ...prev,
                              { pattern_text: "", preferred: "", severity: 60 },
                            ])
                          }
                        >
                          + Banned/Preferred Term
                        </button>
                        <button
                          type="button"
                          className="cg-btn cg-btn-secondary cg-btn-sm"
                          onClick={() =>
                            setInlineFacts((prev) => [
                              ...prev,
                              { text: "", conditions: [], valid_until: "" },
                            ])
                          }
                        >
                          + Approved Fact
                        </button>
                        <button
                          type="button"
                          className="cg-btn cg-btn-secondary cg-btn-sm"
                          onClick={() =>
                            setInlineColors((prev) => [
                              ...prev,
                              { name: "", hex: "#0D3B66", max_delta_e: 3.5 },
                            ])
                          }
                        >
                          + Brand Colour Hex
                        </button>
                        <button
                          type="button"
                          className="cg-btn cg-btn-secondary cg-btn-sm"
                          onClick={() =>
                            setInlineTriggers((prev) => [
                              ...prev,
                              {
                                trigger_pattern: "",
                                required_disclaimer_text: "",
                                severity: 70,
                              },
                            ])
                          }
                        >
                          + Disclaimer Trigger
                        </button>
                      </div>

                      {inlineTerms.map((t, idx) => (
                        <div key={`it-${idx}`} className="cg-inline-rule-row">
                          <input
                            type="text"
                            placeholder="Banned term (e.g. risk-free)"
                            value={t.pattern_text}
                            onChange={(e) =>
                              setInlineTerms((prev) =>
                                prev.map((item, i) =>
                                  i === idx
                                    ? { ...item, pattern_text: e.target.value }
                                    : item,
                                ),
                              )
                            }
                          />
                          <input
                            type="text"
                            placeholder="Preferred replacement (e.g. capital-protected)"
                            value={t.preferred}
                            onChange={(e) =>
                              setInlineTerms((prev) =>
                                prev.map((item, i) =>
                                  i === idx
                                    ? { ...item, preferred: e.target.value }
                                    : item,
                                ),
                              )
                            }
                          />
                          <button
                            type="button"
                            className="cg-btn cg-btn-ghost cg-btn-sm"
                            onClick={() =>
                              setInlineTerms((prev) =>
                                prev.filter((_, i) => i !== idx),
                              )
                            }
                          >
                            ✕
                          </button>
                        </div>
                      ))}

                      {inlineFacts.map((f, idx) => (
                        <div key={`if-${idx}`} className="cg-inline-rule-row">
                          <input
                            type="text"
                            placeholder="Approved fact/claim"
                            value={f.text}
                            onChange={(e) =>
                              setInlineFacts((prev) =>
                                prev.map((item, i) =>
                                  i === idx
                                    ? { ...item, text: e.target.value }
                                    : item,
                                ),
                              )
                            }
                          />
                          <input
                            type="text"
                            placeholder="Valid until YYYY-MM-DD (optional)"
                            value={f.valid_until ?? ""}
                            onChange={(e) =>
                              setInlineFacts((prev) =>
                                prev.map((item, i) =>
                                  i === idx
                                    ? { ...item, valid_until: e.target.value }
                                    : item,
                                ),
                              )
                            }
                          />
                          <button
                            type="button"
                            className="cg-btn cg-btn-ghost cg-btn-sm"
                            onClick={() =>
                              setInlineFacts((prev) =>
                                prev.filter((_, i) => i !== idx),
                              )
                            }
                          >
                            ✕
                          </button>
                        </div>
                      ))}

                      {inlineColors.map((c, idx) => (
                        <div key={`ic-${idx}`} className="cg-inline-rule-row">
                          <input
                            type="text"
                            placeholder="Colour name (e.g. Brand Primary)"
                            value={c.name}
                            onChange={(e) =>
                              setInlineColors((prev) =>
                                prev.map((item, i) =>
                                  i === idx
                                    ? { ...item, name: e.target.value }
                                    : item,
                                ),
                              )
                            }
                          />
                          <input
                            type="text"
                            placeholder="Hex code (e.g. #0D3B66)"
                            value={c.hex}
                            onChange={(e) =>
                              setInlineColors((prev) =>
                                prev.map((item, i) =>
                                  i === idx
                                    ? { ...item, hex: e.target.value }
                                    : item,
                                ),
                              )
                            }
                          />
                          <button
                            type="button"
                            className="cg-btn cg-btn-ghost cg-btn-sm"
                            onClick={() =>
                              setInlineColors((prev) =>
                                prev.filter((_, i) => i !== idx),
                              )
                            }
                          >
                            ✕
                          </button>
                        </div>
                      ))}

                      {inlineTriggers.map((tr, idx) => (
                        <div key={`itr-${idx}`} className="cg-inline-rule-row">
                          <input
                            type="text"
                            placeholder="Trigger keyword (e.g. APR)"
                            value={tr.trigger_pattern}
                            onChange={(e) =>
                              setInlineTriggers((prev) =>
                                prev.map((item, i) =>
                                  i === idx
                                    ? {
                                        ...item,
                                        trigger_pattern: e.target.value,
                                      }
                                    : item,
                                ),
                              )
                            }
                          />
                          <input
                            type="text"
                            placeholder="Required disclaimer text"
                            value={tr.required_disclaimer_text}
                            onChange={(e) =>
                              setInlineTriggers((prev) =>
                                prev.map((item, i) =>
                                  i === idx
                                    ? {
                                        ...item,
                                        required_disclaimer_text:
                                          e.target.value,
                                      }
                                    : item,
                                ),
                              )
                            }
                          />
                          <button
                            type="button"
                            className="cg-btn cg-btn-ghost cg-btn-sm"
                            onClick={() =>
                              setInlineTriggers((prev) =>
                                prev.filter((_, i) => i !== idx),
                              )
                            }
                          >
                            ✕
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="cg-field-row-2">
                    <div className="cg-field-group">
                      <label htmlFor="sub-content">
                        Campaign Copy / Markdown KFS Table / HTML Content
                      </label>
                      <textarea
                        id="sub-content"
                        rows={5}
                        value={rawContent}
                        onChange={(e) => setRawContent(e.target.value)}
                        placeholder="Write or paste your campaign copy, claims, disclaimers, or Markdown pricing table here..."
                      />
                    </div>

                    <div className="cg-field-group">
                      <label htmlFor="sub-files">
                        Attach Campaign Documents or 1080p Banners (`.docx`,
                        `.pdf`, `.html`, `.png`, `.jpg`)
                      </label>
                      <input
                        id="sub-files"
                        type="file"
                        multiple
                        accept=".docx,.pdf,.html,.htm,.md,.txt,.csv,.json,.png,.jpg,.jpeg,.webp"
                        onChange={(e) => handleFileSelect(e.target.files)}
                      />
                      <p className="cg-field-help">
                        All text and visual assets are parsed locally into a
                        unified ContentAST with zero unmasked cloud data leaks.
                      </p>
                      {uploadedAttachments.length > 0 && (
                        <div className="uploaded-files-pills">
                          {uploadedAttachments.map((att, idx) => (
                            <span
                              key={`${att.filename}-${idx}`}
                              className="file-pill"
                            >
                              {att.filename}
                              <button
                                type="button"
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
                  </div>
                </div>

                <div className="cg-composer-footer">
                  <span className="cg-mono-label">
                    DPDP 2023 PII VAULT ACTIVE · AUTO-RUNS TIER 1–2 PRE-FLIGHT
                  </span>
                  <div className="cg-composer-actions">
                    {submissions.length > 0 && (
                      <button
                        type="button"
                        className="cg-btn cg-btn-ghost"
                        onClick={() => setShowForm(false)}
                      >
                        Cancel
                      </button>
                    )}
                    <button
                      type="submit"
                      className="cg-btn cg-btn-primary"
                      disabled={submitting}
                    >
                      <span>
                        {submitting
                          ? "Running Pre-Publish Checks…"
                          : selectedCanon === CUSTOM_PLAYBOOK_VALUE
                            ? "Compile Playbook & Open Studio"
                            : "Create & Open in Review Studio"}
                      </span>
                      <ArrowRight size={15} className="cg-arrow-shift" />
                    </button>
                  </div>
                </div>
              </form>
            )}

            {/* ── Queue Search & Filter Bar ── */}
            <div className="cg-queue-toolbar">
              <div className="cg-queue-filter-pills">
                <button
                  type="button"
                  className={`cg-filter-pill ${
                    stageFilter === "all" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("all")}
                >
                  All ({submissions.length})
                </button>
                <button
                  type="button"
                  className={`cg-filter-pill ${
                    stageFilter === "mine" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("mine")}
                >
                  Needs My Action ({myActionCount})
                </button>
                <button
                  type="button"
                  className={`cg-filter-pill ${
                    stageFilter === "stage1" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("stage1")}
                >
                  Stage 1 ({stageCounts.stage1})
                </button>
                <button
                  type="button"
                  className={`cg-filter-pill ${
                    stageFilter === "stage2" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("stage2")}
                >
                  Stage 2 ({stageCounts.stage2})
                </button>
                <button
                  type="button"
                  className={`cg-filter-pill ${
                    stageFilter === "stage3" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("stage3")}
                >
                  Stage 3 ({stageCounts.stage3})
                </button>
                <button
                  type="button"
                  className={`cg-filter-pill ${
                    stageFilter === "stage4" ? "active" : ""
                  }`}
                  onClick={() => setStageFilter("stage4")}
                >
                  Released ({stageCounts.stage4})
                </button>
              </div>

              <div className="cg-queue-search">
                <Search size={14} className="cg-search-icon" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter by campaign title, playbook, or #ID…"
                  aria-label="Filter campaigns"
                />
                {searchQuery && (
                  <button
                    type="button"
                    className="cg-search-clear"
                    onClick={() => setSearchQuery("")}
                  >
                    ✕
                  </button>
                )}
              </div>
            </div>

            {/* ── Campaign Queue List / Grid ── */}
            {loading ? (
              <div className="cg-empty-box">Loading campaign queue…</div>
            ) : filteredSubmissions.length === 0 ? (
              <div className="cg-empty-box">
                <p>
                  {submissions.length === 0
                    ? "Your campaign queue is empty. Use the composer above (or click a 1-Click Sample Preset) to run your first pre-publication audit."
                    : "No campaigns match your active stage or search filter."}
                </p>
                {(stageFilter !== "all" || searchQuery) && (
                  <button
                    type="button"
                    className="cg-btn cg-btn-secondary"
                    onClick={() => {
                      setStageFilter("all");
                      setSearchQuery("");
                    }}
                  >
                    Reset Filters ({submissions.length})
                  </button>
                )}
              </div>
            ) : (
              <div className="cg-queue-grid">
                {filteredSubmissions.map((s) => {
                  const stageInfo = getStageMeta(s.status);
                  const isMyTurn = stageInfo.ownerRole === role;
                  const textCount = s.text_blocks?.length ?? 0;
                  const imgCount = s.image_nodes?.length ?? 0;

                  return (
                    <article
                      key={s.id}
                      className={`cg-triage-card ${
                        isMyTurn ? "my-turn" : ""
                      }`}
                      onClick={() => navigate(`/submissions/${s.id}`)}
                    >
                      <div className="cg-triage-card-top">
                        <div className="cg-triage-badges">
                          <span className="cg-bundle-id">#{s.id}</span>
                          <span className={`status-badge status-${s.status}`}>
                            {stageInfo.stageLabel}
                          </span>
                          {isMyTurn && (
                            <span className="cg-my-turn-pill">
                              ● Action Required
                            </span>
                          )}
                        </div>

                        <div className="cg-triage-right-meta">
                          <code className="cg-canon-badge">{s.canon_id}</code>
                          <button
                            type="button"
                            className="cg-delete-btn"
                            disabled={deletingId === s.id}
                            onClick={(e) => handleDeleteSubmission(e, s.id)}
                            title="Delete campaign bundle"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>

                      <h3 className="cg-triage-title">{s.title}</h3>

                      {/* 4-Step Visual Stage Progress Bar */}
                      <div
                        className="cg-mini-stage-bar"
                        title={stageInfo.ownerText}
                      >
                        {[1, 2, 3, 4].map((step) => (
                          <span
                            key={step}
                            className={`cg-mini-stage-seg ${
                              step < stageInfo.stageNum
                                ? "done"
                                : step === stageInfo.stageNum
                                  ? "current"
                                  : ""
                            }`}
                          />
                        ))}
                      </div>

                      <div className="cg-triage-footer">
                        <div className="cg-triage-assets">
                          <span className="cg-asset-chip">
                            <FileText size={12} />
                            {textCount} text block{textCount === 1 ? "" : "s"}
                          </span>
                          {imgCount > 0 && (
                            <span className="cg-asset-chip">
                              <ImageIcon size={12} />
                              {imgCount} banner{imgCount === 1 ? "" : "s"}
                            </span>
                          )}
                          <span className="cg-triage-owner-hint">
                            {stageInfo.ownerText}
                          </span>
                        </div>

                        <span className="cg-open-studio-link">
                          <span>Inspect in Studio</span>
                          <ArrowRight size={14} className="cg-arrow-shift" />
                        </span>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          /* ── Tab 2: Progressive-Disclosure Playbook & Rule Studio ── */
          <div key="tab-governance" className="cg-gov-studio cg-animate-swap">
            {/* Top Bar of Playbook Studio */}
            <div className="cg-console-hero-bar">
              <div className="cg-console-hero-left">
                <div className="cg-console-eyebrow">
                  <span className="cg-role-stage-tag">PIPELINE A &amp; C</span>
                  <span>Playbook Compiler, Friction Telemetry &amp; Calibration</span>
                </div>
                <h2 className="cg-console-title">
                  Brand Playbooks &amp; Closed-Loop Rule Studio
                </h2>
                <p className="cg-console-subtitle">
                  Inspect compiled rules, track Empirical Bayes override
                  friction, auto-draft Canon v1.1 pull requests, or onboard new
                  company guideline documents.
                </p>
              </div>

              <div className="cg-gov-selector-box">
                <label htmlFor="gov-canon-select">Active Playbook Canon</label>
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
              <div className="cg-success-banner">{prAppliedBanner}</div>
            )}

            {/* KPI Summary Strip */}
            {activeCanonSummary && (
              <div className="cg-kpi-strip">
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">PLAYBOOK VERSION</span>
                  <strong>v{activeCanonSummary.version}</strong>
                  <code>SHA: {activeCanonSummary.hash.slice(0, 10)}…</code>
                </div>
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">TERMINOLOGY RULES</span>
                  <strong>{activeCanonSummary.term_count}</strong>
                  <span>Aho-Corasick + UTS #39</span>
                </div>
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">APPROVED FACTS</span>
                  <strong>{activeCanonSummary.fact_count}</strong>
                  <span>QASem SlotDiff Grounded</span>
                </div>
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">BRAND COLOUR TOKENS</span>
                  <strong>{activeCanonSummary.color_count}</strong>
                  <span>CIEDE2000 ΔE₀₀ Verified</span>
                </div>
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">TRIGGERS &amp; LOGOS</span>
                  <strong>
                    {(activeCanonSummary.trigger_count ?? 0) +
                      (activeCanonSummary.logo_count ?? 0)}
                  </strong>
                  <span>Mandatory Disclosures + ORB</span>
                </div>
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">KRIPPENDORFF&apos;S α</span>
                  <strong className="cg-text-emerald">
                    {frictionReport
                      ? `${(frictionReport.krippendorff_alpha * 100).toFixed(0)}%`
                      : "100%"}
                  </strong>
                  <span>Inter-Reviewer Agreement</span>
                </div>
              </div>
            )}

            {/* Sub-Navigation Tabs (Progressive Disclosure) */}
            <div className="cg-gov-subtabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={govSubTab === "rules"}
                className={`cg-gov-subtab ${
                  govSubTab === "rules" ? "active" : ""
                }`}
                onClick={() => setGovSubTab("rules")}
              >
                <BookOpen size={14} />
                <span>
                  1. Rule &amp; Fact Catalog (
                  {activeCanonSummary?.rules?.length ?? 0})
                </span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={govSubTab === "friction"}
                className={`cg-gov-subtab ${
                  govSubTab === "friction" ? "active" : ""
                }`}
                onClick={() => setGovSubTab("friction")}
              >
                <GitPullRequest size={14} />
                <span>2. Friction Insights &amp; v1.1 Auto-PRs</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={govSubTab === "calibrate"}
                className={`cg-gov-subtab ${
                  govSubTab === "calibrate" ? "active" : ""
                }`}
                onClick={() => setGovSubTab("calibrate")}
              >
                <Sliders size={14} />
                <span>3. Calibrate Thresholds</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={govSubTab === "compile"}
                className={`cg-gov-subtab ${
                  govSubTab === "compile" ? "active" : ""
                }`}
                onClick={() => setGovSubTab("compile")}
              >
                <FilePlus2 size={14} />
                <span>4. Onboard New Playbook (Pipeline A)</span>
              </button>
            </div>

            {/* Sub-Tab 1: Rule & Fact Catalog */}
            {govSubTab === "rules" && (
              <div key="gov-rules" className="cg-gov-card cg-animate-swap">
                <div className="cg-gov-card-header">
                  <div>
                    <h3>
                      Compiled Rules, Approved Facts &amp; Visual Tokens in{" "}
                      <code>{govCanonId}</code>
                    </h3>
                    <p>
                      Click any rule row to jump directly to its threshold
                      calibration controls.
                    </p>
                  </div>

                  <div className="cg-queue-search">
                    <Filter size={14} className="cg-search-icon" />
                    <input
                      type="text"
                      value={ruleSearchQuery}
                      onChange={(e) => setRuleSearchQuery(e.target.value)}
                      placeholder="Filter rules by ID, type, or keyword…"
                    />
                  </div>
                </div>

                {lintReport && (
                  <div className="cg-lint-strip">
                    <CheckCircle2 size={15} className="cg-text-emerald" />
                    <span>
                      {lintReport.is_valid
                        ? `Playbook Consistency Verified: 0 duplicate IDs, 0 circular replacements, and 0 overlapping ΔE₀₀ colour tokens in ${lintReport.canon_id}.`
                        : `Playbook Lint Warnings: ${lintReport.issues.map((i) => i.message).join("; ")}`}
                    </span>
                  </div>
                )}

                <div className="cg-table-scroll">
                  <table className="cg-data-table">
                    <thead>
                      <tr>
                        <th>Rule ID</th>
                        <th>Modality / Type</th>
                        <th>Enforced Rule / Approved Claim</th>
                        <th>Source Guideline Citation</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRules.map((r) => (
                        <tr key={r.id}>
                          <td>
                            <code>{r.id}</code>
                          </td>
                          <td>
                            <span className="cg-type-pill">
                              {r.rule_type.toUpperCase()}
                            </span>
                          </td>
                          <td>
                            <strong>{r.label}</strong>
                          </td>
                          <td className="cg-td-muted">
                            {r.source_text || "—"}
                          </td>
                          <td>
                            <button
                              type="button"
                              className="cg-btn cg-btn-ghost cg-btn-sm"
                              onClick={() => {
                                handleSelectCalRule(r.id);
                                setGovSubTab("calibrate");
                              }}
                            >
                              Calibrate →
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Sub-Tab 2: Friction Insights & Auto-PRs */}
            {govSubTab === "friction" && (
              <div key="gov-friction" className="cg-animate-swap">
                {govLoading ? (
                  <div className="cg-empty-box">
                    Loading Empirical Bayes friction telemetry…
                  </div>
                ) : (
                  <div className="cg-gov-two-col">
                    <div className="cg-gov-card">
                      <div className="cg-gov-card-header">
                        <div>
                          <h3>Recurring Mistakes by Category</h3>
                          <p>
                            Aggregates compliance findings across campaigns to
                            pinpoint high-risk categories.
                          </p>
                        </div>
                        <span className="cg-brand-version">
                          {frictionReport?.total_findings ?? 0} total findings
                        </span>
                      </div>

                      {frictionReport?.category_breakdown &&
                      frictionReport.category_breakdown.length > 0 ? (
                        <table className="cg-data-table">
                          <thead>
                            <tr>
                              <th>Category</th>
                              <th>Flags</th>
                              <th>Resolved</th>
                              <th>Overridden</th>
                              <th>Actionable Insight</th>
                            </tr>
                          </thead>
                          <tbody>
                            {frictionReport.category_breakdown.map((cat) => (
                              <tr key={cat.category}>
                                <td>
                                  <strong>{cat.category}</strong>
                                </td>
                                <td>{cat.total_flags}</td>
                                <td>{cat.resolved_count}</td>
                                <td>{cat.overridden_count}</td>
                                <td className="cg-td-muted">
                                  <code>{cat.top_rule_id}</code> — {cat.insight}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <div className="cg-clean-note">
                          No recurring category violations recorded yet for{" "}
                          <strong>{govCanonId}</strong>.
                        </div>
                      )}
                    </div>

                    <div className="cg-gov-card">
                      <div className="cg-gov-card-header">
                        <div>
                          <h3>Empirical Bayes Rule Friction &amp; v1.1 PR</h3>
                          <p>
                            Detects rules with high override rates so you can
                            auto-generate a Playbook v1.1 pull request.
                          </p>
                        </div>
                      </div>

                      {frictionReport && frictionReport.rules.length > 0 ? (
                        <table className="cg-data-table">
                          <thead>
                            <tr>
                              <th>Rule ID</th>
                              <th>Flags</th>
                              <th>Overrides</th>
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
                                <td>
                                  {(r.posterior_friction * 100).toFixed(1)}%
                                </td>
                                <td>
                                  <span
                                    className={`cg-slot-badge ${
                                      r.needs_canon_revision
                                        ? "slot-dropped"
                                        : "slot-match"
                                    }`}
                                  >
                                    {r.needs_canon_revision
                                      ? "NEEDS v1.1 REVISION"
                                      : "CALIBRATED"}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <div className="cg-clean-note">
                          Zero disputed rules recorded yet for{" "}
                          <strong>{govCanonId}</strong>.
                        </div>
                      )}

                      <div className="cg-pr-action-bar">
                        <label className="cg-slider-control">
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
                            onChange={(e) =>
                              setPrThreshold(Number(e.target.value))
                            }
                          />
                        </label>
                        <button
                          type="button"
                          className="cg-btn cg-btn-primary"
                          onClick={handleProposePr}
                          disabled={prLoading}
                        >
                          <GitPullRequest size={14} />
                          <span>
                            {prLoading
                              ? "Simulating Impact…"
                              : "Draft Playbook v1.1 PR"}
                          </span>
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {prProposal && (
                  <div
                    className="cg-gov-card cg-animate-swap"
                    style={{ marginTop: "1rem" }}
                  >
                    <div className="cg-gov-card-header">
                      <div>
                        <h3>
                          Proposed Playbook Pull Request: {prProposal.canon_id}{" "}
                          v{prProposal.base_version} → v
                          {prProposal.proposed_version}
                        </h3>
                        <p>
                          Historical blast-radius simulation across{" "}
                          <strong>{prProposal.bundles_evaluated}</strong>{" "}
                          campaign(s): Flags reduced from{" "}
                          <strong>{prProposal.before_findings}</strong> →{" "}
                          <strong>{prProposal.after_findings}</strong> (
                          {(prProposal.reduction_ratio * 100).toFixed(1)}% noise
                          reduction).
                        </p>
                      </div>
                      {prProposal.has_changes && (
                        <button
                          type="button"
                          className="cg-btn cg-btn-emerald"
                          onClick={handleApplyPr}
                          disabled={applyingPr}
                        >
                          <CheckCircle2 size={15} />
                          <span>
                            {applyingPr
                              ? "Activating…"
                              : `Approve & Activate v${prProposal.proposed_version}`}
                          </span>
                        </button>
                      )}
                    </div>

                    {prProposal.revisions.length > 0 ? (
                      <>
                        <table className="cg-data-table">
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
                                  <span className="cg-type-pill">
                                    {rev.action}
                                  </span>
                                </td>
                                <td>{rev.before_summary}</td>
                                <td>
                                  <strong>{rev.after_summary}</strong>
                                </td>
                                <td className="cg-td-muted">{rev.rationale}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>

                        {prProposal.yaml_diff && (
                          <div className="yaml-diff-box">
                            <div className="yaml-diff-title">
                              Unified Canon YAML Diff Preview
                            </div>
                            <pre className="yaml-diff-pre">
                              {prProposal.yaml_diff}
                            </pre>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="cg-clean-note">
                        No rules in <strong>{prProposal.canon_id}</strong>{" "}
                        currently exceed the {(prThreshold * 100).toFixed(0)}%
                        override friction threshold.
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Sub-Tab 3: Calibrate Rule Thresholds */}
            {govSubTab === "calibrate" && (
              <div key="gov-calibrate" className="cg-gov-card cg-animate-swap">
                <div className="cg-gov-card-header">
                  <div>
                    <h3>
                      Calibrate Rule Severity &amp; Perceptual Tolerances (
                      <code>{govCanonId}</code>)
                    </h3>
                    <p>
                      Tune whether a rule acts as a non-blocking Warning (
                      <code>1–49</code>) or a hard Blocker (<code>50–100</code>
                      ), or adjust CIEDE2000 ΔE₀₀ and readability ceilings.
                    </p>
                  </div>
                </div>

                <form
                  onSubmit={handleCalibrateRule}
                  className="cg-calibrate-form"
                >
                  <div className="cg-field-group">
                    <label htmlFor="cal-rule-select">
                      Target Rule in <code>{govCanonId}</code>
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
                            [{r.rule_type.toUpperCase()}] {r.id} — {r.label}
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
                    <div className="cg-clean-note">
                      <strong>Source Guideline Citation:</strong>{" "}
                      {selectedCalRule.source_text}
                    </div>
                  )}

                  <div className="cg-calibration-grid">
                    <label className="cg-cal-box">
                      <div className="cg-cal-box-top">
                        <span>Rule Severity Weight</span>
                        <span
                          className={`cg-sev-badge ${
                            calSeverity >= 50 ? "sev-blocker" : "sev-warning"
                          }`}
                        >
                          {calSeverity} ·{" "}
                          {calSeverity >= 50 ? "BLOCKER" : "WARNING"}
                        </span>
                      </div>
                      <input
                        type="range"
                        min="10"
                        max="95"
                        step="5"
                        value={calSeverity}
                        onChange={(e) => setCalSeverity(Number(e.target.value))}
                      />
                    </label>

                    <label className="cg-cal-box">
                      <div className="cg-cal-box-top">
                        <span>CIEDE2000 Colour Tolerance (ΔE₀₀)</span>
                        <code>≤ {calMaxDeltaE.toFixed(1)}</code>
                      </div>
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

                    <label className="cg-cal-box">
                      <div className="cg-cal-box-top">
                        <span>Max Sentence Length</span>
                        <code>{calMaxWords} words</code>
                      </div>
                      <input
                        type="range"
                        min="15"
                        max="45"
                        step="1"
                        value={calMaxWords}
                        onChange={(e) => setCalMaxWords(Number(e.target.value))}
                      />
                    </label>

                    <label className="cg-cal-box">
                      <div className="cg-cal-box-top">
                        <span>Max Flesch-Kincaid Grade</span>
                        <code>Grade {calMaxFkGrade.toFixed(1)}</code>
                      </div>
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

                  <div className="cg-composer-actions">
                    <button
                      type="submit"
                      className="cg-btn cg-btn-primary"
                      disabled={calibrating || !calRuleId}
                    >
                      {calibrating
                        ? "Saving Calibration…"
                        : `Save Calibration for '${calRuleId}'`}
                    </button>
                  </div>
                </form>

                {calibrationResult && (
                  <div
                    className="cg-success-banner"
                    style={{ marginTop: "1rem" }}
                  >
                    ✓ Updated <strong>{calibrationResult.canon_id}</strong> (v
                    {calibrationResult.previous_version} → v
                    {calibrationResult.new_version})
                  </div>
                )}
              </div>
            )}

            {/* Sub-Tab 4: Onboard New Playbook (Pipeline A) */}
            {govSubTab === "compile" && (
              <div key="gov-compile" className="cg-gov-card cg-animate-swap">
                <div className="cg-gov-card-header">
                  <div>
                    <h3>
                      Compile New Company Brand Playbook (Pipeline A · Guards
                      1–3)
                    </h3>
                    <p>
                      Ingest raw brand books (`.pdf`, `.docx`, `.md`), product
                      fact sheets (`.csv`, `.json`, `.yaml`), and reference
                      logos (`.png`, `.jpg`) into a deterministic YAML canon.
                    </p>
                  </div>
                </div>

                <form
                  onSubmit={handleCompileCanon}
                  className="cg-calibrate-form"
                >
                  <div className="cg-field-row-2">
                    <div className="cg-field-group">
                      <label htmlFor="compile-canon-id">
                        New Playbook Identifier
                      </label>
                      <input
                        id="compile-canon-id"
                        type="text"
                        value={compileId}
                        onChange={(e) => setCompileId(e.target.value)}
                        placeholder="e.g. acme-retail-2026"
                        required
                      />
                    </div>

                    <div className="cg-field-group">
                      <label htmlFor="compile-files">
                        Upload Brand Book, Fact Sheet or Reference Logo
                      </label>
                      <input
                        id="compile-files"
                        type="file"
                        multiple
                        accept=".pdf,.docx,.csv,.json,.yaml,.yml,.md,.txt,.html,.png,.jpg,.jpeg,.webp"
                        onChange={(e) =>
                          handleCompileFileSelect(e.target.files)
                        }
                      />
                      {compileAttachments.length > 0 && (
                        <div className="uploaded-files-pills">
                          {compileAttachments.map((att, idx) => (
                            <span
                              key={`${att.filename}-${idx}`}
                              className="file-pill"
                            >
                              {att.filename}
                              <button
                                type="button"
                                onClick={() =>
                                  setCompileAttachments((prev) =>
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
                  </div>

                  <div className="cg-field-group">
                    <label htmlFor="compile-raw-text">
                      Brand Rules, Approved Claims, Disclaimers &amp; Colour Hex
                      Tokens
                    </label>
                    <textarea
                      id="compile-raw-text"
                      rows={4}
                      value={compileText}
                      onChange={(e) => setCompileText(e.target.value)}
                      placeholder={
                        "Never use 'cheap', prefer 'affordable'.\n" +
                        "Primary Blue: #0D3B66.\n" +
                        "Approved Fact: 0% processing fee on loans under Rs 50,000 valid until 2026-09-30.\n" +
                        "Trigger: 'loan' -> Disclaimer: 'Subject to RBI KFS terms.'"
                      }
                    />
                  </div>

                  <div className="cg-rule-builder-toolbar">
                    <button
                      type="button"
                      className="cg-btn cg-btn-secondary cg-btn-sm"
                      onClick={() =>
                        setStudioTerms((prev) => [
                          ...prev,
                          { pattern_text: "", preferred: "", severity: 60 },
                        ])
                      }
                    >
                      + Term Rule
                    </button>
                    <button
                      type="button"
                      className="cg-btn cg-btn-secondary cg-btn-sm"
                      onClick={() =>
                        setStudioFacts((prev) => [
                          ...prev,
                          { text: "", conditions: [], valid_until: "" },
                        ])
                      }
                    >
                      + Approved Fact
                    </button>
                    <button
                      type="button"
                      className="cg-btn cg-btn-secondary cg-btn-sm"
                      onClick={() =>
                        setStudioColors((prev) => [
                          ...prev,
                          { name: "", hex: "#0D3B66", max_delta_e: 3.0 },
                        ])
                      }
                    >
                      + Colour Token
                    </button>
                    <button
                      type="button"
                      className="cg-btn cg-btn-secondary cg-btn-sm"
                      onClick={() =>
                        setStudioTriggers((prev) => [
                          ...prev,
                          {
                            trigger_pattern: "",
                            required_disclaimer_text: "",
                            severity: 70,
                          },
                        ])
                      }
                    >
                      + Disclaimer Trigger
                    </button>
                  </div>

                  {studioTerms.map((t, idx) => (
                    <div key={`st-${idx}`} className="cg-inline-rule-row">
                      <input
                        type="text"
                        placeholder="Banned term"
                        value={t.pattern_text}
                        onChange={(e) =>
                          setStudioTerms((prev) =>
                            prev.map((item, i) =>
                              i === idx
                                ? { ...item, pattern_text: e.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                      <input
                        type="text"
                        placeholder="Preferred replacement"
                        value={t.preferred}
                        onChange={(e) =>
                          setStudioTerms((prev) =>
                            prev.map((item, i) =>
                              i === idx
                                ? { ...item, preferred: e.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                      <button
                        type="button"
                        className="cg-btn cg-btn-ghost cg-btn-sm"
                        onClick={() =>
                          setStudioTerms((prev) =>
                            prev.filter((_, i) => i !== idx),
                          )
                        }
                      >
                        ✕
                      </button>
                    </div>
                  ))}

                  {studioFacts.map((f, idx) => (
                    <div key={`sf-${idx}`} className="cg-inline-rule-row">
                      <input
                        type="text"
                        placeholder="Approved fact/claim"
                        value={f.text}
                        onChange={(e) =>
                          setStudioFacts((prev) =>
                            prev.map((item, i) =>
                              i === idx
                                ? { ...item, text: e.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                      <input
                        type="text"
                        placeholder="Valid until YYYY-MM-DD"
                        value={f.valid_until ?? ""}
                        onChange={(e) =>
                          setStudioFacts((prev) =>
                            prev.map((item, i) =>
                              i === idx
                                ? { ...item, valid_until: e.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                      <button
                        type="button"
                        className="cg-btn cg-btn-ghost cg-btn-sm"
                        onClick={() =>
                          setStudioFacts((prev) =>
                            prev.filter((_, i) => i !== idx),
                          )
                        }
                      >
                        ✕
                      </button>
                    </div>
                  ))}

                  {studioColors.map((c, idx) => (
                    <div key={`sc-${idx}`} className="cg-inline-rule-row">
                      <input
                        type="text"
                        placeholder="Colour name"
                        value={c.name}
                        onChange={(e) =>
                          setStudioColors((prev) =>
                            prev.map((item, i) =>
                              i === idx
                                ? { ...item, name: e.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                      <input
                        type="text"
                        placeholder="#RRGGBB"
                        value={c.hex}
                        onChange={(e) =>
                          setStudioColors((prev) =>
                            prev.map((item, i) =>
                              i === idx
                                ? { ...item, hex: e.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                      <button
                        type="button"
                        className="cg-btn cg-btn-ghost cg-btn-sm"
                        onClick={() =>
                          setStudioColors((prev) =>
                            prev.filter((_, i) => i !== idx),
                          )
                        }
                      >
                        ✕
                      </button>
                    </div>
                  ))}

                  {studioTriggers.map((tr, idx) => (
                    <div key={`str-${idx}`} className="cg-inline-rule-row">
                      <input
                        type="text"
                        placeholder="Trigger keyword"
                        value={tr.trigger_pattern}
                        onChange={(e) =>
                          setStudioTriggers((prev) =>
                            prev.map((item, i) =>
                              i === idx
                                ? { ...item, trigger_pattern: e.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                      <input
                        type="text"
                        placeholder="Required disclaimer text"
                        value={tr.required_disclaimer_text}
                        onChange={(e) =>
                          setStudioTriggers((prev) =>
                            prev.map((item, i) =>
                              i === idx
                                ? {
                                    ...item,
                                    required_disclaimer_text: e.target.value,
                                  }
                                : item,
                            ),
                          )
                        }
                      />
                      <button
                        type="button"
                        className="cg-btn cg-btn-ghost cg-btn-sm"
                        onClick={() =>
                          setStudioTriggers((prev) =>
                            prev.filter((_, i) => i !== idx),
                          )
                        }
                      >
                        ✕
                      </button>
                    </div>
                  ))}

                  <div className="cg-composer-actions">
                    <button
                      type="submit"
                      className="cg-btn cg-btn-primary"
                      disabled={compiling}
                    >
                      {compiling
                        ? "Compiling Playbook…"
                        : "Compile & Register Playbook"}
                    </button>
                  </div>
                </form>

                {compileResult && (
                  <div
                    className="cg-success-banner"
                    style={{ marginTop: "1rem" }}
                  >
                    ✓ Compiled Playbook{" "}
                    <strong>{compileResult.canon_id}</strong> v
                    {compileResult.version} ({compileResult.term_count} terms,{" "}
                    {compileResult.fact_count} facts,{" "}
                    {compileResult.color_count} colours).
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
