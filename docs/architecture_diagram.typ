#set page(
  paper: "a3",
  flipped: true,
  margin: (x: 1.5cm, top: 1.2cm, bottom: 1.2cm),
  fill: rgb("#090D16"),
)
#set text(
  font: ("Inter", "DejaVu Sans", "Liberation Sans"),
  fill: rgb("#F1F5F9"),
  size: 9.5pt,
)

#let brand-cyan = rgb("#06B6D4")
#let brand-blue = rgb("#3B82F6")
#let brand-purple = rgb("#8B5CF6")
#let brand-emerald = rgb("#10B981")
#let brand-amber = rgb("#F59E0B")
#let brand-rose = rgb("#F43F5E")
#let card-bg = rgb("#111827")
#let card-border = rgb("#1E293B")
#let inner-bg = rgb("#1E293B")

#let card(title: "", color: brand-cyan, badge: "", content) = {
  block(
    stroke: 1pt + card-border,
    fill: card-bg,
    radius: 8pt,
    inset: 10pt,
    width: 100%,
    [
      #grid(
        columns: (1fr, auto),
        align: (left + horizon, right + horizon),
        [
          #text(weight: "bold", size: 11pt, fill: color, title)
        ],
        [
          #if badge != "" {
            box(
              fill: color.transparentize(85%),
              stroke: 0.5pt + color,
              radius: 4pt,
              inset: (x: 5pt, y: 2pt),
              text(size: 7.5pt, weight: "bold", fill: color, badge)
            )
          }
        ]
      )
      #v(6pt)
      #content
    ]
  )
}

#let subbox(title: "", fill-color: inner-bg, content) = {
  block(
    stroke: 0.5pt + rgb("#334155"),
    fill: fill-color,
    radius: 5pt,
    inset: 7pt,
    width: 100%,
    [
      #if title != "" [
        #text(weight: "semibold", size: 8.5pt, fill: rgb("#94A3B8"), title)
        #v(3pt)
      ]
      #content
    ]
  )
}

// ── Header ──
#grid(
  columns: (1fr, auto),
  align: (left + horizon, right + horizon),
  [
    #grid(
      columns: (auto, 1fr),
      gutter: 12pt,
      align: horizon,
      [
        #box(
          fill: brand-cyan.transparentize(85%),
          stroke: 1pt + brand-cyan,
          radius: 6pt,
          inset: 8pt,
          text(size: 16pt, weight: "bold", fill: brand-cyan, "🛡️ CanonGate")
        )
      ],
      [
        #text(size: 18pt, weight: "bold", fill: rgb("#FFFFFF"), "System Architecture Blueprint")
        #v(1pt)
        #text(size: 9.5pt, fill: rgb("#94A3B8"), "Autonomous Pre-Publication Brand & Regulatory Claim Governance Platform • Production Technical Reference")
      ]
    )
  ],
  [
    #align(right)[
      #box(fill: rgb("#1E293B"), radius: 5pt, inset: 6pt)[
        #text(size: 8pt, fill: rgb("#CBD5E1"), [
          *Version:* 2.0 • *Standard:* RFC 9162 / MCP 2026-07-28 • *License:* MIT\
          *Core Stack:* Python 3.12 / FastAPI / Z3 SMT / React 18 / Conformal Risk Engine
        ])
      ]
    ]
  ]
)

#v(10pt)
#line(length: 100%, stroke: 0.5pt + rgb("#334155"))
#v(10pt)

