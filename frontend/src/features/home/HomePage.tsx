import { useState, useEffect, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Copy,
  Cpu,
  FileCheck2,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  Wand2,
} from "lucide-react";
import { useAuth } from "../auth/context";
import {
  listCanons,
  runGateCheck,
  createSubmission,
  getApiBase,
  type CanonSummary,
  type GateCheckResponsePayload,
} from "../../api/client";

/* ──────────────────────────────────────────────────────────────────────────
 * Real Pre-Flight Trial Presets (Evaluated Live by POST /api/gate/check)
 * ────────────────────────────────────────────────────────────────────────── */

interface TrialPreset {
  id: string;
  canonId: string;
  sectorTag: string;
  title: string;
  assetName: string;
  draftCopy: string;
  repairedCopy: string;
  banner: {
    headline: string;
    subline: string;
    disclaimerDraft: string;
    disclaimerFixed: string;
    bgHex: string;
    accentDraftHex: string;
    accentCanonHex: string;
    fgDraftHex: string;
    fgDefaultFixedHex: string;
    kfsBadge: string;
  };
  swatches: Array<{
    label: string;
    hex: string;
    bgHex: string;
    ratio: string;
    deltaE: string;
    badge: string;
  }>;
}

const TRIAL_PRESETS: TrialPreset[] = [
  {
    id: "fintech",
    canonId: "indian-digital-lending",
    sectorTag: "RBI 2025 KFS · ASCI BFSI",
    title: "Acme QuickLoan Diwali Festival Campaign",
    assetName: "acme_quickloan_bundle.yaml",
    draftCopy:
      "Celebrate this season with Acme QuickLoan! Get 0% processing fee on loans under Rs 1,00,000 with guaranteed approval and no credit check — cheap personal credit for everyone.\n\nAnnual Percentage Rate (APR) is 14%.\n\ncolor: #777777; background-color: #FFFFFF; — T&C apply.",
    repairedCopy:
      "Celebrate this season with Acme QuickLoan. Get 0% processing fee on loans under Rs 50,000 for first-time borrowers only, subject to credit assessment and streamlined credit verification. Subject to RBI Key Fact Statement (KFS) schedule.\n\ncolor: #767676; background-color: #FFFFFF; — Transparent digital credit with upfront APR.",
    banner: {
      headline: "0% PROCESSING FEE FESTIVAL LOAN",
      subline: "Instant Disbursal · Check KFS Schedule",
      disclaimerDraft:
        "color: #777777 on #FFFFFF (4.48:1 < 4.5:1) · T&C apply.",
      disclaimerFixed:
        "color: #767676 on #FFFFFF (4.54:1 PASS) · Under Rs 50,000 for first-time borrowers only. Subject to RBI Key Fact Statement (KFS) schedule.",
      bgHex: "#FFFFFF",
      accentDraftHex: "#19528A",
      accentCanonHex: "#0D3B66",
      fgDraftHex: "#777777",
      fgDefaultFixedHex: "#767676",
      kfsBadge: "RBI 2025 KFS",
    },
    swatches: [
      {
        label: "Hue-Preserving WCAG AA",
        hex: "#767676",
        bgHex: "#FFFFFF",
        ratio: "4.54:1",
        deltaE: "ΔE₀₀ 0.4",
        badge: "AA PASS",
      },
      {
        label: "High-Contrast WCAG AAA",
        hex: "#595959",
        bgHex: "#FFFFFF",
        ratio: "7.00:1",
        deltaE: "ΔE₀₀ 11.4",
        badge: "AAA PASS",
      },
      {
        label: "Canon Trust Navy Token",
        hex: "#0D3B66",
        bgHex: "#FFFFFF",
        ratio: "11.45:1",
        deltaE: "ΔE₀₀ 0.0",
        badge: "BRAND + AAA",
      },
    ],
  },
  {
    id: "nutra",
    canonId: "indian-d2c-nutra",
    sectorTag: "ASCI Health · CCPA 2022",
    title: "AyurGlow Curcumin Gold Elixir Launch",
    assetName: "ayurglow_nutra_bundle.yaml",
    draftCopy:
      "Experience our miracle cure formula with 2x faster absorption and 100% fat burn results! AyurGlow cures diabetes naturally in 7 days.\n\nFlat 27% discount — MRP inclusive of all taxes. GST and additional charges may apply on discounted price.\n\ncolor: #777777; background-color: #FFFFFF; — Results vary.",
    repairedCopy:
      "Experience our nutritional support formula with 2x faster absorption in an in-vitro ingredient study only when taken with piperine for 8 weeks. Supports active weight management and supports healthy glycemic metabolism.\n\ncolor: #767676; background-color: #FFFFFF; — Results vary.",
    banner: {
      headline: "AYURGLOW CURCUMIN · 2X ABSORPTION",
      subline: "Botanical Wellness · Clinical & In-Vitro Substantiation",
      disclaimerDraft:
        "color: #777777 on #FFFFFF (4.48:1 < 4.5:1) · Flat 27% off + extra GST.",
      disclaimerFixed:
        "color: #767676 on #FFFFFF (4.54:1 PASS) · In-vitro ingredient study only when taken with piperine for 8 weeks.",
      bgHex: "#FFFFFF",
      accentDraftHex: "#3A7D4E",
      accentCanonHex: "#2E6F40",
      fgDraftHex: "#777777",
      fgDefaultFixedHex: "#767676",
      kfsBadge: "ASCI Health",
    },
    swatches: [
      {
        label: "Hue-Preserving WCAG AA",
        hex: "#767676",
        bgHex: "#FFFFFF",
        ratio: "4.54:1",
        deltaE: "ΔE₀₀ 0.4",
        badge: "AA PASS",
      },
      {
        label: "High-Contrast WCAG AAA",
        hex: "#595959",
        bgHex: "#FFFFFF",
        ratio: "7.00:1",
        deltaE: "ΔE₀₀ 11.4",
        badge: "AAA PASS",
      },
      {
        label: "Canon Botanical Sage",
        hex: "#2E6F40",
        bgHex: "#FFFFFF",
        ratio: "6.12:1",
        deltaE: "ΔE₀₀ 0.0",
        badge: "BRAND + AA",
      },
    ],
  },
  {
    id: "enterprise",
    canonId: "acme-corp",
    sectorTag: "Brand Book · WCAG 2.1 AA",
    title: "Acme Cloud Enterprise Launch Landing Page",
    assetName: "acme_launch.yaml",
    draftCopy:
      "Why buy cheap legacy tools when our cutting-edge platform helps users modernize? Acme Corp has over 500 employees serving global enterprises.\n\ncolor: #777777; background-color: #FFFFFF; — Enterprise SLA footnote text.",
    repairedCopy:
      "Purchase affordable tools when our innovative platform helps customers modernize. Acme Corp has over 500 employees as of Q3 2025.\n\ncolor: #767676; background-color: #FFFFFF; — Enterprise SLA footnote text.",
    banner: {
      headline: "ACME CLOUD · ENTERPRISE PLATFORM",
      subline: "Over 500 Employees (as of Q3 2025)",
      disclaimerDraft:
        "color: #777777 on #FFFFFF (4.48:1 < 4.5:1) · Enterprise SLA footnote.",
      disclaimerFixed:
        "color: #767676 on #FFFFFF (4.54:1 PASS) · Verified against acme-corp v1.0.",
      bgHex: "#FFFFFF",
      accentDraftHex: "#2B6CB0",
      accentCanonHex: "#1A73E8",
      fgDraftHex: "#777777",
      fgDefaultFixedHex: "#767676",
      kfsBadge: "Acme Brand v1.0",
    },
    swatches: [
      {
        label: "Hue-Preserving WCAG AA",
        hex: "#767676",
        bgHex: "#FFFFFF",
        ratio: "4.54:1",
        deltaE: "ΔE₀₀ 0.4",
        badge: "AA PASS",
      },
      {
        label: "High-Contrast WCAG AAA",
        hex: "#595959",
        bgHex: "#FFFFFF",
        ratio: "7.00:1",
        deltaE: "ΔE₀₀ 11.4",
        badge: "AAA PASS",
      },
      {
        label: "Canon Dark Gray Token",
        hex: "#202124",
        bgHex: "#FFFFFF",
        ratio: "16.10:1",
        deltaE: "ΔE₀₀ 0.0",
        badge: "BRAND + AAA",
      },
    ],
  },
];

