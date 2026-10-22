import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { listSubmissions, createSubmission, type Submission, listCanons, type CanonSummary } from "../../api/client";
import { useAuth } from "../auth/AuthContext";

const STATUS_COLORS: Record<string, string> = {
  draft: "#6366f1",
  in_review: "#f59e0b",
  changes_requested: "#ef4444",
  approved: "#22c55e",
  published: "#06b6d4",
};

export function DashboardPage() {
  const { username, role, logout } = useAuth();
  const navigate = useNavigate();
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [canons, setCanons] = useState<CanonSummary[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [canonId, setCanonId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [subs, cans] = await Promise.all([listSubmissions(), listCanons()]);
      setSubmissions(subs);
      setCanons(cans);
      if (cans.length > 0 && !canonId) setCanonId(cans[0].id);
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      const sub = await createSubmission(title || "Untitled", content, canonId);
      setShowCreate(false);
      setTitle("");
      setContent("");
      navigate(`/submissions/${sub.id}`);
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
          <span className="user-badge">{username} <span className="role-chip">{role}</span></span>
          <button className="btn-ghost" onClick={logout}>Sign Out</button>
        </div>
      </header>

      <main className="dashboard-main">
        <div className="section-header">
          <h2>Submissions</h2>
          <button className="btn-primary" onClick={() => setShowCreate(!showCreate)}>
            + New Submission
          </button>
        </div>

        {error && <p className="error-msg">{error}</p>}

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
              <select id="create-canon" value={canonId} onChange={(e) => setCanonId(e.target.value)}>
                {canons.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.id} v{c.version} ({c.term_count} terms, {c.color_count} colors)
                  </option>
                ))}
              </select>
            </div>
            <div className="input-group">
              <label htmlFor="create-content">Content</label>
              <textarea
                id="create-content"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Paste your content here..."
                rows={8}
                required
              />
            </div>
            <div className="form-actions">
              <button type="submit" className="btn-primary">Create & Review</button>
              <button type="button" className="btn-ghost" onClick={() => setShowCreate(false)}>Cancel</button>
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
      </main>
    </div>
  );
}