// ── Main Architecture Grid (5 horizontal workflow stages) ──
#grid(
  columns: (1fr, 1.15fr, 1.25fr, 1fr, 0.9fr),
  gutter: 10pt,
  
  // ── Column 1: Ingestion & Multimodal AST ──
  [
    #card(title: "1. Multimodal AST Layer", color: brand-cyan, badge: "Deterministic Parsing")[
      #subbox(title: "Omnichannel Ingestion Adapters")[
        • *Plaintext & Copy:* Markdown, TXT, Raw\
        • *Structured Web:* HTML5, DOM walker\
        • *Office Docs:* DOCX (`python-docx`), PPTX\
        • *Financial/PDF:* PDF (`pypdf` + `pdfplumber`)\
        • *Tabular:* CSV, TSV, Markdown tables
      ]
      #v(6pt)
      #subbox(title: "Visual Computer Vision (OpenCV + OCR)")[
        • *Contrast Analysis:* WCAG 2.1 AA (4.5:1 / 3:1)\
        • *Font Height Metric:* Bounding-box ratio\
        • *Color Palette:* CIEDE2000 $Delta E$ delta\
        • *Text Recovery:* Tesseract OCR engine\
        • *Visual Placement:* Banner fine print audit
      ]
      #v(6pt)
      #subbox(title: "Normalized ContentAST")[
        • *Frozen Immutable AST:* Zero side-effects\
        • *Node Tree:* Text, Heading, Image, Table\
        • *Locator Tracking:* Exact char/line spans\
        • *Deterministic Hash:* SHA-256 content IDs
      ]
    ]
  ],

  // ── Column 2: Canon Rule Domain Engine ──
  [
    #card(title: "2. Canon Governance Domain", color: brand-blue, badge: "Signed YAML")[
      #subbox(title: "Brand & Legal Canons (YAML)")[
        • *Digital Lending:* RBI Fair Practices Code\
        • *D2C Nutra/Pharma:* ASCI / FDA claim norms\
        • *Enterprise Core:* Brand voice, design tokens\
        • *Cryptographic Seal:* Ed25519 Canon signature\
        • *Dynamic Compilation:* Pipeline A auto-gen
      ]
      #v(6pt)
      #subbox(title: "Multi-Constraint Rule Catalog")[
        • *Term Rules:* Banned words, approved synonyms\
        • *Typography:* Minimum px height & contrast\
        • *Palette Rules:* Primary/secondary HEX bounds\
        • *Obligations:* Trigger $arrow.r$ mandatory disclosures\
        • *Numeric Limits:* APR caps, min tenure constraints\
        • *Fact Catalog:* Grounded enterprise ground truths
      ]
      #v(6pt)
      #subbox(title: "Domain Boundaries (Import-Linter)")[
        • `canongate.domain` is pure & frozen\
        • Zero I/O, zero network, zero internal imports\
        • Strict architectural boundary enforcement
      ]
    ]
  ],

  // ── Column 3: Formal Verification Pipeline ──
  [
    #card(title: "3. Tri-Tier Verification Engine", color: brand-purple, badge: "Hybrid Formal + SMT")[
      #subbox(title: "Tier 1: Deterministic Static Checks (<5ms)")[
        • *Regex & AST Walkers:* Banned phrases & claims\
        • *Visual Contrast:* RGB luminance & font ratios\
        • *Table Integrity:* Header alignment & empty cells\
        • *Trigger Matcher:* Deterministic requirement trigger
      ]
      #v(6pt)
      #subbox(title: "Tier 2: Z3 SMT Prover & Slot NLI (<25ms)")[
        • *Z3 SMT Solver:* Symbolic numeric & interval logic\
        • *Disjunctive Satisfiability:* Contradiction proofs\
        • *Claim Slot NLI:* MiniCheck entailment verification\
        • *Sub-claim Decomposition:* Multi-fact isolation
      ]
      #v(6pt)
      #subbox(title: "Conformal Risk Control Gate (CRC)")[
        • *Miscoverage Bound:* Split-conformal $alpha in [0.01, 0.25]$\
        • *Mathematically Calibrated:* False-positive ceiling\
        • *Dynamic Thresholding:* $lambda^*(alpha)$ risk slider\
        • *Two-Tier Verdict:* Blocker ($s >= 50$) vs Warning ($s < 50$)
      ]
      #v(6pt)
      #subbox(title: "Tier 3: SOTA 6-Gate Surgical Rewriter")[
        • *DPDP 2025 PII Scrubber:* Local PAN/GSTIN/Aadhaar/UPI\
        • *6 Quality Gates:* Length ratio, PII integrity, anchor lock, edit ceiling <= 35%, re-verification, zero collateral\
        • *Gemini 3.x Cascade:* 3.8-flash $arrow.r$ 3.6-flash $arrow.r$ 3.5-flash\
        • *Circuit Breaker:* Failover in < 1ms to deterministic AST
      ]
    ]
  ],

  // ── Column 4: Cryptographic Ledger & Audit ──
  [
    #card(title: "4. Cryptographic Trust Ledger", color: brand-emerald, badge: "RFC 9162 Merkle")[
      #subbox(title: "RFC 9162 Merkle Tree Audit Trail")[
        • *Cryptographic Accumulator:* Binary tree structure\
        • *Audit Proof:* $O(log N)$ inclusion proof path\
        • *Consistency Proof:* Append-only immutability\
        • *Root Hash Anchor:* External transparency log
      ]
      #v(6pt)
      #subbox(title: "SHA-256 Hash-Chained Workflow")[
        • *Deterministic Hash Chain:* $H_i = "SHA-256"(H_(i-1) || E_i)$\
        • *Friction Log:* Justification & time-penalty ledger\
        • *State Machine:* Table-driven lifecycle transitions\
        • *Zero Tamper Window:* Offline verifiable certificate
      ]
      #v(6pt)
      #subbox(title: "C2PA & Export Credentials")[
        • *Content Credentials:* Signed pre-publish manifest\
        • *Offline Verification:* CLI `canongate verify cert.json`\
        • *Courtroom-Ready:* Cryptographic audit bundle
      ]
    ]
  ],

  // ── Column 5: Integration & Execution ──
  [
    #card(title: "5. Surfaces & Endpoints", color: brand-amber, badge: "Omnichannel")[
      #subbox(title: "Pre-Publish Webhook Gate")[
        • `POST /api/gate/check`\
        • *Shopify Adapter:* Products, variant prices, images\
        • *Webflow Adapter:* CMS fields, rich-text, hero assets\
        • *CI/CD Gate:* GitHub Actions / GitLab pipeline blocker
      ]
      #v(6pt)
      #subbox(title: "Model Context Protocol (MCP)")[
        • *Stdio CLI:* `canongate mcp`\
        • *HTTP Transport:* `POST /api/mcp`\
        • *6 Tools:* `verify_campaign`, `list_canons`, `inspect_canon`, `propose_fix`, `explain_rule`, `batch_evaluate`\
        • *Compatibility:* Claude Desktop, Cursor, Antigravity
      ]
      #v(6pt)
      #subbox(title: "Enterprise Studio UI")[
        • *React 18 + Vite:* Tailwind CSS SPA\
        • *3 Personas:* Creator, Brand Mgr, Legal Counsel\
        • *Interactive Studio:* In-situ highlights, diff rewrites, Merkle visualizer, $alpha$-slider
      ]
    ]
  ]
)

