#set page(
  paper: "presentation-16-9",
  margin: (x: 1.8cm, top: 1.4cm, bottom: 1.2cm),
  fill: rgb("#0A0F1D"),
)
#set text(
  font: ("Inter", "DejaVu Sans", "Liberation Sans"),
  fill: rgb("#F8FAFC"),
  size: 11pt,
)

#let brand-cyan = rgb("#06B6D4")
#let brand-blue = rgb("#3B82F6")
#let brand-purple = rgb("#8B5CF6")
#let brand-emerald = rgb("#10B981")
#let brand-amber = rgb("#F59E0B")
#let brand-rose = rgb("#F43F5E")
#let card-bg = rgb("#111827")
#let card-border = rgb("#1E293B")
#let text-muted = rgb("#94A3B8")

#let slide-header(category: "CanonGate Platform", title: "") = [
  #grid(
    columns: (1fr, auto),
    align: (left + horizon, right + horizon),
    [
      #text(size: 9pt, weight: "bold", fill: brand-cyan, upper(category))\
      #v(1pt)
      #text(size: 20pt, weight: "bold", fill: rgb("#FFFFFF"), title)
    ],
    [
      #box(
        fill: brand-cyan.transparentize(88%),
        stroke: 0.5pt + brand-cyan,
        radius: 4pt,
        inset: (x: 6pt, y: 3pt),
        text(size: 8pt, weight: "bold", fill: brand-cyan, "CanonGate • Confidential")
      )
    ]
  )
  #v(6pt)
  #line(length: 100%, stroke: 0.5pt + rgb("#334155"))
  #v(12pt)
]

#let slide-footer(current: 1, total: 12) = [
  #place(
    bottom + left,
    dy: 0pt,
    block(
      width: 100%,
      [
        #line(length: 100%, stroke: 0.5pt + rgb("#1E293B"))
        #v(4pt)
        #grid(
          columns: (1fr, auto),
          text(size: 7.5pt, fill: text-muted, "CanonGate — Autonomous Pre-Publication Brand & Regulatory Governance"),
          text(size: 7.5pt, fill: text-muted, str(current) + " / " + str(total))
        )
      ]
    )
  )
]

#let card(title: "", color: brand-cyan, content) = {
  block(
    stroke: 1pt + card-border,
    fill: card-bg,
    radius: 7pt,
    inset: 12pt,
    width: 100%,
    [
      #if title != "" [
        #text(weight: "bold", size: 12pt, fill: color, title)
        #v(6pt)
      ]
      #content
    ]
  )
}

#let subbox(title: "", content) = {
  block(
    stroke: 0.5pt + rgb("#334155"),
    fill: rgb("#1E293B"),
    radius: 5pt,
    inset: 8pt,
    width: 100%,
    [
      #if title != "" [
        #text(weight: "bold", size: 9pt, fill: rgb("#E2E8F0"), title)
        #v(3pt)
      ]
      #content
    ]
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 1: Title & Executive Summary
// ══════════════════════════════════════════════════════════════════════════════
#align(center + horizon)[
  #box(
    fill: brand-cyan.transparentize(85%),
    stroke: 1.5pt + brand-cyan,
    radius: 8pt,
    inset: (x: 16pt, y: 10pt),
    text(size: 26pt, weight: "bold", fill: brand-cyan, "🛡️ CanonGate")
  )
  #v(14pt)
  #text(size: 26pt, weight: "extrabold", fill: rgb("#FFFFFF"), "Autonomous Pre-Publication Brand & Regulatory Governance")
  #v(8pt)
  #text(size: 13pt, fill: rgb("#CBD5E1"), "The Zero-Hallucination, Mathematically Bounded Gatekeeper for Regulated Enterprise Marketing")
  #v(20pt)
  #block(
    fill: rgb("#111827"),
    stroke: 1pt + rgb("#1E293B"),
    radius: 8pt,
    inset: (x: 20pt, y: 12pt),
    width: 75%,
    [
      #grid(
        columns: (1fr, 1fr, 1fr),
        gutter: 12pt,
        [
          #text(size: 11pt, weight: "bold", fill: brand-cyan, "Formal SMT Prover")\
          #text(size: 8.5pt, fill: text-muted, "Z3 symbolic numeric & interval boundary verification")
        ],
        [
          #text(size: 11pt, weight: "bold", fill: brand-emerald, "Conformal Risk Gate")\
          #text(size: 8.5pt, fill: text-muted, "Mathematically bounded false-positive miscoverage rate")
        ],
        [
          #text(size: 11pt, weight: "bold", fill: brand-purple, "RFC 9162 Merkle Tree")\
          #text(size: 8.5pt, fill: text-muted, "Immutable cryptographic audit trail & C2PA credentials")
        ]
      )
    ]
  )
  #v(16pt)
  #text(size: 8.5pt, fill: text-muted, "Tech Circuit Hackathon 2026 • Enterprise AI & Governance Track • Open Source Production Release")
]
#slide-footer(current: 1, total: 12)

