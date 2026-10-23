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

/* ── Submissions & Multimodal Bundle Upload ────────────────────────── */

export interface BundleAttachmentDto {
  filename: string;
  content_base64: string;
}

export interface ImageNodeMetaDto {
  index: number;
  node_id: string;
  asset_path: string;
  width: number;
  height: number;
  alt?: string | null;
  url: string;
}

export interface SubmissionVersionDto {
  version_number: number;
  content_hash: string;
  canon_hash: string;
  raw_content: string;
  created_by: number;
  change_note: string;
  created_at: string;
}

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
  text_blocks?: string[];
  image_paths?: string[];
  image_nodes?: ImageNodeMetaDto[];
}

export async function createSubmission(
  title: string,
  rawContent: string,
  canonId: string,
  attachments: BundleAttachmentDto[] = []
): Promise<Submission> {
  return request<Submission>("/submissions", {
    method: "POST",
    body: JSON.stringify({
      title,
      raw_content: rawContent,
      canon_id: canonId,
      attachments,
    }),
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
  onDone: (total: number, meta?: { alpha?: number; conformal_threshold?: number }) => void,
  onError?: (err: any) => void,
  alpha = 0.10
): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/submissions/${id}/scan?alpha=${alpha}`, {
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
            const parsed = JSON.parse(data);
            onDone(parsed.total, {
              alpha: parsed.alpha,
              conformal_threshold: parsed.conformal_threshold,
            });
          }
        }
      }
    }
  } catch (err) {
    onError?.(err);
  }
}

/* ── Findings & Discriminated Evidence Types ───────────────────────── */

export interface TermMatchEvidence {
  kind: "term_match";
  term: string;
  preferred: string;
}

export interface ColorDistanceEvidence {
  kind: "color_distance";
  found_hex: string;
  approved_hex: string;
  delta_e: number;
  max_allowed: number;
}

export interface ContrastEvidence {
  kind: "contrast";
  fg_hex: string;
  bg_hex: string;
  contrast_ratio: number;
  required_ratio: number;
  wcag_level: "AA" | "AAA";
  suggested_fg_hex?: string | null;
}

export interface LegibilityEvidence {
  kind: "legibility";
  measured_box_px: number;
  estimated_x_height_px: number;
  required_px: number;
  image_height_px: number;
  ocr_confidence: number;
  script_mismatch?: boolean;
}

export interface SaliencyEvidence {
  kind: "saliency";
  disclaimer_saliency: number;
  headline_saliency: number;
  ratio: number;
  min_ratio: number;
}

export interface ConfusableEvidence {
  kind: "confusable";
  spoofed_token: string;
  normalized_token: string;
  confusable_chars: string[];
  scripts_detected: string[];
}

export interface AlgebraicProofEvidence {
  kind: "algebraic_proof";
  draft_expr: string;
  canon_constraint: string;
  solver_status: "sat_counterexample" | "unsat_valid";
  counterexample: Record<string, string>;
}

export interface SlotEntryDto {
  slot: string;
  canon_value: string;
  draft_value: string;
  status: "match" | "dropped" | "contradicted" | "unverified";
}

export interface SlotDiffEvidence {
  kind: "slot_diff";
  entailment_prob: number;
  canon_claim_id: string;
  canon_text: string;
  slots: SlotEntryDto[];
}

export interface C2paEvidence {
  kind: "c2pa";
  has_manifest: boolean;
  validation_state: string;
  issuer?: string | null;
  digital_source_type?: string | null;
}

export interface HiddenTextEvidence {
  kind: "hidden_text";
  mechanism: string;
  extracted_snippet: string;
}

export type EvidencePayload =
  | TermMatchEvidence
  | ColorDistanceEvidence
  | ContrastEvidence
  | LegibilityEvidence
  | SaliencyEvidence
  | ConfusableEvidence
  | AlgebraicProofEvidence
  | SlotDiffEvidence
  | C2paEvidence
  | HiddenTextEvidence;

export interface TracePayload {
  tier: "deterministic" | "smt" | "nli" | "generative";
  ai_used?: boolean;
  external_call?: boolean;
  model_sha?: string | null;
  latency_ms?: number | null;
}

export interface ReplaceSpanDto {
  span: { kind?: "span"; start: number; end: number };
  replacement: string;
}

export interface SuggestionPayload {
  label: string;
  replacements?: ReplaceSpanDto[];
}

export interface FindingPayload {
  id?: string;
  check_id?: string;
  node_id?: string;
  locator?: {
    kind?: "span" | "bbox";
    start?: number;
    end?: number;
    x?: number;
    y?: number;
    w?: number;
    h?: number;
  };
  severity?: number;
  message?: string;
  rule_ref?: {
    rule_id: string;
    rule_type: string;
    source_text?: string;
  };
  evidence?: EvidencePayload;
  suggestion?: SuggestionPayload | null;
  trace?: TracePayload;
}

export interface FindingResponse {
  row_id: number;
  finding_id: string;
  check_id: string;
  node_id: string;
  severity: number;
  message: string;
  resolution: string;
  resolution_reason?: string;
  payload: FindingPayload;
}

export async function getFindings(submissionId: number): Promise<FindingResponse[]> {
  return request<FindingResponse[]>(`/submissions/${submissionId}/findings`);
}

export async function resolveFinding(
  submissionId: number,
  findingRowId: number,
  resolution: string,
  applySuggestion = true,
  reason = ""
): Promise<FindingResponse> {
  return request<FindingResponse>(
    `/submissions/${submissionId}/findings/${findingRowId}`,
    {
      method: "PATCH",
      body: JSON.stringify({ resolution, apply_suggestion: applySuggestion, reason }),
    }
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

/* ── Audit & Governance Certificates ───────────────────────────────── */

export async function getAuditTrail(submissionId: number): Promise<any[]> {
  return request<any[]>(`/submissions/${submissionId}/audit`);
}

export async function getGovernanceCertificate(
  submissionId: number
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/submissions/${submissionId}/certificate`);
}

