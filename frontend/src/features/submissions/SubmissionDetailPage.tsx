import {
  useState,
  useEffect,
  useCallback,
  useRef,
  useMemo,
  type ReactNode,
} from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  getSubmission,
  getFindings,
  resolveFinding,
  workflowAction,
  getAuditTrail,
  getSubmissionVersions,
  getGovernanceCertificate,
  getSubmissionComments,
  createSubmissionComment,
  rewriteFindingSpan,
  updateSubmissionContent,
  triggerScan,
  type Submission,
  type FindingItem,
  type AuditEvent,
  type SubmissionVersionItem,
  type SubmissionCommentItem,
  type SurgicalRewriteResponse,
  type ImageNodeMeta,
} from "../../api/client";
import { useAuth } from "../auth/context";
import { codepointIndexToUtf16Offset } from "./FindingHighlightsExtension";

const ROLE_DISPLAY: Record<string, string> = {
  creator: "Creator · Stage 1",
  reviewer: "Brand Manager · Stage 2",
  admin: "Authorised Legal Reviewer · Stage 3",
};

// Role-gated workflow transitions matching backend/src/canongate/domain/workflow.py
const WORKFLOW_ACTIONS: Record<
  string,
  Array<{ action: string; label: string; roles: string[] }>
> = {
  draft: [
    {
      action: "submit",
      label: "Submit for Brand Review →",
      roles: ["creator", "admin"],
    },
  ],
  in_review: [
    {
      action: "approve",
      label: "✓ Approve Brand Review → Forward to Legal",
      roles: ["reviewer", "admin"],
    },
    {
      action: "request_changes",
      label: "Request Changes",
      roles: ["reviewer", "admin"],
    },
    { action: "recall", label: "Recall to Draft", roles: ["creator", "admin"] },
  ],
  changes_requested: [
    {
      action: "submit",
      label: "Resubmit for Brand Review →",
      roles: ["creator", "admin"],
    },
  ],
  approved: [
    {
      action: "publish",
      label: "⛨ Execute Final Legal Sign-Off & Release",
      roles: ["admin"],
    },
    {
      action: "recall",
      label: "Return to Brand Review",
      roles: ["reviewer", "admin"],
    },
  ],
  published: [],
};

const WORKFLOW_STAGES = [
  {
    num: 1,
    key: "stage1",
    title: "Creator Pre-Flight",
    ownerRole: "creator",
    ownerLabel: "Creator",
    statuses: ["draft", "changes_requested"],
    desc: "Run pre-flight check, fix Blockers, and document context on Warning overrides.",
  },
  {
    num: 2,
    key: "stage2",
    title: "Brand Manager Review",
    ownerRole: "reviewer",
    ownerLabel: "Brand Manager",
    statuses: ["in_review"],
    desc: "Inspect revision diffs, verify brand compliance & overrides, and approve.",
  },
  {
    num: 3,
    key: "stage3",
    title: "Authorised Legal Sign-Off",
    ownerRole: "admin",
    ownerLabel: "Legal Reviewer",
    statuses: ["approved"],
    desc: "Audit high-risk claims & disclosures; execute final release sign-off.",
  },
  {
    num: 4,
    key: "stage4",
    title: "Approved & Released",
    ownerRole: "published",
    ownerLabel: "Released",
    statuses: ["published"],
    desc: "Cryptographically sealed with a downloadable Governance Certificate.",
  },
] as const;

interface SlotComparisonItem {
  slot?: string;
  slot_name?: string;
  canon_value: string | null;
  draft_value: string | null;
  status: "match" | "contradicted" | "dropped" | "added" | "unverified";
}

interface ExtractedBBoxOverlay {
  rowId: number;
  findingId: string;
  checkId: string;
  severity: number;
  resolution: string;
  message: string;
  x: number;
  y: number;
  w: number;
  h: number;
  assetIndex: number;
}

/** Resolve backend asset URLs cleanly via relative `/api/...` paths or data URIs. */
function resolveAssetUrl(url: string): string {
  if (!url) return "";
  if (url.startsWith("data:") || url.startsWith("blob:")) return url;
  if (url.startsWith("http://") || url.startsWith("https://")) {
    try {
      const parsed = new URL(url);
      return `${parsed.pathname}${parsed.search}`;
    } catch {
      return url;
    }
  }
  return url.startsWith("/") ? url : `/${url}`;
}

/**
 * Pure React inline span highlighter for a paragraph/table block.
 * Highlights every `[start, end]` finding on `nodeId` and scrolls to the
 * corresponding Finding Card when clicked — with zero Tiptap extension crashes.
 */
function renderHighlightedBlock(
  blockText: string,
  nodeId: string | undefined,
  findings: FindingItem[],
  selectedFindingId: number | null,
  onSelectFinding: (rowId: number) => void,
): ReactNode {
  if (!nodeId || !blockText) {
    return blockText;
  }

  const blockFindings = findings
    .filter((f) => {
      const loc = f.payload?.locator;
      return (
        f.node_id === nodeId &&
        typeof loc?.start === "number" &&
        typeof loc?.end === "number" &&
        loc.end > loc.start
      );
    })
    .map((f) => {
      const s = codepointIndexToUtf16Offset(
        blockText,
        Math.max(0, f.payload.locator.start ?? 0),
      );
      const e = Math.min(
        blockText.length,
        codepointIndexToUtf16Offset(
          blockText,
          Math.max(0, f.payload.locator.end ?? 0),
        ),
      );
      return {
        finding: f,
        start: s,
        end: e,
      };
    })
    .filter((r) => r.end > r.start)
    .sort((a, b) => a.start - b.start || b.finding.severity - a.finding.severity);

  if (blockFindings.length === 0) {
    return blockText;
  }

  const segments: ReactNode[] = [];
  let cursor = 0;

  blockFindings.forEach((item, idx) => {
    if (item.start > cursor) {
      segments.push(blockText.slice(cursor, item.start));
    }
    if (item.end > cursor) {
      const sliceStart = Math.max(cursor, item.start);
      const spanText = blockText.slice(sliceStart, item.end);
      const f = item.finding;
      const isBlocker = f.severity >= 50;
      const isSelected = selectedFindingId === f.row_id;
      const cls = [
        "finding-inline-mark",
        f.resolution !== "open"
          ? "finding-mark-resolved"
          : isBlocker
            ? "finding-mark-blocker"
            : "finding-mark-warning",
        isSelected ? "finding-mark-selected" : "",
      ]
        .filter(Boolean)
        .join(" ");

      segments.push(
        <mark
          key={`mark-${f.row_id}-${idx}`}
          className={cls}
          data-finding-row-id={f.row_id}
          title={`${f.check_id}: ${f.message}`}
          onClick={() => onSelectFinding(f.row_id)}
        >
          {spanText}
        </mark>,
      );
      cursor = item.end;
    }
  });

  if (cursor < blockText.length) {
    segments.push(blockText.slice(cursor));
  }

  return segments;
}