#pagebreak()

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 2: The $280B Regulatory Crisis
// ══════════════════════════════════════════════════════════════════════════════
#slide-header(category: "Market Problem", title: "The $280B Cost of Post-Publication Non-Compliance")

#grid(
  columns: (1.2fr, 1fr),
  gutter: 16pt,
  [
    #card(title: "The Compliance Explosion", color: brand-rose)[
      • *Global Regulatory Crackdown:* RBI Fair Lending Practices, ASCI Disclosures, SEBI Investment Ad Codes, US FTC Endorsement Guides, and EU AI Act Article 52.\
      • *Disproportionate Financial Fines:* Regulatory penalties exceed *₹10 Cr+* (\$1.2M+) per infraction, plus mandatory public retractions and class-action risk.\
      • *The GenAI Velocity Paradox:* Marketing teams generate *100x more campaign variants* across social, email, web, and banners than human legal teams can audit.\
      • *Irreversible Harm:* Once non-compliant marketing collateral is published to CMS or social feeds, the regulatory violation is *permanent and legally actionable*.
    ]
  ],
  [
    #card(title: "By The Numbers", color: brand-amber)[
      #align(center)[
        #text(size: 24pt, weight: "bold", fill: brand-rose, "$280B+")\
        #text(size: 9pt, fill: text-muted, "Annual Global Corporate Compliance & Penalty Exposure")\
        #v(10pt)
        #text(size: 24pt, weight: "bold", fill: brand-amber, "4.2 Days")\
        #text(size: 9pt, fill: text-muted, "Average Legal Turnaround Time per Campaign Asset")\
        #v(10pt)
        #text(size: 24pt, weight: "bold", fill: brand-cyan, "78%")\
        #text(size: 9pt, fill: text-muted, "Of Violations Occur in Fine Print, Disclosures & Images")
      ]
    ]
  ]
)
#slide-footer(current: 2, total: 12)

#pagebreak()

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 3: The Broken Status Quo
// ══════════════════════════════════════════════════════════════════════════════
#slide-header(category: "Market Gap", title: "Why Traditional Compliance Solutions Fail")

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: 12pt,
  [
    #card(title: "1. Manual Legal Review", color: brand-rose)[
      *Slow, Expensive & Inconsistent*\
      • 3–7 day review bottlenecks stall marketing cycles\
      • High legal billable hours (\$500+/hr)\
      • Inconsistent human subjective interpretation\
      • Fails completely under real-time automated CMS pipelines
    ]
  ],
  [
    #card(title: "2. Post-Hoc Scanners / DAMs", color: brand-amber)[
      *Too Little, Too Late*\
      • Audits content *after* publication to staging or prod\
      • Zero pre-flight blocking on CMS webhooks\
      • Isolated from creator editing environments (Cursor, Figma)\
      • No formal mathematical bounds on claim veracity
    ]
  ],
  [
    #card(title: "3. Naive LLM Guardrails", color: brand-purple)[
      *Stochastic & Hallucination-Prone*\
      • Non-deterministic: same ad yields different decisions\
      • Zero mathematical false-positive guarantees\
      • No courtroom-defensible cryptographic proofs\
      • Vulnerable to jailbreaks and prompt injections
    ]
  ]
)
#slide-footer(current: 3, total: 12)

