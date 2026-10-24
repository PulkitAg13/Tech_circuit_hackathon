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

import type { components } from "./schema";

export type SchemaTypes = components["schemas"];

/* ── Auth ──────────────────────────────────────────────────────────── */

export type TokenResponse = SchemaTypes["TokenResponse"];
export type RegisterRequest = SchemaTypes["RegisterRequest"];
export type LoginRequest = SchemaTypes["LoginRequest"];

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

export type BundleAttachmentDto = SchemaTypes["BundleAttachmentDto"];
export type ImageNodeMetaDto = SchemaTypes["ImageNodeMetaDto"];
export type SubmissionVersionDto = SchemaTypes["SubmissionVersionResponse"];
export type Submission = SchemaTypes["SubmissionResponse"];
export type CreateSubmissionRequest = SchemaTypes["CreateSubmissionRequest"];

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

export interface LogoGeometryEvidence {
  kind: "logo_geometry";
  logo_id: string;
  expected_aspect_ratio: number;
  detected_aspect_ratio: number;
  aspect_distortion_pct: number;
  max_aspect_distortion_pct: number;
  clear_space_ratio_h: number;
  clear_space_intrusion_pct: number;
  orb_inlier_matches: number;
}

export interface VoiceReadabilityEvidence {
  kind: "voice_readability";
  flesch_kincaid_grade: number;
  max_flesch_kincaid_grade: number;
  passive_voice_pct: number;
  max_passive_voice_pct: number;
  max_sentence_words_observed: number;
  max_sentence_words_allowed: number;
  exemplar_similarity: number;
}

export interface TriggerObligationEvidence {
  kind: "trigger_obligation";
  obligation_id: string;
  matched_trigger: string;
  required_disclaimer_id: string;
  required_disclaimer_text: string;
  same_language_required: boolean;
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
  | HiddenTextEvidence
  | LogoGeometryEvidence
  | VoiceReadabilityEvidence
  | TriggerObligationEvidence;

export interface TracePayload {
  tier: "deterministic" | "smt" | "nli" | "generative" | number;
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

export type FindingResponse = Omit<SchemaTypes["FindingResponse"], "payload"> & {
  payload: FindingPayload;
};

export type FindingResolutionRequest = SchemaTypes["FindingResolutionRequest"];

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

/* ── Tier 3 Surgical Rewriter & Inline Comments ────────────────────── */

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
  suggestion: SuggestionPayload;
}

export async function rewriteFindingSpan(
  submissionId: number,
  findingRowId: number
): Promise<SurgicalRewriteResponse> {
  return request<SurgicalRewriteResponse>(
    `/submissions/${submissionId}/findings/${findingRowId}/rewrite`,
    { method: "POST" }
  );
}

export interface SubmissionCommentDto {
  id: number;
  submission_id: number;
  finding_id?: number | null;
  author_id: number;
  author_name: string;
  role: string;
  body: string;
  created_at: string;
}

export async function listSubmissionComments(
  submissionId: number,
  findingId?: number
): Promise<SubmissionCommentDto[]> {
  const qs = findingId !== undefined ? `?finding_id=${findingId}` : "";
  return request<SubmissionCommentDto[]>(`/submissions/${submissionId}/comments${qs}`);
}

export async function addSubmissionComment(
  submissionId: number,
  body: string,
  findingId?: number | null
): Promise<SubmissionCommentDto> {
  return request<SubmissionCommentDto>(`/submissions/${submissionId}/comments`, {
    method: "POST",
    body: JSON.stringify({ body, finding_id: findingId ?? null }),
  });
}

/* ── Workflow ──────────────────────────────────────────────────────── */

export type WorkflowActionRequest = SchemaTypes["WorkflowActionRequest"];

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

export type CanonSummary = SchemaTypes["CanonSummary"];

export async function listCanons(): Promise<CanonSummary[]> {
  return request<CanonSummary[]>("/canons");
}

export type CanonLintIssueDto = SchemaTypes["CanonLintIssueDto"];
export type CanonLintResponse = SchemaTypes["CanonLintResponse"];

export async function getCanonLint(canonId: string): Promise<CanonLintResponse> {
  return request<CanonLintResponse>(`/canons/${canonId}/lint`);
}

export type RuleFrictionDto = SchemaTypes["RuleFrictionDto"];
export type CanonFrictionResponse = SchemaTypes["CanonFrictionResponse"];

export async function getCanonFriction(canonId: string): Promise<CanonFrictionResponse> {
  return request<CanonFrictionResponse>(`/canons/${canonId}/friction`);
}

export type RuleRevisionDiffDto = SchemaTypes["RuleRevisionDiffDto"];
export type CanonRevisionPrResponse = SchemaTypes["CanonRevisionPrResponse"];

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

export async function applyCanonPr(
  canonId: string,
  overrideNotes: Record<string, string> = {},
  threshold = 0.40,
  minFlags = 3,
  persist = false
): Promise<CanonSummary> {
  return request<CanonSummary>(`/canons/${canonId}/apply-pr`, {
    method: "POST",
    body: JSON.stringify({
      override_notes: overrideNotes,
      threshold,
      min_flags: minFlags,
      persist,
    }),
  });
}

export interface CalibrateCanonRulePayload {
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

export async function calibrateCanonRule(
  canonId: string,
  payload: CalibrateCanonRulePayload
): Promise<CalibrateCanonRuleResponse> {
  return request<CalibrateCanonRuleResponse>(`/canons/${canonId}/calibrate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type GroundedRuleProvenanceDto = SchemaTypes["GroundedRuleProvenanceDto"];
export type CompileCanonResponse = SchemaTypes["CompileCanonResponse"];

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