/**
 * Extract pixel bounding boxes `[x, y, w, h]` from both:
 * 1. Direct `ImageNode` findings (`locator.kind === "bbox"`).
 * 2. Low-confidence / micro-height OCR `TextNode` findings.
 */
function extractBannerOverlays(
  findings: FindingItem[],
  imageNodes: ImageNodeMeta[],
): ExtractedBBoxOverlay[] {
  if (imageNodes.length === 0) return [];
  const overlays: ExtractedBBoxOverlay[] = [];
  const bboxTagRe = /bbox=(\d+)_(\d+)_(\d+)_(\d+)/;

  for (const f of findings) {
    const loc = f.payload?.locator;
    if (
      typeof loc?.x === "number" &&
      typeof loc?.y === "number" &&
      typeof loc?.w === "number" &&
      typeof loc?.h === "number"
    ) {
      const matchedIdx = imageNodes.findIndex(
        (img) => img.node_id === f.node_id,
      );
      overlays.push({
        rowId: f.row_id,
        findingId: f.finding_id,
        checkId: f.check_id,
        severity: f.severity,
        resolution: f.resolution,
        message: f.message,
        x: loc.x,
        y: loc.y,
        w: loc.w,
        h: loc.h,
        assetIndex: matchedIdx >= 0 ? matchedIdx : 0,
      });
      continue;
    }

    const ev = f.payload?.evidence ?? {};
    const bboxStr =
      typeof ev.bbox === "string"
        ? ev.bbox
        : bboxTagRe.exec(f.message)?.[0] ?? "";
    const m =
      bboxTagRe.exec(bboxStr) ?? /(\d+)_(\d+)_(\d+)_(\d+)/.exec(bboxStr);
    if (m) {
      overlays.push({
        rowId: f.row_id,
        findingId: f.finding_id,
        checkId: f.check_id,
        severity: f.severity,
        resolution: f.resolution,
        message: f.message,
        x: Number(m[1]),
        y: Number(m[2]),
        w: Number(m[3]),
        h: Number(m[4]),
        assetIndex: 0,
      });
    }
  }

  return overlays;
}