#pagebreak()

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 4: The CanonGate Solution
// ══════════════════════════════════════════════════════════════════════════════
#slide-header(category: "Product Overview", title: "CanonGate: The Autonomous Pre-Flight Gatekeeper")

#text(size: 12pt, fill: rgb("#E2E8F0"), [
  *CanonGate* shifts compliance from reactive post-publication damage control to an *autonomous, deterministic pre-publish gate* that intercepts and formally verifies content before it goes live.
])
#v(10pt)

#grid(
  columns: (1fr, 1fr),
  gutter: 14pt,
  [
    #card(title: "Core Innovations", color: brand-cyan)[
      • *Tri-Tier Formal Engine:* Combines deterministic AST checks, Z3 SMT constraint solving, and SOTA 6-gate surgical rewriter.\
      • *Conformal Risk Control:* Mathematically bounds false-positive miscoverage rate ($alpha in [0.01, 0.25]$).\
      • *RFC 9162 Merkle Tree Ledger:* Tamper-evident, hash-chained audit log with $O(log N)$ inclusion proofs.\
      • *Multimodal Vision:* OpenCV WCAG contrast, Tesseract OCR font height analysis, and CIEDE2000 color auditing.
    ]
  ],
  [
    #card(title: "Developer & Enterprise Integrations", color: brand-emerald)[
      • *Pre-Publish Webhook Gate (`/api/gate/check`):* Sub-18ms audit for Shopify, Webflow, and CI/CD pipelines.\
      • *Model Context Protocol (MCP 2026-07-28):* Real-time audit & fix in Cursor, Claude Desktop, and Antigravity.\
      • *Air-Gapped DPDP 2025 Local Scrubber:* Masks PAN, GSTIN, Aadhaar, IFSC, UPI locally before optional cloud calls.\
      • *Enterprise Studio:* 3 distinct personas for Creators, Brand Managers, and Legal Counsel.
    ]
  ]
)
#slide-footer(current: 4, total: 12)

#pagebreak()

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 5: Tri-Tier Verification Engine
// ══════════════════════════════════════════════════════════════════════════════
#slide-header(category: "Technical Architecture", title: "Tri-Tier Verification & Formal SMT Proving")

#grid(
  columns: (1fr, 1.1fr, 1.2fr),
  gutter: 12pt,
  [
    #card(title: "Tier 1: Deterministic AST", color: brand-cyan)[
      *Ultra-Fast Static Engine (< 5ms)*\
      • *Text & Headings:* Banned terminology, forbidden claims\
      • *Vision Analysis:* WCAG 4.5:1 text-to-background contrast\
      • *Typography:* Font height bounding box ratios\
      • *Table Grid:* Alignment & column structure audits
    ]
  ],
  [
    #card(title: "Tier 2: Z3 SMT & Slot NLI", color: brand-blue)[
      *Mathematical Constraint Prover (< 25ms)*\
      • *Z3 Theorem Prover:* Symbolic interval arithmetic over numeric rates, APR caps, and loan tenures\
      • *MiniCheck Slot NLI:* Sub-claim fact decomposition and entailment checking\
      • *Contradiction Detection:* Identifies subtle legal inconsistencies
    ]
  ],
  [
    #card(title: "Tier 3: SOTA 6-Gate Rewriter", color: brand-purple)[
      *Constrained Surgical Synthesis*\
      • *DPDP PII Scrubber:* Local tokenization\
      • *6 Quality Gates:* Length ratio, PII integrity, numeric anchor lock, edit distance <= 35%, re-verification, zero collateral\
      • *Gemini 3.x Cascade:* Multi-model fallback\
      • *Circuit Breaker:* < 1ms failover to AST
    ]
  ]
)
#slide-footer(current: 5, total: 12)

#pagebreak()

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 6: Conformal Risk Control
// ══════════════════════════════════════════════════════════════════════════════
#slide-header(category: "Mathematical Rigor", title: "Conformal Risk Control: Bounded False-Positive Guarantees")

