import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import {
  getSubmission,
  getFindings,
  scanSubmission,
  resolveFinding,
  rewriteFindingSpan,
  listSubmissionComments,
  addSubmissionComment,
  workflowAction,
  getAuditTrail,
  getGovernanceCertificate,
  getSubmissionVersions,
  type Submission,
  type FindingResponse,
  type EvidencePayload,
  type ImageNodeMetaDto,
  type SubmissionCommentDto,
} from "../../api/client";
import { useAuth } from "../auth/useAuth";
import { createProseMirrorFindingsPlugin } from "./FindingHighlightsExtension";

const findingsPluginKey = new PluginKey("canongateFindings");

const FindingsDecorationExtension = Extension.create({
  name: "findingsDecoration",
  addProseMirrorPlugins() {
    return [
      createProseMirrorFindingsPlugin({
        pluginKey: findingsPluginKey,
        Decoration,
        DecorationSet,
        Plugin,
      }) as Plugin,
    ];
  },
});

const VERDICT_LABELS: Record<string, string> = {
  "0": "PASS",
  "1": "WARNING",
  "2": "BLOCKER",
};
const VERDICT_COLORS: Record<string, string> = {
  "0": "#22c55e",
  "1": "#f59e0b",
  "2": "#ef4444",
};

/**
 * Escape HTML special characters so `<`, `>`, and `&` inside text blocks or
 * linearized table rows never get stripped as malformed HTML tags by Tiptap,
 * keeping ProseMirror UTF-16 offsets 1-to-1 with backend `TextNode.text`.
 */