/* ──────────────────────────────────────────────────────────────────────────
 * Authentic Repository Canon YAML Files (`canons/*.yaml`)
 * ────────────────────────────────────────────────────────────────────────── */

const PLAYBOOK_YAML_SAMPLES: Record<
  string,
  {
    title: string;
    authority: string;
    rulesCount: number;
    hashPrefix: string;
    yaml: string;
  }
> = {
  "indian-digital-lending.yaml": {
    title: "Indian Digital Lending (RBI 2025 KFS & ASCI BFSI Norms)",
    authority: "RBI Digital Lending Directions (May 2025) & KFS Mandate",
    rulesCount: 11,
    hashPrefix: "1cd1ac13e83f1b00",
    yaml: `# CanonGate Starter Canon — Indian Digital Lending (RBI 2025 KFS & ASCI BFSI Norms)
id: indian-digital-lending
version: "1.0"
require_image_alt: true

terminology:
  - id: term-guaranteed-approval
    pattern_text: guaranteed approval
    preferred: subject to credit assessment
    severity: 85
    note: "RBI Digital Lending Directions: never promise guaranteed loan approval without underwriting."

  - id: term-no-credit-check
    pattern_text: no credit check
    preferred: streamlined credit verification
    severity: 80
    note: "RBI KYC / Bureau mandate: all regulated NBFC loans require bureau reporting."

  - id: term-free-money
    pattern_text: free money
    preferred: credit facility
    severity: 75
    note: "ASCI BFSI code: do not portray credit or loans as free money."

  - id: term-cheap
    pattern_text: cheap
    preferred: competitive-rate
    severity: 40
    note: "Brand voice: use 'competitive-rate' rather than 'cheap'."

palette:
  - id: color-rbi-trust-navy
    hex: "#0D3B66"
    name: "Trust Navy"
    max_delta_e: 3.0
  - id: color-upi-emerald
    hex: "#1B8A5A"
    name: "Verified Emerald"
    max_delta_e: 3.0

facts:
  - id: fact-kfs-processing-fee
    text: "0% processing fee on loans"
    conditions: ["under Rs 50,000", "for first-time borrowers only"]
    valid_until: "2026-09-30"
    subject_product: "processing fee"
    metric_value: "0%"
    comparison_operator: "<="
    kfs_acceptance_validity_days: 3

  - id: fact-kfs-apr-ceiling
    text: "Annual Percentage Rate (APR) is 18%"
    conditions: ["up to Rs 2,00,000"]
    valid_until: "2026-12-31"
    subject_product: "Annual Percentage Rate (APR)"
    metric_value: "18%"
    comparison_operator: "<="

trigger_obligations:
  - id: trig-kfs-schedule
    trigger_pattern: "0%\\\\s+processing\\\\s+fee"
    required_disclaimer_id: rbi-kfs-mandatory
    required_disclaimer_text: "Subject to RBI Key Fact Statement (KFS) schedule"
    same_language: true
    severity: 75`,
  },
  "indian-d2c-nutra.yaml": {
    title: "Indian D2C Nutraceuticals (ASCI Health & CCPA 2022)",
    authority: "ASCI F&B/Health Guidelines & CCPA 2022 Clause 11",
    rulesCount: 7,
    hashPrefix: "eb05d1784ad09bab",
    yaml: `# CanonGate Starter Canon — Indian D2C Nutraceuticals (ASCI Health & CCPA 2022 Guidelines)
id: indian-d2c-nutra
version: "1.0"
require_image_alt: true

terminology:
  - id: term-miracle-cure
    pattern_text: miracle cure
    preferred: nutritional support
    severity: 90
    note: "Drugs and Magic Remedies Act / ASCI: never claim a miracle cure."

  - id: term-cures-diabetes
    pattern_text: cures diabetes
    preferred: supports healthy glycemic metabolism
    severity: 95
    note: "ASCI Health Guidelines: nutraceuticals cannot claim to cure chronic disease."

  - id: term-100pct-fat-burn
    pattern_text: 100% fat burn
    preferred: supports active weight management
    severity: 80
    note: "CCPA 2022: absolute 100% physiological efficacy claims require clinical trial proof."

palette:
  - id: color-botanical-sage
    hex: "#2E6F40"
    name: "Botanical Sage"
    max_delta_e: 3.0
  - id: color-turmeric-gold
    hex: "#D99B26"
    name: "Turmeric Gold"
    max_delta_e: 3.5

facts:
  - id: fact-curcumin-absorption
    text: "2x faster absorption"
    conditions:
      - "in-vitro ingredient study only"
      - "when taken with piperine for 8 weeks"
    valid_until: "2026-12-31"
    substantiation_level: "ingredient_in_vitro"

  - id: fact-protein-per-serving
    text: "24g plant protein per scoop"
    conditions: ["per 35g serving size"]
    valid_until: "2026-12-31"
    substantiation_level: "finished_product_clinical"`,
  },
  "acme-corp.yaml": {
    title: "Acme Corp Enterprise Brand Rules",
    authority: "Brand Voice, Palette ΔE₀₀ & Fact Substantiation",
    rulesCount: 9,
    hashPrefix: "5be7400ed3c8470e",
    yaml: `# CanonGate Demo Canon — "Acme Corp" brand rules
id: acme-corp
version: "1.0"

terminology:
  - id: term-cheap
    pattern_text: cheap
    preferred: affordable
    severity: 60
    note: "Brand voice: never use 'cheap' — it implies low quality."
  - id: term-buy
    pattern_text: buy
    preferred: purchase
    severity: 40
    note: "Formal tone: use 'purchase' instead of 'buy'."
  - id: term-users
    pattern_text: users
    preferred: customers
    severity: 50
    note: "We serve customers, not users."
  - id: term-cutting-edge
    pattern_text: cutting-edge
    preferred: innovative
    severity: 30
    note: "Avoid cliché buzzwords."

palette:
  - id: color-primary
    hex: "#1A73E8"
    name: Primary Blue
    max_delta_e: 3.0
  - id: color-accent
    hex: "#EA4335"
    name: Accent Red
    max_delta_e: 5.0
  - id: color-dark
    hex: "#202124"
    name: Dark Gray
    max_delta_e: 2.0

facts:
  - id: fact-founding
    text: "Acme Corp was founded in 2020."
    conditions: []
  - id: fact-employees
    text: "Acme Corp has over 500 employees."
    conditions: ["as of Q3 2025"]`,
  },
};

/* ──────────────────────────────────────────────────────────────────────────
 * Authentic CLI, MCP (2026-07-28), and Webhook Gate Snippets
 * ────────────────────────────────────────────────────────────────────────── */

const DEV_INTEGRATION_TABS: Record<
  string,
  {
    label: string;
    subtitle: string;
    code: string;
  }
