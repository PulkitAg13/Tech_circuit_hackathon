import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  getSubmission,
  getFindings,
  scanSubmission,
  workflowAction,
  resolveFinding,
  getAuditTrail,
  type Submission,
  type FindingResponse,
} from "../../api/client";
import { useAuth } from "../auth/AuthContext";

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

export function SubmissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { role } = useAuth();
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [findings, setFindings] = useState<FindingResponse[]>([]);
  const [scanning, setScanning] = useState(false);
  const [scanCount, setScanCount] = useState(0);
  const [audit, setAudit] = useState<any[]>([]);
  const [showAudit, setShowAudit] = useState(false);
  const [error, setError] = useState("");
  const [actionComment, setActionComment] = useState("");

  const subId = Number(id);

  useEffect(() => {
    loadSubmission();
  }, [id]);

  async function loadSubmission() {
    try {
      const [sub, fds] = await Promise.all([
        getSubmission(subId),
        getFindings(subId),
      ]);
      setSubmission(sub);
      setFindings(fds);
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleScan() {
    setScanning(true);
    setFindings([]);
    setScanCount(0);

    await scanSubmission(
      subId,
      () => {
        setScanCount((c) => c + 1);
      },
      async () => {
        setScanning(false);
        // Reload persisted findings
        const fds = await getFindings(subId);
        setFindings(fds);
      },
      () => {
        setScanning(false);
        setError("Scan stream disconnected");
      }
    );
  }

  async function handleWorkflow(action: string) {
    try {
      const updated = await workflowAction(subId, action, actionComment);
      setSubmission(updated);
      setActionComment("");
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleResolve(findingRowId: number, resolution: string) {
    try {
      const updated = await resolveFinding(subId, findingRowId, resolution);
      setFindings((prev) =>
        prev.map((f) => (f.row_id === findingRowId ? updated : f))
      );
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function loadAudit() {
    try {
      const trail = await getAuditTrail(subId);
      setAudit(trail);
      setShowAudit(true);
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

      {/* Actions bar */}
      <div className="actions-bar">
        <button
          className="btn-primary"
          onClick={handleScan}
          disabled={scanning}
        >
          {scanning ? `Scanning... (${scanCount})` : "🔍 Run Scan"}
        </button>

        {submission.status === "draft" && (
          <button className="btn-accent" onClick={() => handleWorkflow("submit")}>
            Submit for Review
          </button>
        )}
        {submission.status === "in_review" && role === "reviewer" && (
          <>
            <button className="btn-success" onClick={() => handleWorkflow("approve")}>
              ✓ Approve
            </button>
            <button className="btn-warning" onClick={() => handleWorkflow("request_changes")}>
              ✎ Request Changes
            </button>
          </>
        )}
        {submission.status === "in_review" && role === "admin" && (
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
        <button className="btn-ghost" onClick={loadAudit}>
          📜 Audit Trail
        </button>
      </div>

      {/* Findings list */}
      <section className="findings-section">
        <h2>Findings ({findings.length})</h2>
        {findings.length === 0 && !scanning && (
          <p className="empty-state">No findings. Run a scan to check this content.</p>
        )}
        <div className="findings-list">
          {findings.map((f) => {
            const verdict = f.severity >= 50 ? 2 : f.severity > 0 ? 1 : 0;
            return (
              <div
                key={f.row_id}
                className={`finding-card ${f.resolution !== "open" ? "resolved" : ""}`}
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
                  {f.payload?.trace && (
                    <span className="tier-badge" title={`Tier: ${f.payload.trace.tier}`}>
                      {f.payload.trace.tier === "deterministic" ? "⚙️" : "🤖"}{" "}
                      {f.payload.trace.tier}
                    </span>
                  )}
                </div>
                <p className="finding-message">{f.message}</p>
                {f.payload?.suggestion && (
                  <div className="suggestion">
                    💡 {f.payload.suggestion.label}
                  </div>
                )}
                <div className="finding-actions">
                  {f.resolution === "open" ? (
                    <>
                      <button
                        className="btn-sm btn-success"
                        onClick={() => handleResolve(f.row_id, "accepted")}
                      >
                        Accept
                      </button>
                      <button
                        className="btn-sm btn-ghost"
                        onClick={() => handleResolve(f.row_id, "dismissed")}
                      >
                        Dismiss
                      </button>
                      <button
                        className="btn-sm btn-warning"
                        onClick={() => handleResolve(f.row_id, "overridden")}
                      >
                        Override
                      </button>
                    </>
                  ) : (
                    <span className="resolution-badge">{f.resolution}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Audit trail modal */}
      {showAudit && (
        <div className="modal-overlay" onClick={() => setShowAudit(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2>Audit Trail</h2>
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