#v(10pt)

// ── Bottom Summary Box: End-to-End SLA & Performance Metrics ──
#block(
  stroke: 1pt + rgb("#334155"),
  fill: rgb("#0F172A"),
  radius: 8pt,
  inset: (x: 14pt, y: 10pt),
  width: 100%,
  [
    #grid(
      columns: (1fr, 1fr, 1fr, 1fr),
      align: center,
      [
        #text(size: 16pt, weight: "bold", fill: brand-cyan, "< 18 ms")\
        #text(size: 8.5pt, fill: rgb("#94A3B8"), "Deterministic Pre-Flight Gate Latency")
      ],
      [
        #text(size: 16pt, weight: "bold", fill: brand-emerald, "100% Pass")\
        #text(size: 8.5pt, fill: rgb("#94A3B8"), "114/114 Backend Tests & 3/3 Import Contracts")
      ],
      [
        #text(size: 16pt, weight: "bold", fill: brand-purple, "O(log N)")\
        #text(size: 8.5pt, fill: rgb("#94A3B8"), "RFC 9162 Merkle Audit Inclusion Verification")
      ],
      [
        #text(size: 16pt, weight: "bold", fill: brand-amber, "Zero-Data-Exfiltration")\
        #text(size: 8.5pt, fill: rgb("#94A3B8"), "Air-Gapped DPDP 2025 Local Scrubber & Offline Execution")
      ]
    )
  ]
)