#grid(
  columns: (1.2fr, 1fr),
  gutter: 16pt,
  [
    #card(title: "Why Static Thresholds Fail", color: brand-amber)[
      Traditional compliance tools rely on static heuristics (e.g. `severity > 70`). In high-stakes regulatory domains, arbitrary cutoffs create catastrophic failure modes:\
      • *Over-blocking:* Rejects creative marketing copy, destroying conversion rates.\
      • *Under-blocking:* Allows regulatory non-compliance through subtle edge cases.\
      \
      *The CanonGate Conformal Solution:*\
      Using *Split-Conformal Prediction*, CanonGate maps calibration non-conformity scores to a mathematically bounded miscoverage parameter $alpha in [0.01, 0.25]$:\
      #align(center)[$PP("Loss"(lambda^*) > epsilon) <= alpha$]\
      This guarantees compliance officers an exact, mathematically proven risk ceiling.
    ]
  ],
  [
    #card(title: "Two-Tier Verdict Structure", color: brand-emerald)[
      #block(fill: rgb("#1E293B"), radius: 5pt, inset: 8pt)[
        #text(weight: "bold", fill: brand-rose, "🚫 BLOCKER (Severity >= 50)")\
        #text(size: 8.5pt, fill: text-muted, "Hard statutory violations: missing RBI KFS, prohibited medical claims, illegible contrast (< 3:1). Pre-publish gate immediately halts deployment.")
      ]
      #v(8pt)
      #block(fill: rgb("#1E293B"), radius: 5pt, inset: 8pt)[
        #text(weight: "bold", fill: brand-amber, "⚠️ WARNING (Severity < 50)")\
        #text(size: 8.5pt, fill: text-muted, "Stylistic deviations, secondary brand colors, non-critical fine print. Requires reviewer sign-off with recorded audit friction.")
      ]
    ]
  ]
)
#slide-footer(current: 6, total: 12)

#pagebreak()

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 7: Cryptographic Trust Ledger
// ══════════════════════════════════════════════════════════════════════════════
#slide-header(category: "Auditability & Provenance", title: "Courtroom-Defensible RFC 9162 Merkle Tree Ledger")

#grid(
  columns: (1fr, 1.2fr),
  gutter: 16pt,
  [
    #card(title: "Cryptographic Immutability", color: brand-purple)[
      • *RFC 9162 Merkle Accumulator:* Every submission, audit finding, reviewer action, and surgical rewrite is committed into a cryptographic binary tree.\
      • *Logarithmic Proofs:* Generates compact $O(log N)$ inclusion proofs and append-only consistency proofs.\
      • *SHA-256 Hash Chaining:* Workflow state transitions are bound by strict hash chaining: $H_i = "SHA-256"(H_(i-1) || E_i)$.\
      • *Zero Tamper Window:* Internal databases cannot alter historical records without breaking the Merkle root.
    ]
  ],
  [
    #card(title: "Offline Verifiability & C2PA Manifests", color: brand-cyan)[
      #subbox(title: "Offline CLI Verifier (`canongate verify`)")[
        Regulators, legal counsel, and auditors can independently verify compliance certificates offline without database access:\
        `$ canongate verify audit_certificate.json`\
        `[OK] Merkle root valid. Hash-chain verified across 18 events.`
      ]
      #v(6pt)
      #subbox(title: "C2PA Content Credentials Embedding")[
        • Approved digital assets are cryptographically signed with CanonGate's governance credentials.\
        • Ad networks and consumers can inspect origin and compliance proofs directly in browser.
      ]
    ]
  ]
)
#slide-footer(current: 7, total: 12)

#pagebreak()

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 8: Developer & CMS Integrations
// ══════════════════════════════════════════════════════════════════════════════
#slide-header(category: "Omnichannel Deployment", title: "Omnichannel CMS Webhooks & Model Context Protocol (MCP)")

