import { useState, useEffect, useCallback, useRef, useMemo, type FormEvent } from "react";
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
  runGateCheck,
  callMcpRpc,
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
  type GateCheckResponsePayload,
} from "../../api/client";
import { useAuth } from "../auth/context";
import { useNavigate, Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  Copy,
  Cpu,
  FilePlus2,
  FileText,
  Filter,
  GitPullRequest,
  Globe,
  Image as ImageIcon,
  Layers,
  LogOut,
  Plus,
  Search,
  ShieldCheck,
  Sliders,
  Sparkles,
  Terminal,
  Trash2,
  Upload,
  X,
} from "lucide-react";

const CUSTOM_PLAYBOOK_VALUE = "__custom__";

const AUTO_PURGE_TEST_TITLES = new Set([
  "clean acme announcement", /* taste-skill-ignore */
  "minor tone drift",
  "ayurglow curcumin gold elixir",
  "ayurglow curcumin gold elixir launch",
  "ayurglow curcumin gold elixir landing page",
  "diwali instant digital loan campaign bundle",
  "rbi 2025 kfs & ccpa pre-flight · instant personal loan bundle",
  "quickloan festival credit campaign",
  "quickloan diwali festival campaign",
  "acme quickloan diwali festival campaign", /* taste-skill-ignore */
  "cloudscale enterprise tier release",
  "enterprise cloud launch landing page",
  "acme cloud enterprise launch landing page", /* taste-skill-ignore */
  "duplicate & table alignment test",
  "monsoon digital lending campaign",
  "monsoon kfs campaign",
  "p1-p6 full feature test",
  "e2e verification campaign",
  "test",
  "test sub",
  "test campaign",
]);

const CANON_DISPLAY_LABELS: Record<string, string> = {
  "indian-digital-lending":
    "RBI Digital Lending & Key Fact Statement (KFS) Baseline",
  "indian-d2c-nutra":
    "ASCI & CCPA Advertising & Substantiation Baseline",
  "acme-corp": /* taste-skill-ignore */
    "WCAG 2.1 AA Accessibility & Enterprise Baseline",
  "studio-brand-guidelines":
    "Brand Guidelines (Poppins/Lora ≥24pt · #141413/#FAF9F5/#D97757 · 60/30/10)", /* taste-skill-ignore */
};

function formatCanonName(id: string): string {
  return CANON_DISPLAY_LABELS[id] ?? id;
}

const SAMPLE_PLAYBOOK_TEMPLATES = [
  {
    id: "neobank-credit-2026",
    label: "Fintech NeoBank Credit Playbook",
    rawText: [
      'Never use "instant guaranteed loan" · use "credit facility subject to underwriting"',
      'Never use "zero credit check" · use "streamlined bureau verification"',
      'Never use "risk-free returns" · use "market-linked returns subject to scheme risks"',
      "0% processing fee on credit lines [under Rs 75,000; for salaried applicants only]",
      "Annual Percentage Rate (APR) is 16.5% [up to Rs 3,00,000]",
      'Trigger: "0% processing fee" -> "Subject to RBI Key Fact Statement (KFS) Schedule"',
      "Primary Brand Palette: #0D3B66, #1B6E66",
    ].join("\n"),
  },
  {
    id: "studio-brand-guidelines-2026",
    label: "Official Brand Guidelines (Poppins/Lora + Palette)",
    rawText: [
      "Never use \"Comic Sans\" · use \"Poppins (headings >= 24pt) or Lora (body < 24pt)\"",
      "Never use \"unbranded neon gradient\" · use \"Warm Alabaster (#FAF9F5) or Slate Ink (#141413)\"", /* taste-skill-ignore */
      "Heading typography uses Poppins [at least 24pt; with Arial fallback]",
      "Body typography uses Lora [under 24pt; with Georgia fallback]",
      "Trigger: \"Poppins\" -> \"fallback Arial/Georgia\"",
      "Official Brand Palette: #141413, #FAF9F5, #B0AEA5, #E8E6DC, #D97757, #6A9BCC, #788C5D", /* taste-skill-ignore */
    ].join("\n"),
  },
  {
    id: "ayurveda-wellness-d2c",
    label: "Ayurvedic D2C Wellness Playbook",
    rawText: [
      'Never use "miracle cure" · use "clinically studied botanical support"',
      'Never use "100% permanent weight loss" · use "supports healthy metabolic balance"',
      "2x bioavailability improvement [in a 12-week clinical study of 120 adults]",
      'Trigger: "clinically studied" -> "Results based on controlled ingredient study; not a substitute for medical advice"',
      "Brand Palette Tokens: #2E6F40, #D99B26",
    ].join("\n"),
  },
] as const;

const SAMPLE_CAMPAIGN_PRESETS = [
  {
    id: "preset-rbi",
    label: "RBI Lending Ad (Has Blockers)",
    canonId: "indian-digital-lending",
    title: "Q3 Instant Personal Loan Campaign",
    content:
      "Get instant personal loans with guaranteed approval and no credit check! Enjoy 0% processing fee on loans under Rs 1,00,000. Annual Percentage Rate (APR) is 14%.",
  },
  {
    id: "preset-nutra",
    label: "ASCI Nutra + Drip Pricing Ad",
    canonId: "indian-d2c-nutra",
    title: "Curcumin Gold Festival Bundle",
    content:
      "Try our miracle cure botanical elixir with 2x faster absorption! Flat 27% discount (inclusive of all taxes). GST and additional charges may apply.",
  },
] as const;

