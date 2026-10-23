import { useState, useEffect, type ChangeEvent, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  listSubmissions,
  createSubmission,
  type Submission,
  type BundleAttachmentDto,
  listCanons,
  type CanonSummary,
  getCanonFriction,
  type CanonFrictionResponse,
  getCanonLint,
  type CanonLintResponse,
  proposeCanonPr,
  type CanonRevisionPrResponse,
  compileCanon,
  type CompileCanonResponse,
} from "../../api/client";
import { useAuth } from "../auth/AuthContext";

const STATUS_COLORS: Record<string, string> = {
  draft: "#6366f1",
  in_review: "#f59e0b",
  changes_requested: "#ef4444",
  approved: "#22c55e",
  published: "#06b6d4",
};

function fileToBase64Attachment(file: File): Promise<BundleAttachmentDto> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const idx = result.indexOf(",");
      const b64 = idx >= 0 ? result.slice(idx + 1) : result;
      resolve({ filename: file.name, content_base64: b64 });
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export function DashboardPage() {
  const { username, role, logout } = useAuth();
  const navigate = useNavigate();
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [canons, setCanons] = useState<CanonSummary[]>([]);
  const [activeTab, setActiveTab] = useState<"submissions" | "governance">("submissions");
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [canonId, setCanonId] = useState("");
  const [attachments, setAttachments] = useState<BundleAttachmentDto[]>([]);
  const [error, setError] = useState("");

  // Canon Governance, Friction & PR Studio state
  const [selectedCanonId, setSelectedCanonId] = useState("");
  const [frictionData, setFrictionData] = useState<CanonFrictionResponse | null>(null);
  const [lintData, setLintData] = useState<CanonLintResponse | null>(null);
  const [prProposal, setPrProposal] = useState<CanonRevisionPrResponse | null>(null);
  const [compileId, setCompileId] = useState("brand-canon-v1");
  const [compileText, setCompileText] = useState("");
  const [compileResult, setCompileResult] = useState<CompileCanonResponse | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [subs, cans] = await Promise.all([listSubmissions(), listCanons()]);
      setSubmissions(subs);
      setCanons(cans);
      if (cans.length > 0 && !canonId) {
        setCanonId(cans[0].id);
        setSelectedCanonId(cans[0].id);
      }
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleFileSelect(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    try {
      const converted = await Promise.all(files.map(fileToBase64Attachment));
      setAttachments((prev) => [...prev, ...converted]);
    } catch (err: any) {
      setError(err.message || "Failed to read attachment");
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    try {
      const sub = await createSubmission(title || "Untitled", content, canonId, attachments);
      setShowCreate(false);
      setTitle("");
      setContent("");
      setAttachments([]);
      navigate(`/submissions/${sub.id}`);
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function loadCanonGovernance(cid: string) {
    setSelectedCanonId(cid);
    setPrProposal(null);
    try {
      const [fric, lint] = await Promise.all([getCanonFriction(cid), getCanonLint(cid)]);
      setFrictionData(fric);
      setLintData(lint);
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleProposePr() {
    if (!selectedCanonId) return;
    try {
      const pr = await proposeCanonPr(selectedCanonId);
      setPrProposal(pr);
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleCompileCanon(e: FormEvent) {
    e.preventDefault();
    try {
      const res = await compileCanon(compileId, compileText, "1.0", [], false);
      setCompileResult(res);
      await loadData();
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-left">
          <span className="logo-icon">⚡</span>
          <h1>CanonGate</h1>
        </div>
        <div className="header-right">
          <button
            className={activeTab === "submissions" ? "btn-primary" : "btn-ghost"}
            onClick={() => setActiveTab("submissions")}
          >
            📄 Submissions
          </button>
          <button
            className={activeTab === "governance" ? "btn-primary" : "btn-ghost"}
            onClick={() => {
              setActiveTab("governance");
              if (selectedCanonId) loadCanonGovernance(selectedCanonId);
            }}
          >
            🛡️ Canon Governance & PR Studio
          </button>
          <span className="user-badge">
            {username} <span className="role-chip">{role}</span>
          </span>
          <button className="btn-ghost" onClick={logout}>
            Sign Out
          </button>
        </div>
      </header>

      <main className="dashboard-main">
        {error && <p className="error-msg">{error}</p>}

        {activeTab === "submissions" && (
          <>
            <div className="section-header">
              <h2>Submissions</h2>
              <button className="btn-primary" onClick={() => setShowCreate(!showCreate)}>
                + New Submission
              </button>
            </div>

            {showCreate && (
              <form className="create-form" onSubmit={handleCreate}>
                <div className="input-group">
                  <label htmlFor="create-title">Title</label>
                  <input
                    id="create-title"
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Content title"
                  />
                </div>
                <div className="input-group">
                  <label htmlFor="create-canon">Canon</label>
                  <select
                    id="create-canon"
                    value={canonId}
                    onChange={(e) => setCanonId(e.target.value)}
                  >
                    {canons.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.id} v{c.version} ({c.term_count} terms, {c.color_count} colors,{" "}
                        {c.fact_count} facts)
                      </option>
                    ))}
                  </select>
                </div>
                <div className="input-group">
                  <label htmlFor="create-content">Content (Markdown, HTML, KFS Tables)</label>
                  <textarea
                    id="create-content"
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="Paste your campaign copy or Markdown table here..."
                    rows={8}
                    required={attachments.length === 0}
                  />
                </div>
                <div className="input-group">
                  <label htmlFor="create-files">
                    Multimodal Bundle Attachments (.docx, .pdf, .html, .md, .png, .jpg)
                  </label>
                  <input
                    id="create-files"
                    type="file"
                    multiple
                    accept=".docx,.pdf,.html,.htm,.md,.txt,.png,.jpg,.jpeg,.webp"
                    onChange={handleFileSelect}
                  />
                  {attachments.length > 0 && (
                    <div className="card-meta" style={{ marginTop: "0.5rem" }}>
                      Attached ({attachments.length}):{" "}
                      {attachments.map((a) => a.filename).join(", ")}
                    </div>
                  )}
                </div>
                <div className="form-actions">
                  <button type="submit" className="btn-primary">
                    Create & Review
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => setShowCreate(false)}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}

            <div className="submissions-grid">
              {submissions.map((sub) => (
                <div
                  key={sub.id}
                  className="submission-card"
                  onClick={() => navigate(`/submissions/${sub.id}`)}
                >
                  <div className="card-header">
                    <h3>{sub.title}</h3>
                    <span
                      className="status-badge"
                      style={{ backgroundColor: STATUS_COLORS[sub.status] || "#888" }}
                    >
                      {sub.status.replace(/_/g, " ")}
                    </span>
                  </div>
                  <div className="card-meta">
                    <span>Canon: {sub.canon_id}</span>
                    <span>{new Date(sub.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              ))}
              {submissions.length === 0 && !showCreate && (
                <p className="empty-state">No submissions yet. Create one to get started.</p>
              )}
            </div>
          </>
        )}

        {activeTab === "governance" && (
          <div className="governance-studio">
            <div className="section-header">
              <h2>🛡️ Canon Governance, Friction Telemetry & v1.1 PR Generator</h2>
              <select
                value={selectedCanonId}
                onChange={(e) => loadCanonGovernance(e.target.value)}
              >
                {canons.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.id} v{c.version}
                  </option>
                ))}
              </select>
              <button className="btn-primary" onClick={handleProposePr}>
                ⚡ Auto-Draft Canon v1.1 PR & Simulate Impact
              </button>
            </div>

            {lintData && (
              <div className="evidence-box evidence-box-block" style={{ marginBottom: "1rem" }}>
                <strong>
                  Canon Static Linter ({lintData.canon_id} v{lintData.canon_version}):{" "}
                </strong>
                <span style={{ color: lintData.is_valid ? "#22c55e" : "#ef4444" }}>
                  {lintData.is_valid ? "✓ 0 Contradictions / Overlaps" : `${lintData.issues.length} Issue(s)`}
                </span>
              </div>
            )}

            {frictionData && (
              <div className="evidence-box evidence-box-block" style={{ marginBottom: "1rem" }}>
                <div className="evidence-header-row">
                  <span>
                    <strong>Krippendorff's α (Inter-Reviewer Agreement):</strong>{" "}
                    <code>{frictionData.krippendorff_alpha.toFixed(4)}</code>
                  </span>
                  <span>
                    <strong>Total Findings Tracked:</strong> {frictionData.total_findings}
                  </span>
                </div>
                {frictionData.rules.length > 0 && (
                  <table className="slot-diff-table" style={{ marginTop: "0.75rem" }}>
                    <thead>
                      <tr>
                        <th>Rule ID</th>
                        <th>Flags</th>
                        <th>Overrides</th>
                        <th>Raw Friction</th>
                        <th>Empirical Bayes Posterior</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {frictionData.rules.map((r) => (
                        <tr key={r.rule_id}>
                          <td>
                            <code>{r.rule_id}</code>
                          </td>
                          <td>{r.total_flags}</td>
                          <td>{r.overrides_and_disputes}</td>
                          <td>{(r.raw_friction * 100).toFixed(1)}%</td>
                          <td>
                            <strong>{(r.posterior_friction * 100).toFixed(1)}%</strong>
                          </td>
                          <td>
                            <span
                              className={`slot-status-pill ${
                                r.needs_canon_revision ? "status-dropped" : "status-match"
                              }`}
                            >
                              {r.needs_canon_revision ? "Needs v1.1 PR (>40%)" : "Healthy"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {prProposal && (
              <div className="evidence-box evidence-box-block" style={{ marginBottom: "1rem" }}>
                <h3>
                  Proposed Canon PR: {prProposal.canon_id} v{prProposal.base_version} → v
                  {prProposal.proposed_version}
                </h3>
                <p>
                  <strong>Historical Impact Backtest ({prProposal.bundles_evaluated} bundles):</strong>{" "}
                  Findings {prProposal.before_findings} → {prProposal.after_findings} | Blockers{" "}
                  {prProposal.before_blockers} → {prProposal.after_blockers} (Reduction:{" "}
                  {(prProposal.reduction_ratio * 100).toFixed(1)}%)
                </p>
                {prProposal.yaml_diff && (
                  <pre className="ev-snippet" style={{ whiteSpace: "pre-wrap", marginTop: "0.5rem" }}>
                    {prProposal.yaml_diff}
                  </pre>
                )}
              </div>
            )}

            <form className="create-form" onSubmit={handleCompileCanon}>
              <h3>Pipeline A: Compile Brand Book to Grounded Canon (Guards 1, 2 & 3)</h3>
              <div className="input-group">
                <label htmlFor="compile-id">New Canon ID</label>
                <input
                  id="compile-id"
                  type="text"
                  value={compileId}
                  onChange={(e) => setCompileId(e.target.value)}
                  required
                />
              </div>
              <div className="input-group">
                <label htmlFor="compile-text">Brand Guidelines / KFS Source Text</label>
                <textarea
                  id="compile-text"
                  value={compileText}
                  onChange={(e) => setCompileText(e.target.value)}
                  rows={5}
                  placeholder="Example: Never use 'cheap' — prefer 'affordable'. Primary Blue: #1A73E8. 0% processing fee on loans under Rs 50,000 valid until 2026-09-30."
                  required
                />
              </div>
              <button type="submit" className="btn-primary">
                Compile & Verify Guards 1–3
              </button>
            </form>

            {compileResult && (
              <div className="evidence-box evidence-box-block" style={{ marginTop: "1rem" }}>
                <h4>
                  Compiled {compileResult.canon_id} ({compileResult.hash.slice(0, 12)}…) —{" "}
                  {compileResult.term_count} terms, {compileResult.color_count} colors,{" "}
                  {compileResult.fact_count} facts
                </h4>
                <table className="slot-diff-table" style={{ marginTop: "0.5rem" }}>
                  <thead>
                    <tr>
                      <th>Rule ID</th>
                      <th>Kind</th>
                      <th>Span [s, e]</th>
                      <th>Guard 1 Anchor Recall</th>
                      <th>Guard 3 Round-Trip NLI</th>
                      <th>Guard 2 Grounding</th>
                    </tr>
                  </thead>
                  <tbody>
                    {compileResult.provenance.map((p) => (
                      <tr key={p.rule_id}>
                        <td>
                          <code>{p.rule_id}</code>
                        </td>
                        <td>{p.rule_kind}</td>
                        <td>
                          [{p.start}, {p.end}]
                        </td>
                        <td>{(p.effective_anchor_recall * 100).toFixed(0)}%</td>
                        <td>{(p.round_trip_nli_score * 100).toFixed(0)}%</td>
                        <td>
                          <span className="slot-status-pill status-match">
                            {p.alignment_status}
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
      </main>
    </div>
  );
}