#grid(
  columns: (1fr, 1fr),
  gutter: 14pt,
  [
    #card(title: "Pre-Publish Webhook Gate (`/api/gate/check`)", color: brand-emerald)[
      *Synchronous Pre-Flight Deployment Blocker*\
      • *Sub-18ms Latency:* Audits copy, tables, and images in milliseconds.\
      • *Shopify Adapter:* Automatically parses product titles, HTML bodies, variant pricing tables, and hero image contrast.\
      • *Webflow Adapter:* Ingests CMS rich-text fields, summary copy, and promotional banners.\
      • *CI/CD Pipelines:* Integrates into GitHub Actions to block non-compliant PRs before merge.
    ]
  ],
  [
    #card(title: "Model Context Protocol (MCP 2026-07-28)", color: brand-cyan)[
      *IDE & AI Coding Assistant Native*\
      • *Stdio CLI:* Run `canongate mcp` in Claude Desktop, Cursor, and Antigravity.\
      • *6 Native Tools:* `verify_campaign`, `list_canons`, `inspect_canon`, `propose_fix`, `explain_rule`, `batch_evaluate`.\
      • *120-Asset Batching:* Audits entire backlogs in seconds with fault isolation.\
      • *Streamable HTTP:* `POST /api/mcp` with DNS rebinding security.
    ]
  ]
)
#slide-footer(current: 8, total: 12)

#pagebreak()

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 9: Privacy-by-Design & DPDP 2025
// ══════════════════════════════════════════════════════════════════════════════
#slide-header(category: "Enterprise Security", title: "Privacy-by-Design & Indian DPDP 2025 Compliance")

#grid(
  columns: (1.1fr, 1fr),
  gutter: 16pt,
  [
    #card(title: "Air-Gapped Local Operation by Default", color: brand-emerald)[
      • *Zero Mandatory API Keys:* Core rule parsing, Z3 SMT solving, visual contrast checks, Merkle logging, and deterministic AST rewriting run *100% offline*.\
      • *Zero Customer Data Exfiltration:* Customer campaigns, financial spreadsheets, and proprietary collateral never leave the local container by default.\
      • *Transparent Disclosure:* The UI and API explicitly disclose when running in air-gapped deterministic mode, preventing false claims of cloud AI generation.
    ]
  ],
  [
    #card(title: "Local DPDP 2025 PII Scrubber", color: brand-blue)[
      Before any optional cloud LLM call (Gemini / OpenAI / Inkloom), text is scrubbed locally using Microsoft Presidio + Indian statutory regexes:
      • `PAN_ID` & `GSTIN` Tax Identifiers\
      • `AADHAAR_ID` 12-Digit UIDAI Tokens\
      • `UPI_VPA` & `IFSC` Banking Codes\
      • `PHONE` (+91) & `EMAIL` Addresses\
      • *Bijective Verification:* Validates placeholders before restoring locally.
    ]
  ]
)
#slide-footer(current: 9, total: 12)

#pagebreak()

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 10: Target Markets & Verticals
// ══════════════════════════════════════════════════════════════════════════════
#slide-header(category: "Commercial Strategy", title: "Market Opportunity & Target High-Stakes Verticals")

#grid(
  columns: (1fr, 1fr, 1fr, 1fr),
  gutter: 10pt,
  [
    #card(title: "FinTech & Lending", color: brand-cyan)[
      *Digital Lending & Cards*\
      • RBI Fair Practices Code\
      • APR & Fee Disclosures\
      • Guaranteed Approval bans\
      • Loan tenure minimums
    ]
  ],
  [
    #card(title: "D2C Nutra & Food", color: brand-emerald)[
      *Supplements & Beauty*\
      • ASCI Advertising Standards\
      • FSSAI / FDA efficacy rules\
      • "Miracle cure" bans\
      • Clinical claim contracts
    ]
  ],
  [
    #card(title: "Healthcare / Pharma", color: brand-purple)[
      *Telehealth & Diagnostics*\
      • Prescription ad restrictions\
      • Diagnostic accuracy claims\
      • Statutory medical caveats\
      • Dosage contraindications
    ]
  ],
  [
    #card(title: "Enterprise Brands", color: brand-amber)[
      *Global Omnichannel*\
      • Multi-brand design canons\
      • WCAG 2.1 AA accessibility\
      • Color contrast conformance\
      • FTC greenwashing audits
    ]
  ]
)

#v(8pt)
#card(title: "Total Addressable Market (TAM)", color: brand-blue)[
  #grid(
    columns: (1fr, 1fr, 1fr),
    align: center,
    [
      #text(size: 20pt, weight: "bold", fill: brand-cyan, "$42.8B")\
      #text(size: 8.5pt, fill: text-muted, "Global RegTech & Governance Market (2026)")
    ],
    [
      #text(size: 20pt, weight: "bold", fill: brand-emerald, "21.4% CAGR")\
      #text(size: 8.5pt, fill: text-muted, "Annual Market Growth Rate")
    ],
    [
      #text(size: 20pt, weight: "bold", fill: brand-purple, "$8.5B")\
      #text(size: 8.5pt, fill: text-muted, "Serviceable Addressable Market (SAM)")
    ]
  )
]
#slide-footer(current: 10, total: 12)

