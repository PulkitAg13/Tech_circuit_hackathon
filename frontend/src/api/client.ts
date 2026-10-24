/**
 * Typed API client for the CanonGate backend.
 *
 * Uses relative `/api` URLs so Vite's dev proxy (and production reverse proxy)
 * routes requests without hardcoded hostnames.
 */

const BASE = "/api";

function getToken(): string | null {
  return localStorage.getItem("cg_token");
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers as Record<string, string> | undefined),
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }

  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// ── Auth ─────────────────────────────────────────────────────────────

export interface TokenResponse {
  token: string;
  username: string;
  display_name?: string;
  role: string;
}

export function login(
  username: string,
  password: string,
): Promise<TokenResponse> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function register(
  username: string,
  password: string,
  role = "creator",
  displayName = "",
): Promise<TokenResponse> {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      username,
      password,
      role,
      display_name: displayName || username,
    }),
  });
}

export function switchRole(role: string): Promise<TokenResponse> {
  return request("/auth/switch-role", {
    method: "POST",
    body: JSON.stringify({ role }),
  });
}

// ── Canons ───────────────────────────────────────────────────────────

export interface CanonRuleItem {
  id: string;
  rule_type: "terminology" | "palette" | "fact" | "trigger" | "voice" | "logo" | string;
  label: string;
  severity?: number | null;
  max_delta_e?: number | null;
  max_sentence_words?: number | null;
  max_passive_voice_pct?: number | null;
  max_flesch_kincaid_grade?: number | null;
  max_aspect_distortion_pct?: number | null;
  clear_space_ratio_h?: number | null;
  source_text?: string;
}

export interface CanonSummary {
  id: string;
  version: string;
  hash: string;
  term_count: number;
  color_count: number;
  fact_count: number;
  trigger_count?: number;
  logo_count?: number;
  has_voice_profile?: boolean;
  rules?: CanonRuleItem[];
}

export interface CanonLintIssue {
  rule_ids: string[];
  kind: string;
  message: string;
}

export interface CanonLintResponse {
  canon_id: string;
  canon_version: string;
  is_valid: boolean;
  issues: CanonLintIssue[];
}

export interface RuleFriction {
  rule_id: string;
  total_flags: number;
  overrides_and_disputes: number;
  raw_friction: number;
  posterior_friction: number;
  needs_canon_revision: boolean;
  proposed_action: string | null;
}

export interface RecurringCategoryBreakdown {
  category: string;
  total_flags: number;
  open_count: number;
  resolved_count: number;
  overridden_count: number;
  top_rule_id: string;
  insight: string;
}

export interface CanonFrictionResponse {
  canon_id: string;
  canon_version: string;
  krippendorff_alpha: number;
  total_findings: number;
  rules: RuleFriction[];
  revision_recommendations: string[];
  category_breakdown?: RecurringCategoryBreakdown[];
}

export interface RuleRevisionDiff {
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
  revisions: RuleRevisionDiff[];
  yaml_diff: string;
  bundles_evaluated: number;
  before_findings: number;
  after_findings: number;
  before_blockers: number;
  after_blockers: number;
  reduction_ratio: number;
  resolved_rule_ids: string[];
}

export function listCanons(): Promise<CanonSummary[]> {
  return request("/canons");
}

export function getCanonLint(canonId: string): Promise<CanonLintResponse> {
  return request(`/canons/${canonId}/lint`);
}

export function getCanonFriction(canonId: string): Promise<CanonFrictionResponse> {
  return request(`/canons/${canonId}/friction`);
}

export function proposeCanonPr(
  canonId: string,
  overrideNotes: Record<string, string> = {},
  threshold = 0.4,
  minFlags = 1,
): Promise<CanonRevisionPrResponse> {
  return request(`/canons/${canonId}/propose-pr`, {
    method: "POST",
    body: JSON.stringify({
      override_notes: overrideNotes,
      threshold,
      min_flags: minFlags,
    }),
  });
}

export function applyCanonPr(
  canonId: string,
  overrideNotes: Record<string, string> = {},
  threshold = 0.4,
  minFlags = 1,
  persist = false,
): Promise<CanonSummary> {
  return request(`/canons/${canonId}/apply-pr`, {
    method: "POST",
    body: JSON.stringify({
      override_notes: overrideNotes,
      threshold,
      min_flags: minFlags,
      persist,
    }),
  });
}