function escapeHtmlBlock(raw: string): string {
  return raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Resolve the exact sequence of textblocks to render in Tiptap so every block
 * aligns 1-to-1 with `submission.paragraph_node_ids` (including linearized
 * Markdown table rows produced by `parse_markdown_text` on the backend).
 */
function resolveEditorTextBlocks(submission: Submission): string[] {
  if (submission.text_blocks && submission.text_blocks.length > 0) {
    return submission.text_blocks;
  }
  if (!submission.raw_content) {
    return [];
  }
  return submission.raw_content
    .split(/\n{2,}/)
    .map((b) => b.trim())
    .filter((b) => b.length > 0);
}

/**
 * Interactive SVG viewBox overlay rendering pixel BBox(x, y, w, h) locators
 * on top of attached campaign banner images.
 */
export function BannerBBoxOverlay({
  imageNodes,
  findings,
  selectedRowId,
  onSelectFinding,
}: {
  imageNodes: ImageNodeMetaDto[];
  findings: FindingResponse[];
  selectedRowId: number | null;
  onSelectFinding: (rowId: number) => void;
}) {
  if (!imageNodes || imageNodes.length === 0) return null;

  return (
    <section className="banner-overlay-section">
      <div className="section-header">
        <h2>🖼️ Visual Creative Inspection (BBox Governance Overlay)</h2>
        <span className="editor-subtext">
          Click any bounding box on the banner to inspect its CIEDE2000, WCAG 2.1, ORB Logo, ASCI 26px, or Saliency evidence
        </span>
      </div>
      <div className="banner-grid">
        {imageNodes.map((img) => {
          const boxFindings = findings.filter(
            (f) =>
              f.node_id === img.node_id &&
              f.resolution === "open" &&
              f.payload?.locator &&
              typeof f.payload.locator.x === "number" &&
              typeof f.payload.locator.y === "number"
          );
          const viewW = Math.max(1, img.width || 800);
          const viewH = Math.max(1, img.height || 400);
          const srcUrl = img.url.startsWith("http")
            ? img.url
            : `http://localhost:8000${img.url}`;

          return (
            <div key={img.node_id} className="banner-canvas-card">
              <div className="banner-canvas-header">
                <code>{img.asset_path.split("/").pop() || img.asset_path}</code>
                <span>
                  {viewW}×{viewH}px · {boxFindings.length} open visual finding(s)
                </span>
              </div>
              <div className="banner-stage">
                <img
                  src={srcUrl}
                  alt={img.alt || "Campaign Banner"}
                  className="banner-img"
                />
                <svg
                  className="bbox-svg-overlay"
                  viewBox={`0 0 ${viewW} ${viewH}`}
                  preserveAspectRatio="xMidYMid meet"
                >
                  {boxFindings.map((f) => {
                    const loc = f.payload.locator!;
                    const x = loc.x ?? 0;
                    const y = loc.y ?? 0;
                    const w = Math.max(12, loc.w ?? 40);
                    const h = Math.max(12, loc.h ?? 24);
                    const isBlocker = f.severity >= 50;
                    const isSelected = f.row_id === selectedRowId;
                    const strokeColor = isBlocker ? "#ef4444" : "#f59e0b";

                    return (
                      <g
                        key={f.row_id}
                        className={`bbox-group ${isSelected ? "bbox-selected" : ""}`}
                        onClick={() => onSelectFinding(f.row_id)}
                      >
                        <rect
                          x={x}
                          y={y}
                          width={w}
                          height={h}
                          fill={
                            isSelected
                              ? "rgba(99, 102, 241, 0.28)"
                              : isBlocker
                                ? "rgba(239, 68, 68, 0.16)"
                                : "rgba(245, 158, 11, 0.16)"
                          }
                          stroke={isSelected ? "#818cf8" : strokeColor}
                          strokeWidth={isSelected ? 3 : 2}
                          rx={3}
                        >
                          <title>{`${f.check_id}: ${f.message}`}</title>
                        </rect>
                      </g>
                    );
                  })}
                </svg>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function EvidenceView({
  evidence,
  slotDiffExpanded = true,
  onToggleSlotDiff,
}: {
  evidence?: EvidencePayload;
  slotDiffExpanded?: boolean;
  onToggleSlotDiff?: () => void;
}) {
  if (!evidence) return null;

  switch (evidence.kind) {
    case "term_match":
      return (
        <div className="evidence-box">
          <span className="evidence-kind-tag">Term Match</span>
          <span className="ev-del">{evidence.term}</span>
          <span className="ev-arrow">→</span>
          <span className="ev-ins">{evidence.preferred}</span>
        </div>
      );

    case "color_distance":
      return (
        <div className="evidence-box">
          <span className="evidence-kind-tag">CIEDE2000 Palette Drift</span>
          <span className="swatch-pair">
            <span
              className="color-swatch"
              style={{ backgroundColor: evidence.found_hex }}
              title={`Found: ${evidence.found_hex}`}
            />
            <code>{evidence.found_hex}</code>
          </span>
          <span className="ev-arrow">vs</span>
          <span className="swatch-pair">
            <span
              className="color-swatch"
              style={{ backgroundColor: evidence.approved_hex }}
              title={`Approved: ${evidence.approved_hex}`}
            />
            <code>{evidence.approved_hex}</code>
          </span>
          <span className="ev-metric">
            ΔE₀₀ = <strong>{evidence.delta_e.toFixed(2)}</strong> (max {evidence.max_allowed.toFixed(1)})
          </span>
        </div>
      );

    case "contrast":
      return (
        <div className="evidence-box">
          <span className="evidence-kind-tag">WCAG {evidence.wcag_level} Contrast</span>
          <span
            className="contrast-preview-chip"
            style={{
              color: evidence.fg_hex,
              backgroundColor: evidence.bg_hex,
            }}
          >
            Aa {evidence.fg_hex} on {evidence.bg_hex}
          </span>
          <span className="ev-metric">
            Ratio <strong>{evidence.contrast_ratio.toFixed(2)}:1</strong> (req ≥ {evidence.required_ratio.toFixed(1)}:1)
          </span>
          {evidence.suggested_fg_hex && (
            <span className="swatch-pair">
              <span>Suggested FG:</span>
              <span
                className="color-swatch"
                style={{ backgroundColor: evidence.suggested_fg_hex }}
              />
              <code>{evidence.suggested_fg_hex}</code>
            </span>
          )}
        </div>
      );

    case "slot_diff":
      return (
        <div className="evidence-box evidence-box-block">
          <div className="evidence-header-row">
            <span className="evidence-kind-tag">NLI SlotDiff ({evidence.canon_claim_id})</span>
            <span className="ev-metric">
              Entailment P = <strong>{(evidence.entailment_prob * 100).toFixed(0)}%</strong>
            </span>
            {onToggleSlotDiff && (
              <button
                type="button"
                className="btn-sm btn-ghost"
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleSlotDiff();
                }}
              >
                {slotDiffExpanded ? "▴ Collapse SlotDiff" : "▾ Expand SlotDiff to Unlock Actions"}
              </button>
            )}
          </div>
          {slotDiffExpanded && evidence.slots && evidence.slots.length > 0 && (
            <table className="slot-diff-table">
              <thead>
                <tr>
                  <th>Slot</th>
                  <th>Canon Approved</th>
                  <th>Draft Copy</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {evidence.slots.map((s, idx) => (
                  <tr key={`${s.slot}-${idx}`}>
                    <td><code>{s.slot}</code></td>
                    <td>{s.canon_value}</td>
                    <td>{s.draft_value}</td>
                    <td>
                      <span className={`slot-status-pill status-${s.status}`}>
                        {s.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      );

    case "algebraic_proof": {
      const counterEntries = Object.entries(evidence.counterexample || {});
      return (
        <div className="evidence-box evidence-box-block">
          <div className="evidence-header-row">
            <span className="evidence-kind-tag">Tier 1.5 Algebraic Solver</span>
            <span className="slot-status-pill status-contradicted">
              {evidence.solver_status === "sat_counterexample" ? "SAT Counterexample" : "UNSAT Valid"}
            </span>
          </div>
          <div className="ev-algebra-row">
            <span>Draft: <code>{evidence.draft_expr}</code></span>
            <span>Canon: <code>{evidence.canon_constraint}</code></span>
          </div>
          {counterEntries.length > 0 && (
            <div className="ev-counterexample">
              Witness:{" "}
              {counterEntries.map(([k, v]) => (
                <code key={k} className="ev-witness-chip">
                  {k} = {v}
                </code>
              ))}
            </div>
          )}
        </div>
      );
    }

    case "legibility":
      return (
        <div className="evidence-box">
          <span className="evidence-kind-tag">ASCI / CCPA Legibility</span>
          <span className="ev-metric">
            x-height <strong>{evidence.estimated_x_height_px.toFixed(1)}px</strong> / req{" "}
            <strong>{evidence.required_px.toFixed(1)}px</strong> (box {evidence.measured_box_px.toFixed(0)}px @{" "}
            {evidence.image_height_px}p, OCR {(evidence.ocr_confidence * 100).toFixed(0)}%)
          </span>
          {evidence.script_mismatch && (
            <span className="slot-status-pill status-contradicted">
              CCPA Clause 11 Script Mismatch
            </span>
          )}
        </div>
      );

    case "saliency":
      return (
        <div className="evidence-box">
          <span className="evidence-kind-tag">Montabone & Soto Saliency</span>
          <span className="ev-metric">
            Ratio <strong>{evidence.ratio.toFixed(2)}</strong> &lt; floor{" "}
            <strong>{evidence.min_ratio.toFixed(2)}</strong> (disclaimer {evidence.disclaimer_saliency.toFixed(3)}{" "}
            vs headline {evidence.headline_saliency.toFixed(3)})
          </span>
        </div>
      );

    case "confusable":
      return (
        <div className="evidence-box">
          <span className="evidence-kind-tag">UTS #39 Homoglyph</span>
          <span className="ev-del">{evidence.spoofed_token}</span>
          <span className="ev-arrow">→</span>
          <span className="ev-ins">{evidence.normalized_token}</span>
          {evidence.scripts_detected?.length > 0 && (
            <span className="ev-metric">
              Scripts: <code>{evidence.scripts_detected.join(" + ")}</code>
            </span>
          )}
        </div>
      );

    case "c2pa":
      return (
        <div className="evidence-box">
          <span className="evidence-kind-tag">C2PA Provenance</span>
          <span className="ev-metric">
            State: <strong>{evidence.validation_state}</strong>
            {evidence.issuer ? ` | Issuer: ${evidence.issuer}` : ""}
            {evidence.digital_source_type ? ` | Source: ${evidence.digital_source_type}` : ""}
          </span>
        </div>
      );

    case "hidden_text":
      return (
        <div className="evidence-box">
          <span className="evidence-kind-tag">OWASP LLM01 ({evidence.mechanism})</span>
          <code className="ev-snippet">{evidence.extracted_snippet}</code>
        </div>
      );

    case "logo_geometry":
      return (
        <div className="evidence-box">
          <span className="evidence-kind-tag">OpenCV ORB Logo ({evidence.logo_id})</span>
          <span className="ev-metric">
            AR distortion <strong>{evidence.aspect_distortion_pct.toFixed(1)}%</strong> (max{" "}
            {evidence.max_aspect_distortion_pct.toFixed(1)}%) · Clear-space ({evidence.clear_space_ratio_h.toFixed(2)}H) intrusion{" "}
            <strong>{evidence.clear_space_intrusion_pct.toFixed(1)}%</strong>
          </span>
        </div>
      );

    case "voice_readability":
      return (
        <div className="evidence-box">
          <span className="evidence-kind-tag">Voice & Readability</span>
          <span className="ev-metric">
            FK Grade <strong>{evidence.flesch_kincaid_grade.toFixed(1)}</strong> (max{" "}
            {evidence.max_flesch_kincaid_grade.toFixed(1)}) · Passive{" "}
            <strong>{evidence.passive_voice_pct.toFixed(0)}%</strong> · Max sentence{" "}
            <strong>{evidence.max_sentence_words_observed}w</strong>
          </span>
        </div>
      );

    case "trigger_obligation":
      return (
        <div className="evidence-box">
          <span className="evidence-kind-tag">Trigger Obligation ({evidence.obligation_id})</span>
          <span className="ev-del">{evidence.matched_trigger}</span>
          <span className="ev-arrow">requires</span>
          <span className="ev-ins">{evidence.required_disclaimer_text}</span>
        </div>
      );

    default:
      return null;
  }
}

const EMPTY_FINDINGS: FindingResponse[] = [];
const EMPTY_AUDIT: any[] = [];
const EMPTY_VERSIONS: any[] = [];
const EMPTY_COMMENTS: SubmissionCommentDto[] = [];

export function SubmissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { role } = useAuth();
  const subId = Number(id);

  const queryClient = useQueryClient();

  // TanStack Query for server state
  const { data: submission = null } = useQuery({
    queryKey: ["submission", subId],
    queryFn: () => getSubmission(subId),
    enabled: !Number.isNaN(subId),
  });

  const { data: serverFindings = EMPTY_FINDINGS } = useQuery({
    queryKey: ["findings", subId],
    queryFn: () => getFindings(subId),
    enabled: !Number.isNaN(subId),
  });

  const { data: comments = EMPTY_COMMENTS } = useQuery({
    queryKey: ["comments", subId],
    queryFn: () => listSubmissionComments(subId),
    enabled: !Number.isNaN(subId),
  });

  // Track live SSE stream during active scan
  const [liveFindings, setLiveFindings] = useState<FindingResponse[] | null>(null);
  const findings = liveFindings ?? serverFindings;

  const [scanning, setScanning] = useState(false);
  const [scanCount, setScanCount] = useState(0);
  const [alpha, setAlpha] = useState<number>(0.10);
  const [conformalCutoff, setConformalCutoff] = useState<number | null>(null);

  const [showAudit, setShowAudit] = useState(false);
  const { data: audit = EMPTY_AUDIT } = useQuery({
    queryKey: ["audit", subId],
    queryFn: () => getAuditTrail(subId),
    enabled: showAudit && !Number.isNaN(subId),
  });

  const [showVersions, setShowVersions] = useState(false);
  const { data: versions = EMPTY_VERSIONS } = useQuery({
    queryKey: ["versions", subId],
    queryFn: () => getSubmissionVersions(subId),
    enabled: showVersions && !Number.isNaN(subId),
  });

  const [error, setError] = useState("");
  const [selectedRowId, setSelectedRowId] = useState<number | null>(null);

  // Legal Reviewer Claim-Only / Unresolved Blockers & Overrides filter (Plan §2 Role 3)
  const [reviewerFilterOnly, setReviewerFilterOnly] = useState(false);

  // Cognitive forcing function: Blocker SlotDiff cards start collapsed and lock "Accept & Apply Fix"
  const [expandedSlotDiffIds, setExpandedSlotDiffIds] = useState<Record<number, boolean>>({});

  // Inline comment thread state
  const [activeCommentRowId, setActiveCommentRowId] = useState<number | null>(null);
  const [commentDraft, setCommentDraft] = useState("");

  // Cognitive forcing function state: track pending Override/Dismiss justification reason
  const [pendingReasonRowId, setPendingReasonRowId] = useState<number | null>(null);
  const [pendingResolutionKind, setPendingResolutionKind] = useState<"dismissed" | "overridden">("dismissed");
  const [reasonDraft, setReasonDraft] = useState<string>("");

  const editor = useEditor({
    extensions: [StarterKit, FindingsDecorationExtension],
    content: "",
    editable: false,
  });

  useEffect(() => {
    if (editor && submission) {
      const paragraphs = resolveEditorTextBlocks(submission);
      const html =
        paragraphs.length > 0
          ? paragraphs.map((p) => `<p>${escapeHtmlBlock(p)}</p>`).join("")
          : "<p><em>(Empty document)</em></p>";
      if (editor.getHTML() !== html) {
        editor.commands.setContent(html);
      }
    }
  }, [editor, submission]);

  useEffect(() => {
    if (!editor || !submission) return;
    const tr = editor.state.tr.setMeta(findingsPluginKey, {
      findings,
      paragraphNodeIds: submission.paragraph_node_ids || [],
      selectedRowId,
    });
    editor.view.dispatch(tr);
  }, [editor, submission, findings, selectedRowId]);

  useEffect(() => {
    if (!editor) return;
    const dom = editor.view.dom;
    const handleClick = (e: MouseEvent) => {
      const target = (e.target as HTMLElement).closest("[data-finding-row-id]");
      if (target) {
        const rowId = Number(target.getAttribute("data-finding-row-id"));
        if (!Number.isNaN(rowId)) {
          setSelectedRowId(rowId);
        }
      }
    };
    dom.addEventListener("click", handleClick);
    return () => dom.removeEventListener("click", handleClick);
  }, [editor]);

  // Mutations
  const workflowMutation = useMutation({
    mutationFn: (vars: { action: string; comment?: string }) =>
      workflowAction(subId, vars.action, vars.comment),
    onSuccess: (updated) => {
      queryClient.setQueryData(["submission", subId], updated);
      queryClient.invalidateQueries({ queryKey: ["submission", subId] });
      queryClient.invalidateQueries({ queryKey: ["audit", subId] });
      queryClient.invalidateQueries({ queryKey: ["submissions"] });
    },
    onError: (err: any) => {
      setError(err.message || "Workflow action failed");
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (vars: { rowId: number; resolution: string; reason?: string }) =>
      resolveFinding(subId, vars.rowId, vars.resolution, true, vars.reason),
    onSuccess: () => {
      setPendingReasonRowId(null);
      setReasonDraft("");
      queryClient.invalidateQueries({ queryKey: ["findings", subId] });
      queryClient.invalidateQueries({ queryKey: ["submission", subId] });
      queryClient.invalidateQueries({ queryKey: ["audit", subId] });
      queryClient.invalidateQueries({ queryKey: ["versions", subId] });
      queryClient.invalidateQueries({ queryKey: ["submissions"] });
    },
    onError: (err: any) => {
      setError(err.message || "Failed to resolve finding");
    },
  });

  const rewriteMutation = useMutation({
    mutationFn: (rowId: number) => rewriteFindingSpan(subId, rowId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["findings", subId] });
    },
    onError: (err: any) => {
      setError(err.message || "Tier 3 surgical rewrite failed");
    },
  });

  const commentMutation = useMutation({
    mutationFn: (vars: { body: string; findingId?: number | null }) =>
      addSubmissionComment(subId, vars.body, vars.findingId),
    onSuccess: () => {
      setCommentDraft("");
      queryClient.invalidateQueries({ queryKey: ["comments", subId] });
    },
    onError: (err: any) => {
      setError(err.message || "Failed to post comment");
    },
  });

  async function handleScan() {
    setScanning(true);
    setScanCount(0);
    setLiveFindings([]);
    setError("");

    await scanSubmission(
      subId,
      (finding) => {
        setScanCount((c) => c + 1);
        setLiveFindings((prev) => [...(prev || []), finding]);
      },
      async (_total, meta) => {
        setScanning(false);
        setLiveFindings(null);
        if (meta && typeof meta.conformal_threshold === "number") {
          setConformalCutoff(meta.conformal_threshold);
        }
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["submission", subId] }),
          queryClient.invalidateQueries({ queryKey: ["findings", subId] }),
          queryClient.invalidateQueries({ queryKey: ["audit", subId] }),
          queryClient.invalidateQueries({ queryKey: ["submissions"] }),
        ]);
      },
      (err) => {
        setScanning(false);
        setLiveFindings(null);
        setError(err.message);
      },
      alpha
    );
  }

  function handleWorkflow(action: string, comment?: string) {
    setError("");
    workflowMutation.mutate({ action, comment });
  }

  function handleResolve(findingRowId: number, resolution: string, reason?: string) {
    setError("");
    resolveMutation.mutate({ rowId: findingRowId, resolution, reason });
  }

  function startReasonPrompt(rowId: number, kind: "dismissed" | "overridden") {
    setPendingReasonRowId(rowId);
    setPendingResolutionKind(kind);
    setReasonDraft("");
  }

  function toggleSlotDiff(rowId: number) {
    setExpandedSlotDiffIds((prev) => ({ ...prev, [rowId]: !prev[rowId] }));
  }

  function loadAudit() {
    setShowAudit(true);
  }

  function loadVersions() {
    setShowVersions(true);
  }

  async function handleExportCertificate() {
    setError("");
    try {
      const cert = await getGovernanceCertificate(subId);
      const blob = new Blob([JSON.stringify(cert, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `canongate_cert_sub_${subId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err.message);
    }
  }

  if (!submission) {
    return <div className="loading">Loading...</div>;
  }

  const blockerCount = findings.filter((f) => f.severity >= 50 && f.resolution === "open").length;
  const warningCount = findings.filter((f) => f.severity > 0 && f.severity < 50 && f.resolution === "open").length;
  const resolvedCount = findings.filter((f) => f.resolution !== "open").length;

  const displayedFindings = reviewerFilterOnly
    ? findings.filter(
        (f) =>
          (f.severity >= 50 && f.resolution === "open") ||
          f.resolution === "overridden" ||
          f.payload?.evidence?.kind === "slot_diff"
      )
    : findings;

  return (
    <div className="detail-page">
      <header className="detail-header">
        <button className="btn-ghost" onClick={() => navigate("/")}>
          ← Back
        </button>
        <h1>{submission.title}</h1>
        <span
          className="status-badge large"
          style={{ backgroundColor: getStatusColor(submission.status) }}
        >
          {submission.status.replace(/_/g, " ")}
        </span>
      </header>

      {error && <p className="error-msg">{error}</p>}

      {/* Stats bar */}
      <div className="stats-bar">
        <div className="stat">
          <span className="stat-value" style={{ color: "#ef4444" }}>{blockerCount}</span>
          <span className="stat-label">Blockers</span>
        </div>
        <div className="stat">
          <span className="stat-value" style={{ color: "#f59e0b" }}>{warningCount}</span>
          <span className="stat-label">Warnings</span>
        </div>
        <div className="stat">
          <span className="stat-value" style={{ color: "#22c55e" }}>{resolvedCount}</span>
          <span className="stat-label">Resolved</span>
        </div>
        <div className="stat">
          <span className="stat-value">{findings.length}</span>
          <span className="stat-label">Total</span>
        </div>
      </div>

      {/* Actions bar & Conformal Risk Control Slider */}
      <div className="actions-bar">
        <button
          className="btn-primary"
          onClick={handleScan}
          disabled={scanning}
        >
          {scanning ? `Scanning... (${scanCount})` : "🔍 Run Scan"}
        </button>

        <div className="conformal-slider-box" title="Angelopoulos et al. Conformal Risk Control (controls max expected False Negative Rate α)">
          <label htmlFor="conformal-alpha">
            Conformal Risk α = <strong>{(alpha * 100).toFixed(0)}%</strong>
            {conformalCutoff !== null ? ` (λ̂ = ${conformalCutoff.toFixed(2)})` : ""}
          </label>
          <input
            id="conformal-alpha"
            type="range"
            min={0.02}
            max={0.25}
            step={0.01}
            value={alpha}
            onChange={(e) => setAlpha(parseFloat(e.target.value))}
          />
        </div>

        <button
          className={reviewerFilterOnly ? "btn-accent" : "btn-ghost"}
          onClick={() => setReviewerFilterOnly((v) => !v)}
          title="Authorised Legal Reviewer view: filter to unresolved Blockers, SlotDiff claims, and Creator Overrides"
        >
          ⚖️ {reviewerFilterOnly ? "Showing Claims & Blockers Only" : "Claim-Only / Blocker Filter"}
        </button>

        {submission.status === "draft" && (
          <button className="btn-accent" onClick={() => handleWorkflow("submit")}>
            Submit for Review
          </button>
        )}
        {submission.status === "in_review" && (role === "reviewer" || role === "admin") && (
          <>
            <button className="btn-success" onClick={() => handleWorkflow("approve")}>
              ✓ Approve
            </button>
            <button className="btn-warning" onClick={() => handleWorkflow("request_changes")}>
              ✎ Request Changes
            </button>
          </>
        )}
        {submission.status === "changes_requested" && (
          <button className="btn-accent" onClick={() => handleWorkflow("submit")}>
            Resubmit
          </button>
        )}
        {submission.status === "approved" && role === "admin" && (
          <button className="btn-success" onClick={() => handleWorkflow("publish")}>
            🚀 Publish
          </button>
        )}
        <button className="btn-ghost" onClick={loadVersions}>
          🕘 Revisions
        </button>
        <button className="btn-ghost" onClick={loadAudit}>
          📜 Audit Trail
        </button>
        <button className="btn-ghost" onClick={handleExportCertificate}>
          🔐 Export Certificate
        </button>
      </div>

      {/* Interactive Banner Image BBox SVG Overlay */}
      {submission.image_nodes && submission.image_nodes.length > 0 && (
        <BannerBBoxOverlay
          imageNodes={submission.image_nodes}
          findings={findings}
          selectedRowId={selectedRowId}
          onSelectFinding={(rowId) => setSelectedRowId(rowId)}
        />
      )}

      {/* Interactive ProseMirror Document Viewer with Inline Findings */}
      <section className="editor-section">
        <div className="section-header">
          <h2>📄 Document Content (Interactive Governance View)</h2>
          <span className="editor-subtext">
            Inline highlights indicate policy violations directly on the text (click a finding below to highlight)
          </span>
        </div>
        <div className="editor-container">
          <EditorContent editor={editor} />
        </div>
      </section>

      {/* Findings list */}
      <section className="findings-section">
        <h2>Findings ({displayedFindings.length})</h2>
        {displayedFindings.length === 0 && !scanning && (
          <p className="empty-state">No findings match the current filter. Run a scan to check this content.</p>
        )}
        <div className="findings-list">
          {displayedFindings.map((f) => {
            const verdict = f.severity >= 50 ? 2 : f.severity > 0 ? 1 : 0;
            const isBlocker = f.severity >= 50;
            const trace = f.payload?.trace;
            const hasSlotDiff = f.payload?.evidence?.kind === "slot_diff";
            const isSlotDiffExpanded = !isBlocker || !hasSlotDiff || !!expandedSlotDiffIds[f.row_id];
            const cardComments = comments.filter((c) => c.finding_id === f.row_id);

            return (
              <div
                key={f.row_id}
                className={`finding-card ${f.resolution !== "open" ? "resolved" : ""} ${selectedRowId === f.row_id ? "selected" : ""}`}
                onClick={() => setSelectedRowId(f.row_id)}
                style={{
                  cursor: "pointer",
                  border: selectedRowId === f.row_id ? "1px solid var(--accent-indigo)" : undefined,
                }}
              >
                <div className="finding-header">
                  <span
                    className="verdict-badge"
                    style={{ backgroundColor: VERDICT_COLORS[String(verdict)] }}
                  >
                    {VERDICT_LABELS[String(verdict)]}
                  </span>
                  <span className="check-id">{f.check_id}</span>
                  <span className="severity">S:{f.severity}</span>
                  {f.payload?.rule_ref?.rule_id && (
                    <span className="rule-ref-badge" title={f.payload.rule_ref.source_text || ""}>
                      Rule: {f.payload.rule_ref.rule_id}
                    </span>
                  )}
                  {trace && (
                    <span
                      className="tier-badge"
                      title={`Context Trace — Tier: ${trace.tier}${trace.model_sha ? ` | SHA: ${trace.model_sha}` : ""}`}
                    >
                      {trace.tier === "deterministic" || trace.tier === 1
                        ? "⚙️ CONTEXT TRACE: TIER 1 (ZERO AI)"
                        : trace.tier === "smt"
                          ? "🧮 CONTEXT TRACE: TIER 1.5 (Z3 SMT)"
                          : trace.tier === 3 || trace.tier === "generative"
                            ? "✨ CONTEXT TRACE: TIER 3 (REWRITER)"
                            : "🤖 CONTEXT TRACE: TIER 2 (LOCAL NLI)"}{" "}
                      {typeof trace.latency_ms === "number"
                        ? `· ${trace.latency_ms.toFixed(1)}ms`
                        : ""}
                    </span>
                  )}
                </div>
                <p className="finding-message">{f.message}</p>
                <EvidenceView
                  evidence={f.payload?.evidence}
                  slotDiffExpanded={isSlotDiffExpanded}
                  onToggleSlotDiff={
                    isBlocker && hasSlotDiff ? () => toggleSlotDiff(f.row_id) : undefined
                  }
                />
                {f.payload?.suggestion && (
                  <div className="suggestion">
                    💡 {f.payload.suggestion.label}
                  </div>
                )}
                <div className="finding-actions" onClick={(e) => e.stopPropagation()}>
                  {f.resolution === "open" ? (
                    pendingReasonRowId === f.row_id ? (
                      <div className="reason-forcing-box">
                        <input
                          type="text"
                          className="reason-input"
                          placeholder={`Justification required to ${pendingResolutionKind === "overridden" ? "override" : "dismiss"} (min 3 chars)...`}
                          value={reasonDraft}
                          onChange={(e) => setReasonDraft(e.target.value)}
                          autoFocus
                        />
                        <button
                          className="btn-sm btn-warning"
                          disabled={reasonDraft.trim().length < 3}
                          onClick={() =>
                            handleResolve(
                              f.row_id,
                              pendingResolutionKind,
                              reasonDraft.trim()
                            )
                          }
                        >
                          Confirm {pendingResolutionKind === "overridden" ? "Override" : "Dismiss"}
                        </button>
                        <button
                          className="btn-sm btn-ghost"
                          onClick={() => {
                            setPendingReasonRowId(null);
                            setReasonDraft("");
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          className="btn-sm btn-success"
                          disabled={!isSlotDiffExpanded}
                          title={
                            !isSlotDiffExpanded
                              ? "Apply fix · locked until SlotDiff is expanded (Buçinca et al., CSCW 2021)"
                              : undefined
                          }
                          onClick={() => handleResolve(f.row_id, "accepted")}
                        >
                          {!isSlotDiffExpanded
                            ? "🔒 Apply Fix · Locked Until SlotDiff Expanded"
                            : f.payload?.suggestion?.replacements?.length
                              ? "Accept & Apply Fix"
                              : "Accept"}
                        </button>

                        <button
                          className="btn-sm btn-ghost"
                          onClick={() => rewriteMutation.mutate(f.row_id)}
                          disabled={rewriteMutation.isPending}
                          title="Tier 3 Constrained Rewriter (<=35% edit distance, Presidio PII scrub, Tier 1+2 re-verified)"
                        >
                          ✨ Tier 3 Rewrite
                        </button>

                        {(role === "reviewer" || role === "admin") && (
                          <button
                            className="btn-sm btn-ghost"
                            onClick={() => startReasonPrompt(f.row_id, "dismissed")}
                          >
                            Dismiss
                          </button>
                        )}

                        {(!isBlocker || role === "reviewer" || role === "admin") && (
                          <button
                            className="btn-sm btn-warning"
                            onClick={() => startReasonPrompt(f.row_id, "overridden")}
                          >
                            {isBlocker ? "Reviewer Override" : "Deliberate Override"}
                          </button>
                        )}

                        <button
                          className="btn-sm btn-ghost"
                          onClick={() =>
                            setActiveCommentRowId(
                              activeCommentRowId === f.row_id ? null : f.row_id
                            )
                          }
                        >
                          💬 Comment ({cardComments.length})
                        </button>
                      </>
                    )
                  ) : (
                    <div className="resolved-meta">
                      <span className="resolution-badge">{f.resolution}</span>
                      {f.resolution_reason && (
                        <span className="resolution-reason-note">
                          “{f.resolution_reason}”
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* Inline Comment Thread for this Finding */}
                {(activeCommentRowId === f.row_id || cardComments.length > 0) && (
                  <div
                    className="finding-comments-box"
                    onClick={(e) => e.stopPropagation()}
                    style={{ marginTop: "0.6rem", paddingTop: "0.5rem", borderTop: "1px solid rgba(255,255,255,0.08)" }}
                  >
                    {cardComments.map((c) => (
                      <div key={c.id} className="comment-item" style={{ fontSize: "0.85rem", marginBottom: "0.3rem" }}>
                        <strong>{c.author_name}</strong>{" "}
                        <span className="role-chip">{c.role}</span>: {c.body}
                      </div>
                    ))}
                    {activeCommentRowId === f.row_id && (
                      <div className="reason-forcing-box" style={{ marginTop: "0.4rem" }}>
                        <input
                          type="text"
                          className="reason-input"
                          placeholder="Add an inline comment on this finding..."
                          value={commentDraft}
                          onChange={(e) => setCommentDraft(e.target.value)}
                        />
                        <button
                          className="btn-sm btn-primary"
                          disabled={!commentDraft.trim()}
                          onClick={() =>
                            commentMutation.mutate({
                              body: commentDraft.trim(),
                              findingId: f.row_id,
                            })
                          }
                        >
                          Post
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Immutable Revision History modal */}
      {showVersions && (
        <div className="modal-overlay" onClick={() => setShowVersions(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>Immutable Revision History</h2>
            <div className="audit-list">
              {versions.map((ver) => (
                <div key={ver.version_number} className="audit-event">
                  <div className="audit-chain">
                    <strong>v{ver.version_number}</strong>
                    <code title={ver.content_hash}>{ver.content_hash.slice(0, 10)}…</code>
                  </div>
                  <div className="audit-body">
                    <span>{ver.change_note || "Revision snapshot"}</span>
                  </div>
                  <span className="audit-time">{ver.created_at}</span>
                </div>
              ))}
            </div>
            <button className="btn-ghost" onClick={() => setShowVersions(false)}>
              Close
            </button>
          </div>
        </div>
      )}

      {/* Audit trail modal */}
      {showAudit && (
        <div className="modal-overlay" onClick={() => setShowAudit(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>Audit Trail (RFC 9162 Merkle + Ed25519 STH)</h2>
            <div className="audit-list">
              {audit.map((evt, i) => (
                <div key={evt.id} className="audit-event">
                  <div className="audit-chain">
                    <code title={evt.event_hash}>{evt.event_hash.slice(0, 8)}…</code>
                    {i > 0 && <span className="chain-link">⟵ {evt.prev_hash.slice(0, 8)}…</span>}
                  </div>
                  <div className="audit-body">
                    <strong>{evt.action}</strong>: {evt.from_status} → {evt.to_status}
                    {evt.comment && <p className="audit-comment">"{evt.comment}"</p>}
                  </div>
                  <span className="audit-time">{evt.created_at}</span>
                </div>
              ))}
              {audit.length === 0 && <p>No events yet.</p>}
            </div>
            <button className="btn-ghost" onClick={() => setShowAudit(false)}>Close</button>
          </div>
        </div>
      )}
    </div>
  );
}

function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    draft: "#6366f1",
    in_review: "#f59e0b",
    changes_requested: "#ef4444",
    approved: "#22c55e",
    published: "#06b6d4",
  };
  return colors[status] || "#888";
}
