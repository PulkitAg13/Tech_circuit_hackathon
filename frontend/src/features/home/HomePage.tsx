import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Copy,
  Cpu,
  Eye,
  FileCheck2,
  GitPullRequest,
  Layers,
  Lock,
  Play,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Terminal,
  Wand2,
} from "lucide-react";
import { useAuth } from "../auth/context";

/* ──────────────────────────────────────────────────────────────────────────
 * Interactive Multi-Modal Workbench Scenarios (Real CanonGate Engine Data)
 * ────────────────────────────────────────────────────────────────────────── */

interface SlotDiffRow {
  slot: string;
  draft: string;
  canon: string;
  status: "MATCH" | "DROPPED" | "CONTRADICTED";
}

interface SwatchCandidate {
  label: string;
  hex: string;
  bgHex: string;
  ratio: string;
  deltaE: string;
  badge: string;
}

interface WorkbenchFinding {
  id: string;
  pinLabel: string;
  modality: "COPY" | "VISION" | "Z3_KFS";
  severity: "blocker" | "warning";
  tier: string;
  checkId: string;
  ruleRef: string;
  riskScore: number;
  title: string;
  flaggedSpan: string;
  repairedSpan: string;
  explanation: string;
  slotDiff?: SlotDiffRow[];
  z3Proof?: {
    formula: string;
    statedValue: string;
    solvedValue: string;
    counterexample: string;
  };
  swatches?: SwatchCandidate[];
  bbox?: { x: number; y: number; w: number; h: number };
}

interface WorkbenchScenario {
  id: string;
  canonId: string;
  canonVersion: string;
  sectorTag: string;
  title: string;
  assetName: string;
  draftCopyParts: {
    prefix: string;
    span1: string;
    mid: string;
    span2: string;
    suffix: string;
  };
  repairedCopyParts: {
    prefix: string;
    span1: string;
    mid: string;
    span2: string;
    suffix: string;
  };
  editRatio: string;
  piiMaskedCount: number;
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
  hashes: {
    canonHash: string;
    draftHash: string;
    repairedHash: string;
    merkleRoot: string;
    ed25519Sig: string;
  };
  findings: WorkbenchFinding[];
}