export function SubmissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const submissionId = Number(id);
  const { username, displayName, role, logout } = useAuth();
  const navigate = useNavigate();

  const [submission, setSubmission] = useState<Submission | null>(null);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [versions, setVersions] = useState<SubmissionVersionItem[]>([]);
  const [comments, setComments] = useState<SubmissionCommentItem[]>([]);
  const [scanning, setScanning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<
    "all" | "blockers" | "warnings" | "claims_only"
  >("all");
  const [selectedFindingId, setSelectedFindingId] = useState<number | null>(
    null,
  );
  const [selectedAssetIdx, setSelectedAssetIdx] = useState<number>(0);

  // Direct Draft Editor state (Stage 1: Creator can edit copy & re-scan)
  const [isEditingDraft, setIsEditingDraft] = useState<boolean>(false);
  const [draftEditValue, setDraftEditValue] = useState<string>("");
  const [draftChangeNote, setDraftChangeNote] = useState<string>(
    "Updated campaign copy to resolve compliance findings",
  );
  const [savingDraft, setSavingDraft] = useState<boolean>(false);

  // Sensitivity / Conformal Risk Control (alpha) state
  const [conformalAlpha, setConformalAlpha] = useState<number>(0.1);

  // Track which SlotDiff tables have been expanded by the user
  const [expandedSlotDiffs, setExpandedSlotDiffs] = useState<
    Record<number, boolean>
  >({});

  // Structured Deliberate Override / Dismiss / Remediation popover state
  const [overrideTarget, setOverrideTarget] = useState<{
    rowId: number;
    mode: "overridden" | "dismissed" | "accepted";
  } | null>(null);
  const [overrideReason, setOverrideReason] = useState<string>("");

  // Inline comment composer state
  const [commentTargetRowId, setCommentTargetRowId] = useState<number | null>(
    null,
  );
  const [commentBody, setCommentBody] = useState<string>("");
  const [postingComment, setPostingComment] = useState<boolean>(false);
  const [generalCommentBody, setGeneralCommentBody] = useState<string>("");

  // Constrained Rewriter state
  const [rewritingRowId, setRewritingRowId] = useState<number | null>(null);
  const [rewritePreviews, setRewritePreviews] = useState<
    Record<number, SurgicalRewriteResponse>
  >({});

  // Modals
  const [showAuditModal, setShowAuditModal] = useState(false);
  const [showVersionsModal, setShowVersionsModal] = useState(false);
  const [exportingCert, setExportingCert] = useState(false);

  // Workflow comment modal
  const [wfAction, setWfAction] = useState<string | null>(null);
  const [wfComment, setWfComment] = useState("");

  const autoScannedRef = useRef<boolean>(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sub, fnd, aud, vers, cmts] = await Promise.all([
        getSubmission(submissionId),
        getFindings(submissionId),
        getAuditTrail(submissionId),
        getSubmissionVersions(submissionId).catch(() => []),
        getSubmissionComments(submissionId).catch(() => []),
      ]);
      setSubmission(sub);
      setFindings(fnd);
      setAudit(aud);
      setVersions(vers);
      setComments(cmts);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [submissionId]);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) {
        load();
      }
    });
    return () => {
      active = false;
    };
  }, [load]);

  // Auto-trigger scan once if a newly created draft bundle is opened with 0 findings
  useEffect(() => {
    if (
      !loading &&
      submission &&
      submission.status === "draft" &&
      findings.length === 0 &&
      !scanning &&
      !autoScannedRef.current
    ) {
      autoScannedRef.current = true;
      setScanning(true);
      triggerScan(
        submissionId,
        () => {},
        () => {
          setScanning(false);
          load();
        },
        () => {
          setScanning(false);
        },
        conformalAlpha,
      );
    }
  }, [
    loading,
    submission,
    findings.length,
    scanning,
    submissionId,
    conformalAlpha,
    load,
  ]);

  // Default Authorised Legal Reviewer (admin) to Claim-Only & Overrides view
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active) {
        setFilter(role === "admin" ? "claims_only" : "all");
      }
    });
    return () => {
      active = false;
    };
  }, [role]);

  function handleStartEditDraft() {
    if (!submission) return;
    const textOnlyBlocks =
      submission.text_blocks && submission.text_blocks.length > 0
        ? submission.text_blocks
        : (submission.raw_content || "")
            .split(/\n{2,}/)
            .map((b) => b.trim())
            .filter((b) => b && !b.startsWith("!["));
    setDraftEditValue(textOnlyBlocks.join("\n\n"));
    setIsEditingDraft(true);
  }

  async function handleSaveEditedDraft() {
    if (!submission) return;
    setSavingDraft(true);
    setError(null);
    try {
      await updateSubmissionContent(
        submissionId,
        draftEditValue,
        draftChangeNote.trim() || "Edited campaign copy in Review Studio",
        conformalAlpha,
      );
      setIsEditingDraft(false);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSavingDraft(false);
    }
  }

  function handleScan() {
    setScanning(true);
    setError(null);

    triggerScan(
      submissionId,
      () => {},
      () => {
        setScanning(false);
        load();
      },
      (err) => {
        setScanning(false);
        setError(err.message);
      },
      conformalAlpha,
    );
  }

  async function handleResolve(
    rowId: number,
    resolution: "accepted" | "dismissed" | "overridden",
    reason?: string,
  ) {
    setError(null);
    try {
      await resolveFinding(submissionId, rowId, resolution, reason);
      setOverrideTarget(null);
      setOverrideReason("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handlePostComment(findingId: number | null, bodyText: string) {
    if (!bodyText.trim()) return;
    setPostingComment(true);
    setError(null);
    try {
      const created = await createSubmissionComment(
        submissionId,
        bodyText.trim(),
        findingId,
      );
      setComments((prev) => [...prev, created]);
      if (findingId === null) {
        setGeneralCommentBody("");
      } else {
        setCommentBody("");
        setCommentTargetRowId(null);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPostingComment(false);
    }
  }

  async function handleTier3Rewrite(rowId: number) {
    setRewritingRowId(rowId);
    setError(null);
    try {
      const res = await rewriteFindingSpan(submissionId, rowId);
      setRewritePreviews((prev) => ({ ...prev, [rowId]: res }));
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRewritingRowId(null);
    }
  }

  async function handleExportCertificate() {
    setExportingCert(true);
    setError(null);
    try {
      const cert = await getGovernanceCertificate(submissionId);
      const blob = new Blob([JSON.stringify(cert, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `canongate_certificate_sub_${submissionId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setExportingCert(false);
    }
  }

  async function handleWorkflow() {
    if (!wfAction) return;
    setError(null);
    try {
      const updated = await workflowAction(submissionId, wfAction, wfComment);
      setSubmission(updated);
      setWfAction(null);
      setWfComment("");
      const aud = await getAuditTrail(submissionId);
      setAudit(aud);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  // Filter findings and sort priority-grouped: Open Blockers -> Open Warnings -> Resolved
  const filteredFindings = useMemo(() => {
    const base = findings.filter((f) => {
      if (filter === "blockers") return f.severity >= 50;
      if (filter === "warnings") return f.severity < 50;
      if (filter === "claims_only") {
        const isClaimOrStatutory =
          f.check_id.startsWith("claim.") ||
          f.check_id.startsWith("trigger.") ||
          f.check_id.startsWith("legibility.") ||
          f.payload?.rule_ref?.rule_type === "fact" ||
          f.payload?.rule_ref?.rule_type === "trigger";
        const isOverridden =
          f.resolution === "overridden" || f.resolution === "dismissed";
        return isClaimOrStatutory || isOverridden || f.severity >= 50;
      }
      return true;
    });

    return [...base].sort((a, b) => {
      const aOpen = a.resolution === "open" ? 0 : 1;
      const bOpen = b.resolution === "open" ? 0 : 1;
      if (aOpen !== bOpen) return aOpen - bOpen;
      return b.severity - a.severity;
    });
  }, [findings, filter]);

  const blockerCount = findings.filter(
    (f) => f.severity >= 50 && f.resolution === "open",
  ).length;
  const warningCount = findings.filter(
    (f) => f.severity < 50 && f.resolution === "open",
  ).length;
  const resolvedCount = findings.filter((f) => f.resolution !== "open").length;

  const availableActions = submission
    ? (WORKFLOW_ACTIONS[submission.status] ?? []).filter((a) =>
        a.roles.includes(role ?? ""),
      )
    : [];

  const textBlocks = useMemo(() => {
    if (!submission) return [];
    if (submission.text_blocks && submission.text_blocks.length > 0) {
      return submission.text_blocks;
    }
    if (submission.raw_content) {
      return submission.raw_content
        .split(/\n{2,}/)
        .map((s) => s.trim())
        .filter((s) => s && !s.startsWith("!["));
    }
    return [];
  }, [submission]);

  const paragraphNodeIds = useMemo(
    () => submission?.paragraph_node_ids ?? [],
    [submission],
  );

  const imageNodes = useMemo(
    () => submission?.image_nodes ?? [],
    [submission],
  );

  const bannerOverlays = useMemo(
    () => extractBannerOverlays(findings, imageNodes),
    [findings, imageNodes],
  );

  const handleSelectFindingFromSpan = useCallback((rowId: number) => {
    setSelectedFindingId(rowId);
    const el = document.getElementById(`finding-card-${rowId}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, []);

  if (loading) {
    return (
      <div className="detail-page">
        <div className="loading-state">Opening Review Studio...</div>
      </div>
    );
  }

  if (!submission) {
    return (
      <div className="detail-page">
        <div className="error-banner">
          <span>Submission not found</span>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => navigate("/dashboard")}
          >
            ← Back to Queue
          </button>
        </div>
      </div>
    );
  }

  const activeBannerAsset =
    imageNodes.length > 0
      ? imageNodes[Math.min(selectedAssetIdx, imageNodes.length - 1)]
      : null;

  const activeStageObj =
    WORKFLOW_STAGES.find((st) =>
      (st.statuses as readonly string[]).includes(submission.status),
    ) ?? WORKFLOW_STAGES[0];

  const canCreatorEditDraft =
    submission.status === "draft" || submission.status === "changes_requested";

  return (
    <div className="detail-page">
      {/* Top Bar */}
      <header className="console-header-curved">
        <div className="header-left">
          <button
            type="button"
            onClick={() => navigate("/dashboard")}
            className="btn-ghost"
          >
            ← Queue
          </button>
          <div className="detail-title-group">
            <h1>{submission.title}</h1>
            <div className="detail-meta">
              <span className={`status-badge status-${submission.status}`}>
                {submission.status.replace("_", " ")}
              </span>
              <span className="meta-item">
                Playbook: <strong>{submission.canon_id}</strong> (
                <code>{submission.canon_hash.slice(0, 8)}…</code>)
              </span>
              <span className="meta-item">
                SHA-256: <code>{submission.content_hash.slice(0, 10)}…</code>
              </span>
            </div>
          </div>
        </div>

        <div className="header-right">
          {/* Authenticated User Identity & Locked RBAC Role Badge */}
          <div
            className="user-identity-pill"
            title={`Authenticated as ${displayName || username} (@${username})`}
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

          <span
            className="status-badge status-approved"
            style={{
              padding: "0.36rem 0.72rem",
              fontSize: "0.74rem",
            }}
            title="Role is bound to your signed-in account"
          >
            🔒 Role: {ROLE_DISPLAY[role || "creator"] ?? role}
          </span>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => setShowVersionsModal(true)}
          >
            Revisions ({versions.length || 1})
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => setShowAuditModal(true)}
          >
            Audit Trail ({audit.length})
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={handleExportCertificate}
            disabled={exportingCert}
            title="Download signed Governance Certificate JSON"
          >
            {exportingCert ? "Exporting..." : "⛨ Export Certificate"}
          </button>

          <button
            type="button"
            className="btn-primary"
            onClick={handleScan}
            disabled={scanning}
          >
            {scanning ? "Scanning..." : "⚡ Run Governance Check"}
          </button>
        </div>
      </header>

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

      {/* 4-Stage Collaborative Workflow Stepper & Action Gate */}
      <section
        className="studio-workflow-stepper"
        aria-label="4-Stage Governance Progress"
      >
        <div className="stepper-track">
          {WORKFLOW_STAGES.map((st) => {
            const isCurrent = st.num === activeStageObj.num;
            const isCompleted = st.num < activeStageObj.num;
            return (
              <div
                key={st.key}
                className={`stepper-node ${isCurrent ? "current" : ""} ${
                  isCompleted ? "completed" : ""
                }`}
              >
                <div className="stepper-node-header">
                  <span className="stepper-badge">
                    {isCompleted ? "✓" : st.num}
                  </span>
                  <div>
                    <div className="stepper-title">{st.title}</div>
                    <div className="stepper-owner">Role: {st.ownerLabel}</div>
                  </div>
                </div>
                <p className="stepper-desc">{st.desc}</p>
              </div>
            );
          })}
        </div>

        <div className="stepper-actions-bar">
          <div className="stepper-gate-summary">
            <span className="gate-pill gate-blocker">
              {blockerCount} Open Blocker{blockerCount === 1 ? "" : "s"}
            </span>
            <span className="gate-pill gate-warning">
              {warningCount} Open Warning{warningCount === 1 ? "" : "s"}
            </span>
            <span className="gate-pill gate-resolved">
              {resolvedCount} Resolved
            </span>
            {blockerCount > 0 && (
              <span className="gate-lock-notice">
                🔒 Approval &amp; Release locked until all {blockerCount} Blocker
                {blockerCount === 1 ? "" : "s"} are resolved
              </span>
            )}
          </div>

          <div className="stepper-cta-group">
            {availableActions.length > 0 ? (
              availableActions.map((a) => {
                const blockedByGate =
                  (a.action === "approve" || a.action === "publish") &&
                  blockerCount > 0;
                return (
                  <button
                    key={a.action}
                    type="button"
                    disabled={blockedByGate}
                    title={
                      blockedByGate
                        ? `Resolve ${blockerCount} open Blocker(s) before ${a.action}`
                        : a.label
                    }
                    className={`btn-action btn-action-${a.action}`}
                    onClick={() => setWfAction(a.action)}
                  >
                    {a.label}
                  </button>
                );
              })
            ) : submission.status === "published" ? (
              <span className="published-seal-badge">
                ✓ Approved &amp; Released — Certificate Ready
              </span>
            ) : (
              <div className="role-handoff-hint">
                <span>
                  🔒 Stage {activeStageObj.num} requires{" "}
                  <strong>{activeStageObj.ownerLabel}</strong> sign-off (signed
                  in as <code>@{username}</code>).
                </span>
                {activeStageObj.ownerRole !== "published" && (
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ padding: "0.3rem 0.7rem", fontSize: "0.78rem" }}
                    onClick={() => {
                      logout();
                      navigate(
                        `/login?role=${activeStageObj.ownerRole}&redirect=/submissions/${submissionId}`,
                      );
                    }}
                  >
                    Sign In with {activeStageObj.ownerLabel} Account →
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Workflow transition confirmation modal */}
      {wfAction && (
        <div className="modal-overlay" onClick={() => setWfAction(null)}>
          <div className="modal card" onClick={(e) => e.stopPropagation()}>
            <h3>
              Confirm Stage Transition:{" "}
              <span style={{ textTransform: "capitalize" }}>
                {wfAction.replace("_", " ")}
              </span>
            </h3>
            <p
              style={{
                fontSize: "0.84rem",
                color: "var(--text-secondary)",
                marginBottom: "0.75rem",
              }}
            >
              This transition will be recorded in the tamper-evident audit log
              under <strong>@{username}</strong> ({role}).
            </p>
            <div className="form-group">
              <label htmlFor="wf-comment">Review Note (optional)</label>
              <textarea
                id="wf-comment"
                rows={3}
                value={wfComment}
                onChange={(e) => setWfComment(e.target.value)}
                placeholder="Add context for this decision..."
              />
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setWfAction(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={handleWorkflow}
              >
                Confirm Transition
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Split-Screen Review Studio */}
      <div className="detail-content">
        {/* LEFT PANE: Banner Inspector + Campaign Document + Discussion */}
        <div className="editor-pane">
          {/* 1. Promotional Banner Inspector */}
          {activeBannerAsset && (
            <section className="content-panel card banner-overlay-section">
              <div className="banner-panel-header">
                <div>
                  <h2>Promotional Banner &amp; Visual Inspector</h2>
                  <p className="gov-panel-desc" style={{ marginBottom: 0 }}>
                    Inspecting logo geometry, brand colour accuracy, contrast
                    legibility, and fine-print disclaimers (
                    {activeBannerAsset.width}×{activeBannerAsset.height}px).
                  </p>
                </div>
                {imageNodes.length > 1 && (
                  <div className="banner-asset-tabs">
                    {imageNodes.map((img, idx) => (
                      <button
                        key={img.node_id}
                        type="button"
                        className={`filter-tab ${
                          selectedAssetIdx === idx ? "active" : ""
                        }`}
                        onClick={() => setSelectedAssetIdx(idx)}
                      >
                        Banner #{idx + 1} ({img.width}×{img.height})
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="banner-canvas-wrapper">
                <div
                  className="banner-stage"
                  style={{
                    position: "relative",
                    display: "inline-block",
                    maxWidth: "100%",
                  }}
                >
                  <img
                    src={resolveAssetUrl(activeBannerAsset.url)}
                    alt={activeBannerAsset.alt ?? "Campaign Banner"}
                    className="banner-stage-img"
                  />
                  <svg
                    className="banner-svg-overlay"
                    viewBox={`0 0 ${activeBannerAsset.width} ${activeBannerAsset.height}`}
                    preserveAspectRatio="xMidYMid meet"
                  >
                    {bannerOverlays
                      .filter(
                        (ov) =>
                          ov.assetIndex === selectedAssetIdx ||
                          imageNodes.length === 1,
                      )
                      .map((ov) => {
                        const isSelected = selectedFindingId === ov.rowId;
                        const strokeColor =
                          ov.resolution !== "open"
                            ? "#10b981"
                            : ov.severity >= 50
                              ? "#ef4444"
                              : "#f59e0b";
                        return (
                          <g
                            key={ov.rowId}
                            style={{
                              pointerEvents: "all",
                              cursor: "pointer",
                            }}
                            onClick={() => handleSelectFindingFromSpan(ov.rowId)}
                          >
                            <rect
                              x={ov.x}
                              y={ov.y}
                              width={Math.max(ov.w, 12)}
                              height={Math.max(ov.h, 12)}
                              fill={
                                isSelected
                                  ? "rgba(239, 68, 68, 0.22)"
                                  : "rgba(239, 68, 68, 0.08)"
                              }
                              stroke={strokeColor}
                              strokeWidth={isSelected ? 4 : 2.5}
                              rx={3}
                            />
                            <text
                              x={ov.x + 4}
                              y={Math.max(14, ov.y - 4)}
                              fill="#ffffff"
                              stroke="#111827"
                              strokeWidth={0.6}
                              fontSize={Math.max(
                                11,
                                Math.round(activeBannerAsset.height * 0.032),
                              )}
                              fontWeight="bold"
                            >
                              {ov.checkId} (S={ov.severity})
                            </text>
                          </g>
                        );
                      })}
                  </svg>
                </div>
              </div>
            </section>
          )}

          {/* 2. Campaign Document & Inline Highlights */}
          <section className="content-panel card">
            <div className="editor-panel-header">
              <div>
                <h2>Campaign Content &amp; Highlighted Findings</h2>
                <p className="gov-panel-desc" style={{ marginBottom: 0 }}>
                  Click any highlighted phrase in the document to jump to its
                  finding card on the right.
                </p>
              </div>
              {canCreatorEditDraft && (
                <button
                  type="button"
                  className={isEditingDraft ? "btn-ghost" : "btn-secondary"}
                  onClick={() => {
                    if (isEditingDraft) {
                      setIsEditingDraft(false);
                    } else {
                      handleStartEditDraft();
                    }
                  }}
                >
                  {isEditingDraft
                    ? "Cancel Editing"
                    : "✎ Edit Campaign Copy & Re-Scan"}
                </button>
              )}
            </div>

            {isEditingDraft ? (
              <div className="draft-inline-editor">
                <label
                  htmlFor="studio-draft-textarea"
                  className="draft-editor-label"
                >
                  Edit Campaign Copy / Tables (separate blocks with a blank
                  line):
                </label>
                <textarea
                  id="studio-draft-textarea"
                  rows={10}
                  className="draft-editor-textarea"
                  value={draftEditValue}
                  onChange={(e) => setDraftEditValue(e.target.value)}
                />
                <div className="draft-editor-footer">
                  <input
                    type="text"
                    className="draft-change-note-input"
                    value={draftChangeNote}
                    onChange={(e) => setDraftChangeNote(e.target.value)}
                    placeholder="Revision note (e.g. Added mandatory eligibility condition)"
                  />
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={savingDraft}
                    onClick={handleSaveEditedDraft}
                  >
                    {savingDraft
                      ? "Saving & Re-Scanning..."
                      : "Save Revision & Re-Scan"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="content-preview tiptap-wrapper">
                {textBlocks.length > 0 ? (
                  <div className="ProseMirror">
                    {textBlocks.map((block, idx) => (
                      <p
                        key={paragraphNodeIds[idx] ?? idx}
                        style={{ margin: "0 0 0.85rem" }}
                      >
                        {renderHighlightedBlock(
                          block,
                          paragraphNodeIds[idx],
                          findings,
                          selectedFindingId,
                          handleSelectFindingFromSpan,
                        )}
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="text-muted">
                    No text content blocks in this bundle.
                  </p>
                )}
              </div>
            )}
          </section>

          {/* 3. Collaborative Review Discussion Thread */}
          <section className="content-panel card">
            <div
              className="gov-panel-header"
              style={{ marginBottom: "0.6rem" }}
            >
              <h2 style={{ marginBottom: 0 }}>
                Review Discussion (
                {comments.filter((c) => c.finding_id === null).length})
              </h2>
              <span className="sub-canon-tag">
                Creator · Brand Manager · Legal
              </span>
            </div>

            <div className="general-comments-list">
              {comments.filter((c) => c.finding_id === null).length === 0 ? (
                <p
                  className="text-muted"
                  style={{ fontSize: "0.82rem", marginBottom: "0.6rem" }}
                >
                  No review notes yet. Add a note below for the Brand Manager or
                  Legal Reviewer.
                </p>
              ) : (
                comments
                  .filter((c) => c.finding_id === null)
                  .map((c) => (
                    <div key={c.id} className="comment-item">
                      <span className="comment-author">
                        @{c.author_name} ({c.role}):
                      </span>{" "}
                      <span className="comment-body">{c.body}</span>
                    </div>
                  ))
              )}
            </div>

            <div className="inline-comment-composer">
              <input
                type="text"
                value={generalCommentBody}
                onChange={(e) => setGeneralCommentBody(e.target.value)}
                placeholder="Write a review note on this campaign..."
                className="comment-input"
              />
              <button
                type="button"
                className="btn-secondary"
                disabled={postingComment || !generalCommentBody.trim()}
                onClick={() => handlePostComment(null, generalCommentBody)}
              >
                Post Note
              </button>
            </div>
          </section>
        </div>

        {/* RIGHT PANE: Sticky Priority-Grouped Findings Sidebar */}
        <aside className="findings-pane">
          {/* Confidentiality & AI / External Service Disclosure Banner */}
          <div
            className="card"
            style={{
              padding: "0.65rem 0.9rem",
              marginBottom: "0.75rem",
              background: "rgba(15, 118, 110, 0.05)",
              border: "1px solid rgba(15, 118, 110, 0.24)",
              fontSize: "0.76rem",
              color: "#1e293b",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              <strong>
                🔒 Confidential Material Protection &amp; AI Disclosure
              </strong>
              <span className="tier-badge">DPDP 2025 Compliant</span>
            </div>
            <div style={{ marginTop: "0.22rem", color: "#475569" }}>
              Raw documents, KFS tables, and banners never leave this container.
              Every finding below discloses whether it used{" "}
              <strong>Tier 1 Deterministic Math (Zero AI)</strong>,{" "}
              <strong>Tier 2 Local NLI (MiniCheck-FT5 ONNX)</strong>, or{" "}
              <strong>Tier 3 PII-Scrubbed Rewrite</strong>.
            </div>
          </div>

          <div className="findings-toolbar card">
            <div className="findings-filter-tabs">
              <button
                type="button"
                className={`filter-tab ${filter === "all" ? "active" : ""}`}
                onClick={() => setFilter("all")}
              >
                All ({findings.length})
              </button>
              <button
                type="button"
                className={`filter-tab filter-blocker ${
                  filter === "blockers" ? "active" : ""
                }`}
                onClick={() => setFilter("blockers")}
              >
                Blockers ({blockerCount})
              </button>
              <button
                type="button"
                className={`filter-tab filter-warning ${
                  filter === "warnings" ? "active" : ""
                }`}
                onClick={() => setFilter("warnings")}
              >
                Warnings ({warningCount})
              </button>
              <button
                type="button"
                className={`filter-tab ${
                  filter === "claims_only" ? "active" : ""
                }`}
                onClick={() => setFilter("claims_only")}
                title="Legal Reviewer view: filters to claims, disclosures, blockers, and overrides"
              >
                ⚖ Claims &amp; Overrides
              </button>
            </div>

            <div className="conformal-alpha-control">
              <label htmlFor="alpha-select">Review Strictness:</label>
              <select
                id="alpha-select"
                value={conformalAlpha}
                onChange={(e) => setConformalAlpha(Number(e.target.value))}
              >
                <option value={0.04}>Strict (BFSI / Legal Sign-Off)</option>
                <option value={0.1}>Balanced (Standard Review)</option>
                <option value={0.2}>Permissive (Early Draft)</option>
              </select>
            </div>
          </div>

          {scanning ? (
            <div className="empty-state card">
              Scanning campaign against {submission.canon_id}...
            </div>
          ) : filteredFindings.length === 0 ? (
            <div className="empty-state card">
              {findings.length === 0
                ? "✓ Zero compliance issues found! This campaign bundle passes all active playbook rules."
                : "No findings match the current filter."}
            </div>
          ) : (
            <div className="findings-list">
              {filteredFindings.map((f) => {
                const isBlocker = f.severity >= 50;
                const isSelected = selectedFindingId === f.row_id;
                const evidence = f.payload?.evidence ?? {};
                const isSlotDiff =
                  evidence.kind === "slot_diff" &&
                  Array.isArray(evidence.slots);
                const slots = (
                  isSlotDiff ? evidence.slots : []
                ) as SlotComparisonItem[];
                const entailmentProb =
                  typeof evidence.entailment_prob === "number"
                    ? evidence.entailment_prob
                    : null;

                const isSlotExpanded = Boolean(expandedSlotDiffs[f.row_id]);
                const acceptLockedByForcingFunction =
                  isBlocker && isSlotDiff && !isSlotExpanded;

                const trace = f.payload?.trace;
                const hasTextSuggestion = Boolean(
                  f.payload?.suggestion &&
                    f.payload.suggestion.replacements.length > 0,
                );

                return (
                  <div
                    key={f.row_id}
                    id={`finding-card-${f.row_id}`}
                    onClick={() => setSelectedFindingId(f.row_id)}
                    className={`finding-card card ${
                      isBlocker ? "finding-blocker" : "finding-warning"
                    } ${f.resolution !== "open" ? "finding-resolved" : ""} ${
                      isSelected ? "finding-selected" : ""
                    }`}
                  >
                    <div className="finding-header">
                      <span
                        className={`severity-pill ${
                          isBlocker ? "sev-blocker" : "sev-warning"
                        }`}
                      >
                        {isBlocker ? "BLOCKER" : "WARNING"} · S={f.severity}
                      </span>
                      <span className="check-id">{f.check_id}</span>
                      {trace && (
                        <span
                          className="tier-badge"
                          title={`Tier: ${trace.tier} | AI Used: ${trace.ai_used ? "Yes" : "No"} | Model: ${trace.model_sha ?? trace.model_name ?? "Deterministic Math"} | External Service: ${trace.rewriter_provider ?? trace.external_service ?? (trace.external_call ? "External API" : "None (100% Local)")}${trace.latency_ms != null ? ` | Latency: ${trace.latency_ms.toFixed(1)}ms` : ""}`}
                        >
                          {trace.ai_used
                            ? `AI: ${trace.model_sha ?? trace.model_name ?? "Local NLI"} (${trace.rewriter_provider ?? trace.external_service ?? (trace.external_call ? "External" : "Local")})`
                            : String(trace.tier).toLowerCase() === "smt"
                              ? "TIER 1.5 · SMT SOLVER (100% LOCAL)"
                              : "TIER 1 · ZERO AI (100% LOCAL)"}
                        </span>
                      )}
                      {f.resolution !== "open" && (
                        <span className={`resolution-badge res-${f.resolution}`}>
                          {f.resolution}
                        </span>
                      )}
                    </div>

                    <p className="finding-message">{f.message}</p>

                    {f.payload?.rule_ref?.source_text && (
                      <div className="finding-rule">
                        <strong>
                          Approved Playbook Rule ({f.payload.rule_ref.rule_id}):
                        </strong>{" "}
                        {f.payload.rule_ref.source_text}
                      </div>
                    )}

                    {/* Claim Comparison Table (SlotDiff) */}
                    {isSlotDiff && slots.length > 0 && (
                      <div
                        className="slot-diff-box"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div
                          className="slot-diff-header"
                          style={{
                            cursor: "pointer",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                          }}
                          onClick={() =>
                            setExpandedSlotDiffs((prev) => ({
                              ...prev,
                              [f.row_id]: !prev[f.row_id],
                            }))
                          }
                        >
                          <span>
                            <strong>Claim vs. Approved Fact Comparison</strong>
                            {entailmentProb !== null && (
                              <span>
                                {" "}
                                · Match Confidence ={" "}
                                {(entailmentProb * 100).toFixed(1)}%
                              </span>
                            )}
                          </span>
                          <button
                            type="button"
                            className="btn-ghost"
                            style={{
                              padding: "0.15rem 0.5rem",
                              fontSize: "0.75rem",
                            }}
                          >
                            {isSlotExpanded
                              ? "▲ Hide Comparison"
                              : "▼ Inspect Claim Comparison"}
                          </button>
                        </div>

                        {isSlotExpanded && (
                          <table className="slot-diff-table">
                            <thead>
                              <tr>
                                <th>Attribute</th>
                                <th>Approved Fact</th>
                                <th>Campaign Draft</th>
                                <th>Status</th>
                              </tr>
                            </thead>
                            <tbody>
                              {slots.map((s, idx) => (
                                <tr key={idx}>
                                  <td>
                                    <strong>{s.slot ?? s.slot_name}</strong>
                                  </td>
                                  <td>{s.canon_value ?? "—"}</td>
                                  <td>{s.draft_value ?? "—"}</td>
                                  <td className={`slot-${s.status}`}>
                                    {s.status.toUpperCase()}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
                    )}

                    {f.payload?.suggestion && (
                      <div className="finding-suggestion">
                        <strong>Suggested Fix:</strong>{" "}
                        {f.payload.suggestion.label ??
                          f.payload.suggestion.explanation}
                        {f.payload.suggestion.replacements.map((r, i) => (
                          <code key={i} className="replacement-chip">
                            → &ldquo;{r.replacement}&rdquo;
                          </code>
                        ))}
                      </div>
                    )}

                    {rewritePreviews[f.row_id] && (
                      <div
                        className="gov-clean-box"
                        style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}
                      >
                        <div>
                          <strong>Suggested Rewrite:</strong>{" "}
                          {rewritePreviews[f.row_id].reverified
                            ? "✓ Verified against playbook rules"
                            : "Ready for review"}{" "}
                          · Edit Distance:{" "}
                          {(
                            rewritePreviews[f.row_id].edit_distance_ratio * 100
                          ).toFixed(1)}
                          % · PII Masked:{" "}
                          {rewritePreviews[f.row_id].pii_masked_count} ·
                          Provider: {rewritePreviews[f.row_id].used_provider}
                        </div>
                        {rewritePreviews[f.row_id].provider_notice && (
                          <div
                            style={{
                              marginTop: "0.25rem",
                              padding: "0.25rem 0.45rem",
                              borderRadius: "4px",
                              backgroundColor:
                                rewritePreviews[f.row_id].api_key_configured === false
                                  ? "rgba(217, 119, 6, 0.14)"
                                  : "rgba(16, 185, 129, 0.12)",
                              color:
                                rewritePreviews[f.row_id].api_key_configured === false
                                  ? "#b45309"
                                  : "#065f46",
                              fontSize: "0.75rem",
                            }}
                          >
                            {rewritePreviews[f.row_id].provider_notice}
                          </div>
                        )}
                        <div style={{ marginTop: "0.25rem" }}>
                          <code>
                            → &ldquo;{rewritePreviews[f.row_id].rewritten_text}
                            &rdquo;
                          </code>
                        </div>
                      </div>
                    )}

                    {f.resolution !== "open" && f.resolution_reason && (
                      <div className="finding-override-reason">
                        <strong>Recorded Review Note:</strong>{" "}
                        {f.resolution_reason}
                      </div>
                    )}

                    {/* Action Buttons on Open Findings */}
                    {f.resolution === "open" && (
                      <div
                        className="finding-actions"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {hasTextSuggestion ? (
                          <button
                            type="button"
                            disabled={acceptLockedByForcingFunction}
                            title={
                              acceptLockedByForcingFunction
                                ? "Inspect the Claim Comparison table above first to unlock this action."
                                : "Apply suggested replacement to document"
                            }
                            className="btn-resolve btn-accept"
                            onClick={() => handleResolve(f.row_id, "accepted")}
                          >
                            {acceptLockedByForcingFunction
                              ? "🔒 Inspect Claim Comparison First"
                              : "✓ Accept & Apply Fix"}
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={acceptLockedByForcingFunction}
                            className="btn-resolve btn-accept"
                            onClick={() => {
                              setOverrideTarget({
                                rowId: f.row_id,
                                mode: "accepted",
                              });
                              setOverrideReason("");
                            }}
                          >
                            {acceptLockedByForcingFunction
                              ? "🔒 Inspect Comparison First"
                              : "✓ Mark Remediated"}
                          </button>
                        )}

                        {typeof f.payload?.locator?.start === "number" &&
                          typeof f.payload?.locator?.end === "number" && (
                            <button
                              type="button"
                              className="btn-resolve"
                              disabled={rewritingRowId === f.row_id}
                              onClick={() => handleTier3Rewrite(f.row_id)}
                            >
                              {rewritingRowId === f.row_id
                                ? "Generating..."
                                : "✨ Suggest Rewrite"}
                            </button>
                          )}

                        {!isBlocker && (
                          <button
                            type="button"
                            className="btn-resolve btn-override"
                            onClick={() => {
                              setOverrideTarget({
                                rowId: f.row_id,
                                mode: "overridden",
                              });
                              setOverrideReason("");
                            }}
                          >
                            Override Warning
                          </button>
                        )}

                        {!isBlocker &&
                          (role === "reviewer" || role === "admin") && (
                            <button
                              type="button"
                              className="btn-resolve btn-dismiss"
                              onClick={() => {
                                setOverrideTarget({
                                  rowId: f.row_id,
                                  mode: "dismissed",
                                });
                                setOverrideReason("");
                              }}
                            >
                              Dismiss Warning
                            </button>
                          )}

                        <button
                          type="button"
                          className="btn-resolve"
                          onClick={() =>
                            setCommentTargetRowId(
                              commentTargetRowId === f.row_id ? null : f.row_id,
                            )
                          }
                        >
                          💬 Comment (
                          {
                            comments.filter((c) => c.finding_id === f.row_id)
                              .length
                          }
                          )
                        </button>
                      </div>
                    )}

                    {/* Structured Popover for Override / Dismiss / Remediation Note */}
                    {overrideTarget && overrideTarget.rowId === f.row_id && (
                      <div
                        className="override-popover"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <label htmlFor={`override-reason-${f.row_id}`}>
                          <strong>
                            {overrideTarget.mode === "accepted"
                              ? "Record Remediation Note (min 5 chars):"
                              : `Justification for ${
                                  overrideTarget.mode === "overridden"
                                    ? "Warning Override"
                                    : "Warning Dismissal"
                                } (min 5 chars):`}
                          </strong>
                        </label>
                        <textarea
                          id={`override-reason-${f.row_id}`}
                          rows={2}
                          value={overrideReason}
                          onChange={(e) => setOverrideReason(e.target.value)}
                          placeholder={
                            overrideTarget.mode === "accepted"
                              ? "Explain how this visual/layout issue was resolved..."
                              : "Provide context for overriding or dismissing this warning..."
                          }
                        />
                        <div className="override-popover-actions">
                          <button
                            type="button"
                            className="btn-ghost"
                            onClick={() => setOverrideTarget(null)}
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            className="btn-primary"
                            disabled={overrideReason.trim().length < 5}
                            onClick={() =>
                              handleResolve(
                                f.row_id,
                                overrideTarget.mode,
                                overrideReason.trim(),
                              )
                            }
                          >
                            Confirm &amp; Save
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Inline Comments Thread on this Finding Card */}
                    {(comments.some((c) => c.finding_id === f.row_id) ||
                      commentTargetRowId === f.row_id) && (
                      <div
                        className="finding-comments-box"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {comments
                          .filter((c) => c.finding_id === f.row_id)
                          .map((c) => (
                            <div key={c.id} className="comment-item">
                              <span className="comment-author">
                                @{c.author_name} ({c.role}):
                              </span>{" "}
                              <span className="comment-body">{c.body}</span>
                            </div>
                          ))}
                        {commentTargetRowId === f.row_id && (
                          <div className="inline-comment-composer">
                            <input
                              type="text"
                              value={commentBody}
                              onChange={(e) => setCommentBody(e.target.value)}
                              placeholder="Add comment on this finding..."
                              className="comment-input"
                            />
                            <button
                              type="button"
                              className="btn-primary"
                              disabled={postingComment || !commentBody.trim()}
                              onClick={() =>
                                handlePostComment(f.row_id, commentBody)
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
          )}
        </aside>
      </div>

      {/* Revision History Modal */}
      {showVersionsModal && (
        <div
          className="modal-overlay"
          onClick={() => setShowVersionsModal(false)}
        >
          <div
            className="modal card modal-wide"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="gov-panel-header">
              <h3>Submission Revision History</h3>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setShowVersionsModal(false)}
              >
                ✕ Close
              </button>
            </div>
            <p className="gov-panel-desc">
              Every accepted fix or copy edit records an immutable revision with
              its own content hash.
            </p>
            <div className="audit-timeline">
              {versions.map((v) => (
                <div key={v.version_number} className="audit-event card">
                  <div className="audit-header">
                    <span className="audit-action">
                      Revision v{v.version_number}
                    </span>
                    <span className="audit-transition">{v.change_note}</span>
                    <span className="audit-time">
                      {new Date(v.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="audit-hashes">
                    <span>
                      Content SHA-256: <code>{v.content_hash}</code>
                    </span>
                  </div>
                  <pre className="version-raw-preview">{v.raw_content}</pre>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Audit Trail Modal */}
      {showAuditModal && (
        <div
          className="modal-overlay"
          onClick={() => setShowAuditModal(false)}
        >
          <div
            className="modal card modal-wide"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="gov-panel-header">
              <h3>Approval &amp; Sign-Off Audit Trail</h3>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setShowAuditModal(false)}
              >
                ✕ Close
              </button>
            </div>
            {audit.length === 0 ? (
              <p className="gov-panel-desc">
                No stage transitions recorded yet. Submit, approve, or release
                this campaign to record signed audit events.
              </p>
            ) : (
              <>
                {audit[0].tree_head && (
                  <div
                    className="gov-clean-box"
                    style={{ marginBottom: "1rem" }}
                  >
                    <div>
                      <strong>Cryptographic Audit Summary:</strong>
                    </div>
                    <div
                      className="audit-hashes"
                      style={{ marginTop: "0.35rem" }}
                    >
                      <span>
                        Merkle Root:{" "}
                        <code>
                          {(
                            audit[0].tree_head.root_hash ??
                            audit[0].tree_head.root_hash_hex ??
                            ""
                          ).slice(0, 24)}
                          …
                        </code>
                      </span>
                      <span>
                        Signature:{" "}
                        <code>
                          {(
                            audit[0].tree_head.signature_hex ??
                            audit[0].tree_head.signature ??
                            ""
                          ).slice(0, 24)}
                          …
                        </code>
                      </span>
                      <span>
                        Total Events:{" "}
                        <strong>{audit[0].tree_head.tree_size}</strong>
                      </span>
                    </div>
                  </div>
                )}
                <div className="audit-timeline">
                  {audit.map((evt) => (
                    <div key={evt.id} className="audit-event card">
                      <div className="audit-header">
                        <span className="audit-action">{evt.action}</span>
                        <span className="audit-transition">
                          {evt.from_status} → {evt.to_status}
                        </span>
                        <span className="audit-time">
                          {new Date(evt.created_at).toLocaleString()}
                        </span>
                      </div>
                      {evt.comment && (
                        <p className="audit-comment">{evt.comment}</p>
                      )}
                      <div className="audit-hashes">
                        <span>
                          Prev Hash: <code>{evt.prev_hash.slice(0, 16)}…</code>
                        </span>
                        <span>
                          Event Hash:{" "}
                          <code>{evt.event_hash.slice(0, 16)}…</code>
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
