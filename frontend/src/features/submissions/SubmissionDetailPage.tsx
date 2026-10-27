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
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  FindingHighlightsExtension,
  findingHighlightsPluginKey,
  codepointIndexToUtf16Offset,
} from "./FindingHighlightsExtension";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Download,
  Edit3,
  Eye,
  FileText,
  History,
  Image as ImageIcon,
  Layers,
  Lock,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  Sliders,
  Wand2,
  X,
} from "lucide-react";

const ROLE_DISPLAY: Record<string, string> = {
  creator: "Stage 1 · Creator",
  reviewer: "Stage 2 · Brand Manager",
  admin: "Stage 3 · Legal Reviewer",
};

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
      label: "Approve Brand Review → Legal",
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
      label: "Execute Final Legal Sign-Off & Release",
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
    desc: "Fix Blockers and document context on Warning overrides.",
  },
  {
    num: 2,
    key: "stage2",
    title: "Brand Review",
    ownerRole: "reviewer",
    ownerLabel: "Brand Manager",
    statuses: ["in_review"],
    desc: "Inspect revision diffs, verify brand compliance & overrides.",
  },
  {
    num: 3,
    key: "stage3",
    title: "Legal Sign-Off",
    ownerRole: "admin",
    ownerLabel: "Legal Reviewer",
    statuses: ["approved"],
    desc: "Audit high-risk claims & disclosures; execute final release.",
  },
  {
    num: 4,
    key: "stage4",
    title: "Released & Sealed",
    ownerRole: "published",
    ownerLabel: "Released",
    statuses: ["published"],
    desc: "Cryptographically sealed with a Governance Certificate.",
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

function formatCheckLabel(checkId: string): string {
  const clean = checkId.replace(/^check\./, "").replace(/_/g, " ");
  return clean.replace(/\b\w/g, (c) => c.toUpperCase());
}

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
    .sort(
      (a, b) => a.start - b.start || b.finding.severity - a.finding.severity,
    );

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
  const { username, displayName, role, switchRole } = useAuth();
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

  // Left Canvas View Mode: Split (Both), Copy Only, Banner Only, or Discussion
  const [canvasMode, setCanvasMode] = useState<
    "split" | "copy" | "banner" | "discussion"
  >("split");

  // Direct Draft Editor state
  const [isEditingDraft, setIsEditingDraft] = useState<boolean>(false);
  const [draftEditValue, setDraftEditValue] = useState<string>("");
  const [draftChangeNote, setDraftChangeNote] = useState<string>(
    "Updated campaign copy to resolve compliance findings",
  );
  const [savingDraft, setSavingDraft] = useState<boolean>(false);

  // Conformal Risk Control (alpha)
  const [conformalAlpha, setConformalAlpha] = useState<number>(0.1);

  // Track which SlotDiff tables have been expanded by the user
  const [expandedSlotDiffs, setExpandedSlotDiffs] = useState<
    Record<number, boolean>
  >({});

  // Structured Override / Dismiss / Remediation popover state
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
      if (fnd.length > 0) {
        setSelectedFindingId((prev) =>
          prev !== null && fnd.some((item) => item.row_id === prev)
            ? prev
            : fnd[0].row_id,
        );
      }
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
    if (canvasMode === "banner" || canvasMode === "discussion") {
      setCanvasMode("copy");
    }
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

  function handleScan(overrideAlpha?: number) {
    const targetAlpha =
      typeof overrideAlpha === "number" ? overrideAlpha : conformalAlpha;
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
      targetAlpha,
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

  function stepFindingSelection(delta: number) {
    if (filteredFindings.length === 0) return;
    const currIdx = filteredFindings.findIndex(
      (f) => f.row_id === selectedFindingId,
    );
    const nextIdx =
      currIdx < 0
        ? 0
        : (currIdx + delta + filteredFindings.length) %
          filteredFindings.length;
    const target = filteredFindings[nextIdx];
    if (target) {
      handleSelectFindingFromSpan(target.row_id);
    }
  }

  const tiptapDocContent = useMemo(
    () => ({
      type: "doc",
      content:
        textBlocks.length > 0
          ? textBlocks.map((block) => ({
              type: "paragraph",
              content: block ? [{ type: "text", text: block }] : [],
            }))
          : [{ type: "paragraph" }],
    }),
    [textBlocks],
  );

  const tiptapEditor = useEditor({
    extensions: [
      StarterKit,
      FindingHighlightsExtension.configure({
        onSelectFinding: handleSelectFindingFromSpan,
      }),
    ],
    content: tiptapDocContent,
    editable: false,
  });

  useEffect(() => {
    if (!tiptapEditor || tiptapEditor.isDestroyed) return;
    const currentText = tiptapEditor.getText({ blockSeparator: "\n\n" });
    const nextText = textBlocks.join("\n\n");
    if (currentText !== nextText) {
      tiptapEditor.commands.setContent(tiptapDocContent, false);
    }
    const tr = tiptapEditor.state.tr.setMeta(findingHighlightsPluginKey, {
      findings,
      paragraphNodeIds,
      selectedRowId: selectedFindingId,
    });
    tiptapEditor.view.dispatch(tr);
  }, [
    tiptapEditor,
    tiptapDocContent,
    textBlocks,
    findings,
    paragraphNodeIds,
    selectedFindingId,
  ]);

  if (loading) {
    return (
      <div className="cg-studio-shell">
        <div className="cg-empty-box" style={{ margin: "3rem auto", maxWidth: 520 }}>
          Opening Multimodal Review Studio…
        </div>
      </div>
    );
  }

  if (!submission) {
    return (
      <div className="cg-studio-shell">
        <div className="cg-alert-banner" style={{ margin: "2rem auto", maxWidth: 680 }}>
          <span>Submission not found</span>
          <button
            type="button"
            className="cg-btn cg-btn-secondary cg-btn-sm"
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

  const generalComments = comments.filter((c) => c.finding_id === null);

  return (
    <div className="cg-studio-shell">
      {/* ── Row 1: Compact Studio Top Command Bar ── */}
      <header className="cg-studio-topbar">
        <div className="cg-studio-topbar-left">
          <button
            type="button"
            onClick={() => navigate("/dashboard")}
            className="cg-btn cg-btn-ghost cg-btn-sm"
            title="Return to Campaign Triage Queue"
          >
            <ArrowLeft size={14} />
            <span>Queue</span>
          </button>

          <div className="cg-studio-title-block">
            <div className="cg-studio-title-row">
              <h1>{submission.title}</h1>
              <span className={`status-badge status-${submission.status}`}>
                {submission.status.replace("_", " ")}
              </span>
            </div>
            <div className="cg-studio-meta-row">
              <span>
                Playbook: <code>{submission.canon_id}</code> (
                <code>{submission.canon_hash.slice(0, 8)}…</code>)
              </span>
              <span>·</span>
              <span>
                AST SHA-256: <code>{submission.content_hash.slice(0, 10)}…</code>
              </span>
            </div>
          </div>
        </div>

        <div className="cg-studio-topbar-right">
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
              <option value="creator">{ROLE_DISPLAY.creator}</option>
              <option value="reviewer">{ROLE_DISPLAY.reviewer}</option>
              <option value="admin">{ROLE_DISPLAY.admin}</option>
            </select>
          </label>

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
            className="cg-btn cg-btn-secondary cg-btn-sm"
            onClick={() => setShowVersionsModal(true)}
            title="Inspect immutable content revision history"
          >
            <History size={13} />
            <span>Revisions ({versions.length || 1})</span>
          </button>

          <button
            type="button"
            className="cg-btn cg-btn-secondary cg-btn-sm"
            onClick={() => setShowAuditModal(true)}
            title="Inspect hash-chained RFC 9162 Merkle audit log"
          >
            <Clock size={13} />
            <span>Audit Log ({audit.length})</span>
          </button>

          <button
            type="button"
            className="cg-btn cg-btn-secondary cg-btn-sm"
            onClick={handleExportCertificate}
            disabled={exportingCert}
            title="Download Ed25519 + RFC 9162 Governance Certificate JSON"
          >
            <Download size={13} />
            <span>{exportingCert ? "Exporting…" : "Certificate"}</span>
          </button>

          <button
            type="button"
            className="cg-btn cg-btn-primary cg-btn-sm"
            onClick={() => handleScan()}
            disabled={scanning}
          >
            <RefreshCw size={13} className={scanning ? "cg-spin" : ""} />
            <span>{scanning ? "Scanning…" : "Run Check"}</span>
          </button>
        </div>
      </header>

      {/* ── Row 2: Slim Horizontal 4-Stage Gate & Action Bar ── */}
      <section
        className="cg-studio-gatebar"
        aria-label="4-Stage Governance Progress & Gate Actions"
      >
        {/* Left: Compact 4-Step Progress Track */}
        <div className="cg-gate-steps">
          {WORKFLOW_STAGES.map((st) => {
            const isCurrent = st.num === activeStageObj.num;
            const isCompleted = st.num < activeStageObj.num;
            return (
              <div
                key={st.key}
                className={`cg-gate-step ${isCurrent ? "current" : ""} ${
                  isCompleted ? "completed" : ""
                }`}
                title={`${st.title} (${st.ownerLabel}): ${st.desc}`}
              >
                <span className="cg-gate-step-num">
                  {isCompleted ? "✓" : `0${st.num}`}
                </span>
                <div className="cg-gate-step-text">
                  <span className="cg-gate-step-title">{st.title}</span>
                  <span className="cg-gate-step-owner">{st.ownerLabel}</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Center: Live Fault Counters */}
        <div className="cg-gate-counters">
          <span
            className={`cg-counter-pill ${
              blockerCount > 0 ? "pill-blocker" : "pill-clean"
            }`}
          >
            {blockerCount} Blocker{blockerCount === 1 ? "" : "s"}
          </span>
          <span className="cg-counter-pill pill-warning">
            {warningCount} Warning{warningCount === 1 ? "" : "s"}
          </span>
          <span className="cg-counter-pill pill-resolved">
            {resolvedCount} Resolved
          </span>
          {blockerCount > 0 && (
            <span className="cg-gate-lock-hint">
              <Lock size={12} /> Resolve Blockers to unlock stage sign-off
            </span>
          )}
        </div>

        {/* Right: Primary Stage Transition CTA or Role Switch Helper */}
        <div className="cg-gate-actions">
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
                  className={`cg-btn cg-btn-sm ${
                    a.action === "approve" || a.action === "publish"
                      ? "cg-btn-emerald"
                      : a.action === "submit"
                        ? "cg-btn-primary"
                        : "cg-btn-secondary"
                  }`}
                  onClick={() => setWfAction(a.action)}
                >
                  <span>{a.label}</span>
                </button>
              );
            })
          ) : submission.status === "published" ? (
            <span className="cg-published-seal">
              <CheckCircle2 size={14} /> Released &amp; Merkle Sealed
            </span>
          ) : (
            <div className="cg-handoff-inline">
              <span>
                Stage {activeStageObj.num} owned by{" "}
                <strong>{activeStageObj.ownerLabel}</strong>
              </span>
              {activeStageObj.ownerRole !== "published" && (
                <button
                  type="button"
                  className="cg-btn cg-btn-primary cg-btn-sm"
                  onClick={() => {
                    void switchRole(activeStageObj.ownerRole);
                  }}
                >
                  <span>Switch to {activeStageObj.ownerLabel} Role →</span>
                </button>
              )}
            </div>
          )}
        </div>
      </section>

      {error && (
        <div className="cg-alert-banner" role="alert" style={{ margin: "0.75rem 1.5rem 0" }}>
          <span>{error}</span>
          <button
            type="button"
            className="cg-btn cg-btn-ghost cg-btn-sm"
            onClick={() => setError(null)}
          >
            <X size={14} /> Dismiss
          </button>
        </div>
      )}

      {/* ── Main 2-Column Split-Screen Review IDE ── */}
      <div className="cg-studio-workspace">
        {/* LEFT COLUMN: Multi-Modal Asset Canvas (Copy + Banner + Discussion) */}
        <div className="cg-studio-canvas-col">
          {/* Canvas Mode Switcher Bar */}
          <div className="cg-canvas-toolbar">
            <div className="cg-canvas-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={canvasMode === "split"}
                className={`cg-canvas-tab ${
                  canvasMode === "split" ? "active" : ""
                }`}
                onClick={() => setCanvasMode("split")}
              >
                <Layers size={13} />
                <span>All Assets</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={canvasMode === "copy"}
                className={`cg-canvas-tab ${
                  canvasMode === "copy" ? "active" : ""
                }`}
                onClick={() => setCanvasMode("copy")}
              >
                <FileText size={13} />
                <span>Copy &amp; Claims ({textBlocks.length})</span>
              </button>
              {imageNodes.length > 0 && (
                <button
                  type="button"
                  role="tab"
                  aria-selected={canvasMode === "banner"}
                  className={`cg-canvas-tab ${
                    canvasMode === "banner" ? "active" : ""
                  }`}
                  onClick={() => setCanvasMode("banner")}
                >
                  <ImageIcon size={13} />
                  <span>
                    Visual Banners ({imageNodes.length} ·{" "}
                    {bannerOverlays.length} pins)
                  </span>
                </button>
              )}
              <button
                type="button"
                role="tab"
                aria-selected={canvasMode === "discussion"}
                className={`cg-canvas-tab ${
                  canvasMode === "discussion" ? "active" : ""
                }`}
                onClick={() => setCanvasMode("discussion")}
              >
                <MessageSquare size={13} />
                <span>Review Notes ({generalComments.length})</span>
              </button>
            </div>

            {canCreatorEditDraft && canvasMode !== "discussion" && (
              <button
                type="button"
                className={`cg-btn cg-btn-sm ${
                  isEditingDraft ? "cg-btn-ghost" : "cg-btn-secondary"
                }`}
                onClick={() => {
                  if (isEditingDraft) {
                    setIsEditingDraft(false);
                  } else {
                    handleStartEditDraft();
                  }
                }}
              >
                <Edit3 size={13} />
                <span>
                  {isEditingDraft ? "Cancel Editing" : "Edit Copy & Re-Scan"}
                </span>
              </button>
            )}
          </div>

          {/* 1. Promotional Banner Stage (Shown in Split or Banner Mode) */}
          {activeBannerAsset &&
            (canvasMode === "split" || canvasMode === "banner") && (
              <section className="cg-canvas-card cg-animate-swap">
                <div className="cg-canvas-card-header">
                  <div>
                    <span className="cg-mono-label">
                      VISUAL ASSET INSPECTOR · {activeBannerAsset.width}×
                      {activeBannerAsset.height}px
                    </span>
                    <h2>
                      Promotional Banner Stage (CIEDE2000 ΔE₀₀ · WCAG 2.1 · ORB
                      0.5H)
                    </h2>
                  </div>

                  {imageNodes.length > 1 && (
                    <div className="cg-banner-Asset-tabs">
                      {imageNodes.map((img, idx) => (
                        <button
                          key={img.node_id}
                          type="button"
                          className={`cg-filter-pill ${
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
                              onClick={() =>
                                handleSelectFindingFromSpan(ov.rowId)
                              }
                            >
                              <rect
                                x={ov.x}
                                y={ov.y}
                                width={Math.max(ov.w, 12)}
                                height={Math.max(ov.h, 12)}
                                fill={
                                  isSelected
                                    ? "rgba(239, 68, 68, 0.24)"
                                    : "rgba(239, 68, 68, 0.08)"
                                }
                                stroke={strokeColor}
                                strokeWidth={isSelected ? 4 : 2.5}
                                rx={4}
                              />
                              <text
                                x={ov.x + 6}
                                y={Math.max(16, ov.y - 6)}
                                fill="#ffffff"
                                stroke="#09090b"
                                strokeWidth={0.7}
                                fontSize={Math.max(
                                  11,
                                  Math.round(activeBannerAsset.height * 0.03),
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

          {/* 2. Campaign Copy & ProseMirror Highlights (Shown in Split or Copy Mode) */}
          {(canvasMode === "split" || canvasMode === "copy") && (
            <section className="cg-canvas-card cg-animate-swap">
              <div className="cg-canvas-card-header">
                <div>
                  <span className="cg-mono-label">
                    DOCUMENT AST &amp; PROSEMIRROR INLINE DECORATIONS
                  </span>
                  <h2>Campaign Copy, KFS Tables &amp; Highlighted Claims</h2>
                </div>
                <span className="cg-canvas-hint">
                  Click any highlighted span to focus its fault card →
                </span>
              </div>

              {isEditingDraft ? (
                <div className="draft-inline-editor cg-animate-swap">
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
                      className="cg-btn cg-btn-primary"
                      disabled={savingDraft}
                      onClick={handleSaveEditedDraft}
                    >
                      {savingDraft
                        ? "Saving & Re-Scanning…"
                        : "Save Revision & Re-Scan"}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="content-preview tiptap-wrapper">
                  {textBlocks.length > 0 ? (
                    tiptapEditor ? (
                      <EditorContent editor={tiptapEditor} />
                    ) : (
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
                    )
                  ) : (
                    <p className="text-muted">
                      No text content blocks in this bundle.
                    </p>
                  )}
                </div>
              )}
            </section>
          )}

          {/* 3. Collaborative Review Discussion (Shown in Split or Discussion Mode) */}
          {(canvasMode === "split" || canvasMode === "discussion") && (
            <section className="cg-canvas-card cg-animate-swap">
              <div className="cg-canvas-card-header">
                <div>
                  <span className="cg-mono-label">
                    COLLABORATIVE REVIEW NOTES
                  </span>
                  <h2>
                    Campaign Discussion Thread ({generalComments.length})
                  </h2>
                </div>
                <span className="cg-brand-version">
                  Creator · Brand Manager · Legal
                </span>
              </div>

              <div className="general-comments-list">
                {generalComments.length === 0 ? (
                  <p className="cg-empty-inline-note">
                    No general review notes yet. Leave a handoff note below for
                    the Brand Manager or Legal Reviewer.
                  </p>
                ) : (
                  generalComments.map((c) => (
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
                  placeholder="Write a review handoff note on this campaign…"
                  className="comment-input"
                />
                <button
                  type="button"
                  className="cg-btn cg-btn-secondary cg-btn-sm"
                  disabled={postingComment || !generalCommentBody.trim()}
                  onClick={() => handlePostComment(null, generalCommentBody)}
                >
                  Post Note
                </button>
              </div>
            </section>
          )}
        </div>

        {/* RIGHT COLUMN: Sleek Progressive-Disclosure Fault Inspector */}
        <aside className="cg-studio-inspector-col">
          {/* Sticky Fault Inspector Header */}
          <div className="cg-inspector-toolbar">
            <div className="cg-inspector-toolbar-top">
              <div className="cg-inspector-filter-group">
                <button
                  type="button"
                  className={`cg-filter-pill ${
                    filter === "all" ? "active" : ""
                  }`}
                  onClick={() => setFilter("all")}
                >
                  All ({findings.length})
                </button>
                <button
                  type="button"
                  className={`cg-filter-pill pill-blocker-tab ${
                    filter === "blockers" ? "active" : ""
                  }`}
                  onClick={() => setFilter("blockers")}
                >
                  Blockers ({blockerCount})
                </button>
                <button
                  type="button"
                  className={`cg-filter-pill pill-warning-tab ${
                    filter === "warnings" ? "active" : ""
                  }`}
                  onClick={() => setFilter("warnings")}
                >
                  Warnings ({warningCount})
                </button>
                <button
                  type="button"
                  className={`cg-filter-pill ${
                    filter === "claims_only" ? "active" : ""
                  }`}
                  onClick={() => setFilter("claims_only")}
                  title="Filter to factual claims, disclosures, blockers, and overrides"
                >
                  Claims &amp; Overrides
                </button>
              </div>

              {/* Prev / Next Fault Stepper */}
              {filteredFindings.length > 1 && (
                <div className="cg-fault-stepper-btns">
                  <button
                    type="button"
                    className="cg-icon-btn"
                    onClick={() => stepFindingSelection(-1)}
                    title="Previous finding"
                  >
                    <ChevronUp size={14} />
                  </button>
                  <button
                    type="button"
                    className="cg-icon-btn"
                    onClick={() => stepFindingSelection(1)}
                    title="Next finding"
                  >
                    <ChevronDown size={14} />
                  </button>
                </div>
              )}
            </div>

            <div className="cg-inspector-toolbar-bottom">
              <div
                className="cg-strictness-control"
                title="Distribution-free Conformal Risk Control (Angelopoulos et al.)"
              >
                <Sliders size={12} />
                <label htmlFor="alpha-select">Conformal Strictness:</label>
                <select
                  id="alpha-select"
                  value={conformalAlpha}
                  onChange={(e) => {
                    const nextVal = Number(e.target.value);
                    setConformalAlpha(nextVal);
                    handleScan(nextVal);
                  }}
                >
                  <option value={0.04}>Strict (α = 0.04 · Legal/BFSI)</option>
                  <option value={0.1}>Balanced (α = 0.10 · Standard)</option>
                  <option value={0.2}>Permissive (α = 0.20 · Early Draft)</option>
                </select>
              </div>

              <span
                className="cg-dpdp-micro-pill"
                title="Raw documents and banners never leave this container; PII is masked locally via PiiVault before any optional Tier 3 rewrite."
              >
                <ShieldCheck size={12} /> DPDP Local Vault
              </span>
            </div>
          </div>

          {/* Fault Cards List */}
          {scanning ? (
            <div className="cg-empty-box">
              Auditing campaign against <code>{submission.canon_id}</code>…
            </div>
          ) : filteredFindings.length === 0 ? (
            <div className="cg-empty-box cg-empty-clean">
              <CheckCircle2 size={24} className="cg-text-emerald" />
              <p>
                {findings.length === 0
                  ? "Zero compliance issues found! This campaign bundle passes all active playbook rules."
                  : "No findings match the active filter."}
              </p>
            </div>
          ) : (
            <div className="cg-fault-list">
              {filteredFindings.map((f, idx) => {
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
                const findingComments = comments.filter(
                  (c) => c.finding_id === f.row_id,
                );

                const shortTierBadge = trace
                  ? trace.ai_used
                    ? `Tier 2 NLI · ${trace.model_name ?? "Local ONNX"}`
                    : String(trace.tier).toLowerCase() === "smt"
                      ? "Tier 1.5 · Z3 SMT"
                      : "Tier 1 · Deterministic"
                  : "Tier 1 · Deterministic";

                return (
                  <article
                    key={f.row_id}
                    id={`finding-card-${f.row_id}`}
                    onClick={() => setSelectedFindingId(f.row_id)}
                    className={`cg-fault-card finding-card ${
                      isBlocker ? "fault-blocker" : "fault-warning"
                    } ${f.resolution !== "open" ? "fault-resolved" : ""} ${
                      isSelected ? "selected finding-selected" : ""
                    }`}
                  >
                    {/* Card Top Metadata Bar */}
                    <div className="cg-fault-card-top">
                      <span className="cg-fault-index">#{idx + 1}</span>
                      <span
                        className={`cg-sev-badge ${
                          f.resolution !== "open"
                            ? "sev-pass"
                            : isBlocker
                              ? "sev-blocker"
                              : "sev-warning"
                        }`}
                      >
                        {f.resolution !== "open"
                          ? f.resolution.toUpperCase()
                          : `${isBlocker ? "BLOCKER" : "WARNING"} · ${f.severity}`}
                      </span>

                      <span className="cg-fault-category">
                        {formatCheckLabel(f.check_id)}
                      </span>

                      <span
                        className="cg-fault-tier-pill"
                        title={
                          trace
                            ? `Tier: ${trace.tier} | Model: ${trace.model_sha ?? trace.model_name ?? "Deterministic Math"}${trace.latency_ms != null ? ` | ${trace.latency_ms.toFixed(1)}ms` : ""}`
                            : "Deterministic local check"
                        }
                      >
                        {shortTierBadge}
                      </span>
                    </div>

                    {/* Primary Finding Message */}
                    <p className="cg-fault-message">{f.message}</p>

                    {/* Grounding Citation */}
                    {f.payload?.rule_ref?.source_text && (
                      <div className="cg-fault-rule-box">
                        <span className="cg-mono-label">
                          PLAYBOOK RULE · {f.payload.rule_ref.rule_id}
                        </span>
                        <p>{f.payload.rule_ref.source_text}</p>
                      </div>
                    )}

                    {/* Progressive Disclosure 1: QASem 4-Column SlotDiff Table */}
                    {isSlotDiff && slots.length > 0 && (
                      <div
                        className="cg-fault-slotdiff-wrap"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          type="button"
                          className="cg-slotdiff-toggle-bar"
                          onClick={() =>
                            setExpandedSlotDiffs((prev) => ({
                              ...prev,
                              [f.row_id]: !prev[f.row_id],
                            }))
                          }
                        >
                          <span>
                            <Eye size={13} />
                            <strong>
                              QASem Claim vs. Approved Fact SlotDiff
                            </strong>
                            {entailmentProb !== null && (
                              <code style={{ marginLeft: "0.4rem" }}>
                                NLI={(entailmentProb * 100).toFixed(1)}%
                              </code>
                            )}
                          </span>
                          <span className="cg-slotdiff-toggle-action">
                            {isSlotExpanded ? "Hide Matrix ▲" : "Inspect Matrix ▼"}
                          </span>
                        </button>

                        {isSlotExpanded && (
                          <div className="cg-slotdiff-table-container cg-animate-swap">
                            <table className="cg-slotdiff-table">
                              <thead>
                                <tr>
                                  <th>Slot</th>
                                  <th>Approved Canon</th>
                                  <th>Campaign Draft</th>
                                  <th>Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {slots.map((s, sIdx) => (
                                  <tr key={sIdx}>
                                    <td>
                                      <code>{s.slot ?? s.slot_name}</code>
                                    </td>
                                    <td>{s.canon_value ?? "—"}</td>
                                    <td>{s.draft_value ?? "—"}</td>
                                    <td>
                                      <span
                                        className={`cg-slot-badge slot-${s.status}`}
                                      >
                                        {s.status.toUpperCase()}
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Progressive Disclosure 2: Suggested Text Replacement */}
                    {f.payload?.suggestion && (
                      <div className="cg-fault-suggestion-box">
                        <div className="cg-fault-suggestion-header">
                          <span className="cg-mono-label">
                            RECOMMENDED REMEDIATION
                          </span>
                        </div>
                        <p className="cg-fault-suggestion-text">
                          {f.payload.suggestion.label ??
                            f.payload.suggestion.explanation}
                        </p>
                        {f.payload.suggestion.replacements.map((r, i) => (
                          <div key={i} className="cg-replacement-diff">
                            <span className="cg-diff-plus">+</span>
                            <code>{r.replacement}</code>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Progressive Disclosure 3: 3-Candidate DesignAlternativeProvider Swatches */}
                    {Array.isArray(evidence.design_alternatives) &&
                      evidence.design_alternatives.length > 0 && (
                        <div
                          className="cg-fault-swatches-box"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="cg-evidence-header">
                            <span>
                              3-Candidate WCAG &amp; Brand Palette Alternatives
                            </span>
                            <code>DesignAlternativeProvider</code>
                          </div>
                          <div className="cg-swatch-grid">
                            {evidence.design_alternatives.map(
                              (alt: any, aIdx: number) => (
                                <div
                                  key={alt.candidate_id ?? aIdx}
                                  className="cg-swatch-card"
                                >
                                  <div className="cg-swatch-top">
                                    <span
                                      className="cg-swatch-chip"
                                      style={{
                                        backgroundColor:
                                          alt.foreground_hex ?? "#000000",
                                      }}
                                    />
                                    <code>{alt.foreground_hex}</code>
                                    <span className="cg-swatch-pass">
                                      {alt.contrast_ratio}:1
                                    </span>
                                  </div>
                                  <div className="cg-swatch-label">
                                    {alt.label ?? `Option ${aIdx + 1}`}
                                  </div>
                                  {typeof alt.delta_e_from_brand ===
                                    "number" && (
                                    <div className="cg-swatch-meta">
                                      <span>
                                        ΔE₀₀ = {alt.delta_e_from_brand}
                                      </span>
                                    </div>
                                  )}
                                </div>
                              ),
                            )}
                          </div>
                        </div>
                      )}

                    {/* Progressive Disclosure 4: Tier 3 Surgical Rewrite Result */}
                    {rewritePreviews[f.row_id] && (
                      <div className="cg-fault-rewrite-preview cg-animate-swap">
                        <div className="cg-evidence-header">
                          <span>
                            ✓ Surgical Rewrite Verified (Edit Ratio:{" "}
                            {(
                              rewritePreviews[f.row_id].edit_distance_ratio *
                              100
                            ).toFixed(1)}
                            % · PII Masked:{" "}
                            {rewritePreviews[f.row_id].pii_masked_count})
                          </span>
                          <code>{rewritePreviews[f.row_id].used_provider}</code>
                        </div>
                        {rewritePreviews[f.row_id].provider_notice && (
                          <div className="cg-rewrite-notice">
                            {rewritePreviews[f.row_id].provider_notice}
                          </div>
                        )}
                        <div className="cg-replacement-diff">
                          <span className="cg-diff-plus">+</span>
                          <code>
                            {rewritePreviews[f.row_id].rewritten_text}
                          </code>
                        </div>
                      </div>
                    )}

                    {/* Recorded Resolution Rationale */}
                    {f.resolution !== "open" && f.resolution_reason && (
                      <div className="cg-recorded-note">
                        <strong>Review Note:</strong> {f.resolution_reason}
                      </div>
                    )}

                    {/* Action Bar on Open Findings */}
                    {f.resolution === "open" && (
                      <div
                        className="cg-fault-actions-bar"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {hasTextSuggestion ? (
                          <button
                            type="button"
                            disabled={acceptLockedByForcingFunction}
                            title={
                              acceptLockedByForcingFunction
                                ? "Inspect the SlotDiff matrix above first to unlock."
                                : "Apply suggested replacement to document"
                            }
                            className="cg-btn cg-btn-emerald cg-btn-sm"
                            onClick={() => handleResolve(f.row_id, "accepted")}
                          >
                            <Check size={13} />
                            <span>
                              {acceptLockedByForcingFunction
                                ? "Inspect SlotDiff First"
                                : "Accept & Apply Fix"}
                            </span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={acceptLockedByForcingFunction}
                            className="cg-btn cg-btn-emerald cg-btn-sm"
                            onClick={() => {
                              setOverrideTarget({
                                rowId: f.row_id,
                                mode: "accepted",
                              });
                              setOverrideReason("");
                            }}
                          >
                            <Check size={13} />
                            <span>
                              {acceptLockedByForcingFunction
                                ? "Inspect SlotDiff First"
                                : "Mark Remediated"}
                            </span>
                          </button>
                        )}

                        {typeof f.payload?.locator?.start === "number" &&
                          typeof f.payload?.locator?.end === "number" && (
                            <button
                              type="button"
                              className="cg-btn cg-btn-secondary cg-btn-sm"
                              disabled={rewritingRowId === f.row_id}
                              onClick={() => handleTier3Rewrite(f.row_id)}
                            >
                              <Wand2 size={13} />
                              <span>
                                {rewritingRowId === f.row_id
                                  ? "Rewriting…"
                                  : "Surgical Rewrite"}
                              </span>
                            </button>
                          )}

                        {!isBlocker && (
                          <button
                            type="button"
                            className="cg-btn cg-btn-secondary cg-btn-sm"
                            onClick={() => {
                              setOverrideTarget({
                                rowId: f.row_id,
                                mode: "overridden",
                              });
                              setOverrideReason("");
                            }}
                          >
                            <span>Override</span>
                          </button>
                        )}

                        {!isBlocker &&
                          (role === "reviewer" || role === "admin") && (
                            <button
                              type="button"
                              className="cg-btn cg-btn-ghost cg-btn-sm"
                              onClick={() => {
                                setOverrideTarget({
                                  rowId: f.row_id,
                                  mode: "dismissed",
                                });
                                setOverrideReason("");
                              }}
                            >
                              <span>Dismiss</span>
                            </button>
                          )}

                        <button
                          type="button"
                          className="cg-btn cg-btn-ghost cg-btn-sm"
                          onClick={() =>
                            setCommentTargetRowId(
                              commentTargetRowId === f.row_id
                                ? null
                                : f.row_id,
                            )
                          }
                        >
                          <MessageSquare size={12} />
                          <span>{findingComments.length}</span>
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
                              ? "Explain how this visual/layout issue was resolved…"
                              : "Provide context for overriding or dismissing this warning…"
                          }
                        />
                        <div className="override-popover-actions">
                          <button
                            type="button"
                            className="cg-btn cg-btn-ghost cg-btn-sm"
                            onClick={() => setOverrideTarget(null)}
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            className="cg-btn cg-btn-primary cg-btn-sm"
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
                    {(findingComments.length > 0 ||
                      commentTargetRowId === f.row_id) && (
                      <div
                        className="finding-comments-box"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {findingComments.map((c) => (
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
                              placeholder="Add comment on this finding…"
                              className="comment-input"
                            />
                            <button
                              type="button"
                              className="cg-btn cg-btn-primary cg-btn-sm"
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
                  </article>
                );
              })}
            </div>
          )}
        </aside>
      </div>

      {/* Workflow Transition Confirmation Modal */}
      {wfAction && (
        <div className="modal-overlay" onClick={() => setWfAction(null)}>
          <div className="modal card" onClick={(e) => e.stopPropagation()}>
            <div className="cg-gov-card-header">
              <h3>
                Confirm Stage Transition:{" "}
                <span style={{ textTransform: "capitalize" }}>
                  {wfAction.replace("_", " ")}
                </span>
              </h3>
              <button
                type="button"
                className="cg-btn cg-btn-ghost cg-btn-sm"
                onClick={() => setWfAction(null)}
              >
                <X size={14} />
              </button>
            </div>
            <p
              style={{
                fontSize: "0.84rem",
                color: "var(--cg-text-secondary)",
                marginBottom: "0.85rem",
              }}
            >
              This transition will be sealed in the tamper-evident RFC 9162
              Merkle audit log under <strong>@{username}</strong> ({role}).
            </p>
            <div className="cg-field-group">
              <label htmlFor="wf-comment">Review Sign-Off Note (optional)</label>
              <textarea
                id="wf-comment"
                rows={3}
                value={wfComment}
                onChange={(e) => setWfComment(e.target.value)}
                placeholder="Add context for this stage decision…"
              />
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="cg-btn cg-btn-ghost"
                onClick={() => setWfAction(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="cg-btn cg-btn-primary"
                onClick={handleWorkflow}
              >
                Confirm Transition
              </button>
            </div>
          </div>
        </div>
      )}

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
            <div className="cg-gov-card-header">
              <div>
                <h3>Immutable Submission Revision History</h3>
                <p>
                  Every accepted fix or copy edit records an immutable revision
                  with its own SHA-256 content hash.
                </p>
              </div>
              <button
                type="button"
                className="cg-btn cg-btn-ghost cg-btn-sm"
                onClick={() => setShowVersionsModal(false)}
              >
                <X size={14} /> Close
              </button>
            </div>
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
            <div className="cg-gov-card-header">
              <div>
                <h3>RFC 9162 Merkle &amp; Ed25519 Audit Ledger</h3>
                <p>
                  Hash-chained state transitions with cryptographic inclusion
                  proofs.
                </p>
              </div>
              <button
                type="button"
                className="cg-btn cg-btn-ghost cg-btn-sm"
                onClick={() => setShowAuditModal(false)}
              >
                <X size={14} /> Close
              </button>
            </div>
            {audit.length === 0 ? (
              <p className="cg-empty-inline-note">
                No stage transitions recorded yet. Submit, approve, or release
                this campaign to record signed audit events.
              </p>
            ) : (
              <>
                {audit[0].tree_head && (
                  <div
                    className="cg-clean-note"
                    style={{ marginBottom: "1rem" }}
                  >
                    <div>
                      <strong>Cryptographic Tree Head Summary:</strong>
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
                        Ed25519 Sig:{" "}
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
                        Tree Size:{" "}
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