const WORKBENCH_SCENARIOS: WorkbenchScenario[] = [
  {
    id: "fintech",
    canonId: "indian-digital-lending",
    canonVersion: "1.4.0",
    sectorTag: "RBI 2025 KFS · CCPA 2022",
    title: "Acme QuickLoan Festival Campaign",
    assetName: "acme_diwali_kfs_bundle.yaml",
    draftCopyParts: {
      prefix: "Celebrate this season with Acme QuickLoan: enjoy ",
      span1: "0% interest on all personal loans",
      mid: " with ",
      span2: "guaranteed instant approval in 60 seconds",
      suffix:
        ". Principal ₹50,000 · Processing Fee ₹1,500 · Interest ₹3,500 · Stated APR 14.00%.",
    },
    repairedCopyParts: {
      prefix: "Celebrate this season with Acme QuickLoan: enjoy ",
      span1:
        "0% interest on personal loans under ₹50,000 for first-time borrowers",
      mid: " with ",
      span2:
        "instant eligibility assessment subject to credit bureau verification",
      suffix:
        ". Principal ₹50,000 · Processing Fee ₹1,500 · Interest ₹3,500 · Effective APR 28.18% (KFS Attached).",
    },
    editRatio: "0.24 ≤ 0.35",
    piiMaskedCount: 2,
    banner: {
      headline: "0% INTEREST FESTIVAL LOAN",
      subline: "Instant ₹50,000 disbursal · Stated APR 14.00%",
      disclaimerDraft: "T&C apply. Subject to internal policy.",
      disclaimerFixed:
        "Valid for first-time borrowers under ₹50,000. Effective APR 28.18% per RBI KFS.",
      bgHex: "#F4F4F6",
      accentDraftHex: "#19528A",
      accentCanonHex: "#0D3B66",
      fgDraftHex: "#787878",
      fgDefaultFixedHex: "#767676",
      kfsBadge: "RBI/2024-25/18 KFS",
    },
    hashes: {
      canonHash: "dd5f040bb7ebed33",
      draftHash: "8f91c204a7d10e42",
      repairedHash: "2cc156965f6d260b",
      merkleRoot: "b5baae0a9d4f010288266c930bd95702",
      ed25519Sig: "ed25519:94a8f01c...7e2b9104",
    },
    findings: [
      {
        id: "f-slot",
        pinLabel: "C1",
        modality: "COPY",
        severity: "blocker",
        tier: "Tier 2 · QASem + Calibrated NLI",
        checkId: "check.factual_claim",
        ruleRef: "fact.zero_interest_promo",
        riskScore: 0.94,
        title: "Dropped Mandatory Eligibility & Ceiling Qualifiers",
        flaggedSpan: "0% interest on all personal loans",
        repairedSpan:
          "0% interest on personal loans under ₹50,000 for first-time borrowers",
        explanation:
          "Draft generalizes a conditional promotional rate ('0% interest') to all loans, dropping two mandatory canon qualifiers required under CCPA 2022 §2(28).",
        slotDiff: [
          {
            slot: "metric",
            draft: "0% interest",
            canon: "0% interest",
            status: "MATCH",
          },
          {
            slot: "scope / ceiling",
            draft: "all personal loans",
            canon: "loans under ₹50,000",
            status: "DROPPED",
          },
          {
            slot: "target_cohort",
            draft: "— (omitted)",
            canon: "first-time borrowers",
            status: "DROPPED",
          },
          {
            slot: "disclosure",
            draft: "— (omitted)",
            canon: "processing fee of 2.5% applies",
            status: "DROPPED",
          },
        ],
      },
      {
        id: "f-z3",
        pinLabel: "K1",
        modality: "Z3_KFS",
        severity: "blocker",
        tier: "Tier 1.5 · SymPy + Z3 QF_NRA",
        checkId: "check.numeric_consistency",
        ruleRef: "rbi.kfs.apr_reconciliation",
        riskScore: 0.99,
        title: "Algebraic APR & Fee Reconciliation Contradiction",
        flaggedSpan:
          "Principal ₹50,000 · Processing Fee ₹1,500 · Interest ₹3,500 · Stated APR 14.00%",
        repairedSpan:
          "Principal ₹50,000 · Processing Fee ₹1,500 · Interest ₹3,500 · Effective APR 28.18% (KFS Attached)",
        explanation:
          "Z3 nonlinear real arithmetic solver proved that ₹3,500 interest + ₹1,500 upfront fee on ₹50,000 over 6 monthly installments yields an effective annualized APR of 28.18%, contradicting the stated 14.00% APR.",
        z3Proof: {
          formula:
            "APR_eff = ((Interest + UpfrontFee) / NetDisbursed) * (12 / TenureMonths) * (2 * N / (N + 1))",
          statedValue: "14.00% APR",
          solvedValue: "28.18% APR (Δ = +14.18%)",
          counterexample:
            "sat: [P = 50000, F = 1500, I = 3500, T = 6] => APR_actual = 0.2818 != 0.1400",
        },
      },
      {
        id: "f-wcag",
        pinLabel: "V1",
        modality: "VISION",
        severity: "blocker",
        tier: "Tier 1 · OpenCV + WCAG 2.1",
        checkId: "check.visual_contrast",
        ruleRef: "wcag.aa.normal_text (4.5:1)",
        riskScore: 0.91,
        title: "Banner Disclaimer Contrast Below WCAG 2.1 AA Floor",
        flaggedSpan: "Foreground #787878 on #F4F4F6 (4.06:1 < 4.50:1)",
        repairedSpan: "Foreground #767676 on #F4F4F6 (4.54:1 PASS)",
        explanation:
          "Sobel + Otsu text-region segmentation isolated the bottom statutory disclaimer bar. Relative luminance ratio is 4.06:1, failing the 4.50:1 statutory floor for <18pt text.",
        swatches: [
          {
            label: "WCAG AA Minimal Shift",
            hex: "#6E6E6E",
            bgHex: "#F4F4F6",
            ratio: "4.62:1",
            deltaE: "ΔE₀₀ 1.4",
            badge: "AA PASS",
          },
          {
            label: "WCAG AAA High-Contrast",
            hex: "#525252",
            bgHex: "#F4F4F6",
            ratio: "7.14:1",
            deltaE: "ΔE₀₀ 4.8",
            badge: "AAA PASS",
          },
          {
            label: "Canon Brand Navy Token",
            hex: "#0D3B66",
            bgHex: "#F4F4F6",
            ratio: "10.38:1",
            deltaE: "ΔE₀₀ 0.0",
            badge: "BRAND + AAA",
          },
        ],
        bbox: { x: 8, y: 74, w: 84, h: 18 },
      },
    ],
  },
  {
    id: "nutra",
    canonId: "indian-d2c-nutra",
    canonVersion: "1.2.0",
    sectorTag: "ASCI FY25-26 · FSSAI",
    title: "VitalGlow Marine Collagen D2C Launch",
    assetName: "vitalglow_instagram_bundle.yaml",
    draftCopyParts: {
      prefix: "Transform your skin with VitalGlow Peptides: ",
      span1: "clinically proven to permanently reverse skin aging in 7 days",
      mid: " and ",
      span2: "100% doctor-endorsed with zero side effects",
      suffix: ". Order your 30-day starter pack today.",
    },
    repairedCopyParts: {
      prefix: "Support skin hydration with VitalGlow Peptides: ",
      span1:
        "shown in an 8-week consumer study (n=64) to improve skin elasticity by 18%",
      mid: " and ",
      span2: "formulated in FSSAI-compliant GMP facilities",
      suffix:
        ". Order your 30-day starter pack today. Not intended to diagnose, treat, cure, or prevent any disease.",
    },
    editRatio: "0.29 ≤ 0.35",
    piiMaskedCount: 1,
    banner: {
      headline: "CLINICALLY PROVEN 7-DAY REVERSAL",
      subline: "100% Doctor-Endorsed Marine Peptides",
      disclaimerDraft: "Results vary by individual.",
      disclaimerFixed:
        "Nutraceutical supplement. Not for medicinal use. 8-week study (n=64).",
      bgHex: "#FAF8F5",
      accentDraftHex: "#1E4D40",
      accentCanonHex: "#134E4A",
      fgDraftHex: "#827E78",
      fgDefaultFixedHex: "#57534E",
      kfsBadge: "FSSAI Lic. 10024022",
    },
    hashes: {
      canonHash: "91a4c830e2f17b09",
      draftHash: "4d82e109c3a711f0",
      repairedHash: "7b39f401d8e622a5",
      merkleRoot: "e4190c82a7f31109d4b2609188a1c30f",
      ed25519Sig: "ed25519:31c9d84a...0f41e822",
    },
    findings: [
      {
        id: "n-claim",
        pinLabel: "C1",
        modality: "COPY",
        severity: "blocker",
        tier: "Tier 2 · QASem + Calibrated NLI",
        checkId: "check.factual_claim",
        ruleRef: "fact.collagen_study_2025",
        riskScore: 0.96,
        title: "Unsubstantiated Clinical Timeframe & Permanence Claim",
        flaggedSpan:
          "clinically proven to permanently reverse skin aging in 7 days",
        repairedSpan:
          "shown in an 8-week consumer study (n=64) to improve skin elasticity by 18%",
        explanation:
          "Canon clinical dossier only substantiates an 18% elasticity improvement over 8 weeks (n=64). '7 days' and 'permanently reverse' violate ASCI Chapter I.1 truthfulness mandates.",
        slotDiff: [
          {
            slot: "outcome",
            draft: "permanently reverse skin aging",
            canon: "improve skin elasticity by 18%",
            status: "CONTRADICTED",
          },
          {
            slot: "duration",
            draft: "in 7 days",
            canon: "after 8 weeks",
            status: "CONTRADICTED",
          },
          {
            slot: "sample_size",
            draft: "— (omitted)",
            canon: "consumer study (n=64)",
            status: "DROPPED",
          },
        ],
      },
      {
        id: "n-trigger",
        pinLabel: "C2",
        modality: "COPY",
        severity: "blocker",
        tier: "Tier 1 · Deterministic Trigger AST",
        checkId: "check.required_disclaimer",
        ruleRef: "trigger.fssai_medicinal_disclaimer",
        riskScore: 0.89,
        title: "Missing Mandatory FSSAI Non-Medicinal Statutory Disclosure",
        flaggedSpan: "100% doctor-endorsed with zero side effects",
        repairedSpan:
          "formulated in FSSAI-compliant GMP facilities ... Not intended to diagnose, treat, cure, or prevent any disease.",
        explanation:
          "Health & wellness efficacy claims trigger mandatory FSSAI Food Safety and Standards (Health Supplements) disclosure.",
      },
      {
        id: "n-wcag",
        pinLabel: "V1",
        modality: "VISION",
        severity: "warning",
        tier: "Tier 1 · OpenCV + WCAG 2.1",
        checkId: "check.visual_contrast",
        ruleRef: "wcag.aa.disclaimer",
        riskScore: 0.78,
        title: "Low-Contrast Supplement Footnote on Warm Canvas",
        flaggedSpan: "Foreground #827E78 on #FAF8F5 (3.74:1 < 4.50:1)",
        repairedSpan: "Foreground #57534E on #FAF8F5 (6.89:1 PASS)",
        explanation:
          "Footnote contrast ratio is 3.74:1 against warm ivory background, below the 4.50:1 ASCI legibility threshold.",
        swatches: [
          {
            label: "WCAG AA Warm Stone",
            hex: "#6B6661",
            bgHex: "#FAF8F5",
            ratio: "4.85:1",
            deltaE: "ΔE₀₀ 1.9",
            badge: "AA PASS",
          },
          {
            label: "WCAG AAA Deep Umber",
            hex: "#57534E",
            bgHex: "#FAF8F5",
            ratio: "6.89:1",
            deltaE: "ΔE₀₀ 3.6",
            badge: "AAA PASS",
          },
          {
            label: "Canon Botanical Teal",
            hex: "#134E4A",
            bgHex: "#FAF8F5",
            ratio: "8.92:1",
            deltaE: "ΔE₀₀ 0.0",
            badge: "BRAND + AAA",
          },
        ],
        bbox: { x: 8, y: 74, w: 84, h: 18 },
      },
    ],
  },
  {
    id: "enterprise",
    canonId: "acme-corp",
    canonVersion: "2.1.0",
    sectorTag: "Brand Book · Palette ΔE₀₀ & ORB Logo",
    title: "Acme Cloud Enterprise Security Keynote",
    assetName: "acme_keynote_hero_bundle.yaml",
    draftCopyParts: {
      prefix: "Deploy Acme Cloud Shield for ",
      span1: "100% unhackable zero-downtime infrastructure",
      mid: " backed by ",
      span2: "unlimited SLA payouts on every tier",
      suffix: " across 24 global regions.",
    },
    repairedCopyParts: {
      prefix: "Deploy Acme Cloud Shield for ",
      span1: "SOC 2 Type II certified infrastructure with 99.99% uptime SLA",
      mid: " backed by ",
      span2: "service credit remedies for Enterprise Plan customers",
      suffix: " across 24 global regions.",
    },
    editRatio: "0.26 ≤ 0.35",
    piiMaskedCount: 1,
    banner: {
      headline: "ACME CLOUD SHIELD · ZERO DOWNTIME",
      subline: "Enterprise Mesh · 24 Global Regions",
      disclaimerDraft: "SLA terms subject to change without notice.",
      disclaimerFixed:
        "99.99% uptime SLA applies to Enterprise tier per Master Services Agreement.",
      bgHex: "#F1F5F9",
      accentDraftHex: "#1E6091",
      accentCanonHex: "#0D3B66",
      fgDraftHex: "#7A869A",
      fgDefaultFixedHex: "#475569",
      kfsBadge: "SOC2 · ISO27001",
    },
    hashes: {
      canonHash: "5be7400ed3c8470e",
      draftHash: "6a10f92c8b41d307",
      repairedHash: "01c86e8aabc61c79",
      merkleRoot: "82c3e4c252a40a7c065b39e07eb91bce",
      ed25519Sig: "ed25519:7f02a19b...4c8e1130",
    },
    findings: [
      {
        id: "e-term",
        pinLabel: "C1",
        modality: "COPY",
        severity: "blocker",
        tier: "Tier 1 · Aho-Corasick + UTS #39",
        checkId: "check.banned_terms",
        ruleRef: "term.unhackable_absolutist",
        riskScore: 0.98,
        title: "Prohibited Absolutist Security Claim ('100% unhackable')",
        flaggedSpan: "100% unhackable zero-downtime infrastructure",
        repairedSpan:
          "SOC 2 Type II certified infrastructure with 99.99% uptime SLA",
        explanation:
          "Acme Brand Canon §3.1 bans unverifiable security superlatives ('unhackable', 'zero-downtime') and mandates citing the verified 99.99% SLA.",
        slotDiff: [
          {
            slot: "security_posture",
            draft: "100% unhackable",
            canon: "SOC 2 Type II certified",
            status: "CONTRADICTED",
          },
          {
            slot: "availability_metric",
            draft: "zero-downtime",
            canon: "99.99% uptime SLA",
            status: "CONTRADICTED",
          },
          {
            slot: "eligible_tier",
            draft: "every tier",
            canon: "Enterprise Plan customers",
            status: "CONTRADICTED",
          },
        ],
      },
      {
        id: "e-palette",
        pinLabel: "V1",
        modality: "VISION",
        severity: "warning",
        tier: "Tier 1 · K-Means + CIEDE2000 ΔE₀₀",
        checkId: "check.visual_palette",
        ruleRef: "palette.acme_primary_navy (#0D3B66)",
        riskScore: 0.81,
        title: "Off-Brand Primary Header Swatch (ΔE₀₀ = 6.42 > 3.0)",
        flaggedSpan: "Sampled #1E6091 vs Canon #0D3B66 (ΔE₀₀ = 6.42)",
        repairedSpan: "Snapped to Canon Token #0D3B66 (ΔE₀₀ = 0.00)",
        explanation:
          "K-Means dominant colour extraction in CIE L*a*b* space detected #1E6091 on the hero banner header, exceeding the perceptual tolerance threshold ΔE₀₀ ≤ 3.0.",
        swatches: [
          {
            label: "Canon Primary Navy",
            hex: "#0D3B66",
            bgHex: "#F1F5F9",
            ratio: "10.61:1",
            deltaE: "ΔE₀₀ 0.0",
            badge: "EXACT TOKEN",
          },
          {
            label: "Canon Slate Ink",
            hex: "#1E293B",
            bgHex: "#F1F5F9",
            ratio: "12.84:1",
            deltaE: "ΔE₀₀ 0.0",
            badge: "SECONDARY TOKEN",
          },
          {
            label: "WCAG AA Slate",
            hex: "#475569",
            bgHex: "#F1F5F9",
            ratio: "6.72:1",
            deltaE: "ΔE₀₀ 1.2",
            badge: "AA PASS",
          },
        ],
        bbox: { x: 6, y: 12, w: 88, h: 28 },
      },
    ],
  },
];

