/* API client for CanonGate backend */

const API_BASE = "http://localhost:8000/api";

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = localStorage.getItem("cg_token");
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: { ...getHeaders(), ...opts?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

/* ── Auth ──────────────────────────────────────────────────────────── */

export interface TokenResponse {
  token: string;
  username: string;
  role: string;
}

export async function register(
  username: string, password: string, role: string, displayName?: string
): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, role, display_name: displayName || username }),
  });
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

/* ── Submissions ───────────────────────────────────────────────────── */

export interface Submission {
  id: number;
  title: string;
  status: string;
  content_hash: string;
  canon_id: string;
  canon_hash: string;
  creator_id: number;
  created_at: string;
  updated_at: string;
  raw_content?: string;
  paragraph_node_ids?: string[];
  image_paths?: string[];
}

export async function createSubmission(
  title: string, rawContent: string, canonId: string
): Promise<Submission> {
  return request<Submission>("/submissions", {
    method: "POST",
    body: JSON.stringify({ title, raw_content: rawContent, canon_id: canonId }),
  });
}

export async function listSubmissions(): Promise<Submission[]> {
  return request<Submission[]>("/submissions");
}

export async function getSubmission(id: number): Promise<Submission> {
  return request<Submission>(`/submissions/${id}`);
}

/* ── Scan (SSE via fetch, because scan is POST) ────────────────────── */

export async function scanSubmission(
  id: number,
  onFinding: (finding: any) => void,
  onDone: (total: number) => void,
  onError?: (err: any) => void
): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/submissions/${id}/scan`, {
      method: "POST",
      headers: getHeaders(),
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || res.statusText);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      let currentEvent = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (currentEvent === "finding") {
            onFinding(JSON.parse(data));
          } else if (currentEvent === "done") {
            onDone(JSON.parse(data).total);
          }
        }
      }
    }
  } catch (err) {
    onError?.(err);
  }
}

/* ── Findings ──────────────────────────────────────────────────────── */

export interface FindingResponse {
  row_id: number;
  finding_id: string;
  check_id: string;
  node_id: string;
  severity: number;
  message: string;
  resolution: string;
  payload: any;
}

export async function getFindings(submissionId: number): Promise<FindingResponse[]> {
  return request<FindingResponse[]>(`/submissions/${submissionId}/findings`);
}

export async function resolveFinding(
  submissionId: number, findingRowId: number, resolution: string
): Promise<FindingResponse> {
  return request<FindingResponse>(
    `/submissions/${submissionId}/findings/${findingRowId}`,
    { method: "PATCH", body: JSON.stringify({ resolution }) }
  );
}

/* ── Workflow ──────────────────────────────────────────────────────── */

export async function workflowAction(
  submissionId: number, action: string, comment?: string
): Promise<Submission> {
  return request<Submission>(`/submissions/${submissionId}/workflow`, {
    method: "POST",
    body: JSON.stringify({ action, comment: comment || "" }),
  });
}

/* ── Audit ─────────────────────────────────────────────────────────── */

export async function getAuditTrail(submissionId: number): Promise<any[]> {
  return request<any[]>(`/submissions/${submissionId}/audit`);
}

/* ── Canons ────────────────────────────────────────────────────────── */

export interface CanonSummary {
  id: string;
  version: string;
  hash: string;
  term_count: number;
  color_count: number;
  fact_count: number;
}

export async function listCanons(): Promise<CanonSummary[]> {
  return request<CanonSummary[]>("/canons");
}

export interface RuleFrictionDto {
  rule_id: string;
  total_flags: number;
  overrides_and_disputes: number;
  raw_friction: number;
  posterior_friction: number;
  needs_canon_revision: boolean;
  proposed_action?: string;
}

export interface CanonFrictionResponse {
  canon_id: string;
  canon_version: string;
  krippendorff_alpha: number;
  total_findings: number;
  rules: RuleFrictionDto[];
  revision_recommendations: string[];
}

export async function getCanonFriction(canonId: string): Promise<CanonFrictionResponse> {
  return request<CanonFrictionResponse>(`/canons/${canonId}/friction`);
}