export interface CalibrateCanonRuleRequest {
  rule_id: string;
  severity?: number;
  max_delta_e?: number;
  max_sentence_words?: number;
  max_passive_voice_pct?: number;
  max_flesch_kincaid_grade?: number;
  max_aspect_distortion_pct?: number;
  clear_space_ratio_h?: number;
  persist?: boolean;
}

export interface CalibrateCanonRuleResponse {
  canon_id: string;
  previous_version: string;
  new_version: string;
  new_hash: string;
  yaml_preview: string;
}

export function calibrateCanonRule(
  canonId: string,
  payload: CalibrateCanonRuleRequest,
): Promise<CalibrateCanonRuleResponse> {
  return request(`/canons/${canonId}/calibrate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface GroundedRuleProvenance {
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

export interface CustomTermInput {
  pattern_text: string;
  preferred: string;
  severity?: number;
}

export interface CustomFactInput {
  text: string;
  conditions?: string[];
  valid_until?: string | null;
}

export interface CustomColorInput {
  name: string;
  hex: string;
  max_delta_e?: number;
}

export interface CustomTriggerInput {
  trigger_pattern: string;
  required_disclaimer_text: string;
  severity?: number;
}

export interface CompileCanonExtraOptions {
  custom_terms?: CustomTermInput[];
  custom_facts?: CustomFactInput[];
  custom_colors?: CustomColorInput[];
  custom_triggers?: CustomTriggerInput[];
  voice_max_words?: number;
  voice_passive_pct?: number;
  voice_fk_grade?: number;
}

export interface CompileCanonResponse {
  canon_id: string;
  version: string;
  hash: string;
  term_count: number;
  color_count: number;
  fact_count: number;
  trigger_count?: number;
  logo_count?: number;
  has_voice_profile?: boolean;
  yaml_preview: string;
  provenance: GroundedRuleProvenance[];
}

export function compileBrandCanon(
  canonId: string,
  rawText: string,
  attachments: BundleAttachmentPayload[] = [],
  version = "1.0",
  persist = false,
  extra: CompileCanonExtraOptions = {},
): Promise<CompileCanonResponse> {
  return request("/canons/compile", {
    method: "POST",
    body: JSON.stringify({
      canon_id: canonId,
      version,
      raw_text: rawText,
      attachments,
      persist,
      ...extra,
    }),
  });
}

// ── Submissions ──────────────────────────────────────────────────────

export interface ImageNodeMeta {
  index: number;
  node_id: string;
  asset_path: string;
  width: number;
  height: number;
  alt: string | null;
  url: string;
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
  image_nodes?: ImageNodeMeta[];
}

export interface FindingItem {
  row_id: number;
  finding_id: string;
  check_id: string;
  node_id: string;
  severity: number;
  message: string;
  resolution: string;
  resolution_reason?: string;
  payload: {
    locator: {
      kind: string;
      start?: number;
      end?: number;
      x?: number;
      y?: number;
      w?: number;
      h?: number;
    };
    rule_ref: { rule_id: string; rule_type: string; source_text: string };
    evidence: Record<string, unknown>;
    suggestion: {
      explanation: string;
      replacements: Array<{
        span: { start: number; end: number };
        replacement: string;
      }>;
    } | null;
    trace: {
      tier: string;
      ai_used: boolean;
      model_name?: string | null;
      external_service?: string | null;
      pii_scrubbed?: boolean;
    };
  };
}

export interface BundleAttachmentPayload {
  filename: string;
  content_base64: string;
}

export function createSubmission(
  title: string,
  rawContent: string,
  canonId: string,
  imagePaths: string[] = [],
  attachments: BundleAttachmentPayload[] = [],
): Promise<Submission> {
  return request("/submissions", {
    method: "POST",
    body: JSON.stringify({
      title,
      raw_content: rawContent,
      canon_id: canonId,
      image_paths: imagePaths,
      attachments,
    }),
  });
}

export function listSubmissions(): Promise<Submission[]> {
  return request("/submissions");
}

export function getSubmission(id: number): Promise<Submission> {
  return request(`/submissions/${id}`);
}

export function deleteSubmission(id: number): Promise<{ deleted: boolean; id: number }> {
  return request(`/submissions/${id}`, {
    method: "DELETE",
  });
}

export function updateSubmissionContent(
  id: number,
  rawContent: string,
  changeNote = "Edited campaign copy in Review Studio",
  alpha = 0.1,
): Promise<Submission> {
  return request(`/submissions/${id}/content`, {
    method: "PUT",
    body: JSON.stringify({
      raw_content: rawContent,
      change_note: changeNote,
      alpha,
    }),
  });
}

export function getFindings(submissionId: number): Promise<FindingItem[]> {
  return request(`/submissions/${submissionId}/findings`);
}

export function resolveFinding(
  submissionId: number,
  findingRowId: number,
  resolution: "accepted" | "dismissed" | "overridden",
  reason?: string,
): Promise<FindingItem> {
  return request(`/submissions/${submissionId}/findings/${findingRowId}`, {
    method: "PATCH",
    body: JSON.stringify({
      resolution,
      apply_suggestion: resolution === "accepted",
      reason: reason ?? null,
    }),
  });
}

export function workflowAction(
  submissionId: number,
  action: string,
  comment = "",
): Promise<Submission> {
  return request(`/submissions/${submissionId}/workflow`, {
    method: "POST",
    body: JSON.stringify({ action, comment }),
  });
}

export interface AuditEvent {
  id: number;
  submission_id: number;
  action: string;
  from_status: string;
  to_status: string;
  actor_id: number;
  comment: string;
  prev_hash: string;
  event_hash: string;
  created_at: string;
  leaf_index?: number;
  audit_path?: Array<{ sibling_hex: string; position: "left" | "right" }>;
  tree_size?: number;
  merkle_root?: string;
  tree_head?: {
    tree_size: number;
    timestamp: string;
    root_hash_hex: string;
    signature_hex: string;
    public_key_hex: string;
    algorithm: string;
  };
}

export function getAuditTrail(submissionId: number): Promise<AuditEvent[]> {
  return request(`/submissions/${submissionId}/audit`);
}

export interface SubmissionVersionItem {
  version_number: number;
  content_hash: string;
  canon_hash: string;
  raw_content: string;
  created_by: number;
  change_note: string;
  created_at: string;
}

export function getSubmissionVersions(
  submissionId: number,
): Promise<SubmissionVersionItem[]> {
  return request(`/submissions/${submissionId}/versions`);
}

export function getGovernanceCertificate(
  submissionId: number,
): Promise<Record<string, unknown>> {
  return request(`/submissions/${submissionId}/certificate`);
}

export interface SubmissionCommentItem {
  id: number;
  submission_id: number;
  finding_id: number | null;
  author_id: number;
  author_name: string;
  role: string;
  body: string;
  created_at: string;
}

export function getSubmissionComments(
  submissionId: number,
  findingId?: number,
): Promise<SubmissionCommentItem[]> {
  const qs = findingId !== undefined ? `?finding_id=${findingId}` : "";
  return request(`/submissions/${submissionId}/comments${qs}`);
}

export function createSubmissionComment(
  submissionId: number,
  body: string,
  findingId: number | null = null,
): Promise<SubmissionCommentItem> {
  return request(`/submissions/${submissionId}/comments`, {
    method: "POST",
    body: JSON.stringify({ body, finding_id: findingId }),
  });
}

export interface SurgicalRewriteResponse {
  row_id: number;
  finding_id: string;
  original_text: string;
  rewritten_text: string;
  edit_distance_ratio: number;
  max_edit_distance_ratio: number;
  reverified: boolean;
  remaining_findings_count: number;
  pii_masked_count: number;
  masked_prompt_preview: string;
  used_provider: string;
  suggestion: {
    explanation: string;
    replacements: Array<{
      span: { start: number; end: number };
      replacement: string;
    }>;
  };
}

export function rewriteFindingSpan(
  submissionId: number,
  findingRowId: number,
): Promise<SurgicalRewriteResponse> {
  return request(`/submissions/${submissionId}/findings/${findingRowId}/rewrite`, {
    method: "POST",
  });
}

// ── SSE Scan ─────────────────────────────────────────────────────────

export function triggerScan(
  submissionId: number,
  onFinding: (finding: FindingItem["payload"] & { id: string; check_id: string; node_id: string; severity: number; message: string }) => void,
  onDone: (total: number) => void,
  onError: (err: Error) => void,
  alpha = 0.1,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(
        `${BASE}/submissions/${submissionId}/scan?alpha=${encodeURIComponent(alpha)}`,
        {
          method: "POST",
          headers: authHeaders(),
          signal: controller.signal,
        },
      );

      if (!res.ok || !res.body) {
        throw new ApiError(res.status, res.statusText);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let eventType = "";
        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            const raw = line.slice(5).trim();
            if (!raw) continue;
            const parsed = JSON.parse(raw);
            if (eventType === "finding") {
              onFinding(parsed);
            } else if (eventType === "done") {
              onDone(parsed.total);
            }
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onError(err as Error);
      }
    }
  })();

  return () => controller.abort();
}