> = {
  cli: {
    label: "CLI Pre-Publish Gate",
    subtitle:
      "Run `canongate gate` locally or in CI with split-conformal calibration (`canongate/cli.py`).",
    code: `# Audit fixtures/golden_bundle/acme_launch.yaml against acme-corp (alpha = 0.10 -> lambda = 0.34)
$ uv run canongate gate \\
    --canon acme-corp \\
    --paths fixtures/golden_bundle/acme_launch.yaml \\
    --alpha 0.10

[BLOCK] CanonGate Pre-Publish Gate — Canon 'acme-corp' v1.0 (alpha=0.10, lambda=0.34)
  • Assets Audited : acme_launch.yaml
  • Findings       : 5 total (3 Blockers, 2 Warnings)
    - [BLOCKER · S=60] terminology.banned (term-cheap): Use "affordable" instead of "cheap"
    - [WARNING · S=30] terminology.banned (term-cutting-edge): Use "innovative" instead of "cutting-edge"
    - [WARNING · S=40] terminology.banned (term-buy): Use "purchase" instead of "Buy"
    - [BLOCKER · S=50] terminology.banned (term-users): Use "customers" instead of "users"
    - [BLOCKER · S=80] claim.slot_nli (fact-founding): Factual contradiction ('2018' vs '2020')

# Verify an exported Ed25519 + RFC 9162 Merkle governance certificate offline
$ uv run canongate verify canongate_certificate_sub_1.json`,
  },
  mcp: {
    label: "MCP Server (2026-07-28)",
    subtitle:
      "Exposes 6 read-only tools (`list_canons`, `submit_batch`, `job_status`, `get_findings`, `explain_finding`, `propose_fix`) over stdio or POST /api/mcp.",
    code: `// JSON-RPC 2.0 -> POST /api/mcp (or stdio via \`uv run canongate-mcp\`)
// Note: approve / override / publish are intentionally omitted (OWASP LLM06 human-in-the-loop gate)
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "method": "tools/call",
  "params": {
    "name": "submit_batch",
    "arguments": {
      "canon_id": "indian-digital-lending",
      "paths": ["fixtures/golden_bundle/acme_launch.yaml"],
      "alpha": 0.10,
      "wait_ms": 1500
    }
  }
}

// Follow-up surgical fix preview for a specific finding row_id:
// { "method": "tools/call", "params": { "name": "propose_fix", "arguments": { "submission_id": 1, "row_id": 1 } } }`,
  },
  webhook: {
    label: "Shopify & Webflow Gate",
    subtitle:
      "Synchronous `POST /api/gate/check` endpoint with built-in generic, Shopify, and Webflow payload adapters.",
    code: `POST /api/gate/check HTTP/1.1
Content-Type: application/json

{
  "adapter": "webflow",
  "canon_id": "indian-digital-lending",
  "alpha": 0.10,
  "persist": false,
  "title": "Diwali Instant Loan Landing Page",
  "raw_content": "Get 0% processing fee on loans under Rs 50,000 for first-time borrowers only. Subject to RBI Key Fact Statement (KFS) schedule."
}

// Response: HTTP 200 OK
// { "decision": "allow", "conformal_threshold": 0.34, "blocker_count": 0, "warning_count": 0 }`,
  },
};

const WORKFLOW_STAGE_SPECS = [
  {
    stage: "STAGE 01",
    roleKey: "creator",
    username: "creative_lead",
    roleLabel: "Creator (@creative_lead)",
    statusTag: "draft → in_review",
    title: "Pre-Flight Triage & Surgical Remediation",
    summary:
      "Uploads campaign copy, documents, and banners, runs Tier 1–2 checks, applies ≤35% surgical rewrites or WCAG contrast swatches, and documents context on Warning overrides.",
  },
  {
    stage: "STAGE 02",
    roleKey: "reviewer",
    username: "brand_manager",
    roleLabel: "Brand Manager (@brand_manager)",
    statusTag: "in_review → approved | changes_requested",
    title: "Brand Review & Playbook Calibration",
    summary:
      "Reviews inline ProseMirror diffs and warning overrides, monitors Krippendorff's α rule friction, and calibrates rule thresholds or generates Canon v1.1 PRs.",
  },
  {
    stage: "STAGE 03",
    roleKey: "admin",
    username: "legal_counsel",
    roleLabel: "Legal Reviewer (@legal_counsel)",
    statusTag: "approved → published",
    title: "Statutory Sign-Off & Cryptographic Certificate",
    summary:
      "Audits high-risk SlotDiff and SMT algebraic claims in a dedicated Claim-Only view, executes final release sign-off, and seals the RFC 9162 Merkle + Ed25519 certificate.",
  },
];