/* ──────────────────────────────────────────────────────────────────────────
 * Compiled YAML Playbook & Developer Integration Snippets
 * ────────────────────────────────────────────────────────────────────────── */

const PLAYBOOK_YAML_SAMPLES: Record<
  string,
  {
    title: string;
    authority: string;
    rulesCount: number;
    yaml: string;
  }
> = {
  "indian-digital-lending.yaml": {
    title: "Indian Digital Lending & KFS Pack",
    authority: "RBI/2024-25/18 · CCPA 2022 · ASCI",
    rulesCount: 18,
    yaml: `id: indian-digital-lending
version: "1.4.0"
name: "RBI 2025 Digital Lending & Key Fact Statement Canon"

palette:
  primary:
    - name: "Canon Trust Navy"
      hex: "#0D3B66"
      tolerance_delta_e: 3.0

terminology:
  banned:
    - pattern: "guaranteed instant approval"
      replacement: "instant eligibility assessment subject to credit verification"
      severity: blocker
      rationale: "RBI Digital Lending Directions prohibit unconditional approval promises."

facts:
  - id: "fact.zero_interest_promo"
    claim: "0% interest promotional rate applies only to personal loans under ₹50,000 for first-time borrowers; a 2.5% processing fee applies."
    required_qualifiers:
      - "under ₹50,000"
      - "first-time borrowers"
    severity: blocker

triggers:
  - id: "trigger.rbi_kfs_apr"
    keywords: ["APR", "interest", "loan", "EMI"]
    required_disclaimer: "Subject to credit verification. Refer to the Key Fact Statement (KFS) for all-inclusive Annual Percentage Rate (APR)."
    severity: blocker`,
  },
  "indian-d2c-nutra.yaml": {
    title: "Indian D2C Nutraceutical & Health Claims Pack",
    authority: "ASCI FY25-26 Chapter I · FSSAI Health Supplements",
    rulesCount: 14,
    yaml: `id: indian-d2c-nutra
version: "1.2.0"
name: "ASCI & FSSAI D2C Health & Personal Care Canon"

terminology:
  banned:
    - pattern: "permanently cure"
      replacement: "clinically formulated to support"
      severity: blocker
    - pattern: "zero side effects"
      replacement: "well-tolerated in consumer trials"
      severity: blocker

facts:
  - id: "fact.collagen_study_2025"
    claim: "VitalGlow Marine Peptides improved skin elasticity by 18% after 8 weeks in a consumer study (n=64)."
    required_qualifiers:
      - "8 weeks"
      - "n=64"
    severity: blocker

triggers:
  - id: "trigger.fssai_medicinal_disclaimer"
    keywords: ["clinically", "collagen", "peptides", "supplement"]
    required_disclaimer: "Nutraceutical. Not for medicinal use. Not intended to diagnose, treat, cure, or prevent any disease."
    severity: blocker`,
  },
  "acme-corp.yaml": {
    title: "Acme Corp Enterprise Brand & Visual Governance",
    authority: "Brand Design System v2.1 · WCAG 2.1 Level AA",
    rulesCount: 16,
    yaml: `id: acme-corp
version: "2.1.0"
name: "Acme Enterprise Brand Identity & Accessibility Canon"

palette:
  primary:
    - name: "Acme Brand Navy"
      hex: "#0D3B66"
      tolerance_delta_e: 3.0
  secondary:
    - name: "Acme Emerald"
      hex: "#059669"
      tolerance_delta_e: 3.5

logo:
  reference_path: "fixtures/golden_bundle/acme_logo.png"
  min_clear_space_ratio: 0.50
  min_aspect_similarity: 0.92

voice:
  max_sentence_words: 28
  max_flesch_kincaid_grade: 11.0
  prohibited_superlatives: ["100% unhackable", "zero-downtime", "unlimited SLA"]`,
  },
};

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
      "Run deterministic + conformal pre-publish checks locally or in pre-commit hooks with non-zero exit codes on blockers.",
    code: `# Audit a multi-modal campaign bundle with Conformal Risk Control (alpha = 0.10)
$ uv run canongate gate \\
    --canon indian-digital-lending \\
    --paths fixtures/golden_bundle/acme_launch.yaml \\
    --alpha 0.10

[BLOCK] CanonGate Pre-Publish Gate — Canon 'indian-digital-lending' v1.4.0 (alpha=0.10, lambda=0.75)
  • Assets Audited : acme_launch.yaml, acme_banner_bad.png
  • Findings       : 4 total (3 Blockers, 1 Warning)
  • [BLOCKER] check.factual_claim (fact.zero_interest_promo) — score=0.94
  • [BLOCKER] check.numeric_consistency (rbi.kfs.apr_reconciliation) — score=0.99
  • [BLOCKER] check.visual_contrast (wcag.aa.normal_text) — score=0.91

# Verify an Ed25519 + RFC 9162 Merkle compliance certificate offline
$ uv run canongate verify release_cert_sub_01.json`,
  },
  github: {
    label: "GitHub Actions CI/CD",
    subtitle:
      "Drop the composite action into .github/workflows to block non-compliant campaign PRs before merge.",
    code: `name: CanonGate Pre-Publication Gate
on:
  pull_request:
    paths: ["campaigns/**", "canons/**"]

jobs:
  governance-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run CanonGate Multi-Modal Audit
        uses: ./
        with:
          canon: "indian-digital-lending"
          paths: "fixtures/golden_bundle/acme_launch.yaml"
          alpha: "0.10"
          fail-on-warning: "false"`,
  },
  mcp: {
    label: "FastMCP 3.0 Agent Server",
    subtitle:
      "Expose CanonGate to Claude Desktop, Cursor, or autonomous marketing agents via Streamable HTTP or stdio.",
    code: `// JSON-RPC 2.0 Call -> POST /api/mcp (or stdio via \`uv run canongate-mcp\`)
{
  "jsonrpc": "2.0",
  "id": "req-42",
  "method": "tools/call",
  "params": {
    "name": "surgical_rewrite_and_reverify",
    "arguments": {
      "canon_id": "indian-digital-lending",
      "draft_text": "Get 0% interest on all loans with guaranteed instant approval!",
      "max_edit_ratio": 0.35
    }
  }
}`,
  },
  webhook: {
    label: "Shopify & Webflow Gate",
    subtitle:
      "Synchronous HTTP 200 (allow) / HTTP 422 (block) webhook gate with SSRF-hardened asset fetching.",
    code: `POST /api/gate/check HTTP/1.1
Content-Type: application/json

{
  "provider": "webflow",
  "canon_id": "indian-digital-lending",
  "alpha": 0.10,
  "title": "Diwali Instant Loan Landing Page",
  "text": "0% interest for first-time borrowers on loans under ₹50,000. Refer to KFS for APR."
}

// Response: HTTP 200 OK
// { "decision": "allow", "blocker_count": 0, "conformal_alpha": 0.10, "latency_ms": 38.4 }`,
  },
};

const WORKFLOW_STAGE_SPECS = [
  {
    stage: "STAGE 01",
    roleKey: "creator",
    username: "creative_lead",
    roleLabel: "Creator (@creative_lead)",
    statusTag: "draft → in_review",
    title: "Multi-Modal Pre-Flight & Surgical Repair",
    summary:
      "Ingests Markdown, HTML, DOCX, PDF, YAML bundles, and 1080p banners into a unified ContentAST. Creators resolve deterministic & semantic blockers via 1-click surgical rewrites (≤35% edit ratio) or WCAG swatch snapping before submitting for review.",
    gates: [
      "Tier 1 AST + OpenCV Vision (CIEDE2000 ΔE₀₀, WCAG 2.1, ORB 0.5H clear-space)",
      "Tier 1.5 SymPy + Z3 QF_NRA algebraic KFS APR reconciliation",
      "DPDP Act 2023 local PII vault masks Aadhaar, PAN, GSTIN, UPI before Tier 3",
    ],
  },
  {
    stage: "STAGE 02",
    roleKey: "reviewer",
    username: "brand_manager",
    roleLabel: "Brand Manager (@brand_manager)",
    statusTag: "in_review → changes_requested | brand_approved",
    title: "Brand Identity & Conformal Calibration Review",
    summary:
      "Brand Managers inspect bidirectional ProseMirror spans and banner bounding boxes, adjudicate creator override rationales, and monitor rule friction via vectorized Krippendorff's α inter-reviewer agreement.",
    gates: [
      "Every Blocker must be Accepted or carry a ≥15-character documented override rationale",
      "Live Conformal Risk Control slider (α ∈ [0.01, 0.25]) calibrates recall guarantees",
      "Auto-generates Canon v1.1 YAML pull requests when rule override rate > 30%",
    ],
  },
  {
    stage: "STAGE 03",
    roleKey: "admin",
    username: "legal_counsel",
    roleLabel: "Legal Counsel (@legal_counsel)",
    statusTag: "in_review → approved → published",
    title: "Statutory Sign-Off & Cryptographic Release Seal",
    summary:
      "Legal Counsel performs final statutory verification against CCPA 2022, RBI 2025 KFS, and ASCI mandates. Publishing seals the transition in an RFC 9162 SHA-256 Merkle ledger and issues an Ed25519 + C2PA 2.2 manifest.",
    gates: [
      "Strict RBAC transition matrix prevents creators from self-approving campaigns",
      "RFC 9162 Certificate Transparency Merkle tree with inclusion & consistency proofs",
      "Offline-verifiable Ed25519 signature (`uv run canongate verify cert.json`)",
    ],
  },
];