export async function getSubmissionVersions(
  submissionId: number
): Promise<SubmissionVersionDto[]> {
  return request<SubmissionVersionDto[]>(`/submissions/${submissionId}/versions`);
}

export async function getReplayManifest(
  submissionId: number,
  alpha = 0.10
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(
    `/submissions/${submissionId}/replay-manifest?alpha=${alpha}`
  );
}

/* ── Canons, Lint, Friction, Pipeline A Compile & v1.1 PRs ────────── */

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

export interface CanonLintIssueDto {
  rule_ids: string[];
  kind: string;
  message: string;
}

export interface CanonLintResponse {
  canon_id: string;
  canon_version: string;
  is_valid: boolean;
  issues: CanonLintIssueDto[];
}

export async function getCanonLint(canonId: string): Promise<CanonLintResponse> {
  return request<CanonLintResponse>(`/canons/${canonId}/lint`);
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

export interface RuleRevisionDiffDto {
  rule_id: string;
  posterior_friction: number;
  action: string;
  before_summary: string;
  after_summary: string;
  rationale: string;
}

export interface CanonRevisionPrResponse {
  canon_id: string;
  base_version: string;
  proposed_version: string;
  has_changes: boolean;
  revisions: RuleRevisionDiffDto[];
  yaml_diff: string;
  bundles_evaluated: number;
  before_findings: number;
  after_findings: number;
  before_blockers: number;
  after_blockers: number;
  reduction_ratio: number;
  resolved_rule_ids: string[];
}

export async function proposeCanonPr(
  canonId: string,
  overrideNotes: Record<string, string> = {},
  threshold = 0.40,
  minFlags = 3
): Promise<CanonRevisionPrResponse> {
  return request<CanonRevisionPrResponse>(`/canons/${canonId}/propose-pr`, {
    method: "POST",
    body: JSON.stringify({
      override_notes: overrideNotes,
      threshold,
      min_flags: minFlags,
    }),
  });
}

export interface GroundedRuleProvenanceDto {
  rule_id: string;
  rule_kind: string;
  start: number;
  end: number;
  source_text: string;
  raw_anchor_recall: number;
  effective_anchor_recall: number;
  recovered_conditions: string[];
  round_trip_nli_score: number;
  alignment_status: string;
}

export interface CompileCanonResponse {
  canon_id: string;
  version: string;
  hash: string;
  term_count: number;
  color_count: number;
  fact_count: number;
  yaml_preview: string;
  provenance: GroundedRuleProvenanceDto[];
}

export async function compileCanon(
  canonId: string,
  rawText: string,
  version = "1.0",
  attachments: BundleAttachmentDto[] = [],
  persist = false
): Promise<CompileCanonResponse> {
  return request<CompileCanonResponse>("/canons/compile", {
    method: "POST",
    body: JSON.stringify({
      canon_id: canonId,
      version,
      raw_text: rawText,
      attachments,
      persist,
    }),
  });
}