export function HomePage() {
  const { isAuthenticated, username, role, login } = useAuth();
  const navigate = useNavigate();

  // Live Canon & Gate Check state
  const [canons, setCanons] = useState<CanonSummary[]>([]);
  const [presetId, setPresetId] = useState<string>("fintech");
  const [selectedCanonId, setSelectedCanonId] = useState<string>(
    "indian-digital-lending",
  );
  const [draftTitle, setDraftTitle] = useState<string>(
    TRIAL_PRESETS[0].title,
  );
  const [draftText, setDraftText] = useState<string>(
    TRIAL_PRESETS[0].draftCopy,
  );
  const [isRepaired, setIsRepaired] = useState<boolean>(false);
  const [conformalAlpha, setConformalAlpha] = useState<number>(0.1);
  const [selectedSwatchHex, setSelectedSwatchHex] = useState<string | null>(
    null,
  );

  // Live API response from POST /api/gate/check
  const [gateResult, setGateResult] =
    useState<GateCheckResponsePayload | null>(null);
  const [selectedFindingIdx, setSelectedFindingIdx] = useState<number>(0);
  const [checkingGate, setCheckingGate] = useState<boolean>(false);
  const [launchingTrial, setLaunchingTrial] = useState<boolean>(false);
  const [launchingRole, setLaunchingRole] = useState<string | null>(null);

  // Code explorer tabs
  const [activePlaybookKey, setActivePlaybookKey] = useState<string>(
    "indian-digital-lending.yaml",
  );
  const [activeDevTab, setActiveDevTab] = useState<string>("cli");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const currentPreset =
    TRIAL_PRESETS.find((p) => p.id === presetId) ?? TRIAL_PRESETS[0];

  // Fetch real canons on mount
  useEffect(() => {
    let active = true;
    listCanons()
      .then((list) => {
        if (active && list.length > 0) {
          setCanons(list);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  // Run real `POST /api/gate/check` (persist: false) whenever copy, canon, or alpha changes
  const executeLiveGateCheck = useCallback(
    async (contentToAudit: string, canonToUse: string, alphaToUse: number) => {
      if (!contentToAudit.trim()) return;
      setCheckingGate(true);
      try {
        const res = await runGateCheck({
          canon_id: canonToUse,
          title: draftTitle || "Interactive Pre-Publish Check",
          raw_content: contentToAudit,
          alpha: alphaToUse,
          persist: false,
        });
        setGateResult(res);
        setSelectedFindingIdx(0);
      } catch {
        // Fallback handled inside client.ts
      } finally {
        setCheckingGate(false);
      }
    },
    [draftTitle],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void executeLiveGateCheck(draftText, selectedCanonId, conformalAlpha);
    }, 180);
    return () => window.clearTimeout(timer);
  }, [draftText, selectedCanonId, conformalAlpha, executeLiveGateCheck]);

  function handleSelectPreset(nextPreset: TrialPreset) {
    setPresetId(nextPreset.id);
    setSelectedCanonId(nextPreset.canonId);
    setDraftTitle(nextPreset.title);
    setDraftText(nextPreset.draftCopy);
    setIsRepaired(false);
    setSelectedSwatchHex(null);
    setSelectedFindingIdx(0);
    const matchingYamlKey = `${nextPreset.canonId}.yaml`;
    if (PLAYBOOK_YAML_SAMPLES[matchingYamlKey]) {
      setActivePlaybookKey(matchingYamlKey);
    }
  }

  function handleToggleSurgicalRepair() {
    if (!isRepaired) {
      setDraftText(currentPreset.repairedCopy);
      setIsRepaired(true);
      setSelectedSwatchHex("#767676");
    } else {
      setDraftText(currentPreset.draftCopy);
      setIsRepaired(false);
      setSelectedSwatchHex(null);
    }
  }

  function handleApplySwatchToCopy(hex: string) {
    setSelectedSwatchHex(hex);
    setDraftText((prev) =>
      prev.replace(/color:\s*#[0-9a-fA-F]{6}/i, `color: ${hex}`),
    );
  }

  function handleCopyText(id: string, text: string) {
    void navigator.clipboard?.writeText(text);
    setCopiedId(id);
    window.setTimeout(() => {
      setCopiedId((prev) => (prev === id ? null : prev));
    }, 1600);
  }

  async function handleQuickPersonaLaunch(targetUsername: string) {
    setLaunchingRole(targetUsername);
    try {
      await login(targetUsername, "demoPassword123!");
      navigate("/dashboard");
    } catch {
      navigate("/login");
    } finally {
      setLaunchingRole(null);
    }
  }

  // Launch a real Guided Trial Run inside the Review Studio (`/submissions/:id`),
  // tagged in localStorage so the user can test all 4 stages and then 1-click reset to an empty workspace.
  async function handleStartGuidedTrialRun() {
    setLaunchingTrial(true);
    try {
      if (!isAuthenticated) {
        await login("creative_lead", "demoPassword123!");
      }
      const trialTitle = `[Trial Run] ${draftTitle.replace(/^\[Trial Run\]\s*/i, "")}`;
      const contentForTrial = isRepaired
        ? currentPreset.draftCopy
        : draftText.trim() || currentPreset.draftCopy;
      const sub = await createSubmission(
        trialTitle,
        contentForTrial,
        selectedCanonId,
        [],
        [],
      );
      const apiBase = getApiBase();
      await fetch(`${apiBase}/submissions/${sub.id}/scan?alpha=${conformalAlpha}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("cg_token") ?? ""}`,
        },
      }).catch(() => {});

      const existingIds: number[] = JSON.parse(
        localStorage.getItem("cg_trial_submission_ids") || "[]",
      );
      if (!existingIds.includes(sub.id)) {
        existingIds.push(sub.id);
      }
      localStorage.setItem(
        "cg_trial_submission_ids",
        JSON.stringify(existingIds),
      );
      localStorage.setItem("cg_trial_active", "true");
      navigate(`/submissions/${sub.id}`);
    } catch {
      navigate("/login");
    } finally {
      setLaunchingTrial(false);
    }
  }

  const findings = gateResult?.findings ?? [];
  const activeFinding =
    findings[Math.min(selectedFindingIdx, Math.max(0, findings.length - 1))] ??
    null;
  const blockerCount = gateResult?.blocker_count ?? 0;
  const warningCount = gateResult?.warning_count ?? 0;
  const conformalLambda =
    gateResult?.conformal_threshold ??
    (conformalAlpha <= 0.05 ? 0.42 : conformalAlpha <= 0.1 ? 0.34 : 0.22);

  const matchedCanonMeta = canons.find((c) => c.id === selectedCanonId);
  const activeBannerFgHex =
    selectedSwatchHex ??
    (isRepaired || draftText.includes("#767676")
      ? currentPreset.banner.fgDefaultFixedHex
      : currentPreset.banner.fgDraftHex);

  return (
    <div className="cg-home">
      {/* ── Top Product Navigation Bar ── */}
      <header className="cg-topbar">
        <div className="cg-topbar-inner">
          <div className="cg-topbar-left">
            <Link to="/" className="cg-brand">
              <span className="cg-brand-mark" aria-hidden="true">
                <ShieldCheck size={17} strokeWidth={2.2} />
              </span>
              <span className="cg-brand-name">CanonGate</span>
              <span className="cg-brand-version">v1.0 · Live Engine</span>
            </Link>

            <nav className="cg-topnav" aria-label="Product sections">
              <a href="#workbench">Live Pre-Publish Gate</a>
              <a href="#workflow">3-Role Workflow</a>
              <a href="#developers">Canons, CLI &amp; MCP</a>
            </nav>
          </div>

          <div className="cg-topbar-right">
            {isAuthenticated ? (
              <>
                <span className="cg-session-pill">
                  <span className="cg-status-dot cg-dot-live" />@{username} ·{" "}
                  <strong>{role}</strong>
                </span>
                <Link to="/dashboard" className="cg-btn cg-btn-primary">
                  <span>Open Workspace</span>
                  <ArrowRight size={15} className="cg-arrow-shift" />
                </Link>
              </>
            ) : (
              <>
                <div
                  className="cg-persona-quickbar"
                  aria-label="Instant Workspace Role Access"
                >
                  <span className="cg-persona-quickbar-label">
                    Enter Studio as:
                  </span>
                  <button
                    type="button"
                    className="cg-persona-chip"
                    disabled={launchingRole !== null}
                    onClick={() =>
                      void handleQuickPersonaLaunch("creative_lead")
                    }
                    title="Sign in as @creative_lead (Stage 1 Creator)"
                  >
                    {launchingRole === "creative_lead"
                      ? "Opening…"
                      : "Creator"}
                  </button>
                  <button
                    type="button"
                    className="cg-persona-chip"
                    disabled={launchingRole !== null}
                    onClick={() =>
                      void handleQuickPersonaLaunch("brand_manager")
                    }
                    title="Sign in as @brand_manager (Stage 2 Brand Manager)"
                  >
                    {launchingRole === "brand_manager"
                      ? "Opening…"
                      : "Brand Mgr"}
                  </button>
                  <button
                    type="button"
                    className="cg-persona-chip"
                    disabled={launchingRole !== null}
                    onClick={() =>
                      void handleQuickPersonaLaunch("legal_counsel")
                    }
                    title="Sign in as @legal_counsel (Stage 3 Legal Reviewer)"
                  >
                    {launchingRole === "legal_counsel" ? "Opening…" : "Legal"}
                  </button>
                </div>

                <Link to="/login" className="cg-btn cg-btn-ghost">
                  Sign In
                </Link>
                <Link to="/login" className="cg-btn cg-btn-primary">
                  <span>Open Studio</span>
                  <ArrowRight size={15} className="cg-arrow-shift" />
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ── Streamlined Product Entry + Live Pre-Flight Workbench ── */}
      <section className="cg-hero-section">
        <div className="cg-container">
          <div className="cg-hero-grid">
            {/* Left Column: Focused Product Value Proposition & Guided Trial Launcher */}
            <div className="cg-hero-copy">
              <div className="cg-eyebrow-pill">
                <span className="cg-status-dot cg-dot-live" />
                <span>LIVE PRE-PUBLICATION GOVERNANCE GATE</span>
                <span className="cg-eyebrow-sep">·</span>
                <code>POST /api/gate/check</code>
              </div>

              <h1 className="cg-hero-title">
                Pre-Publish Brand &amp; Regulatory Governance: Audit claims, disclaimers &amp; contrast against{" "}
                <span className="cg-serif-italic">signed</span> brand canons.
              </h1>

              <p className="cg-hero-lead">
                Test any campaign draft in the live pre-flight sandbox below, or
                launch a guided <strong>Trial Run</strong> inside the 4-stage
                Review Studio. Once you finish or clear the trial run, your
                workspace resets to a clean slate ready for your own brand
                playbooks and campaign bundles.
              </p>

              <div className="cg-hero-cta-row">
                <button
                  type="button"
                  className="cg-btn cg-btn-primary cg-btn-lg"
                  disabled={launchingTrial}
                  onClick={() => void handleStartGuidedTrialRun()}
                >
                  <Sparkles size={16} />
                  <span>
                    {launchingTrial
                      ? "Starting Guided Trial Run…"
                      : "Start Guided Trial Run in Studio"}
                  </span>
                  <ArrowRight size={16} className="cg-arrow-shift" />
                </button>

                <Link
                  to={isAuthenticated ? "/dashboard" : "/login"}
                  className="cg-btn cg-btn-secondary cg-btn-lg"
                >
                  <span>
                    {isAuthenticated
                      ? "Open Clean Campaign Queue"
                      : "Sign In to Clean Workspace"}
                  </span>
                </Link>
              </div>

              {/* Direct 1-Click Role Workspace Strip */}
              <div className="cg-role-launch-strip">
                <div className="cg-role-launch-header">
                  <span className="cg-mono-label">
                    Workspace Role Gateway (Direct Role Access)
                  </span>
                  <span className="cg-role-launch-hint">
                    Enter the governance console directly under any RBAC role,
                    or switch roles in-session from the top bar:
                  </span>
                </div>
                <div className="cg-role-launch-buttons">
                  <button
                    type="button"
                    className="cg-role-card-btn"
                    onClick={() =>
                      void handleQuickPersonaLaunch("creative_lead")
                    }
                  >
                    <div className="cg-role-card-top">
                      <span className="cg-role-stage-tag">STAGE 01</span>
                      <code>@creative_lead</code>
                    </div>
                    <div className="cg-role-card-name">
                      <span>Creator Pre-Flight</span>
                      <ArrowRight size={13} className="cg-arrow-shift" />
                    </div>
                  </button>

                  <button
                    type="button"
                    className="cg-role-card-btn"
                    onClick={() =>
                      void handleQuickPersonaLaunch("brand_manager")
                    }
                  >
                    <div className="cg-role-card-top">
                      <span className="cg-role-stage-tag">STAGE 02</span>
                      <code>@brand_manager</code>
                    </div>
                    <div className="cg-role-card-name">
                      <span>Brand &amp; Playbook Studio</span>
                      <ArrowRight size={13} className="cg-arrow-shift" />
                    </div>
                  </button>

                  <button
                    type="button"
                    className="cg-role-card-btn"
                    onClick={() =>
                      void handleQuickPersonaLaunch("legal_counsel")
                    }
                  >
                    <div className="cg-role-card-top">
                      <span className="cg-role-stage-tag">STAGE 03</span>
                      <code>@legal_counsel</code>
                    </div>
                    <div className="cg-role-card-name">
                      <span>Legal Sign-Off &amp; Cert</span>
                      <ArrowRight size={13} className="cg-arrow-shift" />
                    </div>
                  </button>
                </div>
              </div>
            </div>

            {/* Right Column: Live Engine Response Summary Card (Bound to Real /api/gate/check) */}
            <aside
              className="cg-hero-telemetry-card"
              aria-label="Live Gate Check Verdict"
            >
              <div className="cg-telemetry-header">
                <div className="cg-telemetry-title-group">
                  <Cpu size={15} />
                  <span>LIVE GATE VERDICT (`POST /api/gate/check`)</span>
                  <button
                    type="button"
                    className="cg-trace-replay-btn"
                    disabled={checkingGate}
                    onClick={() =>
                      void executeLiveGateCheck(
                        draftText,
                        selectedCanonId,
                        conformalAlpha,
                      )
                    }
                    title="Execute live POST /api/gate/check against the engine"
                  >
                    <RefreshCw size={10} />
                    <span>{checkingGate ? "Auditing…" : "Run Check"}</span>
                  </button>
                </div>
                <span
                  className={`cg-gate-verdict-pill ${
                    blockerCount === 0 ? "verdict-allow" : "verdict-block"
                  }`}
                >
                  {blockerCount === 0 && warningCount === 0
                    ? "DECISION: ALLOW (0 FLAGS)"
                    : blockerCount === 0
                      ? `NEEDS REVIEW (${warningCount} WARN)`
                      : `DECISION: BLOCK (${blockerCount} BLOCKER${blockerCount === 1 ? "" : "S"})`}
                </span>
              </div>

              <div className="cg-telemetry-rows">
                <div className="cg-telemetry-row">
                  <div className="cg-telemetry-tier">
                    <span className="cg-tier-dot tier-1" />
                    <div>
                      <div className="cg-tier-name">
                        Tier 1 · Deterministic Terminology, Triggers &amp; WCAG
                      </div>
                      <div className="cg-tier-sub">
                        <code>terminology.banned</code> ·{" "}
                        <code>trigger.disclaimer</code> ·{" "}
                        <code>accessibility.contrast</code>
                      </div>
                    </div>
                  </div>
                  <code className="cg-tier-latency">
                    {
                      findings.filter((f) => f.tier === "deterministic")
                        .length
                    }{" "}
                    flagged
                  </code>
                </div>

                <div className="cg-telemetry-row">
                  <div className="cg-telemetry-tier">
                    <span className="cg-tier-dot tier-15" />
                    <div>
                      <div className="cg-tier-name">
                        Tier 1.5 · SMT / Algebraic Constraint Solver
                      </div>
                      <div className="cg-tier-sub">
                        <code>claim.algebra</code> (Z3 / SymPy + SciPy HiGHS
                        caps &amp; drip pricing)
                      </div>
                    </div>
                  </div>
                  <code className="cg-tier-latency">
                    {findings.filter((f) => f.tier === "smt").length} flagged
                  </code>
                </div>

                <div className="cg-telemetry-row">
                  <div className="cg-telemetry-tier">
                    <span className="cg-tier-dot tier-2" />
                    <div>
                      <div className="cg-tier-name">
                        Tier 2 · Claim Slot NLI &amp; Substantiation
                      </div>
                      <div className="cg-tier-sub">
                        <code>claim.slot_nli</code> (qualifier stripping &amp;
                        factual contradictions)
                      </div>
                    </div>
                  </div>
                  <code className="cg-tier-latency">
                    {findings.filter((f) => f.tier === "nli").length} flagged
                  </code>
                </div>

                <div className="cg-telemetry-row">
                  <div className="cg-telemetry-tier">
                    <span className="cg-tier-dot tier-3" />
                    <div>
                      <div className="cg-tier-name">
                        Engine Execution Latency &amp; Mode
                      </div>
                      <div className="cg-tier-sub">
                        Canon{" "}
                        <code>
                          {gateResult?.canon_id ?? selectedCanonId}@v
                          {gateResult?.canon_version ?? "1.0"}
                        </code>{" "}
                        · {findings.length} total finding(s)
                      </div>
                    </div>
                  </div>
                  <code className="cg-tier-latency">
                    {gateResult ? `${gateResult.latency_ms} ms` : "…"}
                  </code>
                </div>
              </div>

              {/* Real Split-Conformal Risk Threshold Meter */}
              <div className="cg-conformal-meter-wrap">
                <div className="cg-conformal-meter-labels">
                  <span>
                    Split-Conformal Threshold{" "}
                    <code>
                      λ̂(α={conformalAlpha.toFixed(2)}) ={" "}
                      {conformalLambda.toFixed(2)}
                    </code>
                  </span>
                  <span>
                    {blockerCount} Blockers · {warningCount} Warnings
                  </span>
                </div>
                <div className="cg-conformal-meter-track">
                  <div
                    className="cg-conformal-meter-fill"
                    style={{
                      transform: `scaleX(${Math.min(1, conformalLambda)})`,
                    }}
                  />
                </div>
              </div>

              <div className="cg-telemetry-footer">
                <div className="cg-telemetry-hash-col">
                  <span className="cg-mono-label">CANON SHA-256</span>
                  <code>
                    {(
                      gateResult?.canon_hash ??
                      matchedCanonMeta?.hash ??
                      "1cd1ac13e83f1b00"
                    ).slice(0, 16)}
                    …
                  </code>
                </div>
                <div className="cg-telemetry-hash-col">
                  <span className="cg-mono-label">CONTENT SHA-256</span>
                  <code>
                    {(gateResult?.content_hash ?? "—").slice(0, 16)}
                    {gateResult?.content_hash ? "…" : ""}
                  </code>
                </div>
                <div className="cg-telemetry-hash-col">
                  <span className="cg-mono-label">CONFORMAL λ̂(α)</span>
                  <code>{conformalLambda.toFixed(2)}</code>
                </div>
              </div>
            </aside>
          </div>

          {/* ── Interactive Live Pre-Publish Gate Workbench ── */}
          <div id="workbench" className="cg-workbench-shell">
            {/* Workbench Top Bar: Preset Selector + Conformal Alpha + Surgical Repair */}
            <div className="cg-workbench-bar">
              <div className="cg-workbench-tabs" role="tablist">
                {TRIAL_PRESETS.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    role="tab"
                    aria-selected={presetId === preset.id}
                    className={`cg-workbench-tab ${
                      presetId === preset.id ? "active" : ""
                    }`}
                    onClick={() => handleSelectPreset(preset)}
                  >
                    <span className="cg-tab-canon">{preset.canonId}.yaml</span>
                    <span className="cg-tab-sector">{preset.sectorTag}</span>
                  </button>
                ))}
              </div>

              <div className="cg-workbench-controls">
                <div
                  className="cg-alpha-control"
                  title="Split-Conformal miscoverage alpha in [0.05, 0.20] (engine/conformal.py)"
                >
                  <Sliders size={13} />
                  <span>Conformal α:</span>
                  {[0.05, 0.1, 0.2].map((val) => (
                    <button
                      key={val}
                      type="button"
                      className={`cg-alpha-btn ${
                        Math.abs(conformalAlpha - val) < 0.001 ? "active" : ""
                      }`}
                      onClick={() => setConformalAlpha(val)}
                    >
                      {val.toFixed(2)}
                    </button>
                  ))}
                </div>

                <button
                  type="button"
                  className={`cg-surgical-toggle-btn ${
                    isRepaired ? "repaired" : ""
                  }`}
                  onClick={handleToggleSurgicalRepair}
                >
                  <Wand2 size={14} />
                  <span>
                    {isRepaired
                      ? "Showing Compliant Copy (Revert to Draft)"
                      : "Apply Compliant Fix & Re-Verify"}
                  </span>
                </button>
              </div>
            </div>

            {/* Workbench 3-Pane Body */}
            <div className="cg-workbench-grid">
              {/* Pane 1: Editable Campaign Copy + Visual Contrast Preview */}
              <div className="cg-workbench-pane cg-pane-canvas">
                <div className="cg-pane-header">
                  <div>
                    <span className="cg-mono-label">
                      LIVE INPUT CANVAS · EDIT OR PASTE YOUR OWN COPY
                    </span>
                    <h3 className="cg-pane-title">{draftTitle}</h3>
                  </div>
                  <span
                    className={`cg-status-chip ${
                      blockerCount === 0 ? "chip-pass" : "chip-fail"
                    }`}
                  >
                    {checkingGate
                      ? "Auditing…"
                      : blockerCount === 0
                        ? `0 Blockers (${warningCount} Warning${warningCount === 1 ? "" : "s"})`
                        : `${blockerCount} Blocker${blockerCount === 1 ? "" : "s"} Flagged`}
                  </span>
                </div>

                <div className="cg-prosemirror-surface">
                  <div className="cg-surface-subbar">
                    <span>
                      ACTIVE CANON: <code>{selectedCanonId}</code> (v1.0)
                    </span>
                    <span>Edits auto-run `POST /api/gate/check`</span>
                  </div>

                  <textarea
                    aria-label="Interactive campaign copy input"
                    value={draftText}
                    onChange={(e) => {
                      setDraftText(e.target.value);
                      setIsRepaired(false);
                    }}
                    rows={6}
                    style={{
                      width: "100%",
                      fontFamily: "var(--font-sans, inherit)",
                      fontSize: "0.92rem",
                      lineHeight: 1.55,
                      padding: "0.75rem",
                      borderRadius: "6px",
                      border: "1px solid rgba(148, 163, 184, 0.35)",
                      background: "rgba(255, 255, 255, 0.9)",
                      color: "#0f172a",
                      resize: "vertical",
                    }}
                  />
                </div>

                {/* Visual Contrast & Banner Preview */}
                <div className="cg-banner-stage-wrap">
                  <div className="cg-surface-subbar">
                    <span>
                      WCAG 2.1 CONTRAST &amp; BANNER PREVIEW (
                      <code>accessibility.contrast</code>)
                    </span>
                    <span>Click swatches in Inspector to test #767676</span>
                  </div>

                  <div
                    className="cg-simulated-banner"
                    style={{ backgroundColor: currentPreset.banner.bgHex }}
                  >
                    <div
                      className="cg-sim-banner-header"
                      style={{
                        backgroundColor: isRepaired
                          ? currentPreset.banner.accentCanonHex
                          : currentPreset.banner.accentDraftHex,
                      }}
                    >
                      <div className="cg-sim-logo-box">
                        <span>⛨ {selectedCanonId.toUpperCase()}</span>
                        <span className="cg-sim-collar-tag">
                          ORB Collar ≥ 0.50H
                        </span>
                      </div>
                      <span className="cg-sim-kfs-pill">
                        {currentPreset.banner.kfsBadge}
                      </span>
                    </div>

                    <div className="cg-sim-banner-body">
                      <div className="cg-sim-banner-headline">
                        {currentPreset.banner.headline}
                      </div>
                      <div className="cg-sim-banner-subline">
                        {currentPreset.banner.subline}
                      </div>
                    </div>

                    <div
                      className={`cg-sim-banner-disclaimer ${
                        activeBannerFgHex.toUpperCase() === "#777777"
                          ? "bbox-flagged"
                          : "bbox-repaired"
                      }`}
                      style={{ color: activeBannerFgHex }}
                    >
                      <span className="cg-bbox-pin-badge">
                        {activeBannerFgHex.toUpperCase() === "#777777"
                          ? "WCAG 4.48:1 FAIL (#777777)"
                          : `WCAG PASS (${activeBannerFgHex})`}
                      </span>
                      <span>
                        {activeBannerFgHex.toUpperCase() === "#777777"
                          ? currentPreset.banner.disclaimerDraft
                          : currentPreset.banner.disclaimerFixed}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Pane 2: Live Engine Findings Inspector */}
              <div className="cg-workbench-pane cg-pane-inspector">
                <div className="cg-pane-header">
                  <div>
                    <span className="cg-mono-label">
                      REAL ENGINE FINDINGS ({findings.length} RETURNED)
                    </span>
                    <h3 className="cg-pane-title">
                      Check Evidence &amp; Suggested Replacements
                    </h3>
                  </div>
                </div>

                {findings.length === 0 ? (
                  <div className="cg-inspector-card">
                    <div className="cg-inspector-top">
                      <span className="cg-sev-badge sev-pass">
                        ALL CHECKS PASSED
                      </span>
                      <code className="cg-rule-code">
                        decision = &quot;allow&quot;
                      </code>
                    </div>
                    <h4 className="cg-inspector-title">
                      Zero Blockers or Warnings Flagged
                    </h4>
                    <p className="cg-inspector-desc">
                      The current draft satisfies all active rules in{" "}
                      <code>{selectedCanonId}@v1.0</code> at Conformal Risk
                      threshold{" "}
                      <code>λ̂ = {conformalLambda.toFixed(2)}</code>. Click{" "}
                      <strong>Revert to Draft</strong> above or edit the text to
                      test violations.
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="cg-finding-selector-row">
                      {findings.map((f, idx) => (
                        <button
                          key={`${f.finding_id}-${idx}`}
                          type="button"
                          className={`cg-finding-tab-pill ${
                            selectedFindingIdx === idx ? "active" : ""
                          } ${f.verdict === "BLOCKER" ? "blocker" : "warning"}`}
                          onClick={() => setSelectedFindingIdx(idx)}
                        >
                          <span className="cg-pin-circle">F{idx + 1}</span>
                          <span>{f.check_id}</span>
                          <code>S={f.severity}</code>
                        </button>
                      ))}
                    </div>

                    {activeFinding && (
                      <div
                        key={activeFinding.finding_id}
                        className="cg-inspector-card cg-animate-swap"
                      >
                        <div className="cg-inspector-top">
                          <span
                            className={`cg-sev-badge ${
                              activeFinding.verdict === "BLOCKER"
                                ? "sev-blocker"
                                : "sev-warning"
                            }`}
                          >
                            {activeFinding.verdict} · S={activeFinding.severity}
                          </span>
                          <code className="cg-rule-code">
                            {activeFinding.rule_id}
                          </code>
                          <span className="cg-tier-tag">
                            tier: {activeFinding.tier}
                          </span>
                        </div>

                        <h4 className="cg-inspector-title">
                          {activeFinding.check_id}
                        </h4>
                        <p className="cg-inspector-desc">
                          {activeFinding.message}
                        </p>

                        {activeFinding.replacement_preview && (
                          <div className="cg-diff-preview-box">
                            <div className="cg-diff-line diff-removed">
                              <span className="cg-diff-sign">Rule</span>
                              <span>
                                {activeFinding.rule_id} (
                                {activeFinding.suggestion_label ||
                                  "Suggested remediation"}
                                )
                              </span>
                            </div>
                            <div className="cg-diff-line diff-added">
                              <span className="cg-diff-sign">+ Fix</span>
                              <span>{activeFinding.replacement_preview}</span>
                            </div>
                          </div>
                        )}

                        {activeFinding.check_id ===
                          "accessibility.contrast" && (
                          <div className="cg-evidence-block">
                            <div className="cg-evidence-header">
                              <span>
                                DesignAlternativeProvider · Click Swatch to
                                Apply to Copy
                              </span>
                              <code>checks/accessibility_contrast.py</code>
                            </div>
                            <div className="cg-swatch-grid">
                              {currentPreset.swatches.map((sw) => (
                                <button
                                  key={sw.hex}
                                  type="button"
                                  className={`cg-swatch-card ${
                                    activeBannerFgHex.toUpperCase() ===
                                    sw.hex.toUpperCase()
                                      ? "active"
                                      : ""
                                  }`}
                                  onClick={() =>
                                    handleApplySwatchToCopy(sw.hex)
                                  }
                                >
                                  <div className="cg-swatch-top">
                                    <span
                                      className="cg-swatch-chip"
                                      style={{ backgroundColor: sw.hex }}
                                    />
                                    <code>{sw.hex}</code>
                                    <span className="cg-swatch-pass">
                                      {sw.badge}
                                    </span>
                                  </div>
                                  <div className="cg-swatch-label">
                                    {sw.label}
                                  </div>
                                  <div className="cg-swatch-meta">
                                    <span>Contrast {sw.ratio}</span>
                                    <span>{sw.deltaE}</span>
                                  </div>
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Pane 3: Guided Trial Run & Cryptographic Release Handoff */}
              <div className="cg-workbench-pane cg-pane-ledger">
                <div className="cg-pane-header">
                  <div>
                    <span className="cg-mono-label">
                      GUIDED TRIAL RUN · END-TO-END STUDIO HANDOFF
                    </span>
                    <h3 className="cg-pane-title">
                      Try the Full 4-Stage Workflow
                    </h3>
                  </div>
                </div>

                <div
                  className={`cg-release-seal-card ${
                    blockerCount === 0 ? "seal-ready" : "seal-blocked"
                  }`}
                >
                  <div className="cg-seal-status-row">
                    {blockerCount === 0 ? (
                      <CheckCircle2 size={20} className="cg-seal-icon-pass" />
                    ) : (
                      <ShieldAlert size={20} className="cg-seal-icon-block" />
                    )}
                    <div>
                      <div className="cg-seal-title">
                        {blockerCount === 0
                          ? "Pre-Flight Gate Passed (ALLOW)"
                          : `Publication Gate Locked (${blockerCount} Blocker${blockerCount === 1 ? "" : "s"})`}
                      </div>
                      <div className="cg-seal-sub">
                        {blockerCount === 0
                          ? "Ready for Brand Manager & Legal Sign-Off"
                          : "Open in Review Studio to accept fixes, override warnings, and sign off"}
                      </div>
                    </div>
                  </div>

                  <div className="cg-ledger-kv-list">
                    <div className="cg-ledger-kv">
                      <span>Playbook Canon</span>
                      <code>
                        {selectedCanonId}@v
                        {gateResult?.canon_version ?? "1.0"}
                      </code>
                    </div>
                    <div className="cg-ledger-kv">
                      <span>Canon SHA-256</span>
                      <code>
                        {(
                          gateResult?.canon_hash ??
                          matchedCanonMeta?.hash ??
                          "1cd1ac13e83f1b00"
                        ).slice(0, 16)}
                        …
                      </code>
                    </div>
                    <div className="cg-ledger-kv">
                      <span>Content SHA-256</span>
                      <code>
                        {(gateResult?.content_hash ?? "—").slice(0, 16)}
                        {gateResult?.content_hash ? "…" : ""}
                      </code>
                    </div>
                    <div className="cg-ledger-kv">
                      <span>Conformal Threshold</span>
                      <code>
                        α={conformalAlpha.toFixed(2)} → λ̂=
                        {conformalLambda.toFixed(2)}
                      </code>
                    </div>
                  </div>

                  <div className="cg-ledger-actions">
                    <button
                      type="button"
                      className="cg-btn cg-btn-primary cg-btn-full"
                      disabled={launchingTrial}
                      onClick={() => void handleStartGuidedTrialRun()}
                    >
                      <FileCheck2 size={14} />
                      <span>
                        {launchingTrial
                          ? "Creating Trial Bundle…"
                          : "Open as Guided Trial Run in Studio →"}
                      </span>
                    </button>
                  </div>
                </div>

                <div className="cg-mini-audit-log">
                  <div className="cg-mono-label">
                    HOW THE GUIDED TRIAL RUN WORKS
                  </div>
                  <div className="cg-mini-audit-item">
                    <span className="cg-audit-step">01</span>
                    <div>
                      <strong>Inspect &amp; Remediate in Review Studio</strong>
                      <p>
                        Opens this draft in `/submissions/:id` with real inline
                        ProseMirror highlights, SlotDiff tables, and 1-click
                        fixes.
                      </p>
                    </div>
                  </div>
                  <div className="cg-mini-audit-item">
                    <span className="cg-audit-step">02</span>
                    <div>
                      <strong>Test Role Switching &amp; Sign-Off</strong>
                      <p>
                        Switch roles in the top bar (`Creator → Brand Manager →
                        Legal Reviewer`) to approve and export the signed
                        Merkle certificate.
                      </p>
                    </div>
                  </div>
                  <div className="cg-mini-audit-item">
                    <span className="cg-audit-step">03</span>
                    <div>
                      <strong>1-Click Reset to Clean Slate</strong>
                      <p>
                        Click <em>&quot;Finish Trial &amp; Clear Sample&quot;</em>{" "}
                        in the banner at any time so your queue is 100% empty
                        and ready for your own data.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Compact 3-Role Governance Workflow Section (#workflow) ── */}
      <section id="workflow" className="cg-section cg-section-subtle">
        <div className="cg-container">
          <div className="cg-section-header-split">
            <div>
              <span className="cg-mono-eyebrow">
                ROLE-GATED WORKFLOW &amp; AUDIT TRAIL
              </span>
              <h2 className="cg-section-heading">
                Three-role separation of duties with{" "}
                <span className="cg-serif-italic">hash-chained</span> sign-off.
              </h2>
            </div>
            <p className="cg-section-lead">
              Creators can resolve Blockers or deliberately override Warnings
              with a recorded reason, Brand Managers calibrate playbooks and
              review diffs, and Legal Reviewers issue the final Ed25519 + RFC
              9162 Merkle release certificate.
            </p>
          </div>

          <div className="cg-stage-tabs">
            {WORKFLOW_STAGE_SPECS.map((item) => (
              <div key={item.stage} className="cg-stage-tab-card active">
                <div className="cg-stage-tab-top">
                  <span className="cg-stage-num">{item.stage}</span>
                  <code className="cg-stage-status">{item.statusTag}</code>
                </div>
                <div className="cg-stage-tab-title">{item.title}</div>
                <p
                  style={{
                    fontSize: "0.86rem",
                    color: "#475569",
                    margin: "0.5rem 0 0.9rem",
                    lineHeight: 1.5,
                  }}
                >
                  {item.summary}
                </p>
                <button
                  type="button"
                  className="cg-btn cg-btn-secondary cg-btn-sm"
                  onClick={() => void handleQuickPersonaLaunch(item.username)}
                >
                  <Play size={12} />
                  <span>Enter as @{item.username}</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Authentic Repository Canons, CLI & MCP Integration (#developers) ── */}
      <section id="developers" className="cg-section cg-section-bordered">
        <div className="cg-container">
          <div className="cg-section-header-split">
            <div>
              <span className="cg-mono-eyebrow">
                CANON PLAYBOOKS (`canons/*.yaml`), CLI &amp; MCP (`2026-07-28`)
              </span>
              <h2 className="cg-section-heading">
                Exact YAML schemas and{" "}
                <span className="cg-serif-italic">headless</span> CI/CD gates.
              </h2>
            </div>
            <p className="cg-section-lead">
              Inspect the exact starter Canons shipped in `canons/*.yaml` or
              onboard your own company guidelines via Pipeline A (`POST
              /api/canons/compile`). Enforce the same Canon via the CLI, MCP
              server, or CMS webhooks.
            </p>
          </div>

          <div className="cg-dev-split-grid">
            {/* Left Column: Real Canon YAML Files */}
            <div className="cg-code-window">
              <div className="cg-code-window-bar">
                <div className="cg-code-tabs">
                  {Object.keys(PLAYBOOK_YAML_SAMPLES).map((key) => (
                    <button
                      key={key}
                      type="button"
                      className={`cg-code-tab ${
                        activePlaybookKey === key ? "active" : ""
                      }`}
                      onClick={() => setActivePlaybookKey(key)}
                    >
                      {key}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  className="cg-copy-code-btn"
                  onClick={() =>
                    handleCopyText(
                      "yaml-copy",
                      PLAYBOOK_YAML_SAMPLES[activePlaybookKey].yaml,
                    )
                  }
                >
                  {copiedId === "yaml-copy" ? (
                    <>
                      <Check size={12} /> Copied
                    </>
                  ) : (
                    <>
                      <Copy size={12} /> Copy YAML
                    </>
                  )}
                </button>
              </div>

              <div key={activePlaybookKey} className="cg-code-body-wrap">
                <div className="cg-code-meta-strip">
                  <span>
                    <strong>
                      {PLAYBOOK_YAML_SAMPLES[activePlaybookKey].title}
                    </strong>{" "}
                    · sha256:{" "}
                    <code>
                      {PLAYBOOK_YAML_SAMPLES[activePlaybookKey].hashPrefix}…
                    </code>
                  </span>
                  <code>
                    {PLAYBOOK_YAML_SAMPLES[activePlaybookKey].rulesCount} rules
                  </code>
                </div>

                <pre className="cg-code-pre">
                  <code>{PLAYBOOK_YAML_SAMPLES[activePlaybookKey].yaml}</code>
                </pre>
              </div>
            </div>

            {/* Right Column: Authentic CLI, MCP & Webhook Snippets */}
            <div className="cg-code-window">
              <div className="cg-code-window-bar">
                <div className="cg-code-tabs">
                  {Object.entries(DEV_INTEGRATION_TABS).map(([key, item]) => (
                    <button
                      key={key}
                      type="button"
                      className={`cg-code-tab ${
                        activeDevTab === key ? "active" : ""
                      }`}
                      onClick={() => setActiveDevTab(key)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  className="cg-copy-code-btn"
                  onClick={() =>
                    handleCopyText(
                      "dev-copy",
                      DEV_INTEGRATION_TABS[activeDevTab].code,
                    )
                  }
                >
                  {copiedId === "dev-copy" ? (
                    <>
                      <Check size={12} /> Copied
                    </>
                  ) : (
                    <>
                      <Copy size={12} /> Copy Snippet
                    </>
                  )}
                </button>
              </div>

              <div key={activeDevTab} className="cg-code-body-wrap">
                <div className="cg-code-meta-strip">
                  <span>{DEV_INTEGRATION_TABS[activeDevTab].subtitle}</span>
                </div>

                <pre className="cg-code-pre">
                  <code>{DEV_INTEGRATION_TABS[activeDevTab].code}</code>
                </pre>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="cg-footer">
        <div className="cg-container cg-footer-inner">
          <div className="cg-footer-left">
            <div className="cg-brand">
              <span className="cg-brand-mark" aria-hidden="true">
                <ShieldCheck size={16} strokeWidth={2.2} />
              </span>
              <span className="cg-brand-name">CanonGate</span>
              <span className="cg-brand-version">
                Pre-Publication Brand &amp; Claim Governance
              </span>
            </div>
            <p className="cg-footer-note">
              Tier 1 Deterministic &amp; WCAG · Tier 1.5 SMT Claim Algebra ·
              Tier 2 Claim Slot NLI · Tier 3 Surgical Rewriter · RFC 9162 Merkle
              Certificates.
            </p>
          </div>

          <div className="cg-footer-actions">
            <a href="#workbench" className="cg-footer-link">
              Live Gate
            </a>
            <a href="#workflow" className="cg-footer-link">
              Workflow
            </a>
            <a href="#developers" className="cg-footer-link">
              Canons &amp; CLI
            </a>
            <Link
              to={isAuthenticated ? "/dashboard" : "/login"}
              className="cg-btn cg-btn-primary"
            >
              <span>
                {isAuthenticated ? "Open Console" : "Sign In to Studio"}
              </span>
              <ArrowRight size={14} className="cg-arrow-shift" />
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