export function HomePage() {
  const { isAuthenticated, username, role, login } = useAuth();
  const navigate = useNavigate();

  // Workbench interactive state
  const [scenarioId, setScenarioId] = useState<string>("fintech");
  const [selectedFindingIdx, setSelectedFindingIdx] = useState<number>(0);
  const [isRepaired, setIsRepaired] = useState<boolean>(false);
  const [conformalAlpha, setConformalAlpha] = useState<number>(0.1);
  const [selectedSwatchHex, setSelectedSwatchHex] = useState<string | null>(
    null,
  );
  const [scanPulseKey, setScanPulseKey] = useState<number>(1);
  const [tracePulseKey, setTracePulseKey] = useState<number>(1);

  // Interactive Bento specimen states
  const [bentoSnappedPalette, setBentoSnappedPalette] =
    useState<boolean>(false);
  const [bentoZ3Reconciled, setBentoZ3Reconciled] = useState<boolean>(false);

  // Architecture & Developer section interactive tabs
  const [activeStageIdx, setActiveStageIdx] = useState<number>(0);
  const [activePlaybookKey, setActivePlaybookKey] = useState<string>(
    "indian-digital-lending.yaml",
  );
  const [activeDevTab, setActiveDevTab] = useState<string>("cli");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [launchingRole, setLaunchingRole] = useState<string | null>(null);

  const currentScenario =
    WORKBENCH_SCENARIOS.find((s) => s.id === scenarioId) ??
    WORKBENCH_SCENARIOS[0];

  const activeFinding =
    currentScenario.findings[
      Math.min(selectedFindingIdx, currentScenario.findings.length - 1)
    ] ?? currentScenario.findings[0];

  // Conformal threshold math
  const conformalLambda =
    conformalAlpha <= 0.05 ? 0.68 : conformalAlpha <= 0.1 ? 0.75 : 0.85;
  const calibratedFindings = currentScenario.findings.filter(
    (f) => f.riskScore >= conformalLambda,
  );
  const blockerCount = isRepaired
    ? 0
    : calibratedFindings.filter((f) => f.severity === "blocker").length;

  const activeBannerFgHex =
    selectedSwatchHex ??
    (isRepaired
      ? currentScenario.banner.fgDefaultFixedHex
      : currentScenario.banner.fgDraftHex);

  const activeBannerAccentHex = isRepaired
    ? currentScenario.banner.accentCanonHex
    : currentScenario.banner.accentDraftHex;

  function triggerScanSweep() {
    setScanPulseKey((prev) => prev + 1);
    setTracePulseKey((prev) => prev + 1);
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

  return (
    <div className="cg-home">
      {/* ── Architectural Top Command Bar ── */}
      <header className="cg-topbar">
        <div className="cg-topbar-inner">
          <div className="cg-topbar-left">
            <Link to="/" className="cg-brand">
              <span className="cg-brand-mark" aria-hidden="true">
                <ShieldCheck size={17} strokeWidth={2.2} />
              </span>
              <span className="cg-brand-name">CanonGate</span>
              <span className="cg-brand-version">v2.4 · MCP</span>
            </Link>

            <nav className="cg-topnav" aria-label="Product sections">
              <a href="#workbench">Live Workbench</a>
              <a href="#architecture">Verification Stack</a>
              <a href="#workflow">4-Stage RBAC</a>
              <a href="#developers">Playbooks &amp; CLI</a>
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
                  aria-label="Instant Demo Workspace Access"
                >
                  <span className="cg-persona-quickbar-label">
                    Instant Studio:
                  </span>
                  <button
                    type="button"
                    className="cg-persona-chip"
                    disabled={launchingRole !== null}
                    onClick={() =>
                      void handleQuickPersonaLaunch("creative_lead")
                    }
                    title="Sign in immediately as @creative_lead (Stage 1 Creator)"
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
                    title="Sign in immediately as @brand_manager (Stage 2 Brand Manager)"
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
                    title="Sign in immediately as @legal_counsel (Stage 3 Legal Counsel)"
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

      {/* ── Architectural Hero + Asymmetric Telemetry Split ── */}
      <section className="cg-hero-section">
        <div className="cg-container">
          <div className="cg-hero-grid">
            {/* Left Column: Editorial Headline + CTAs + Role Launchers */}
            <div className="cg-hero-copy">
              <div className="cg-eyebrow-pill">
                <span className="cg-status-dot cg-dot-live" />
                <span>
                  PRE-PUBLICATION BRAND, CLAIM &amp; VISUAL GOVERNANCE
                </span>
                <span className="cg-eyebrow-sep">·</span>
                <code>RFC 9162 + C2PA 2.2</code>
              </div>

              <h1 className="cg-hero-title">
                Compile brand playbooks and statutory mandates into{" "}
                <span className="cg-serif-italic">deterministic</span>{" "}
                pre-publish gates.
              </h1>

              <p className="cg-hero-lead">
                CanonGate audits campaign copy, HTML, PDFs, and 1080p banners
                before release—combining CIEDE2000 colorimetry, WCAG 2.1
                luminance math, Z3 algebraic KFS verification, and QASem{" "}
                <code>SlotDiff</code> alignment with surgical{" "}
                <code>≤35%</code> copy repair.
              </p>

              <div className="cg-hero-cta-row">
                <Link
                  to={isAuthenticated ? "/dashboard" : "/login"}
                  className="cg-btn cg-btn-primary cg-btn-lg"
                >
                  <span>
                    {isAuthenticated
                      ? "Launch Governance Queue"
                      : "Enter Review Studio"}
                  </span>
                  <ArrowRight size={16} className="cg-arrow-shift" />
                </Link>

                <button
                  type="button"
                  className={`cg-cli-pill ${
                    copiedId === "hero-cli" ? "cg-cli-copied" : ""
                  }`}
                  onClick={() =>
                    handleCopyText(
                      "hero-cli",
                      "uv run canongate gate --canon indian-digital-lending --paths fixtures/golden_bundle/acme_launch.yaml",
                    )
                  }
                  title="Copy CLI pre-publish gate command"
                >
                  <Terminal size={14} className="cg-cli-icon" />
                  <code>
                    uv run canongate gate --canon indian-digital-lending
                  </code>
                  <span
                    key={copiedId === "hero-cli" ? "copied" : "copy"}
                    className="cg-cli-copy-badge cg-icon-pop"
                  >
                    {copiedId === "hero-cli" ? (
                      <>
                        <Check size={12} /> Copied
                      </>
                    ) : (
                      <>
                        <Copy size={12} /> Copy
                      </>
                    )}
                  </span>
                </button>
              </div>

              {/* Direct 1-Click Role Sandbox Launch Strip */}
              <div className="cg-role-launch-strip">
                <div className="cg-role-launch-header">
                  <span className="cg-mono-label">
                    1-CLICK ROLE WORKSPACE LAUNCH
                  </span>
                  <span className="cg-role-launch-hint">
                    Jump straight into the live multi-modal studio with seeded
                    RBAC personas:
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
                      <span>Creator Pre-Flight Studio</span>
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
                      <span>Brand &amp; Friction Review</span>
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
                      <span>Legal Sign-Off &amp; Seal</span>
                      <ArrowRight size={13} className="cg-arrow-shift" />
                    </div>
                  </button>
                </div>
              </div>
            </div>

            {/* Right Column: Live Engine Execution Trace & Conformal Spec Card */}
            <aside
              className="cg-hero-telemetry-card"
              aria-label="Live Verification Engine Telemetry"
            >
              <div className="cg-telemetry-header">
                <div className="cg-telemetry-title-group">
                  <Cpu size={15} />
                  <span>VERIFICATION PIPELINE TRACE</span>
                  <button
                    type="button"
                    className="cg-trace-replay-btn"
                    onClick={triggerScanSweep}
                    title="Re-run 4-tier verification trace"
                  >
                    <Play size={10} />
                    <span>Re-Run</span>
                  </button>
                </div>
                <span
                  key={blockerCount === 0 ? "allow" : "block"}
                  className={`cg-gate-verdict-pill cg-icon-pop ${
                    blockerCount === 0 ? "verdict-allow" : "verdict-block"
                  }`}
                >
                  {blockerCount === 0
                    ? "HTTP 200 · ALLOW"
                    : `HTTP 422 · BLOCK (${blockerCount})`}
                </span>
              </div>

              <div key={tracePulseKey} className="cg-telemetry-rows">
                <div className="cg-telemetry-row cg-stagger-1">
                  <div className="cg-telemetry-tier">
                    <span className="cg-tier-dot tier-1" />
                    <div>
                      <div className="cg-tier-name">
                        Tier 1 · Deterministic AST &amp; OpenCV Vision
                      </div>
                      <div className="cg-tier-sub">
                        Aho-Corasick · UTS #39 · CIEDE2000 ΔE₀₀ · WCAG 2.1 · ORB
                        0.5H
                      </div>
                    </div>
                  </div>
                  <code className="cg-tier-latency">14.2 ms</code>
                </div>

                <div className="cg-telemetry-row cg-stagger-2">
                  <div className="cg-telemetry-tier">
                    <span className="cg-tier-dot tier-15" />
                    <div>
                      <div className="cg-tier-name">
                        Tier 1.5 · SymPy + Z3 SMT Algebraic Solver
                      </div>
                      <div className="cg-tier-sub">
                        Nonlinear real arithmetic (QF_NRA) KFS APR &amp; fee
                        reconciliation
                      </div>
                    </div>
                  </div>
                  <code className="cg-tier-latency">9.8 ms</code>
                </div>

                <div className="cg-telemetry-row cg-stagger-3">
                  <div className="cg-telemetry-tier">
                    <span className="cg-tier-dot tier-2" />
                    <div>
                      <div className="cg-tier-name">
                        Tier 2 · Hybrid Retriever + QASem SlotDiff
                      </div>
                      <div className="cg-tier-sub">
                        BM25 + Dense Cosine RRF · ONNX INT8 NLI · Conformal α ={" "}
                        {conformalAlpha.toFixed(2)}
                      </div>
                    </div>
                  </div>
                  <code className="cg-tier-latency">31.6 ms</code>
                </div>

                <div className="cg-telemetry-row cg-stagger-4">
                  <div className="cg-telemetry-tier">
                    <span className="cg-tier-dot tier-3" />
                    <div>
                      <div className="cg-tier-name">
                        Tier 3 · DPDP PII Vault + Surgical Rewriter
                      </div>
                      <div className="cg-tier-sub">
                        Local Presidio/regex masking (
                        {currentScenario.piiMaskedCount} tokens) · edit_ratio{" "}
                        {currentScenario.editRatio}
                      </div>
                    </div>
                  </div>
                  <code
                    className={`cg-tier-latency ${
                      isRepaired ? "cg-latency-repaired" : ""
                    }`}
                  >
                    {isRepaired ? "APPLIED" : "READY"}
                  </code>
                </div>
              </div>

              {/* Animated Conformal Risk Threshold Meter */}
              <div className="cg-conformal-meter-wrap">
                <div className="cg-conformal-meter-labels">
                  <span>
                    Conformal Quantile Threshold{" "}
                    <code>
                      λ̂(α={conformalAlpha.toFixed(2)}) ={" "}
                      {conformalLambda.toFixed(2)}
                    </code>
                  </span>
                  <span>
                    {calibratedFindings.length} /{" "}
                    {currentScenario.findings.length} checks active
                  </span>
                </div>
                <div className="cg-conformal-meter-track">
                  <div
                    className="cg-conformal-meter-fill"
                    style={{
                      transform: `scaleX(${conformalLambda})`,
                    }}
                  />
                </div>
              </div>

              <div className="cg-telemetry-footer">
                <div className="cg-telemetry-hash-col">
                  <span className="cg-mono-label">CANON SHA-256</span>
                  <code>{currentScenario.hashes.canonHash}…</code>
                </div>
                <div className="cg-telemetry-hash-col">
                  <span className="cg-mono-label">BUNDLE SHA-256</span>
                  <code>
                    {isRepaired
                      ? currentScenario.hashes.repairedHash
                      : currentScenario.hashes.draftHash}
                    …
                  </code>
                </div>
                <div className="cg-telemetry-hash-col">
                  <span className="cg-mono-label">CONFORMAL λ̂(α)</span>
                  <code>{conformalLambda.toFixed(2)}</code>
                </div>
              </div>
            </aside>
          </div>

          {/* ── Interactive Multi-Modal Pre-Publish Workbench ── */}
          <div id="workbench" className="cg-workbench-shell">
            {/* Workbench Top Chrome */}
            <div className="cg-workbench-bar">
              <div className="cg-workbench-tabs" role="tablist">
                {WORKBENCH_SCENARIOS.map((scen) => (
                  <button
                    key={scen.id}
                    type="button"
                    role="tab"
                    aria-selected={scenarioId === scen.id}
                    className={`cg-workbench-tab ${
                      scenarioId === scen.id ? "active" : ""
                    }`}
                    onClick={() => {
                      setScenarioId(scen.id);
                      setSelectedFindingIdx(0);
                      setIsRepaired(false);
                      setSelectedSwatchHex(null);
                      triggerScanSweep();
                    }}
                  >
                    <span className="cg-tab-canon">{scen.canonId}.yaml</span>
                    <span className="cg-tab-sector">{scen.sectorTag}</span>
                  </button>
                ))}
              </div>

              <div className="cg-workbench-controls">
                {/* Conformal Alpha Selector */}
                <div
                  className="cg-alpha-control"
                  title="Distribution-free Conformal Risk Control (Angelopoulos et al., 2024)"
                >
                  <Sliders size={13} />
                  <span>Conformal Risk α:</span>
                  {[0.05, 0.1, 0.2].map((val) => (
                    <button
                      key={val}
                      type="button"
                      className={`cg-alpha-btn ${
                        Math.abs(conformalAlpha - val) < 0.001 ? "active" : ""
                      }`}
                      onClick={() => {
                        setConformalAlpha(val);
                        setTracePulseKey((prev) => prev + 1);
                      }}
                    >
                      {val.toFixed(2)}
                    </button>
                  ))}
                </div>

                {/* Live Surgical Rewrite Toggle */}
                <button
                  type="button"
                  className={`cg-surgical-toggle-btn ${
                    isRepaired ? "repaired" : ""
                  }`}
                  onClick={() => {
                    setIsRepaired((prev) => !prev);
                    if (isRepaired) {
                      setSelectedSwatchHex(null);
                    }
                    triggerScanSweep();
                  }}
                >
                  <Wand2 size={14} />
                  <span>
                    {isRepaired
                      ? "Showing Repaired Bundle (Revert to Draft)"
                      : "Apply Surgical Fix (≤35% Edit)"}
                  </span>
                </button>
              </div>
            </div>

            {/* Workbench 3-Pane Studio Body */}
            <div className="cg-workbench-grid">
              {/* Pane 1: Multi-Modal Asset Canvas (Copy + Visual Ad Banner) */}
              <div
                key={`${currentScenario.id}-${isRepaired ? "rep" : "raw"}`}
                className="cg-workbench-pane cg-pane-canvas cg-animate-swap"
              >
                {/* GPU-composited verification scanline sweep */}
                <div
                  key={scanPulseKey}
                  className="cg-scanline-sweep"
                  aria-hidden="true"
                />

                <div className="cg-pane-header">
                  <div>
                    <span className="cg-mono-label">
                      MULTI-MODAL ASSET CANVAS · {currentScenario.assetName}
                    </span>
                    <h3 className="cg-pane-title">{currentScenario.title}</h3>
                  </div>
                  <span
                    className={`cg-status-chip ${
                      isRepaired ? "chip-pass" : "chip-fail"
                    }`}
                  >
                    {isRepaired
                      ? `0 Blockers · Edit Ratio ${currentScenario.editRatio}`
                      : `${blockerCount} Blockers Flagged`}
                  </span>
                </div>

                {/* ProseMirror Copy Surface */}
                <div className="cg-prosemirror-surface">
                  <div className="cg-surface-subbar">
                    <span>TEXT AST NODE · paragraph[0]</span>
                    <span>
                      DPDP PII Vault: {currentScenario.piiMaskedCount} tokens
                      scrubbed locally
                    </span>
                  </div>

                  {!isRepaired ? (
                    <p className="cg-copy-paragraph">
                      {currentScenario.draftCopyParts.prefix}
                      <button
                        type="button"
                        className={`cg-inline-finding-span span-blocker ${
                          selectedFindingIdx === 0 ? "selected" : ""
                        }`}
                        onClick={() => setSelectedFindingIdx(0)}
                      >
                        <span className="cg-pin-tag">C1</span>
                        {currentScenario.draftCopyParts.span1}
                      </button>
                      {currentScenario.draftCopyParts.mid}
                      <button
                        type="button"
                        className={`cg-inline-finding-span span-blocker ${
                          selectedFindingIdx === 1 ? "selected" : ""
                        }`}
                        onClick={() => setSelectedFindingIdx(1)}
                      >
                        <span className="cg-pin-tag">
                          {currentScenario.findings[1]?.pinLabel ?? "C2"}
                        </span>
                        {currentScenario.draftCopyParts.span2}
                      </button>
                      {currentScenario.draftCopyParts.suffix}
                    </p>
                  ) : (
                    <p className="cg-copy-paragraph">
                      {currentScenario.repairedCopyParts.prefix}
                      <span className="cg-inline-finding-span span-repaired">
                        <Check size={12} />
                        {currentScenario.repairedCopyParts.span1}
                      </span>
                      {currentScenario.repairedCopyParts.mid}
                      <span className="cg-inline-finding-span span-repaired">
                        <Check size={12} />
                        {currentScenario.repairedCopyParts.span2}
                      </span>
                      {currentScenario.repairedCopyParts.suffix}
                    </p>
                  )}
                </div>

                {/* Simulated 1080p Campaign Banner Canvas with Interactive Bounding Boxes */}
                <div className="cg-banner-stage-wrap">
                  <div className="cg-surface-subbar">
                    <span>
                      IMAGE AST NODE · 1920×1080 BANNER (OpenCV + Sobel/Otsu
                      ROI)
                    </span>
                    <span>Click pin [V1] or swatches to test contrast</span>
                  </div>

                  <div
                    className="cg-simulated-banner"
                    style={{ backgroundColor: currentScenario.banner.bgHex }}
                  >
                    {/* Header Bar of Simulated Banner */}
                    <div
                      className="cg-sim-banner-header"
                      style={{ backgroundColor: activeBannerAccentHex }}
                    >
                      <div className="cg-sim-logo-box">
                        <span>⛨ ACME</span>
                        <span className="cg-sim-collar-tag">
                          ORB Collar ≥ 0.50H
                        </span>
                      </div>
                      <span className="cg-sim-kfs-pill">
                        {currentScenario.banner.kfsBadge}
                      </span>
                    </div>

                    {/* Main Headline of Simulated Banner */}
                    <div className="cg-sim-banner-body">
                      <div className="cg-sim-banner-headline">
                        {currentScenario.banner.headline}
                      </div>
                      <div className="cg-sim-banner-subline">
                        {currentScenario.banner.subline}
                      </div>
                    </div>

                    {/* Disclaimer Region with Interactive BBox Overlay */}
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() =>
                        setSelectedFindingIdx(
                          currentScenario.findings.length - 1,
                        )
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          setSelectedFindingIdx(
                            currentScenario.findings.length - 1,
                          );
                        }
                      }}
                      className={`cg-sim-banner-disclaimer ${
                        !isRepaired && !selectedSwatchHex
                          ? "bbox-flagged"
                          : "bbox-repaired"
                      } ${
                        selectedFindingIdx ===
                        currentScenario.findings.length - 1
                          ? "bbox-selected"
                          : ""
                      }`}
                      style={{ color: activeBannerFgHex }}
                    >
                      <span className="cg-bbox-pin-badge">
                        {!isRepaired && !selectedSwatchHex
                          ? "V1 · WCAG FAIL"
                          : `V1 · ${activeBannerFgHex} PASS`}
                      </span>
                      <span>
                        {isRepaired || selectedSwatchHex
                          ? currentScenario.banner.disclaimerFixed
                          : currentScenario.banner.disclaimerDraft}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Pane 2: Active Finding Inspector (SlotDiff, Z3 Proof & WCAG Swatches) */}
              <div className="cg-workbench-pane cg-pane-inspector">
                <div className="cg-pane-header">
                  <div>
                    <span className="cg-mono-label">
                      EVIDENCE INSPECTOR · CLICK ANY FINDING
                    </span>
                    <h3 className="cg-pane-title">
                      Mathematical &amp; Semantic Grounding
                    </h3>
                  </div>
                </div>

                {/* Finding Selector Pills */}
                <div className="cg-finding-selector-row">
                  {currentScenario.findings.map((f, idx) => (
                    <button
                      key={f.id}
                      type="button"
                      className={`cg-finding-tab-pill ${
                        selectedFindingIdx === idx ? "active" : ""
                      } ${isRepaired ? "resolved" : f.severity}`}
                      onClick={() => setSelectedFindingIdx(idx)}
                    >
                      <span className="cg-pin-circle">{f.pinLabel}</span>
                      <span>{f.checkId.replace("check.", "")}</span>
                      <code>{f.riskScore.toFixed(2)}</code>
                    </button>
                  ))}
                </div>

                {/* Active Finding Detail Card (Keyed for snappy 180ms transition) */}
                <div
                  key={`${activeFinding.id}-${isRepaired ? "rep" : "raw"}`}
                  className="cg-inspector-card cg-animate-swap"
                >
                  <div className="cg-inspector-top">
                    <span
                      className={`cg-sev-badge ${
                        isRepaired
                          ? "sev-pass"
                          : `sev-${activeFinding.severity}`
                      }`}
                    >
                      {isRepaired
                        ? "RESOLVED"
                        : activeFinding.severity.toUpperCase()}
                    </span>
                    <code className="cg-rule-code">
                      {activeFinding.ruleRef}
                    </code>
                    <span className="cg-tier-tag">{activeFinding.tier}</span>
                  </div>

                  <h4 className="cg-inspector-title">{activeFinding.title}</h4>
                  <p className="cg-inspector-desc">
                    {activeFinding.explanation}
                  </p>

                  {/* Conditional Evidence 1: QASem 4-Column SlotDiff Matrix */}
                  {activeFinding.slotDiff && (
                    <div className="cg-evidence-block">
                      <div className="cg-evidence-header">
                        <span>
                          QASem Predicate-Argument <code>SlotDiff</code> Matrix
                        </span>
                        <code>Tang et al. / Klein et al.</code>
                      </div>
                      <table className="cg-slotdiff-table">
                        <thead>
                          <tr>
                            <th>Semantic Slot</th>
                            <th>Draft Span</th>
                            <th>Canon Fact</th>
                            <th>Alignment</th>
                          </tr>
                        </thead>
                        <tbody>
                          {activeFinding.slotDiff.map((row) => (
                            <tr key={row.slot}>
                              <td>
                                <code>{row.slot}</code>
                              </td>
                              <td>{isRepaired ? row.canon : row.draft}</td>
                              <td>{row.canon}</td>
                              <td>
                                <span
                                  className={`cg-slot-badge slot-${
                                    isRepaired
                                      ? "match"
                                      : row.status.toLowerCase()
                                  }`}
                                >
                                  {isRepaired ? "MATCH" : row.status}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Conditional Evidence 2: Z3 SMT Algebraic Proof */}
                  {activeFinding.z3Proof && (
                    <div className="cg-evidence-block cg-z3-block">
                      <div className="cg-evidence-header">
                        <span>SymPy + Z3 SMT Algebraic Counterexample</span>
                        <code>QF_NRA Solver</code>
                      </div>
                      <div className="cg-z3-grid">
                        <div>
                          <span className="cg-mono-label">STATED IN DRAFT</span>
                          <strong className="cg-z3-bad">
                            {activeFinding.z3Proof.statedValue}
                          </strong>
                        </div>
                        <div>
                          <span className="cg-mono-label">
                            Z3 SOLVED GROUND TRUTH
                          </span>
                          <strong className="cg-z3-good">
                            {activeFinding.z3Proof.solvedValue}
                          </strong>
                        </div>
                      </div>
                      <pre className="cg-z3-code">
                        {activeFinding.z3Proof.counterexample}
                      </pre>
                    </div>
                  )}

                  {/* Conditional Evidence 3: 3-Candidate DesignAlternativeProvider Swatches */}
                  {activeFinding.swatches && (
                    <div className="cg-evidence-block">
                      <div className="cg-evidence-header">
                        <span>
                          DesignAlternativeProvider · Click Swatch to Preview
                        </span>
                        <code>Bisection L* Solver</code>
                      </div>
                      <div className="cg-swatch-grid">
                        {activeFinding.swatches.map((sw) => (
                          <button
                            key={sw.hex}
                            type="button"
                            className={`cg-swatch-card ${
                              activeBannerFgHex === sw.hex ? "active" : ""
                            }`}
                            onClick={() => {
                              setSelectedSwatchHex(sw.hex);
                              triggerScanSweep();
                            }}
                          >
                            <div className="cg-swatch-top">
                              <span
                                className="cg-swatch-chip"
                                style={{ backgroundColor: sw.hex }}
                              />
                              <code>{sw.hex}</code>
                              <span className="cg-swatch-pass">{sw.badge}</span>
                            </div>
                            <div className="cg-swatch-label">{sw.label}</div>
                            <div className="cg-swatch-meta">
                              <span>Contrast {sw.ratio}</span>
                              <span>{sw.deltaE}</span>
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Before / After Surgical Diff Box */}
                  <div className="cg-diff-preview-box">
                    <div className="cg-diff-line diff-removed">
                      <span className="cg-diff-sign">−</span>
                      <span>{activeFinding.flaggedSpan}</span>
                    </div>
                    <div className="cg-diff-line diff-added">
                      <span className="cg-diff-sign">+</span>
                      <span>{activeFinding.repairedSpan}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Pane 3: Cryptographic Release Ledger & Merkle Certificate */}
              <div className="cg-workbench-pane cg-pane-ledger">
                <div className="cg-pane-header">
                  <div>
                    <span className="cg-mono-label">
                      RELEASE LEDGER · RFC 9162 MERKLE
                    </span>
                    <h3 className="cg-pane-title">
                      Cryptographic Provenance
                    </h3>
                  </div>
                </div>

                <div
                  key={blockerCount === 0 ? "seal-ready" : "seal-blocked"}
                  className={`cg-release-seal-card cg-animate-swap ${
                    blockerCount === 0 ? "seal-ready" : "seal-blocked"
                  }`}
                >
                  <div className="cg-seal-status-row">
                    {blockerCount === 0 ? (
                      <CheckCircle2
                        size={20}
                        className="cg-seal-icon-pass cg-icon-pop"
                      />
                    ) : (
                      <ShieldAlert
                        size={20}
                        className="cg-seal-icon-block cg-icon-pop"
                      />
                    )}
                    <div>
                      <div className="cg-seal-title">
                        {blockerCount === 0
                          ? "Release Certificate Verified"
                          : "Publication Gate Locked"}
                      </div>
                      <div className="cg-seal-sub">
                        {blockerCount === 0
                          ? "All Blockers resolved · Ed25519 + C2PA 2.2 signed"
                          : `Resolve ${blockerCount} active Blocker(s) or toggle Surgical Fix`}
                      </div>
                    </div>
                  </div>

                  <div className="cg-ledger-kv-list">
                    <div className="cg-ledger-kv">
                      <span>Playbook Canon</span>
                      <code>
                        {currentScenario.canonId}@{currentScenario.canonVersion}
                      </code>
                    </div>
                    <div className="cg-ledger-kv">
                      <span>Canon SHA-256</span>
                      <code>{currentScenario.hashes.canonHash}…</code>
                    </div>
                    <div className="cg-ledger-kv">
                      <span>Content AST SHA-256</span>
                      <code>
                        {isRepaired
                          ? currentScenario.hashes.repairedHash
                          : currentScenario.hashes.draftHash}
                        …
                      </code>
                    </div>
                    <div className="cg-ledger-kv">
                      <span>RFC 9162 Merkle Root</span>
                      <code>
                        {currentScenario.hashes.merkleRoot.slice(0, 16)}…
                      </code>
                    </div>
                    <div className="cg-ledger-kv">
                      <span>Ed25519 Signature</span>
                      <code>
                        {blockerCount === 0
                          ? currentScenario.hashes.ed25519Sig
                          : "PENDING_STAGE_3_SIGNOFF"}
                      </code>
                    </div>
                  </div>

                  <div className="cg-ledger-actions">
                    {!isRepaired ? (
                      <button
                        type="button"
                        className="cg-btn cg-btn-primary cg-btn-full"
                        onClick={() => {
                          setIsRepaired(true);
                          triggerScanSweep();
                        }}
                      >
                        <Wand2 size={14} />
                        <span>Apply Surgical Repair &amp; Re-Verify</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="cg-btn cg-btn-emerald cg-btn-full"
                        onClick={() =>
                          void handleQuickPersonaLaunch("creative_lead")
                        }
                      >
                        <FileCheck2 size={14} />
                        <span>Inspect Full Bundle in Review Studio →</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Mini Audit Trail Timeline */}
                <div className="cg-mini-audit-log">
                  <div className="cg-mono-label">
                    HASH-CHAINED LEDGER EVENTS
                  </div>
                  <div className="cg-mini-audit-item">
                    <span className="cg-audit-step">01</span>
                    <div>
                      <strong>ContentAST Parsed &amp; Hashed</strong>
                      <p>
                        Normalized NFC text + 1080p banner Sobel/Otsu regions
                      </p>
                    </div>
                  </div>
                  <div className="cg-mini-audit-item">
                    <span className="cg-audit-step">02</span>
                    <div>
                      <strong>
                        Conformal Risk Calibration (α ={" "}
                        {conformalAlpha.toFixed(2)})
                      </strong>
                      <p>
                        Empirical quantile threshold λ̂ ={" "}
                        {conformalLambda.toFixed(2)} applied
                      </p>
                    </div>
                  </div>
                  <div className="cg-mini-audit-item">
                    <span className="cg-audit-step">03</span>
                    <div>
                      <strong>
                        {isRepaired
                          ? "Tier 3 Surgical Rewrite Verified"
                          : "Awaiting Creator Resolution"}
                      </strong>
                      <p>
                        {isRepaired
                          ? `Levenshtein edit_ratio ${currentScenario.editRatio} · 0 new violations`
                          : "Click 'Apply Surgical Fix' to preview automated repair"}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Asymmetric 12-Column Architectural Bento Grid (#architecture) ── */}
      <section id="architecture" className="cg-section cg-section-bordered">
        <div className="cg-container">
          <div className="cg-section-header-split">
            <div>
              <span className="cg-mono-eyebrow">
                01 / THREE-TIER VERIFICATION ARCHITECTURE
              </span>
              <h2 className="cg-section-heading">
                Built on deterministic math, formal SMT proofs, and{" "}
                <span className="cg-serif-italic">calibrated</span> NLI.
              </h2>
            </div>
            <p className="cg-section-lead">
              Generic LLM wrappers hallucinate compliance verdicts and miss
              pixel-level visual violations. CanonGate executes an asynchronous
              DAG of 9 specialized verifiers where every finding is backed by a
              reproducible mathematical witness.
            </p>
          </div>

          <div className="cg-bento-grid">
            {/* Bento Cell 1 (7 Cols): Tier 1 Computer Vision & Colorimetry */}
            <article className="cg-bento-cell cg-bento-span-7">
              <div className="cg-bento-top">
                <span className="cg-bento-tier-pill">
                  <Eye size={13} /> TIER 1 · COMPUTER VISION &amp; COLORIMETRY
                </span>
                <code>checks/visual_*.py</code>
              </div>
              <h3 className="cg-bento-title">
                Perceptual CIEDE2000 (ΔE₀₀), W3C Relative Luminance &amp; ORB
                Homography
              </h3>
              <p className="cg-bento-desc">
                Audits 1080p campaign banners without sending images to cloud
                VLM APIs. Extracts dominant K-Means swatches in CIE{" "}
                <code>L*a*b*</code> space, segments text bounding boxes via
                Sobel gradients + Otsu thresholding, and verifies{" "}
                <code>0.5H</code> logo clear-space collars using OpenCV ORB
                keypoint RANSAC homography.
              </p>

              {/* Interactive Visual Specimen inside Cell 1 */}
              <div className="cg-bento-specimen">
                <div className="cg-specimen-row">
                  <div className="cg-colorimeter-pair">
                    <div className="cg-color-chip-box">
                      <span
                        className="cg-color-circle"
                        style={{
                          backgroundColor: bentoSnappedPalette
                            ? "#0D3B66"
                            : "#1E6091",
                        }}
                      />
                      <div>
                        <code>
                          {bentoSnappedPalette ? "#0D3B66" : "#1E6091"}
                        </code>
                        <span>Sampled Banner ROI</span>
                      </div>
                    </div>

                    <button
                      type="button"
                      className={`cg-delta-arrow ${
                        bentoSnappedPalette ? "delta-pass" : ""
                      }`}
                      onClick={() => setBentoSnappedPalette((prev) => !prev)}
                      title="Click to test snapping off-brand swatch to Canon token"
                    >
                      {bentoSnappedPalette
                        ? "ΔE₀₀ = 0.00 ≤ 3.0 (PASS · Click to Reset)"
                        : "ΔE₀₀ = 6.42 > 3.0 (Click to Snap Token)"}
                    </button>

                    <div className="cg-color-chip-box">
                      <span
                        className="cg-color-circle"
                        style={{ backgroundColor: "#0D3B66" }}
                      />
                      <div>
                        <code>#0D3B66</code>
                        <span>Canon Brand Token</span>
                      </div>
                    </div>
                  </div>
                  <div className="cg-luminance-formula">
                    <span className="cg-mono-label">WCAG 2.1 LUMINANCE</span>
                    <code>L = 0.2126·R + 0.7152·G + 0.0722·B</code>
                  </div>
                </div>
              </div>
            </article>

            {/* Bento Cell 2 (5 Cols): Tier 1.5 SymPy + Z3 Algebraic Verifier */}
            <article className="cg-bento-cell cg-bento-span-5">
              <div className="cg-bento-top">
                <span className="cg-bento-tier-pill">
                  <Scale size={13} /> TIER 1.5 · FORMAL SMT SOLVER
                </span>
                <code>checks/numeric_consistency.py</code>
              </div>
              <h3 className="cg-bento-title">
                SymPy + Z3 Algebraic KFS &amp; APR Verification
              </h3>
              <p className="cg-bento-desc">
                Translates financial tables, percentage claims, and RBI 2025 Key
                Fact Statements into quantifier-free nonlinear real arithmetic (
                <code>QF_NRA</code>) constraints—proving when stated APRs or fee
                totals are mathematically impossible.
              </p>

              <div className="cg-bento-specimen cg-specimen-dark">
                <div className="cg-specimen-code-header">
                  <span>Z3 SMT-LIBv2 Proof Trace</span>
                  <button
                    type="button"
                    className={`cg-badge-unsat ${
                      bentoZ3Reconciled ? "z3-sat" : ""
                    }`}
                    onClick={() => setBentoZ3Reconciled((prev) => !prev)}
                    title="Click to toggle between Contradicted and Reconciled KFS APR"
                  >
                    {bentoZ3Reconciled
                      ? "SAT · KFS RECONCILED (Click to Toggle)"
                      : "CONTRADICTION PROVED (Click to Fix APR)"}
                  </button>
                </div>
                <pre className="cg-specimen-pre">
                  {bentoZ3Reconciled
                    ? `(declare-const APR Real)
(assert (= Principal 50000.0))
(assert (= UpfrontFee 1500.0))
(assert (= Interest 3500.0))
(assert (= StatedAPR 0.2818))
; Solved Effective APR = 0.2818 == 0.2818 (VALID)`
                    : `(declare-const APR Real)
(assert (= Principal 50000.0))
(assert (= UpfrontFee 1500.0))
(assert (= Interest 3500.0))
(assert (= StatedAPR 0.1400))
; Solved Effective APR = 0.2818 != 0.1400`}
                  <span className="cg-terminal-cursor" aria-hidden="true" />
                </pre>
              </div>
            </article>

            {/* Bento Cell 3 (5 Cols): Tier 2 Hybrid Retrieval + QASem SlotDiff */}
            <article className="cg-bento-cell cg-bento-span-5">
              <div className="cg-bento-top">
                <span className="cg-bento-tier-pill">
                  <Layers size={13} /> TIER 2 · SEMANTIC SLOT ALIGNMENT
                </span>
                <code>engine/nlp.py · conformal.py</code>
              </div>
              <h3 className="cg-bento-title">
                Hybrid BM25 + Dense RRF &amp; QASem <code>SlotDiff</code>
              </h3>
              <p className="cg-bento-desc">
                Standard cosine similarity passes misleading claims that drop
                eligibility caps. CanonGate decomposes claims into{" "}
                <code>(metric, ceiling, cohort, condition)</code> slots and
                wraps ONNX INT8 NLI scores in distribution-free Conformal Risk
                Control (<var>α</var> = 0.10).
              </p>

              <div className="cg-bento-specimen">
                <div className="cg-mini-slot-list">
                  <div className="cg-mini-slot-item">
                    <code>slot:metric</code>
                    <span>&quot;0% interest&quot;</span>
                    <span className="cg-slot-badge slot-match">MATCH</span>
                  </div>
                  <div className="cg-mini-slot-item">
                    <code>slot:ceiling</code>
                    <span>&quot;under ₹50,000&quot;</span>
                    <span className="cg-slot-badge slot-dropped">DROPPED</span>
                  </div>
                  <div className="cg-mini-slot-item">
                    <code>slot:cohort</code>
                    <span>&quot;first-time borrowers&quot;</span>
                    <span className="cg-slot-badge slot-dropped">DROPPED</span>
                  </div>
                </div>
              </div>
            </article>

            {/* Bento Cell 4 (7 Cols): Tier 3 DPDP PII Vault + Constrained Surgical Rewriter */}
            <article className="cg-bento-cell cg-bento-span-7">
              <div className="cg-bento-top">
                <span className="cg-bento-tier-pill">
                  <Lock size={13} /> TIER 3 · DPDP PII VAULT &amp; SURGICAL
                  REWRITER
                </span>
                <code>domain/pii.py · engine/rewriter.py</code>
              </div>
              <h3 className="cg-bento-title">
                Zero-Trust PII Tokenization &amp; Bounded Levenshtein Repair (
                <code>≤35%</code>)
              </h3>
              <p className="cg-bento-desc">
                Before any optional cloud LLM call, <code>PiiVault</code>{" "}
                scrubs Indian statutory identifiers (Aadhaar, PAN, GSTIN, UPI
                VPA, phone, email) into local reversible placeholders. Every
                proposed fix must pass a strict{" "}
                <code>edit_ratio ≤ 0.35</code> bound and re-run Tier 1 + Tier 2
                checks to guarantee zero new violations.
              </p>

              <div className="cg-bento-specimen">
                <div className="cg-pii-pipeline-strip">
                  <div className="cg-pii-step">
                    <span className="cg-mono-label">1. LOCAL SCRUB</span>
                    <code>PAN: ABCDE1234F → &lt;PAN_ID_1&gt;</code>
                  </div>
                  <ArrowRight
                    size={14}
                    className="cg-pii-arrow cg-flow-pulse"
                  />
                  <div className="cg-pii-step">
                    <span className="cg-mono-label">2. BOUNDED DIFF</span>
                    <code>edit_ratio = 0.21 ≤ 0.35</code>
                  </div>
                  <ArrowRight
                    size={14}
                    className="cg-pii-arrow cg-flow-pulse"
                  />
                  <div className="cg-pii-step">
                    <span className="cg-mono-label">3. RE-VERIFY</span>
                    <code className="cg-text-emerald">
                      0 Blockers · Restored
                    </code>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>

      {/* ── Interactive 4-Stage Role-Gated Governance Pipeline (#workflow) ── */}
      <section id="workflow" className="cg-section cg-section-subtle">
        <div className="cg-container">
          <div className="cg-section-header-split">
            <div>
              <span className="cg-mono-eyebrow">
                02 / HUMAN-IN-THE-LOOP RBAC &amp; FEEDBACK LOOP
              </span>
              <h2 className="cg-section-heading">
                Role-separated state machine with{" "}
                <span className="cg-serif-italic">cryptographic</span>{" "}
                accountability.
              </h2>
            </div>
            <p className="cg-section-lead">
              Governance fails when creators can silently dismiss compliance
              flags or when brittle rules bottleneck legal teams. CanonGate
              enforces strict separation of duties across three roles while
              automatically turning high-friction rules into Canon v1.1 pull
              requests.
            </p>
          </div>

          <div className="cg-workflow-explorer">
            {/* Stage Selector Tabs */}
            <div className="cg-stage-tabs">
              {WORKFLOW_STAGE_SPECS.map((item, idx) => (
                <button
                  key={item.stage}
                  type="button"
                  className={`cg-stage-tab-card ${
                    activeStageIdx === idx ? "active" : ""
                  }`}
                  onClick={() => setActiveStageIdx(idx)}
                >
                  <div className="cg-stage-tab-top">
                    <span className="cg-stage-num">{item.stage}</span>
                    <code className="cg-stage-status">{item.statusTag}</code>
                  </div>
                  <div className="cg-stage-tab-title">{item.title}</div>
                  <div className="cg-stage-tab-role">{item.roleLabel}</div>
                </button>
              ))}
            </div>

            {/* Active Stage Detail Panel (Keyed for snappy 180ms transition) */}
            <div
              key={activeStageIdx}
              className="cg-stage-detail-card cg-animate-swap"
            >
              <div className="cg-stage-detail-main">
                <div className="cg-stage-detail-eyebrow">
                  <span>{WORKFLOW_STAGE_SPECS[activeStageIdx].stage}</span>
                  <span>·</span>
                  <code>{WORKFLOW_STAGE_SPECS[activeStageIdx].roleLabel}</code>
                </div>
                <h3>{WORKFLOW_STAGE_SPECS[activeStageIdx].title}</h3>
                <p>{WORKFLOW_STAGE_SPECS[activeStageIdx].summary}</p>

                <ul className="cg-stage-gate-list">
                  {WORKFLOW_STAGE_SPECS[activeStageIdx].gates.map((g) => (
                    <li key={g}>
                      <CheckCircle2 size={15} className="cg-check-icon" />
                      <span>{g}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="cg-stage-detail-aside">
                <div className="cg-friction-preview-box">
                  <div className="cg-friction-header">
                    <GitPullRequest size={15} />
                    <span>Closed-Loop Rule Calibration</span>
                  </div>
                  <p>
                    When reviewers repeatedly override a brittle rule (override
                    rate &gt; 30%), CanonGate computes vectorized{" "}
                    <strong>Krippendorff&apos;s α</strong> inter-reviewer
                    reliability and drafts a 1-click{" "}
                    <code>Canon v1.1 YAML PR</code> with historical blast-radius
                    simulation.
                  </p>
                  <button
                    type="button"
                    className="cg-btn cg-btn-primary cg-btn-full"
                    onClick={() =>
                      void handleQuickPersonaLaunch(
                        WORKFLOW_STAGE_SPECS[activeStageIdx].username,
                      )
                    }
                  >
                    <span>
                      Launch Workspace as @
                      {WORKFLOW_STAGE_SPECS[activeStageIdx].username}
                    </span>
                    <ArrowRight size={15} className="cg-arrow-shift" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Interactive Statutory Playbooks & Developer CLI / MCP Hub (#developers) ── */}
      <section id="developers" className="cg-section cg-section-bordered">
        <div className="cg-container">
          <div className="cg-section-header-split">
            <div>
              <span className="cg-mono-eyebrow">
                03 / STATUTORY PLAYBOOKS, CLI &amp; FASTMCP 3.0
              </span>
              <h2 className="cg-section-heading">
                Version-controlled YAML canons and{" "}
                <span className="cg-serif-italic">headless</span> CI/CD gates.
              </h2>
            </div>
            <p className="cg-section-lead">
              Ingest raw PDF/DOCX brand guidelines via Pipeline A or use
              pre-built Indian statutory packs. Enforce the exact same canon in
              the web studio, GitHub Actions, Shopify/Webflow webhooks, or
              autonomous MCP agents.
            </p>
          </div>

          <div className="cg-dev-split-grid">
            {/* Left Column: Compiled Canon YAML Explorer */}
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
                  <span
                    key={copiedId === "yaml-copy" ? "copied" : "copy"}
                    className="cg-icon-pop"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.3rem",
                    }}
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
                  </span>
                </button>
              </div>

              <div
                key={activePlaybookKey}
                className="cg-code-body-wrap cg-animate-swap"
              >
                <div className="cg-code-meta-strip">
                  <span>
                    <strong>
                      {PLAYBOOK_YAML_SAMPLES[activePlaybookKey].title}
                    </strong>{" "}
                    · {PLAYBOOK_YAML_SAMPLES[activePlaybookKey].authority}
                  </span>
                  <code>
                    {PLAYBOOK_YAML_SAMPLES[activePlaybookKey].rulesCount}{" "}
                    compiled rules
                  </code>
                </div>

                <pre className="cg-code-pre">
                  <code>{PLAYBOOK_YAML_SAMPLES[activePlaybookKey].yaml}</code>
                </pre>
              </div>
            </div>

            {/* Right Column: CLI, GitHub Actions, FastMCP & Webhook Terminal */}
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
                  <span
                    key={copiedId === "dev-copy" ? "copied" : "copy"}
                    className="cg-icon-pop"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.3rem",
                    }}
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
                  </span>
                </button>
              </div>

              <div
                key={activeDevTab}
                className="cg-code-body-wrap cg-animate-swap"
              >
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

      {/* ── Architectural Footer ── */}
      <footer className="cg-footer">
        <div className="cg-container cg-footer-inner">
          <div className="cg-footer-left">
            <div className="cg-brand">
              <span className="cg-brand-mark" aria-hidden="true">
                <ShieldCheck size={16} strokeWidth={2.2} />
              </span>
              <span className="cg-brand-name">CanonGate</span>
              <span className="cg-brand-version">
                Pre-Publication Governance Platform
              </span>
            </div>
            <p className="cg-footer-note">
              Deterministic AST &amp; OpenCV Vision · SymPy + Z3 Algebraic KFS ·
              QASem SlotDiff · Conformal Risk Control · RFC 9162 Merkle + C2PA
              2.2 Provenance.
            </p>
          </div>

          <div className="cg-footer-actions">
            <a href="#workbench" className="cg-footer-link">
              Workbench
            </a>
            <a href="#architecture" className="cg-footer-link">
              Architecture
            </a>
            <a href="#workflow" className="cg-footer-link">
              RBAC Workflow
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