function estimateLiveRuleExtraction(
  text: string,
  extraTerms: CustomTermInput[],
  extraFacts: CustomFactInput[],
  extraColors: CustomColorInput[],
  extraTriggers: CustomTriggerInput[],
) {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  let termCount = extraTerms.filter((t) => t.pattern_text.trim() && t.preferred.trim()).length;
  let factCount = extraFacts.filter((f) => f.text.trim()).length;
  let trigCount = extraTriggers.filter((t) => t.trigger_pattern.trim() && t.required_disclaimer_text.trim()).length;

  for (const line of lines) {
    if (/(?:never\s+use|avoid|ban|do\s+not\s+use)\s+/i.test(line) || /["'“][^"'”]+["'”]\s*(?:->|→|=>)\s*["'“]/i.test(line)) {
      termCount++;
    } else if (/(?:trigger|when\s+mentioning|if\s+claiming)\s*[:-]?/i.test(line)) {
      trigCount++;
    } else if (/\[[^\]]+\]/.test(line)) {
      factCount++;
    }
  }
  const hexes = new Set((text.match(/#[0-9A-Fa-f]{6}\b/g) || []).map((h) => h.toUpperCase()));
  for (const c of extraColors) {
    if (c.hex?.trim()) hexes.add(c.hex.trim().toUpperCase());
  }
  if (text.trim() && termCount === 0) termCount = 1;
  return {
    terms: termCount,
    facts: Math.max(factCount, text.trim() ? 1 : 0),
    colors: Math.max(hexes.size, text.trim() ? 1 : 0),
    triggers: trigCount,
  };
}

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
    shortLabel: "Stage 1 · Creator",
    stageOwned: "Stage 1 · Pre-Flight & Remediation",
    stageNum: 1,
    responsibility:
      "Uploads campaign copy, documents, and banners, runs pre-flight checks, resolves blocking issues, and documents context on warning overrides.",
  },
  reviewer: {
    label: "Brand Manager (Playbook Owner)",
    shortLabel: "Stage 2 · Brand Manager",
    stageOwned: "Stage 2 · Brand & Playbook Review",
    stageNum: 2,
    responsibility:
      "Manages brand playbooks and rule thresholds, reviews revision history and warning overrides, and approves brand compliance.",
  },
  admin: {
    label: "Authorised Legal Reviewer",
    shortLabel: "Stage 3 · Legal Sign-Off",
    stageOwned: "Stage 3 · Regulatory & Legal Sign-Off",
    stageNum: 3,
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
  const { token, username, displayName, role, switchRole, logout } = useAuth();
  const navigate = useNavigate();
  const isSigningOutRef = useRef(false);

  const [activeTab, setActiveTab] = useState<
    "submissions" | "governance" | "mcp" | "gate"
  >("submissions");
  const [govSubTab, setGovSubTab] = useState<
    "rules" | "friction" | "calibrate" | "compile"
  >("rules");

  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [canons, setCanons] = useState<CanonSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [ruleSearchQuery, setRuleSearchQuery] = useState<string>("");

  // New submission form · automatically shown when queue is empty
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [rawContent, setRawContent] = useState("");
  const [selectedCanon, setSelectedCanon] = useState("");
  const [uploadedAttachments, setUploadedAttachments] = useState<
    BundleAttachmentPayload[]
  >([]);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [clearingAll, setClearingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playbookNotice, setPlaybookNotice] = useState<string | null>(null);

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
  const [inlineCompilingOnly, setInlineCompilingOnly] = useState(false);

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

  // Rule Calibration Sliders state
  const [calRuleId, setCalRuleId] = useState<string>("");
  const [calSeverity, setCalSeverity] = useState<number>(40);
  const [calMaxDeltaE, setCalMaxDeltaE] = useState<number>(5.0);
  const [calMaxWords, setCalMaxWords] = useState<number>(28);
  const [calMaxFkGrade, setCalMaxFkGrade] = useState<number>(11.0);
  const [calibrating, setCalibrating] = useState(false);
  const [calibrationResult, setCalibrationResult] =
    useState<CalibrateCanonRuleResponse | null>(null);

  // Playbook Studio Import state (Tab: Onboard New Playbook)
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

  // MCP Brand Rule Server Hub state (`activeTab === "mcp"`)
  const [mcpCanonName, setMcpCanonName] = useState<string>("fintech-mcp-playbook");
  const [mcpRawGuidelines, setMcpRawGuidelines] = useState<string>(
    SAMPLE_PLAYBOOK_TEMPLATES[0].rawText,
  );
  const [mcpSelectedTool, setMcpSelectedTool] = useState<string>("list_canons");
  const [mcpRequestJson, setMcpRequestJson] = useState<string>("");
  const [mcpResponseJson, setMcpResponseJson] = useState<string>("");
  const [mcpRunning, setMcpRunning] = useState<boolean>(false);
  const [mcpCopiedKey, setMcpCopiedKey] = useState<string | null>(null);

  // Pre-Publish Webhook Gate Studio state (`POST /api/gate/check`)
  const [gateCanonId, setGateCanonId] = useState<string>(
    "indian-digital-lending",
  );
  const [gateAdapter, setGateAdapter] = useState<
    "generic" | "shopify" | "webflow"
  >("generic");
  const [gateAlpha, setGateAlpha] = useState<number>(0.1);
  const [gateTitle, setGateTitle] = useState<string>(SAMPLE_CAMPAIGN_PRESETS[0].title);
  const [gateContent, setGateContent] = useState<string>(SAMPLE_CAMPAIGN_PRESETS[0].content);
  const [gatePersist, setGatePersist] = useState<boolean>(false);
  const [gateRunning, setGateRunning] = useState<boolean>(false);
  const [gateResult, setGateResult] =
    useState<GateCheckResponsePayload | null>(null);

  const inlineLiveStats = useMemo(
    () =>
      estimateLiveRuleExtraction(
        inlineCanonText,
        inlineTerms,
        inlineFacts,
        inlineColors,
        inlineTriggers,
      ),
    [inlineCanonText, inlineTerms, inlineFacts, inlineColors, inlineTriggers],
  );

  const studioLiveStats = useMemo(
    () =>
      estimateLiveRuleExtraction(
        compileText,
        studioTerms,
        studioFacts,
        studioColors,
        studioTriggers,
      ),
    [compileText, studioTerms, studioFacts, studioColors, studioTriggers],
  );

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
    if (isSigningOutRef.current || !localStorage.getItem("cg_token")) {
      return;
    }
    setLoading(true);
    setError(null);
    const [subsRes, cansRes] = await Promise.allSettled([
      listSubmissions(),
      listCanons(),
    ]);

    if (cansRes.status === "fulfilled") {
      const cans = cansRes.value;
      setCanons(cans);
      if (cans.length > 0) {
        const defaultCanon =
          cans.find((c) => c.id === "indian-digital-lending")?.id ?? cans[0].id;
        setSelectedCanon((prev) => prev || defaultCanon);
        setGateCanonId((prev) => prev || defaultCanon);
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
    }

    if (subsRes.status === "fulfilled") {
      const rawList = subsRes.value;
      const junkRows = rawList.filter((s) =>
        AUTO_PURGE_TEST_TITLES.has(s.title.trim().toLowerCase()),
      );
      const userRows = rawList.filter(
        (s) => !AUTO_PURGE_TEST_TITLES.has(s.title.trim().toLowerCase()),
      );

      if (junkRows.length > 0) {
        void Promise.allSettled(
          junkRows.map((j) => deleteSubmission(j.id)),
        );
      }

      setSubmissions(userRows);
      if (userRows.length === 0) {
        setShowForm(true);
      }
    } else if (!isSigningOutRef.current) {
      setError(
        (subsRes.reason as Error)?.message || "Failed to load submissions",
      );
    }

    setLoading(false);
  }, [syncRuleSliders]);

  async function handleRoleSwitch(targetRole: string) {
    setError(null);
    try {
      await switchRole(targetRole);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function handleSignOut() {
    isSigningOutRef.current = true;
    logout();
    navigate("/login", { replace: true });
  }

  useEffect(() => {
    if (!token || isSigningOutRef.current) return;
    let active = true;
    void Promise.resolve().then(() => {
      if (active && !isSigningOutRef.current) {
        setSubmissions([]);
        void refresh();
      }
    });
    return () => {
      active = false;
    };
  }, [refresh, token, username, role]);

  const loadGovernanceTelemetry = useCallback(async (canonId: string) => {
    if (!canonId || isSigningOutRef.current) return;
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
          void loadGovernanceTelemetry(govCanonId);
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

  // Standalone compilation of inline playbook rules (without requiring campaign copy!)
  async function handleCompileInlinePlaybookOnly() {
    const cleanId =
      inlineCanonId
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9-_]+/g, "-") || "custom-company-playbook";
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
        "Paste your company brand guidelines/facts or click a Sample Playbook Template below to compile.",
      );
      return;
    }

    setInlineCompilingOnly(true);
    setError(null);
    setPlaybookNotice(null);
    try {
      const res = await compileBrandCanon(
        cleanId,
        inlineCanonText,
        inlineCanonFiles,
        "1.0",
        true,
        {
          custom_terms: inlineTerms,
          custom_facts: inlineFacts,
          custom_colors: inlineColors,
          custom_triggers: inlineTriggers,
        },
      );
      await refresh();
      setSelectedCanon(res.canon_id);
      setGovCanonId(res.canon_id);
      setCompileResult(res);
      setPlaybookNotice(
        `Compiled & Activated Playbook "${res.canon_id}" (v${res.version}) · extracted ${res.term_count} terminology rules, ${res.fact_count} facts, ${res.color_count} brand colour tokens, and ${res.trigger_count ?? 0} disclaimer triggers.`,
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setInlineCompilingOnly(false);
    }
  }

  async function handleCompileCanon(e: FormEvent) {
    e.preventDefault();
    const targetId = compileId.trim() || "custom-brand-playbook";
    const hasCustomRules =
      studioTerms.length > 0 ||
      studioFacts.length > 0 ||
      studioColors.length > 0 ||
      studioTriggers.length > 0;
    if (
      !compileText.trim() &&
      compileAttachments.length === 0 &&
      !hasCustomRules
    ) {
      setError(
        "Please paste company guideline text, select a sample template above, upload a document, or add structured rules.",
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
        true,
        {
          custom_terms: studioTerms,
          custom_facts: studioFacts,
          custom_colors: studioColors,
          custom_triggers: studioTriggers,
        },
      );
      setCompileResult(res);
      await refresh();
      setSelectedCanon(res.canon_id);
      handleSelectGovCanon(res.canon_id);
      setPrAppliedBanner(
        `Compiled & Activated Playbook "${res.canon_id}" (v${res.version}) · ${res.term_count} terminology rules, ${res.fact_count} facts, ${res.color_count} colour tokens now active.`,
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCompiling(false);
    }
  }

  async function handleRunMcpTool(
    toolName: string,
    toolArgs: Record<string, unknown>,
  ) {
    setMcpRunning(true);
    setMcpSelectedTool(toolName);
    const reqObj = {
      jsonrpc: "2.0",
      id: Date.now(),
      method: "tools/call",
      params: {
        name: toolName,
        arguments: toolArgs,
      },
    };
    setMcpRequestJson(JSON.stringify(reqObj, null, 2));
    try {
      const res = await callMcpRpc("tools/call", {
        name: toolName,
        arguments: toolArgs,
      });
      setMcpResponseJson(JSON.stringify(res, null, 2));
      if (toolName === "compile_canon" || toolName === "submit_batch") {
        await refresh();
      }
    } catch (err) {
      setMcpResponseJson(
        JSON.stringify({ error: (err as Error).message }, null, 2),
      );
    } finally {
      setMcpRunning(false);
    }
  }

  async function handleReadMcpResource(uri: string) {
    setMcpRunning(true);
    const reqObj = {
      jsonrpc: "2.0",
      id: Date.now(),
      method: "resources/read",
      params: { uri },
    };
    setMcpRequestJson(JSON.stringify(reqObj, null, 2));
    try {
      const res = await callMcpRpc("resources/read", { uri });
      setMcpResponseJson(JSON.stringify(res, null, 2));
    } catch (err) {
      setMcpResponseJson(
        JSON.stringify({ error: (err as Error).message }, null, 2),
      );
    } finally {
      setMcpRunning(false);
    }
  }

  function handleCopyText(key: string, text: string) {
    navigator.clipboard?.writeText(text).catch(() => {});
    setMcpCopiedKey(key);
    setTimeout(() => setMcpCopiedKey(null), 2000);
  }

  async function handleRunWebhookGate(e?: FormEvent) {
    if (e) e.preventDefault();
    if (!gateContent.trim()) return;
    setGateRunning(true);
    setError(null);
    try {
      const res = await runGateCheck({
        canon_id: gateCanonId,
        adapter: gateAdapter,
        title: gateTitle.trim() || "Webhook Pre-Publish Check",
        raw_content: gateContent,
        alpha: gateAlpha,
        persist: gatePersist,
      });
      setGateResult(res);
      if (gatePersist && res.submission_id) {
        await refresh();
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setGateRunning(false);
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPlaybookNotice(null);

    const hasInlinePlaybookInput =
      selectedCanon === CUSTOM_PLAYBOOK_VALUE &&
      (inlineCanonText.trim().length > 0 ||
        inlineCanonFiles.length > 0 ||
        inlineTerms.length > 0 ||
        inlineFacts.length > 0 ||
        inlineColors.length > 0 ||
        inlineTriggers.length > 0);

    // If user pasted custom playbook guidelines and clicked submit without campaign copy,
    // compile & activate the playbook standalone instead of throwing an error!
    if (hasInlinePlaybookInput && !rawContent.trim() && uploadedAttachments.length === 0) {
      await handleCompileInlinePlaybookOnly();
      return;
    }

    if (!rawContent.trim() && uploadedAttachments.length === 0) {
      setError(
        "Please enter campaign copy (or click a 1-Click Sample Campaign above) or attach a document/banner.",
      );
      return;
    }

    setSubmitting(true);
    try {
      let targetCanonId = selectedCanon;

      if (selectedCanon === CUSTOM_PLAYBOOK_VALUE) {
        const cleanId =
          inlineCanonId
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9-_]+/g, "-") || "company-custom-playbook";
        if (!hasInlinePlaybookInput) {
          setError(
            "Please paste your company rules/facts, click a sample playbook template, or add structured rules.",
          );
          setSubmitting(false);
          return;
        }
        const compiled = await compileBrandCanon(
          cleanId,
          inlineCanonText,
          inlineCanonFiles,
          "1.0",
          true,
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
        title.trim() || "Campaign Compliance Audit",
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

  async function handleClearAllSubmissions() {
    if (submissions.length === 0) return;
    setClearingAll(true);
    setError(null);
    try {
      await Promise.allSettled(submissions.map((s) => deleteSubmission(s.id)));
      localStorage.removeItem("cg_trial_submission_ids");
      localStorage.removeItem("cg_trial_active");
      setSubmissions([]);
      setShowForm(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setClearingAll(false);
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
      if (
        role === "creator" &&
        s.status !== "draft" &&
        s.status !== "changes_requested"
      )
        return false;
      if (role === "reviewer" && s.status !== "in_review") return false;
      if (role === "admin" && s.status !== "approved") return false;
    } else if (stageFilter === "stage1") {
      if (s.status !== "draft" && s.status !== "changes_requested")
        return false;
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
    <div className="cg-workspace-layout">
      {/* ── Left Sidebar Navigation Rail ── */}
      <aside className="cg-sidebar" aria-label="Workspace Navigation">
        <div className="cg-sidebar-top">
          <div className="cg-sidebar-brand-row">
            <Link to="/welcome" className="cg-brand">
              <span className="cg-brand-mark" aria-hidden="true">
                <ShieldCheck size={16} strokeWidth={2.2} />
              </span>
              <span className="cg-brand-name">CanonGate</span>
              <span className="cg-brand-version">Console</span>
            </Link>
          </div>

          <nav className="cg-sidebar-nav" aria-label="Primary Views">
            <span className="cg-nav-section-title">Operations</span>
            <button
              type="button"
              data-testid="nav-campaign-queue"
              className={`cg-nav-item ${
                activeTab === "submissions" ? "active" : ""
              }`}
              onClick={() => setActiveTab("submissions")}
            >
              <span className="cg-nav-item-left">
                <Layers size={15} />
                <span>Campaign Queue</span>
              </span>
              <span className="cg-ws-count">{submissions.length}</span>
            </button>

            <button
              type="button"
              data-testid="nav-import-playbook"
              className={`cg-nav-item ${
                activeTab === "governance" && govSubTab === "compile"
                  ? "active"
                  : ""
              }`}
              onClick={() => {
                setActiveTab("governance");
                setGovSubTab("compile");
              }}
            >
              <span className="cg-nav-item-left">
                <FilePlus2 size={15} />
                <span>Import Custom Playbook</span>
              </span>
              <span className="cg-ws-count">+New</span>
            </button>

            <button
              type="button"
              data-testid="nav-playbooks-rules"
              className={`cg-nav-item ${
                activeTab === "governance" &&
                govSubTab !== "friction" &&
                govSubTab !== "compile"
                  ? "active"
                  : ""
              }`}
              onClick={() => {
                setActiveTab("governance");
                setGovSubTab("rules");
              }}
            >
              <span className="cg-nav-item-left">
                <BookOpen size={15} />
                <span>Playbooks &amp; Rules</span>
              </span>
              <span className="cg-ws-count">{canons.length}</span>
            </button>

            <button
              type="button"
              className={`cg-nav-item ${
                activeTab === "governance" && govSubTab === "friction"
                  ? "active"
                  : ""
              }`}
              onClick={() => {
                setActiveTab("governance");
                setGovSubTab("friction");
              }}
            >
              <span className="cg-nav-item-left">
                <GitPullRequest size={15} />
                <span>Friction &amp; v1.1 PRs</span>
              </span>
            </button>

            <span className="cg-nav-section-title">Developer &amp; AI Agents</span>
            <button
              type="button"
              data-testid="nav-mcp-server"
              className={`cg-nav-item ${activeTab === "mcp" ? "active" : ""}`}
              onClick={() => setActiveTab("mcp")}
            >
              <span className="cg-nav-item-left">
                <Cpu size={15} />
                <span>MCP Brand Rule Server</span>
              </span>
              <span className="cg-ws-count">MCP</span>
            </button>

            <button
              type="button"
              data-testid="nav-gate-api"
              className={`cg-nav-item ${activeTab === "gate" ? "active" : ""}`}
              onClick={() => setActiveTab("gate")}
            >
              <span className="cg-nav-item-left">
                <Terminal size={15} />
                <span>Pre-Publish Gate API</span>
              </span>
            </button>

            <span className="cg-nav-section-title">Platform</span>
            <Link
              to="/welcome"
              className="cg-nav-item"
              style={{ textDecoration: "none" }}
            >
              <span className="cg-nav-item-left">
                <Globe size={15} />
                <span>Home &amp; Auth Gateway</span>
              </span>
            </Link>
          </nav>
        </div>

        {/* Bottom Identity & In-Session RBAC Switcher */}
        <div className="cg-sidebar-bottom">
          <div className="cg-rbac-card">
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "6px",
              }}
            >
              <div
                className="cg-user-pill"
                title={`Authenticated as ${displayName || username} (@${username})`}
              >
                <span className="cg-user-avatar">
                  {(displayName || username || "U").slice(0, 1).toUpperCase()}
                </span>
                <span className="cg-user-handle">@{username}</span>
              </div>
              <span className="cg-role-stage-tag">
                {currentRoleMeta.shortLabel}
              </span>
            </div>

            <div
              className="cg-quick-role-switchers"
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3, 1fr)",
                gap: "4px",
              }}
              title="Active RBAC Role (POST /api/auth/switch-role)"
            >
              <button
                type="button"
                className={`cg-btn cg-btn-sm ${
                  role === "creator" ? "cg-btn-primary" : "cg-btn-secondary"
                }`}
                onClick={() => void handleRoleSwitch("creator")}
              >
                Creator
              </button>
              <button
                type="button"
                className={`cg-btn cg-btn-sm ${
                  role === "reviewer" ? "cg-btn-primary" : "cg-btn-secondary"
                }`}
                onClick={() => void handleRoleSwitch("reviewer")}
              >
                Brand
              </button>
              <button
                type="button"
                className={`cg-btn cg-btn-sm ${
                  role === "admin" ? "cg-btn-primary" : "cg-btn-secondary"
                }`}
                onClick={() => void handleRoleSwitch("admin")}
              >
                Legal
              </button>
            </div>

            <button
              type="button"
              data-testid="sidebar-signout-btn"
              onClick={handleSignOut}
              className="cg-btn cg-btn-ghost cg-btn-sm"
              style={{ width: "100%", justifyContent: "center" }}
              title="Sign out and return to Sign In screen"
            >
              <LogOut size={13} />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main White Sheet Workspace Surface ── */}
      <div className="cg-workspace-sheet-wrap">
        <main className="cg-workspace-sheet">
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

          {playbookNotice && (
            <div className="cg-success-banner" role="status" data-testid="playbook-compiled-banner">
              <CheckCircle2 size={15} />
              <span>{playbookNotice}</span>
              <button
                type="button"
                className="cg-btn cg-btn-ghost cg-btn-sm"
                style={{ marginLeft: "auto" }}
                onClick={() => {
                  setActiveTab("governance");
                  setGovSubTab("rules");
                }}
              >
                <span>Inspect Compiled Rules →</span>
              </button>
            </div>
          )}

          {activeTab === "submissions" ? (
            <div
              key="tab-submissions"
              className="cg-animate-swap"
              style={{ display: "flex", flexDirection: "column", gap: "18px" }}
            >
              {/* ── Workspace Header Bar ── */}
              <section className="cg-console-hero-bar">
                <div className="cg-console-hero-left">
                  <h1 className="cg-console-title">Campaign Queue</h1>
                  <span className="cg-role-stage-tag">
                    {currentRoleMeta.stageOwned}
                  </span>
                  {myActionCount > 0 && (
                    <span className="cg-action-needed-pill">
                      {myActionCount} awaiting your action
                    </span>
                  )}
                </div>

                <div className="cg-console-hero-actions">
                  {submissions.length > 0 && (
                    <button
                      type="button"
                      className="cg-btn cg-btn-secondary cg-btn-sm"
                      disabled={clearingAll}
                      onClick={() => void handleClearAllSubmissions()}
                      title="Remove all submissions from the queue"
                    >
                      <Trash2 size={13} />
                      <span>
                        {clearingAll
                          ? "Clearing…"
                          : `Clear Queue (${submissions.length})`}
                      </span>
                    </button>
                  )}
                  <button
                    type="button"
                    data-testid="header-import-playbook-btn"
                    className="cg-btn cg-btn-secondary cg-btn-sm"
                    onClick={() => {
                      const hasPastedInline =
                        inlineCanonText.trim().length > 0 ||
                        inlineCanonFiles.length > 0 ||
                        inlineTerms.length > 0 ||
                        inlineFacts.length > 0 ||
                        inlineColors.length > 0 ||
                        inlineTriggers.length > 0;
                      if (showForm && selectedCanon === CUSTOM_PLAYBOOK_VALUE && hasPastedInline) {
                        void handleCompileInlinePlaybookOnly();
                      } else {
                        setShowForm(true);
                        setSelectedCanon(CUSTOM_PLAYBOOK_VALUE);
                        setTimeout(() => {
                          document.getElementById("inline-canon-text")?.focus();
                        }, 60);
                      }
                    }}
                  >
                    <Upload size={13} />
                    <span>Import Custom Playbook</span>
                  </button>
                  <button
                    type="button"
                    className="cg-btn cg-btn-primary cg-btn-sm"
                    onClick={() => setShowForm(!showForm)}
                  >
                    {showForm ? (
                      <>
                        <X size={14} />
                        <span>Close Composer</span>
                      </>
                    ) : (
                      <>
                        <Plus size={14} />
                        <span>New Campaign Bundle</span>
                      </>
                    )}
                  </button>
                </div>
              </section>

              {/* ── Divided 4-Cell Ledger KPI Strip ── */}
              <div className="cg-kpi-strip">
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">Active Campaign Bundles</span>
                  <strong>{submissions.length}</strong>
                  <span>{canons.length} governing playbooks available</span>
                </div>
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">Awaiting Your Action</span>
                  <strong>{myActionCount}</strong>
                  <span>Assigned to {currentRoleMeta.shortLabel}</span>
                </div>
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">
                    In Brand &amp; Legal Review
                  </span>
                  <strong>{stageCounts.stage2 + stageCounts.stage3}</strong>
                  <span>
                    Stage 2 ({stageCounts.stage2}) · Stage 3 (
                    {stageCounts.stage3})
                  </span>
                </div>
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">
                    Released &amp; Merkle Sealed
                  </span>
                  <strong className="cg-text-emerald">
                    {stageCounts.stage4}
                  </strong>
                  <span>Ed25519 + C2PA v2.3 signed</span>
                </div>
              </div>

              {/* ── Campaign Bundle Composer ── */}
              {showForm && (
                <form
                  className="cg-composer-card cg-animate-swap"
                  onSubmit={handleCreate}
                >
                  <div className="cg-composer-header">
                    <div>
                      <h3>New Campaign Pre-Flight Audit</h3>
                    </div>
                    <div className="cg-composer-presets">
                      <span style={{ fontSize: "12px", color: "var(--muted)", marginRight: "4px" }}>
                        Quick Fill:
                      </span>
                      {SAMPLE_CAMPAIGN_PRESETS.map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          className="cg-preset-chip"
                          onClick={() => {
                            setTitle(p.title);
                            setSelectedCanon(p.canonId);
                            setRawContent(p.content);
                          }}
                        >
                          <Sparkles size={12} />
                          <span>{p.label}</span>
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
                          placeholder="e.g., Q3 Lending Launch"
                        />
                      </div>

                      <div className="cg-field-group">
                        <div className="cg-field-label-row">
                          <label htmlFor="sub-canon">
                            Governing Regulatory or Brand Playbook
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
                              ? "Use Built-In Baseline"
                              : "+ Upload Custom Company Guidelines"}
                          </button>
                        </div>
                        <select
                          id="sub-canon"
                          value={selectedCanon}
                          onChange={(e) => setSelectedCanon(e.target.value)}
                        >
                          {canons.map((c) => (
                            <option key={c.id} value={c.id}>
                              {formatCanonName(c.id)} ({c.id} v{c.version})
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
                      <div className="cg-custom-canon-box cg-animate-swap" data-testid="inline-custom-playbook-box">
                        <div className="cg-custom-canon-header">
                          <div>
                            <h4>
                              Compile Custom Company Brand Playbook (Pipeline A)
                            </h4>
                            <p>
                              Paste your brand rules, approved facts, hex colors, and disclaimer triggers below (or load a sample template) and click <strong>Compile &amp; Activate Playbook Only</strong> to save immediately.
                            </p>
                          </div>
                          <div className="cg-composer-presets">
                            {SAMPLE_PLAYBOOK_TEMPLATES.map((tpl) => (
                              <button
                                key={tpl.id}
                                type="button"
                                data-testid={`sample-playbook-${tpl.id}`}
                                className="cg-preset-chip"
                                onClick={() => {
                                  setInlineCanonId(tpl.id);
                                  setInlineCanonText(tpl.rawText);
                                }}
                              >
                                <Sparkles size={12} />
                                <span>Load {tpl.label}</span>
                              </button>
                            ))}
                          </div>
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
                                void handleInlineCanonFileSelect(e.target.files)
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
                                      <X size={12} />
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
                            rows={4}
                            value={inlineCanonText}
                            onChange={(e) => setInlineCanonText(e.target.value)}
                            placeholder='e.g. Never use "guaranteed approval" · use "subject to credit assessment". 0% processing fee [under Rs 50,000]. Trigger: "0% processing fee" -> "Subject to KFS". Brand Hex: #0D3B66'
                          />
                        </div>

                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            flexWrap: "wrap",
                            gap: "10px",
                          }}
                        >
                          <div className="cg-rule-builder-toolbar">
                            <button
                              type="button"
                              className="cg-btn cg-btn-secondary cg-btn-sm"
                              onClick={() =>
                                setInlineTerms((prev) => [
                                  ...prev,
                                  {
                                    pattern_text: "",
                                    preferred: "",
                                    severity: 60,
                                  },
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

                          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                            <span className="cg-brand-version" data-testid="inline-live-parser-preview">
                              Live Extract: {inlineLiveStats.terms} terms · {inlineLiveStats.facts} facts · {inlineLiveStats.colors} hex · {inlineLiveStats.triggers} triggers
                            </span>
                            <button
                              type="button"
                              data-testid="compile-inline-playbook-btn"
                              className="cg-btn cg-btn-emerald cg-btn-sm"
                              disabled={inlineCompilingOnly}
                              onClick={() => void handleCompileInlinePlaybookOnly()}
                            >
                              <CheckCircle2 size={13} />
                              <span>
                                {inlineCompilingOnly
                                  ? "Compiling Playbook…"
                                  : "Compile & Activate Playbook Only"}
                              </span>
                            </button>
                          </div>
                        </div>

                        {inlineTerms.map((t, idx) => (
                          <div key={`it-${idx}`} className="cg-inline-rule-row">
                            <input
                              type="text"
                              placeholder="Banned term"
                              value={t.pattern_text}
                              onChange={(e) =>
                                setInlineTerms((prev) =>
                                  prev.map((item, i) =>
                                    i === idx
                                      ? {
                                          ...item,
                                          pattern_text: e.target.value,
                                        }
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
                              <X size={13} />
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
                                      ? {
                                          ...item,
                                          valid_until: e.target.value,
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
                                setInlineFacts((prev) =>
                                  prev.filter((_, i) => i !== idx),
                                )
                              }
                            >
                              <X size={13} />
                            </button>
                          </div>
                        ))}

                        {inlineColors.map((c, idx) => (
                          <div key={`ic-${idx}`} className="cg-inline-rule-row">
                            <input
                              type="text"
                              placeholder="Colour name"
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
                              <X size={13} />
                            </button>
                          </div>
                        ))}

                        {inlineTriggers.map((tr, idx) => (
                          <div key={`itr-${idx}`} className="cg-inline-rule-row">
                            <input
                              type="text"
                              placeholder="Trigger keyword"
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
                              <X size={13} />
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
                          placeholder="Paste or write campaign text, claims, disclaimers, or pricing tables here..."
                        />
                      </div>

                      <div className="cg-field-group">
                        <label htmlFor="sub-files">
                          Attach Campaign Documents or Banners (`.docx`, `.pdf`,
                          `.html`, `.png`, `.jpg`)
                        </label>
                        <input
                          id="sub-files"
                          type="file"
                          multiple
                          accept=".docx,.pdf,.html,.htm,.md,.txt,.csv,.json,.png,.jpg,.jpeg,.webp"
                          onChange={(e) => void handleFileSelect(e.target.files)}
                        />
                        <p className="cg-field-help">
                          All text and visual assets are parsed locally into a
                          unified ContentAST with zero unmasked cloud data
                          leaks.
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
                                  <X size={12} />
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
                      DPDP 2023 PII Vault Active · Auto-runs Tier 1–2 Pre-Flight
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
                            : selectedCanon === CUSTOM_PLAYBOOK_VALUE && !rawContent.trim()
                              ? "Compile & Activate Playbook"
                              : "Create & Run Scan"}
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
                      <X size={12} />
                    </button>
                  )}
                </div>
              </div>

              {/* ── Campaign Queue List ── */}
              {loading ? (
                <div className="cg-empty-box">Loading campaign queue…</div>
              ) : filteredSubmissions.length === 0 ? (
                <div className="cg-empty-box">
                  <p style={{ margin: 0 }}>
                    {submissions.length === 0
                      ? "Your campaign queue is clean and empty. Use the composer above (or click a Quick Fill preset) to run your first pre-flight audit."
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
                                Action Required
                              </span>
                            )}
                          </div>

                          <div className="cg-triage-right-meta">
                            <code className="cg-canon-badge">
                              {formatCanonName(s.canon_id)}
                            </code>
                            <button
                              type="button"
                              className="cg-delete-btn"
                              disabled={deletingId === s.id}
                              onClick={(e) => void handleDeleteSubmission(e, s.id)}
                              title="Delete campaign bundle"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </div>

                        <h3 className="cg-triage-title">{s.title}</h3>

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
          ) : activeTab === "governance" ? (
            /* ── Tab 2: Brand Playbooks, Rules & Custom Playbook Compiler ── */
            <div key="tab-governance" className="cg-gov-studio cg-animate-swap">
              <div className="cg-console-hero-bar">
                <div className="cg-console-hero-left">
                  <h1 className="cg-console-title">
                    Regulatory Baselines &amp; Brand Playbooks
                  </h1>
                </div>

                <div className="cg-gov-selector-box">
                  <label htmlFor="gov-canon-select">Active Playbook</label>
                  <select
                    id="gov-canon-select"
                    value={govCanonId}
                    onChange={(e) => handleSelectGovCanon(e.target.value)}
                  >
                    {canons.map((c) => (
                      <option key={c.id} value={c.id}>
                        {formatCanonName(c.id)} ({c.id} v{c.version})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {prAppliedBanner && (
                <div className="cg-success-banner">
                  <Check size={14} />
                  <span>{prAppliedBanner}</span>
                </div>
              )}

              {activeCanonSummary && (
                <div className="cg-kpi-strip">
                  <div className="cg-kpi-cell">
                    <span className="cg-mono-label">Playbook Version</span>
                    <strong>v{activeCanonSummary.version}</strong>
                    <code>SHA: {activeCanonSummary.hash.slice(0, 10)}…</code>
                  </div>
                  <div className="cg-kpi-cell">
                    <span className="cg-mono-label">Terminology Rules</span>
                    <strong>{activeCanonSummary.term_count}</strong>
                    <span>Aho-Corasick + UTS #39</span>
                  </div>
                  <div className="cg-kpi-cell">
                    <span className="cg-mono-label">Approved Facts</span>
                    <strong>{activeCanonSummary.fact_count}</strong>
                    <span>QASem SlotDiff Grounded</span>
                  </div>
                  <div className="cg-kpi-cell">
                    <span className="cg-mono-label">Brand Colour Tokens</span>
                    <strong>{activeCanonSummary.color_count}</strong>
                    <span>CIEDE2000 ΔE₀₀ Verified</span>
                  </div>
                  <div className="cg-kpi-cell">
                    <span className="cg-mono-label">Triggers &amp; Logos</span>
                    <strong>
                      {(activeCanonSummary.trigger_count ?? 0) +
                        (activeCanonSummary.logo_count ?? 0)}
                    </strong>
                    <span>Mandatory Disclosures + ORB</span>
                  </div>
                  <div className="cg-kpi-cell">
                    <span className="cg-mono-label">Krippendorff&apos;s α</span>
                    <strong className="cg-text-emerald">
                      {frictionReport
                        ? `${(frictionReport.krippendorff_alpha * 100).toFixed(0)}%`
                        : "100%"}
                    </strong>
                    <span>Inter-Reviewer Agreement</span>
                  </div>
                </div>
              )}

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
                    Rule &amp; Fact Catalog (
                    {activeCanonSummary?.rules?.length ?? 0})
                  </span>
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
                  <span>Import Custom Playbook (Pipeline A)</span>
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
                  <span>Friction Insights &amp; v1.1 Auto-PRs</span>
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
                  <span>Calibrate Thresholds</span>
                </button>
              </div>

              {/* Sub-Tab 1: Rule & Fact Catalog */}
              {govSubTab === "rules" && (
                <div key="gov-rules" className="cg-gov-card cg-animate-swap">
                  <div className="cg-gov-card-header">
                    <div>
                      <h3>
                        Compiled Rules, Approved Facts &amp; Visual Tokens in{" "}
                        <strong>{formatCanonName(govCanonId)}</strong> (
                        <code>{govCanonId}</code>)
                      </h3>
                      <p>
                        Select any rule row to calibrate its severity weight or
                        perceptual tolerance.
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
                              {r.source_text || "·"}
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
                              Aggregates compliance findings across your
                              campaigns to pinpoint high-risk categories.
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
                                <th className="cg-num-col">Flags</th>
                                <th className="cg-num-col">Resolved</th>
                                <th className="cg-num-col">Overridden</th>
                                <th>Actionable Insight</th>
                              </tr>
                            </thead>
                            <tbody>
                              {frictionReport.category_breakdown.map((cat) => (
                                <tr key={cat.category}>
                                  <td>
                                    <strong>{cat.category}</strong>
                                  </td>
                                  <td className="cg-num-col">
                                    {cat.total_flags}
                                  </td>
                                  <td className="cg-num-col">
                                    {cat.resolved_count}
                                  </td>
                                  <td className="cg-num-col">
                                    {cat.overridden_count}
                                  </td>
                                  <td className="cg-td-muted">
                                    <code>{cat.top_rule_id}</code> ·{" "}
                                    {cat.insight}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <div className="cg-clean-note">
                            No recurring category violations recorded yet for{" "}
                            <strong>{formatCanonName(govCanonId)}</strong>.
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
                                <th className="cg-num-col">Flags</th>
                                <th className="cg-num-col">Overrides</th>
                                <th className="cg-num-col">
                                  Posterior Friction
                                </th>
                                <th>Status</th>
                              </tr>
                            </thead>
                            <tbody>
                              {frictionReport.rules.map((r) => (
                                <tr key={r.rule_id}>
                                  <td>
                                    <code>{r.rule_id}</code>
                                  </td>
                                  <td className="cg-num-col">
                                    {r.total_flags}
                                  </td>
                                  <td className="cg-num-col">
                                    {r.overrides_and_disputes}
                                  </td>
                                  <td className="cg-num-col">
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
                            <strong>{formatCanonName(govCanonId)}</strong>.
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
                            onClick={() => void handleProposePr()}
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
                      style={{ marginTop: "14px" }}
                    >
                      <div className="cg-gov-card-header">
                        <div>
                          <h3>
                            Proposed Playbook Pull Request:{" "}
                            {prProposal.canon_id} v{prProposal.base_version} → v
                            {prProposal.proposed_version}
                          </h3>
                          <p>
                            Historical blast-radius simulation across{" "}
                            <strong>{prProposal.bundles_evaluated}</strong>{" "}
                            campaign(s): Flags reduced from{" "}
                            <strong>{prProposal.before_findings}</strong> →{" "}
                            <strong>{prProposal.after_findings}</strong> (
                            {(prProposal.reduction_ratio * 100).toFixed(1)}%
                            noise reduction).
                          </p>
                        </div>
                        {prProposal.has_changes && (
                          <button
                            type="button"
                            className="cg-btn cg-btn-emerald"
                            onClick={() => void handleApplyPr()}
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
                                  <td className="cg-td-muted">
                                    {rev.rationale}
                                  </td>
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
                        <code>1–49</code>) or a hard Blocker (
                        <code>50–100</code>
                        ), or adjust CIEDE2000 ΔE₀₀ and readability ceilings.
                      </p>
                    </div>
                  </div>

                  <form
                    onSubmit={(e) => void handleCalibrateRule(e)}
                    className="cg-calibrate-form"
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "14px",
                    }}
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
                              [{r.rule_type.toUpperCase()}] {r.id} · {r.label}
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
                          onChange={(e) =>
                            setCalSeverity(Number(e.target.value))
                          }
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
                      style={{ marginTop: "10px" }}
                    >
                      <Check size={14} />
                      <span>
                        Updated <strong>{calibrationResult.canon_id}</strong> (v
                        {calibrationResult.previous_version} → v
                        {calibrationResult.new_version})
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Sub-Tab 4: Import Custom Playbook (Pipeline A) */}
              {govSubTab === "compile" && (
                <div key="gov-compile" className="cg-gov-card cg-animate-swap" data-testid="studio-compile-playbook-card">
                  <div className="cg-gov-card-header">
                    <div>
                      <h3>
                        Import &amp; Compile Custom Company Playbook (Pipeline A · Guards 1–3)
                      </h3>
                      <p>
                        Paste raw brand rules, approved facts, hex color tokens, and disclaimer triggers·or click a 1-click template·to compile a deterministic YAML canon.
                      </p>
                    </div>
                    <div className="cg-composer-presets">
                      {SAMPLE_PLAYBOOK_TEMPLATES.map((tpl) => (
                        <button
                          key={tpl.id}
                          type="button"
                          data-testid={`studio-template-${tpl.id}`}
                          className="cg-preset-chip"
                          onClick={() => {
                            setCompileId(tpl.id);
                            setCompileText(tpl.rawText);
                          }}
                        >
                          <Sparkles size={12} />
                          <span>Load {tpl.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <form
                    onSubmit={(e) => void handleCompileCanon(e)}
                    className="cg-calibrate-form"
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "14px",
                    }}
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
                          placeholder="e.g. enterprise-retail-2026"
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
                            void handleCompileFileSelect(e.target.files)
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
                                  <X size={12} />
                                </button>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="cg-field-group">
                      <label htmlFor="compile-raw-text">
                        Brand Rules, Approved Claims, Disclaimers &amp; Colour
                        Hex Tokens
                      </label>
                      <textarea
                        id="compile-raw-text"
                        rows={5}
                        value={compileText}
                        onChange={(e) => setCompileText(e.target.value)}
                        placeholder='Paste your company brand rules, approved claims, required disclosures, and hex colour tokens…'
                      />
                    </div>

                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        flexWrap: "wrap",
                        gap: "10px",
                      }}
                    >
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

                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <span className="cg-brand-version">
                          Live Extract: {studioLiveStats.terms} terms · {studioLiveStats.facts} facts · {studioLiveStats.colors} hex · {studioLiveStats.triggers} triggers
                        </span>
                        <button
                          type="submit"
                          data-testid="studio-compile-submit-btn"
                          className="cg-btn cg-btn-primary"
                          disabled={compiling}
                        >
                          <CheckCircle2 size={14} />
                          <span>
                            {compiling
                              ? "Compiling Playbook…"
                              : "Compile & Register Playbook"}
                          </span>
                        </button>
                      </div>
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
                          <X size={13} />
                        </button>
                      </div>
                    ))}
                  </form>

                  {compileResult && (
                    <div
                      className="cg-animate-swap"
                      style={{ marginTop: "14px", display: "flex", flexDirection: "column", gap: "10px" }}
                      data-testid="studio-compile-result"
                    >
                      <div className="cg-success-banner">
                        <Check size={14} />
                        <span>
                          Compiled &amp; Registered Playbook{" "}
                          <strong>{compileResult.canon_id}</strong> v
                          {compileResult.version} ({compileResult.term_count}{" "}
                          terminology rules, {compileResult.fact_count} facts,{" "}
                          {compileResult.color_count} colour tokens).
                        </span>
                        <button
                          type="button"
                          className="cg-btn cg-btn-secondary cg-btn-sm"
                          style={{ marginLeft: "auto" }}
                          onClick={() => {
                            handleSelectGovCanon(compileResult.canon_id);
                            setGovSubTab("rules");
                          }}
                        >
                          <span>View in Rule Catalog →</span>
                        </button>
                      </div>
                      <div className="yaml-diff-box">
                        <div className="yaml-diff-title">
                          Compiled Canon YAML Preview (<code>canons/{compileResult.canon_id}/canon.yaml</code>)
                        </div>
                        <pre className="yaml-diff-pre">{compileResult.yaml_preview}</pre>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : activeTab === "mcp" ? (
            /* ── Tab 3: MCP Brand Rule Server & AI Agent Hub (`canongate-mcp`) ── */
            <div key="tab-mcp" className="cg-gov-studio cg-animate-swap" data-testid="mcp-server-hub">
              <div className="cg-console-hero-bar">
                <div className="cg-console-hero-left">
                  <h1 className="cg-console-title">
                    MCP Brand Rule Server &amp; AI Agent Hub (<code>canongate-mcp</code>)
                  </h1>
                  <span className="cg-role-stage-tag">MCP 2026-07-28</span>
                </div>
                <span className="cg-brand-version">stdio + Streamable HTTP (POST /api/mcp)</span>
              </div>

              <div className="cg-kpi-strip">
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">MCP Protocol Version</span>
                  <strong>2026-07-28</strong>
                  <span>JSON-RPC 2.0 Compliant</span>
                </div>
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">Exposed Governance Tools</span>
                  <strong>8 Tools</strong>
                  <span>Compile, List, Audit, Explain &amp; Fix</span>
                </div>
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">Live Canon Resources</span>
                  <strong>{canons.length}</strong>
                  <code>canongate://canons/&lt;id&gt;</code>
                </div>
                <div className="cg-kpi-cell">
                  <span className="cg-mono-label">HTTP Endpoint</span>
                  <strong>/api/mcp</strong>
                  <span>Streamable HTTP + Local Engine</span>
                </div>
              </div>

              <div className="cg-gov-two-col">
                {/* Left Card: How Users & AI Agents Supply/Get Brand Rules via MCP */}
                <div className="cg-gov-card">
                  <div className="cg-gov-card-header">
                    <div>
                      <h3>1. Connect Your AI Agent &amp; Push Brand Rules via MCP</h3>
                      <p>
                        Give Claude Desktop, Cursor, Windsurf, or custom AI agents direct access to your company brand rules·or push new brand rules directly via the <code>compile_canon</code> MCP tool below.
                      </p>
                    </div>
                  </div>

                  <div className="cg-mcp-code-card">
                    <div className="cg-mcp-card-title">
                      <span>Claude Desktop / Cursor Config (<code>claude_desktop_config.json</code>)</span>
                      <button
                        type="button"
                        className="cg-btn cg-btn-secondary cg-btn-sm"
                        onClick={() =>
                          handleCopyText(
                            "stdio",
                            JSON.stringify(
                              {
                                mcpServers: {
                                  canongate: {
                                    command: "uv",
                                    args: ["run", "canongate-mcp"],
                                    env: {
                                      CANONGATE_HTTP_ENDPOINT: "http://localhost:8000/api/mcp",
                                    },
                                  },
                                },
                              },
                              null,
                              2,
                            ),
                          )
                        }
                      >
                        {mcpCopiedKey === "stdio" ? <Check size={12} /> : <Copy size={12} />}
                        <span>{mcpCopiedKey === "stdio" ? "Copied" : "Copy Config"}</span>
                      </button>
                    </div>
                    <pre className="cg-mcp-pre">{`{
  "mcpServers": {
    "canongate": {
      "command": "uv",
      "args": ["run", "canongate-mcp"],
      "env": {
        "CANONGATE_HTTP_ENDPOINT": "http://localhost:8000/api/mcp"
      }
    }
  }
}`}</pre>
                  </div>

                  {/* Direct MCP Brand Rule Compiler Form */}
                  <div
                    style={{
                      borderTop: "1px solid var(--border)",
                      paddingTop: "12px",
                      display: "flex",
                      flexDirection: "column",
                      gap: "10px",
                    }}
                  >
                    <h4 style={{ margin: 0, fontSize: "14px" }}>
                      Push Brand Rules Directly via MCP <code>compile_canon</code> Tool
                    </h4>
                    <div className="cg-field-group">
                      <label htmlFor="mcp-canon-name">Playbook ID to Register via MCP</label>
                      <input
                        id="mcp-canon-name"
                        type="text"
                        value={mcpCanonName}
                        onChange={(e) => setMcpCanonName(e.target.value)}
                        placeholder="e.g. fintech-mcp-playbook"
                      />
                    </div>
                    <div className="cg-field-group">
                      <label htmlFor="mcp-raw-guidelines">
                        Brand Rules, Approved Claims &amp; Hex Tokens Payload
                      </label>
                      <textarea
                        id="mcp-raw-guidelines"
                        rows={4}
                        value={mcpRawGuidelines}
                        onChange={(e) => setMcpRawGuidelines(e.target.value)}
                      />
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                      <span style={{ fontSize: "12px", color: "var(--muted)" }}>
                        Calls <code>POST /api/mcp</code> → <code>tools/call (compile_canon)</code>
                      </span>
                      <button
                        type="button"
                        data-testid="mcp-compile-canon-btn"
                        className="cg-btn cg-btn-primary cg-btn-sm"
                        disabled={mcpRunning || !mcpRawGuidelines.trim()}
                        onClick={() =>
                          void handleRunMcpTool("compile_canon", {
                            canon_id: mcpCanonName.trim() || "mcp-custom-playbook",
                            canon_name: mcpCanonName.trim() || "mcp-custom-playbook",
                            raw_text: mcpRawGuidelines,
                            persist: true,
                          })
                        }
                      >
                        <Cpu size={13} />
                        <span>
                          {mcpRunning ? "Executing MCP RPC…" : "Compile Brand Rules via MCP"}
                        </span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Right Card: Live MCP Tool & Resource Playground */}
                <div className="cg-gov-card">
                  <div className="cg-gov-card-header">
                    <div>
                      <h3>2. Live MCP JSON-RPC 2.0 Tool &amp; Resource Tester</h3>
                      <p>
                        Click any MCP tool or <code>canongate://canons/&lt;id&gt;</code> resource URI below to execute a live JSON-RPC 2.0 request and inspect the exact payload returned to AI agents.
                      </p>
                    </div>
                  </div>

                  <div>
                    <span className="cg-mono-label" style={{ marginBottom: "6px" }}>
                      Execute MCP Governance Tools (<code>tools/call</code>):
                    </span>
                    <div className="cg-composer-presets">
                      <button
                        type="button"
                        data-testid="mcp-tool-list_canons"
                        className={`cg-preset-chip ${mcpSelectedTool === "list_canons" ? "active" : ""}`}
                        onClick={() => void handleRunMcpTool("list_canons", {})}
                      >
                        <code>list_canons</code>
                      </button>
                      <button
                        type="button"
                        data-testid="mcp-tool-get_canon_rules"
                        className={`cg-preset-chip ${mcpSelectedTool === "get_canon_rules" ? "active" : ""}`}
                        onClick={() =>
                          void handleRunMcpTool("get_canon_rules", {
                            canon_id: canons[0]?.id || "indian-digital-lending",
                          })
                        }
                      >
                        <code>get_canon_rules</code>
                      </button>
                      <button
                        type="button"
                        data-testid="mcp-tool-submit_batch"
                        className={`cg-preset-chip ${mcpSelectedTool === "submit_batch" ? "active" : ""}`}
                        onClick={() =>
                          void handleRunMcpTool("submit_batch", {
                            title: "MCP Agent Loan Ad Audit",
                            canon_id: "indian-digital-lending",
                            raw_content:
                              "Instant personal loan with guaranteed approval and 0% processing fee on loans under Rs 1,00,000!",
                          })
                        }
                      >
                        <code>submit_batch</code>
                      </button>
                      <button
                        type="button"
                        data-testid="mcp-tool-get_findings"
                        className={`cg-preset-chip ${mcpSelectedTool === "get_findings" ? "active" : ""}`}
                        onClick={() =>
                          void handleRunMcpTool("get_findings", {
                            submission_id: submissions[0]?.id ?? 1,
                          })
                        }
                      >
                        <code>get_findings</code>
                      </button>
                      <button
                        type="button"
                        data-testid="mcp-tool-explain_finding"
                        className={`cg-preset-chip ${mcpSelectedTool === "explain_finding" ? "active" : ""}`}
                        onClick={() =>
                          void handleRunMcpTool("explain_finding", {
                            finding_id: "1",
                          })
                        }
                      >
                        <code>explain_finding</code>
                      </button>
                      <button
                        type="button"
                        data-testid="mcp-tool-propose_fix"
                        className={`cg-preset-chip ${mcpSelectedTool === "propose_fix" ? "active" : ""}`}
                        onClick={() =>
                          void handleRunMcpTool("propose_fix", {
                            finding_id: "1",
                          })
                        }
                      >
                        <code>propose_fix</code>
                      </button>
                    </div>
                  </div>

                  <div>
                    <span className="cg-mono-label" style={{ marginBottom: "6px" }}>
                      Read MCP Brand Rule Resources (<code>resources/read</code>):
                    </span>
                    <div className="cg-composer-presets">
                      {canons.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          className="cg-preset-chip"
                          onClick={() =>
                            void handleReadMcpResource(`canongate://canons/${c.id}`)
                          }
                        >
                          <code>canongate://canons/{c.id}</code>
                        </button>
                      ))}
                    </div>
                  </div>

                  {mcpRequestJson ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                      <div className="cg-mcp-code-card">
                        <div className="cg-mcp-card-title">
                          <span>JSON-RPC 2.0 Request (<code>POST /api/mcp</code>)</span>
                          <code>MCP-Protocol-Version: 2026-07-28</code>
                        </div>
                        <pre className="cg-mcp-pre" style={{ maxHeight: "120px", overflowY: "auto" }}>
                          {mcpRequestJson}
                        </pre>
                      </div>
                      <div className="cg-mcp-code-card" data-testid="mcp-rpc-response-box">
                        <div className="cg-mcp-card-title">
                          <span>JSON-RPC 2.0 Response</span>
                          <span className="cg-text-emerald">200 OK</span>
                        </div>
                        <pre className="cg-mcp-pre" style={{ maxHeight: "220px", overflowY: "auto" }}>
                          {mcpResponseJson}
                        </pre>
                      </div>
                    </div>
                  ) : (
                    <div className="cg-clean-note">
                      Click any MCP tool chip above (such as <code>list_canons</code>, <code>get_canon_rules</code>, or <code>submit_batch</code>) or click <strong>Compile Brand Rules via MCP</strong> on the left to inspect live JSON-RPC 2.0 payloads.
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            /* ── Tab 4: Pre-Publish Webhook Gate Studio (`POST /api/gate/check`) ── */
            <div key="tab-gate" className="cg-gov-studio cg-animate-swap">
              <div className="cg-console-hero-bar">
                <div className="cg-console-hero-left">
                  <h1 className="cg-console-title">
                    Synchronous Pre-Publish Webhook Gate (
                    <code>POST /api/gate/check</code>)
                  </h1>
                </div>
                <span className="cg-brand-version">CMS &amp; CI/CD Gate</span>
              </div>

              <div className="cg-gov-two-col">
                <form onSubmit={(e) => void handleRunWebhookGate(e)} className="cg-gov-card">
                  <div className="cg-gov-card-header">
                    <div>
                      <h3>Simulate CMS / CI-CD Publish Webhook</h3>
                      <p>
                        Test synchronous pre-publish gating for Shopify,
                        Webflow, or Generic JSON payloads with conformal risk
                        control.
                      </p>
                    </div>
                    <div className="cg-composer-presets">
                      {SAMPLE_CAMPAIGN_PRESETS.map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          className="cg-preset-chip"
                          onClick={() => {
                            setGateCanonId(p.canonId);
                            setGateTitle(p.title);
                            setGateContent(p.content);
                          }}
                        >
                          <Sparkles size={12} />
                          <span>{p.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="cg-field-row-2">
                    <div className="cg-field-group">
                      <label htmlFor="gate-canon-select">Playbook ID</label>
                      <select
                        id="gate-canon-select"
                        value={gateCanonId}
                        onChange={(e) => setGateCanonId(e.target.value)}
                      >
                        {canons.map((c) => (
                          <option key={c.id} value={c.id}>
                            {formatCanonName(c.id)} ({c.id})
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="cg-field-group">
                      <label htmlFor="gate-adapter-select">CMS Adapter</label>
                      <select
                        id="gate-adapter-select"
                        value={gateAdapter}
                        onChange={(e) =>
                          setGateAdapter(
                            e.target.value as
                              | "generic"
                              | "shopify"
                              | "webflow",
                          )
                        }
                      >
                        <option value="generic">Generic Content Payload</option>
                        <option value="shopify">
                          Shopify Product / Page Webhook
                        </option>
                        <option value="webflow">
                          Webflow CMS Item Publish
                        </option>
                      </select>
                    </div>
                  </div>

                  <div className="cg-field-row-2">
                    <div className="cg-field-group">
                      <label htmlFor="gate-title-input">Asset Title</label>
                      <input
                        id="gate-title-input"
                        type="text"
                        value={gateTitle}
                        onChange={(e) => setGateTitle(e.target.value)}
                        placeholder="Enter asset title…"
                      />
                    </div>

                    <div className="cg-field-group">
                      <label htmlFor="gate-alpha-select">
                        Conformal Risk Level (α)
                      </label>
                      <select
                        id="gate-alpha-select"
                        value={gateAlpha}
                        onChange={(e) => setGateAlpha(Number(e.target.value))}
                      >
                        <option value={0.04}>
                          Strict (α = 0.04 · BFSI/Legal)
                        </option>
                        <option value={0.1}>
                          Balanced (α = 0.10 · Standard)
                        </option>
                        <option value={0.2}>
                          Permissive (α = 0.20 · Draft)
                        </option>
                      </select>
                    </div>
                  </div>

                  <div className="cg-field-group">
                    <label htmlFor="gate-raw-textarea">
                      Raw Campaign / CMS Payload Content
                    </label>
                    <textarea
                      id="gate-raw-textarea"
                      rows={5}
                      value={gateContent}
                      onChange={(e) => setGateContent(e.target.value)}
                      placeholder="Paste your campaign copy, HTML, or CMS payload here…"
                    />
                  </div>

                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: "10px",
                    }}
                  >
                    <label
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "6px",
                        fontSize: "13px",
                        cursor: "pointer",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={gatePersist}
                        onChange={(e) => setGatePersist(e.target.checked)}
                      />
                      <span>
                        Persist bundle to Campaign Queue for human review
                      </span>
                    </label>

                    <button
                      type="submit"
                      data-testid="dashboard-run-gate-btn"
                      className="cg-btn cg-btn-primary"
                      disabled={gateRunning || !gateContent.trim()}
                    >
                      <span>
                        {gateRunning ? "Evaluating Gate…" : "Run Gate Check"}
                      </span>
                      <ArrowRight size={14} className="cg-arrow-shift" />
                    </button>
                  </div>
                </form>

                {/* Gate Response Inspector */}
                <div className="cg-gov-card">
                  <div className="cg-gov-card-header">
                    <div>
                      <h3>Gate Verdict &amp; Calibrated Findings</h3>
                      <p>
                        Returns <code>allow</code>, <code>needs_review</code>,
                        or <code>block</code> in &lt;25 ms for deterministic
                        checks.
                      </p>
                    </div>

                    {gateResult && (
                      <span
                        className={`status-badge ${
                          gateResult.decision === "block"
                            ? "status-blocked"
                            : gateResult.decision === "needs_review"
                              ? "status-changes_requested"
                              : "status-approved"
                        }`}
                      >
                        {gateResult.decision.toUpperCase()} ·{" "}
                        {gateResult.latency_ms.toFixed(1)} ms
                      </span>
                    )}
                  </div>

                  {!gateResult ? (
                    <div className="cg-clean-note">
                      Click <strong>Run Gate Check</strong> on the left to execute <code>POST /api/gate/check</code> and inspect the calibrated decision payload.
                    </div>
                  ) : (
                    <>
                      <div className="cg-kpi-strip">
                        <div className="cg-kpi-cell">
                          <span className="cg-mono-label">Decision</span>
                          <strong>{gateResult.decision.toUpperCase()}</strong>
                          <span>Adapter: {gateResult.adapter_used}</span>
                        </div>
                        <div className="cg-kpi-cell">
                          <span className="cg-mono-label">Blockers</span>
                          <strong>{gateResult.blocker_count}</strong>
                          <span>Warnings: {gateResult.warning_count}</span>
                        </div>
                        <div className="cg-kpi-cell">
                          <span className="cg-mono-label">Threshold</span>
                          <strong>
                            {(gateResult.conformal_threshold * 100).toFixed(0)}
                          </strong>
                          <span>α = {gateResult.alpha.toFixed(2)}</span>
                        </div>
                      </div>

                      {gateResult.submission_id && (
                        <div className="cg-success-banner">
                          <Check size={14} />
                          <span>
                            Persisted as Bundle #{gateResult.submission_id}.{" "}
                            <button
                              type="button"
                              className="cg-link-btn"
                              onClick={() =>
                                navigate(
                                  `/submissions/${gateResult.submission_id}`,
                                )
                              }
                            >
                              Open in Review Studio →
                            </button>
                          </span>
                        </div>
                      )}

                      {gateResult.findings.length === 0 ? (
                        <div className="cg-clean-note">
                          Zero violations above the conformal threshold.
                          Content is cleared for publication.
                        </div>
                      ) : (
                        <div className="cg-finding-list">
                          {gateResult.findings.map((f) => (
                            <div key={f.finding_id} className="cg-finding-item">
                              <div className="cg-finding-item-top">
                                <span
                                  className={`cg-sev-badge ${
                                    f.verdict === "BLOCKER"
                                      ? "sev-blocker"
                                      : "sev-warning"
                                  }`}
                                >
                                  {f.verdict} · {f.severity}
                                </span>
                                <code>{f.check_id}</code>
                                <span className="cg-tier-tag">
                                  Tier: {f.tier}
                                </span>
                              </div>
                              <p className="cg-finding-msg">{f.message}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