#pagebreak()

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 11: Business Model & Pricing
// ══════════════════════════════════════════════════════════════════════════════
#slide-header(category: "Financial Model", title: "Enterprise SaaS Business Model & Unit Economics")

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: 12pt,
  [
    #card(title: "Developer / Starter", color: brand-cyan)[
      *Free / Open-Core*\
      • CLI & Local MCP Stdio server\
      • Standard community Canons\
      • Offline SQLite audit storage\
      • Unlimited local AST audits
    ]
  ],
  [
    #card(title: "Team / Growth", color: brand-emerald)[
      *₹39,999 / mo (\$499/mo)*\
      • Cloud Hosted REST API\
      • Shopify & Webflow Webhook Gates\
      • 50,000 automated checks / mo\
      • Conformal Risk Control slider\
      • 3-Persona Studio Collaboration
    ]
  ],
  [
    #card(title: "Enterprise Governance", color: brand-purple)[
      *₹1,99,999+ / mo (\$2,499+/mo)*\
      • Air-gapped on-premise container\
      • Custom Canon compiler pipeline\
      • RFC 9162 Merkle proof export\
      • Dedicated enterprise SLA (99.9%)\
      • SSO / SAML & role-based access
    ]
  ]
)

#v(8pt)
#card(title: "Exceptional Unit Economics", color: brand-amber)[
  • *Gross Margins > 85%:* Deterministic Tier 1 & Z3 SMT checks cost under \$0.0001 per check in compute.\
  • *Zero API Cost by Default:* Local execution eliminates dependency on expensive third-party LLM API tokens.\
  • *High Expansion Revenue (NRR > 135%):* check volume grows automatically with marketing content velocity.
]
#slide-footer(current: 11, total: 12)

#pagebreak()

// ══════════════════════════════════════════════════════════════════════════════
// SLIDE 12: Competitive Landscape & Vision
// ══════════════════════════════════════════════════════════════════════════════
#slide-header(category: "Competitive Advantage", title: "Defensible Moats & The CanonGate Vision")

#table(
  columns: (1.5fr, 1fr, 1fr, 1fr, 1.2fr),
  fill: (x, y) => if y == 0 { rgb("#1E293B") } else if calc.even(y) { rgb("#111827") } else { rgb("#0F172A") },
  stroke: 0.5pt + rgb("#334155"),
  align: (left, center, center, center, center),
  table.header(
    [*Capability*],
    [*Grammarly / Copy.ai*],
    [*Traditional DAM*],
    [*Generic LLMs*],
    [*🛡️ CanonGate*]
  ),
  [Pre-Publish Deployment Gate], [❌ Post-facto], [❌ Staging only], [❌ None], [✅ *Sub-18ms Webhook*],
  [Formal SMT Constraint Proving], [❌ None], [❌ None], [❌ None], [✅ *Z3 SMT Solver*],
  [Mathematical Risk Bounds], [❌ None], [❌ None], [❌ None], [✅ *Conformal $alpha$-Gate*],
  [Cryptographic Audit Proofs], [❌ Plain logs], [❌ DB rows], [❌ None], [✅ *RFC 9162 Merkle*],
  [Model Context Protocol (MCP)], [❌ None], [❌ None], [⚠️ Basic], [✅ *Native 2026-07-28*],
  [Air-Gapped DPDP 2025 Local], [❌ Cloud only], [⚠️ Partial], [❌ Cloud only], [✅ *100% Offline*]
)

#v(10pt)
#align(center)[
  #text(size: 14pt, weight: "bold", fill: brand-cyan, "The Operating System for Pre-Publication Digital Trust")\
  #v(2pt)
  #text(size: 9.5pt, fill: text-muted, "Transforming how regulated enterprises create, verify, and publish content at scale.")
]
#slide-footer(current: 12, total: 12)
