/**
 * Typed API client for the CanonGate backend.
 *
 * Uses relative `/api` URLs so Vite's dev proxy (and production reverse proxy)
 * routes requests without hardcoded hostnames.
 *
 * In static environments (such as GitHub Pages or offline demos), automatically
 * activates `browserBackend` for full-fidelity interactive governance.
 */

import { browserBackend, sha256Hex } from "./browserEngine";

export function getApiBase(): string {
  if (typeof window !== "undefined" && localStorage.getItem("cg_api_base")) {
    return localStorage.getItem("cg_api_base")!;
  }
  if (import.meta.env.VITE_API_URL) {
    return `${import.meta.env.VITE_API_URL.replace(/\/$/, "")}/api`;
  }
  // If hosted on Render or GitHub Pages, default to the live Render backend:
  if (
    typeof window !== "undefined" &&
    (window.location.hostname.includes("onrender.com") ||
      window.location.hostname.includes("github.io"))
  ) {
    return "https://canongate-api.onrender.com/api";
  }
  return "/api";
}

export function isStaticOrGitHubPages(): boolean {
  if (typeof window === "undefined") return false;
  if (localStorage.getItem("cg_mode") === "standalone") return true;
  return false;
}

export function isJwtExpired(token: string | null): boolean {
  if (!token) return true;
  if (token.startsWith("browser_jwt_")) return false;
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded)) as { exp?: number };
    if (typeof payload.exp === "number") {
      return payload.exp * 1000 <= Date.now() + 5000;
    }
    return false;
  } catch {
    return false;
  }
}

function getToken(): string | null {
  const token = localStorage.getItem("cg_token");
  if (token && isJwtExpired(token)) {
    return null;
  }
  return token;
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return {
    "Bypass-Tunnel-Reminder": "true",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

let _reauthPromise: Promise<TokenResponse | null> | null = null;

async function trySilentReauth(base: string): Promise<TokenResponse | null> {
  if (_reauthPromise) return _reauthPromise;
  _reauthPromise = (async () => {
    const storedUser = localStorage.getItem("cg_username") || "creative_lead";
    const storedRole = localStorage.getItem("cg_role");
    const storedDisplay = localStorage.getItem("cg_display_name") || storedUser;
    try {
      let loginRes = await fetch(`${base}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: storedUser,
          password: "demoPassword123!",
        }),
      });
      if (!loginRes.ok) {
        // Fallback to creative_lead demo persona or re-register if DB was reset
        loginRes = await fetch(`${base}/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: storedUser,
            password: "demoPassword123!",
            role: storedRole || "creator",
            display_name: storedDisplay,
          }),
        });
      }
      if (!loginRes.ok) return null;
      let data = (await loginRes.json()) as TokenResponse;
      if (storedRole && data.role !== storedRole) {
        const switchRes = await fetch(`${base}/auth/switch-role`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${data.token}`,
          },
          body: JSON.stringify({ role: storedRole }),
        });
        if (switchRes.ok) {
          data = (await switchRes.json()) as TokenResponse;
        }
      }
      localStorage.setItem("cg_token", data.token);
      localStorage.setItem("cg_username", data.username);
      localStorage.setItem(
        "cg_display_name",
        data.display_name || storedDisplay || data.username,
      );
      localStorage.setItem("cg_role", data.role);
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("cg:auth-refreshed", { detail: data }),
        );
      }
      return data;
    } catch {
      return null;
    } finally {
      _reauthPromise = null;
    }
  })();
  return _reauthPromise;
}

function clearAndNotifyExpiredAuth() {
  localStorage.removeItem("cg_token");
  localStorage.removeItem("cg_username");
  localStorage.removeItem("cg_display_name");
  localStorage.removeItem("cg_role");
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("cg:auth-expired"));
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  isRetry = false,
): Promise<T> {
  if (isStaticOrGitHubPages()) {
    return handleBrowserRequest<T>(path, options);
  }

  const base = getApiBase();
  try {
    // Proactively refresh if the token in storage is already expired
    const rawToken = localStorage.getItem("cg_token");
    if (
      rawToken &&
      isJwtExpired(rawToken) &&
      !path.startsWith("/auth/login") &&
      !path.startsWith("/auth/register")
    ) {
      const refreshed = await trySilentReauth(base);
      if (!refreshed) {
        clearAndNotifyExpiredAuth();
        throw new ApiError(401, "Session expired. Please sign in again.");
      }
    }

    const res = await fetch(`${base}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(options.headers as Record<string, string> | undefined),
      },
    });

    const contentType = res.headers.get("content-type") || "";
    // If static hosting returned HTML SPA fallback (like index.html) instead of API JSON:
    if (contentType.includes("text/html")) {
      console.warn(`[CanonGate] API at ${base}${path} returned HTML fallback; falling back to in-browser engine.`);
      return handleBrowserRequest<T>(path, options);
    }

    if (!res.ok) {
      if (
        res.status === 401 &&
        !isRetry &&
        !path.startsWith("/auth/login") &&
        !path.startsWith("/auth/register")
      ) {
        const refreshed = await trySilentReauth(base);
        if (refreshed) {
          return request<T>(path, options, true);
        }
        clearAndNotifyExpiredAuth();
        throw new ApiError(401, "Session expired. Please sign in again.");
      }

      if (
        res.status === 404 &&
        !window.location.hostname.includes("localhost") &&
        !window.location.hostname.includes("127.0.0.1")
      ) {
        return handleBrowserRequest<T>(path, options);
      }
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail ?? res.statusText);
    }

    return res.json() as Promise<T>;
  } catch (err) {
    if (
      (err as Error)?.message?.includes("Failed to fetch") ||
      (err as Error)?.message?.includes("NetworkError") ||
      (err as Error)?.message?.includes("Load failed") ||
      (err as Error)?.message?.includes("Unexpected token '<'") ||
      (err as Error)?.message?.includes("JSON.parse")
    ) {
      console.warn(`[CanonGate] API unreachable at ${base}${path}; falling back to in-browser engine.`);
      return handleBrowserRequest<T>(path, options);
    }
    throw err;
  }
}

async function handleBrowserRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const body = options.body ? JSON.parse(options.body as string) : {};

  // Auth
  if (path === "/auth/register" || path === "/auth/login") {
    const username = body.username || "creator";
    const role =
      body.role ||
      (username.includes("reviewer") || username.includes("manager")
        ? "reviewer"
        : username.includes("admin") || username.includes("legal")
          ? "admin"
          : "creator");
    const display = body.display_name || username;
    return {
      token: `browser_jwt_${username}_${Date.now()}`,
      username,
      role,
      display_name: display,
    } as unknown as T;
  }

  if (path === "/auth/me") {
    const username = localStorage.getItem("cg_username") || "creative_lead";
    const role = localStorage.getItem("cg_role") || "creator";
    const display = localStorage.getItem("cg_display_name") || username;
    return {
      token: `browser_jwt_${username}_${Date.now()}`,
      username,
      role,
      display_name: display,
    } as unknown as T;
  }

  if (path === "/auth/switch-role") {
    const role = body.role || "creator";
    return {
      token: `browser_jwt_${role}_${Date.now()}`,
      username: `user_${role}`,
      role,
      display_name: `Persona (${role})`,
    } as unknown as T;
  }

  // Gate Check (`POST /api/gate/check`)
  if (path === "/gate/check" && method === "POST") {
    return browserBackend.gateCheck(body) as unknown as T;
  }

  // Canons (`GET /api/canons`) — matches exact hashes & counts from `canons/*.yaml`
  if (path === "/canons" && method === "GET") {
    return [
      {
        id: "indian-digital-lending",
        version: "1.0",
        hash: "1cd1ac13e83f1b00b2f9d64dd24a887c3cbd189830ba14b0e6c08f77a2e832ec",
        term_count: 4,
        color_count: 2,
        fact_count: 2,
        trigger_count: 1,
        logo_count: 1,
        has_voice_profile: true,
        rules: [
          {
            id: "term-guaranteed-approval",
            rule_type: "terminology",
            label: "guaranteed approval → subject to credit assessment",
            severity: 85,
            source_text: "RBI Digital Lending Directions: never promise guaranteed loan approval without underwriting.",
          },
          {
            id: "term-no-credit-check",
            rule_type: "terminology",
            label: "no credit check → streamlined credit verification",
            severity: 80,
            source_text: "RBI KYC / Bureau mandate: all regulated NBFC loans require bureau reporting.",
          },
          {
            id: "term-free-money",
            rule_type: "terminology",
            label: "free money → credit facility",
            severity: 75,
            source_text: "ASCI BFSI code: do not portray credit or loans as free money.",
          },
          {
            id: "term-cheap",
            rule_type: "terminology",
            label: "cheap → competitive-rate",
            severity: 40,
            source_text: "Brand voice: use 'competitive-rate' rather than 'cheap'.",
          },
          {
            id: "fact-kfs-processing-fee",
            rule_type: "fact",
            label: "0% processing fee on loans (under Rs 50,000; first-time borrowers only)",
            severity: 75,
            source_text: "0% processing fee on loans [under Rs 50,000, for first-time borrowers only]",
          },
          {
            id: "fact-kfs-apr-ceiling",
            rule_type: "fact",
            label: "Annual Percentage Rate (APR) is 18% (up to Rs 2,00,000)",
            severity: 80,
            source_text: "Annual Percentage Rate (APR) is 18% [up to Rs 2,00,000]",
          },
          {
            id: "trig-kfs-schedule",
            rule_type: "trigger",
            label: "Trigger: 0% processing fee → Subject to RBI Key Fact Statement (KFS) schedule",
            severity: 75,
            source_text: "Subject to RBI Key Fact Statement (KFS) schedule",
          },
          {
            id: "color-rbi-trust-navy",
            rule_type: "palette",
            label: "Trust Navy (#0D3B66 · ΔE₀₀ ≤ 3.0)",
            max_delta_e: 3.0,
            source_text: "#0D3B66",
          },
          {
            id: "color-upi-emerald",
            rule_type: "palette",
            label: "Verified Emerald (#1B8A5A · ΔE₀₀ ≤ 3.0)",
            max_delta_e: 3.0,
            source_text: "#1B8A5A",
          },
          {
            id: "lending-voice",
            rule_type: "voice",
            label: "Voice Profile (max 28 words, passive ≤ 25%, FK ≤ 12.0)",
            severity: 35,
            max_sentence_words: 28,
            max_passive_voice_pct: 25.0,
            max_flesch_kincaid_grade: 12.0,
            source_text: "Transparent digital credit with upfront APR and zero hidden charges.",
          },
          {
            id: "nbfc-primary-logo",
            rule_type: "logo",
            label: "NBFC Trust Mark (0.50H clear-space, aspect ≤ 2%)",
            severity: 65,
            clear_space_ratio_h: 0.5,
            max_aspect_distortion_pct: 2.0,
            source_text: "NBFC Trust Mark",
          },
        ],
      },
      {
        id: "indian-d2c-nutra",
        version: "1.0",
        hash: "eb05d1784ad09bab4677f33a8f8ba1b6a83f4a23c38df07b8a96d8552a133899",
        term_count: 3,
        color_count: 2,
        fact_count: 2,
        trigger_count: 0,
        logo_count: 0,
        has_voice_profile: false,
        rules: [
          {
            id: "term-miracle-cure",
            rule_type: "terminology",
            label: "miracle cure → nutritional support",
            severity: 90,
            source_text: "Drugs and Magic Remedies Act / ASCI: never claim a miracle cure.",
          },
          {
            id: "term-cures-diabetes",
            rule_type: "terminology",
            label: "cures diabetes → supports healthy glycemic metabolism",
            severity: 95,
            source_text: "ASCI Health Guidelines: nutraceuticals cannot claim to cure chronic disease.",
          },
          {
            id: "term-100pct-fat-burn",
            rule_type: "terminology",
            label: "100% fat burn → supports active weight management",
            severity: 80,
            source_text: "CCPA 2022: absolute 100% physiological efficacy claims require clinical trial proof.",
          },
          {
            id: "fact-curcumin-absorption",
            rule_type: "fact",
            label: "2x faster absorption (in-vitro ingredient study only; 8 weeks with piperine)",
            severity: 85,
            source_text: "2x faster absorption [in-vitro ingredient study only, when taken with piperine for 8 weeks]",
          },
          {
            id: "fact-protein-per-serving",
            rule_type: "fact",
            label: "24g plant protein per scoop (per 35g serving size)",
            severity: 75,
            source_text: "24g plant protein per scoop [per 35g serving size]",
          },
          {
            id: "color-botanical-sage",
            rule_type: "palette",
            label: "Botanical Sage (#2E6F40 · ΔE₀₀ ≤ 3.0)",
            max_delta_e: 3.0,
            source_text: "#2E6F40",
          },
          {
            id: "color-turmeric-gold",
            rule_type: "palette",
            label: "Turmeric Gold (#D99B26 · ΔE₀₀ ≤ 3.5)",
            max_delta_e: 3.5,
            source_text: "#D99B26",
          },
        ],
      },
      {
        id: "acme-corp",
        version: "1.0",
        hash: "5be7400ed3c8470ed07ed1cafeaade500f8f85619f333af28472e7f1d5ae06a9",
        term_count: 4,
        color_count: 3,
        fact_count: 2,
        trigger_count: 0,
        logo_count: 0,
        has_voice_profile: false,
        rules: [
          {
            id: "term-cheap",
            rule_type: "terminology",
            label: "cheap → affordable",
            severity: 60,
            source_text: "Brand voice: never use 'cheap' — it implies low quality.",
          },
          {
            id: "term-buy",
            rule_type: "terminology",
            label: "buy → purchase",
            severity: 40,
            source_text: "Formal tone: use 'purchase' instead of 'buy'.",
          },
          {
            id: "term-users",
            rule_type: "terminology",
            label: "users → customers",
            severity: 50,
            source_text: "We serve customers, not users.",
          },
          {
            id: "term-cutting-edge",
            rule_type: "terminology",
            label: "cutting-edge → innovative",
            severity: 30,
            source_text: "Avoid cliché buzzwords.",
          },
          {
            id: "fact-founding",
            rule_type: "fact",
            label: "Acme Corp was founded in 2020.",
            severity: 80,
            source_text: "Acme Corp was founded in 2020.",
          },
          {
            id: "fact-employees",
            rule_type: "fact",
            label: "Acme Corp has over 500 employees. (as of Q3 2025)",
            severity: 75,
            source_text: "Acme Corp has over 500 employees. [as of Q3 2025]",
          },
          {
            id: "color-primary",
            rule_type: "palette",
            label: "Primary Blue (#1A73E8 · ΔE₀₀ ≤ 3.0)",
            max_delta_e: 3.0,
            source_text: "#1A73E8",
          },
          {
            id: "color-accent",
            rule_type: "palette",
            label: "Accent Red (#EA4335 · ΔE₀₀ ≤ 5.0)",
            max_delta_e: 5.0,
            source_text: "#EA4335",
          },
          {
            id: "color-dark",
            rule_type: "palette",
            label: "Dark Gray (#202124 · ΔE₀₀ ≤ 2.0)",
            max_delta_e: 2.0,
            source_text: "#202124",
          },
        ],
      },
    ] as unknown as T;
  }

  const lintMatch = path.match(/^\/canons\/([^/]+)\/lint$/);
  if (lintMatch && method === "GET") {
    return {
      canon_id: lintMatch[1],
      canon_version: "1.0",
      is_valid: true,
      issues: [],
    } as unknown as T;
  }

  const frictionMatch = path.match(/^\/canons\/([^/]+)\/friction$/);
  if (frictionMatch && method === "GET") {
    return {
      canon_id: frictionMatch[1],
      canon_version: "1.0",
      krippendorff_alpha: 1.0,
      total_findings: 12,
      rules: [
        {
          rule_id: "term-guaranteed-approval",
          total_flags: 5,
          overrides_and_disputes: 0,
          raw_friction: 0.0,
          posterior_friction: 0.08,
          needs_canon_revision: false,
          proposed_action: "keep",
        },
        {
          rule_id: "term-cheap",
          total_flags: 7,
          overrides_and_disputes: 4,
          raw_friction: 0.57,
          posterior_friction: 0.49,
          needs_canon_revision: true,
          proposed_action: "relax_or_calibrate",
        },
      ],
      revision_recommendations: [
        "Rule 'term-cheap' shows high creator friction (alpha=0.49). Consider calibrating severity down to 40.",
      ],
    } as unknown as T;
  }

  const proposePrMatch = path.match(/^\/canons\/([^/]+)\/propose-pr$/);
  if (proposePrMatch && method === "POST") {
    const cId = proposePrMatch[1];
    return {
      canon_id: cId,
      base_version: "1.0",
      proposed_version: "1.1",
      has_changes: true,
      revisions: [
        {
          rule_id: "term-cheap",
          posterior_friction: 0.49,
          action: "calibrate",
          before_summary: "Severity 60 (Blocker)",
          after_summary: "Severity 40 (Warning)",
          rationale: "High creator override frequency with zero legal escalation",
        },
      ],
      yaml_diff: "@@ -11,2 +11,2 @@\n-    severity: 60\n+    severity: 40",
      bundles_evaluated: 15,
      before_findings: 18,
      after_findings: 11,
      before_blockers: 4,
      after_blockers: 2,
      reduction_ratio: 0.39,
      resolved_rule_ids: ["term-cheap"],
    } as unknown as T;
  }

  const applyPrMatch = path.match(/^\/canons\/([^/]+)\/apply-pr$/);
  if (applyPrMatch && method === "POST") {
    const cId = applyPrMatch[1];
    return {
      id: cId,
      version: "1.1",
      hash: sha256Hex(cId + "v1.1"),
      term_count: 4,
      color_count: 2,
      fact_count: 2,
      trigger_count: 1,
      logo_count: 1,
      has_voice_profile: true,
    } as unknown as T;
  }

  const calibrateMatch = path.match(/^\/canons\/([^/]+)\/calibrate$/);
  if (calibrateMatch && method === "POST") {
    const cId = calibrateMatch[1];
    return {
      canon_id: cId,
      previous_version: "1.0",
      new_version: "1.1",
      new_hash: sha256Hex(cId + "calibrated"),
      yaml_preview: `id: ${cId}\nversion: "1.1"\nterminology:\n  - id: ${body.rule_id}\n    severity: ${body.severity ?? 40}`,
    } as unknown as T;
  }

  if (path === "/canons/compile" && method === "POST") {
    const cId = body.canon_id || "brand-playbook";
    return {
      canon_id: cId,
      version: "1.0",
      hash: sha256Hex(cId),
      term_count: 3,
      color_count: 2,
      fact_count: 2,
      yaml_preview: `id: ${cId}\nversion: "1.0"\n# Compiled via Pipeline A Grounded Anchor Extractor`,
      provenance: [
        {
          rule_id: "term-guaranteed-approval",
          rule_kind: "terminology",
          start: 0,
          end: 42,
          source_text: "Loans must never guarantee instant approval without bureau pull.",
          raw_anchor_recall: 0.95,
          effective_anchor_recall: 0.92,
          recovered_conditions: ["bureau pull required"],
          round_trip_nli_score: 0.98,
          alignment_status: "verified",
        },
      ],
    } as unknown as T;
  }

  // Submissions
  if (path === "/submissions" && method === "GET") {
    return browserBackend.submissions as unknown as T;
  }

  if (path === "/submissions" && method === "POST") {
    const sub = browserBackend.createSubmission(
      body.title || "Untitled",
      body.raw_content || "",
      body.canon_id || "indian-digital-lending",
      body.attachments || [],
    );
    return sub as unknown as T;
  }

  const subDetailMatch = path.match(/^\/submissions\/(\d+)$/);
  if (subDetailMatch && method === "GET") {
    const sub = browserBackend.getSubmission(Number(subDetailMatch[1]));
    if (!sub) throw new ApiError(404, "Submission not found");
    return sub as unknown as T;
  }
  if (subDetailMatch && method === "DELETE") {
    const id = Number(subDetailMatch[1]);
    const idx = browserBackend.submissions.findIndex((s) => s.id === id);
    if (idx !== -1) browserBackend.submissions.splice(idx, 1);
    browserBackend.save();
    return { deleted: true, id } as unknown as T;
  }

  const contentUpdateMatch = path.match(/^\/submissions\/(\d+)\/content$/);
  if (contentUpdateMatch && method === "PUT") {
    const subId = Number(contentUpdateMatch[1]);
    const updated = browserBackend.updateSubmissionContent(
      subId,
      body.raw_content || "",
      body.change_note || "Edited campaign copy in Review Studio",
    );
    return updated as unknown as T;
  }

  const findingsMatch = path.match(/^\/submissions\/(\d+)\/findings$/);
  if (findingsMatch && method === "GET") {
    const list = browserBackend.findings[Number(findingsMatch[1])] || [];
    return list as unknown as T;
  }

  const patchFindingMatch = path.match(/^\/submissions\/(\d+)\/findings\/(\d+)$/);
  if (patchFindingMatch && method === "PATCH") {
    const subId = Number(patchFindingMatch[1]);
    const rowId = Number(patchFindingMatch[2]);
    const updated = browserBackend.resolveFinding(
      subId,
      rowId,
      body.resolution,
      body.apply_suggestion !== false,
      body.reason || "",
    );
    return updated as unknown as T;
  }

  const rewriteMatch = path.match(/^\/submissions\/(\d+)\/findings\/(\d+)\/rewrite$/);
  if (rewriteMatch && method === "POST") {
    const subId = Number(rewriteMatch[1]);
    const rowId = Number(rewriteMatch[2]);
    const res = browserBackend.rewriteFinding(subId, rowId);
    return res as unknown as T;
  }

  const wfMatch = path.match(/^\/submissions\/(\d+)\/workflow$/);
  if (wfMatch && method === "POST") {
    const subId = Number(wfMatch[1]);
    const res = browserBackend.workflow(subId, body.action, body.comment || "");
    return res as unknown as T;
  }

  const auditMatch = path.match(/^\/submissions\/(\d+)\/audit$/);
  if (auditMatch && method === "GET") {
    return browserBackend.getAuditTrail(Number(auditMatch[1])) as unknown as T;
  }

  const versMatch = path.match(/^\/submissions\/(\d+)\/versions$/);
  if (versMatch && method === "GET") {
    const sub = browserBackend.getSubmission(Number(versMatch[1]));
    if (!sub) return [] as unknown as T;
    return [
      {
        version_number: 1,
        content_hash: sub.content_hash,
        canon_hash: sub.canon_hash,
        raw_content: sub.raw_content,
        created_by: sub.creator_id,
        change_note: "Initial Draft Submission",
        created_at: sub.created_at,
      },
    ] as unknown as T;
  }

  const certMatch = path.match(/^\/submissions\/(\d+)\/certificate$/);
  if (certMatch && method === "GET") {
    return browserBackend.getCertificate(Number(certMatch[1])) as unknown as T;
  }

  const commentsMatch = path.match(/^\/submissions\/(\d+)\/comments(\?.*)?$/);
  if (commentsMatch && method === "GET") {
    const subId = Number(commentsMatch[1]);
    const urlParams = new URLSearchParams(commentsMatch[2] || "");
    const fId = urlParams.has("finding_id") ? Number(urlParams.get("finding_id")) : undefined;
    return browserBackend.listComments(subId, fId) as unknown as T;
  }
  if (commentsMatch && method === "POST") {
    const subId = Number(commentsMatch[1]);
    const comment = browserBackend.addComment(subId, body.body, body.finding_id);
    return comment as unknown as T;
  }

  throw new ApiError(404, `Endpoint ${method} ${path} not found`);
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

export function getMe(): Promise<TokenResponse> {
  return request("/auth/me");
}

export function switchRole(role: string): Promise<TokenResponse> {
  return request("/auth/switch-role", {
    method: "POST",
    body: JSON.stringify({ role }),
  });
}

// ── Synchronous Pre-Publish Gate (`POST /api/gate/check`) ────────────

export interface GateFindingItem {
  finding_id: string;
  row_id?: number | null;
  check_id: string;
  node_id: string;
  severity: number;
  verdict: "BLOCKER" | "WARNING";
  rule_id: string;
  locator: {
    kind?: string;
    start?: number;
    end?: number;
    x?: number;
    y?: number;
    w?: number;
    h?: number;
  };
  message: string;
  suggestion_label?: string | null;
  replacement_preview?: string | null;
  tier: string;
}

export interface GateCheckRequestPayload {
  canon_id: string;
  adapter?: "auto" | "generic" | "shopify" | "webflow";
  title?: string;
  raw_content: string;
  alpha?: number;
  persist?: boolean;
}

export interface GateCheckResponsePayload {
  decision: "allow" | "needs_review" | "block";
  adapter_used: string;
  canon_id: string;
  canon_version: string;
  canon_hash: string;
  content_hash: string;
  submission_id: number | null;
  studio_url: string | null;
  alpha: number;
  conformal_threshold: number;
  blocker_count: number;
  warning_count: number;
  total_findings: number;
  latency_ms: number;
  findings: GateFindingItem[];
}

export function runGateCheck(
  payload: GateCheckRequestPayload,
): Promise<GateCheckResponsePayload> {
  return request("/gate/check", {
    method: "POST",
    body: JSON.stringify({
      adapter: "generic",
      alpha: 0.1,
      persist: false,
      ...payload,
    }),
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
      label?: string;
      explanation?: string;
      replacements: Array<{
        span: { start: number; end: number };
        replacement: string;
      }>;
    } | null;
    trace: {
      tier: string | number;
      ai_used: boolean;
      external_call?: boolean;
      model_sha?: string | null;
      latency_ms?: number | null;
      rewriter_provider?: string | null;
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
  audit_path?: string[] | Array<{ sibling_hex: string; position: "left" | "right" }>;
  tree_size?: number;
  merkle_root?: string;
  tree_head?: {
    tree_size: number;
    timestamp: string;
    root_hash?: string;
    root_hash_hex?: string;
    signature?: string;
    signature_hex: string;
    public_key?: string;
    public_key_hex: string;
    algorithm?: string;
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
  api_key_configured?: boolean;
  provider_notice?: string;
  quality_gates?: Record<string, unknown>;
  context_trace?: Record<string, unknown>;
  suggestion: {
    label?: string;
    explanation?: string;
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

function runBrowserScan(
  submissionId: number,
  onFinding: (finding: FindingItem["payload"] & { id: string; check_id: string; node_id: string; severity: number; message: string }) => void,
  onDone: (total: number) => void,
): () => void {
  let active = true;
  const timer = setTimeout(() => {
    if (!active) return;
    const findings = browserBackend.scan(submissionId);
    for (const f of findings) {
      if (!active) return;
      onFinding({
        ...f.payload,
        id: f.finding_id,
        check_id: f.check_id,
        node_id: f.node_id,
        severity: f.severity,
        message: f.message,
      });
    }
    onDone(findings.length);
  }, 120);

  return () => {
    active = false;
    clearTimeout(timer);
  };
}

export function triggerScan(
  submissionId: number,
  onFinding: (finding: FindingItem["payload"] & { id: string; check_id: string; node_id: string; severity: number; message: string }) => void,
  onDone: (total: number) => void,
  onError: (err: Error) => void,
  alpha = 0.1,
): () => void {
  if (isStaticOrGitHubPages()) {
    return runBrowserScan(submissionId, onFinding, onDone);
  }

  const controller = new AbortController();

  (async () => {
    try {
      const base = getApiBase();
      const res = await fetch(
        `${base}/submissions/${submissionId}/scan?alpha=${encodeURIComponent(alpha)}`,
        {
          method: "POST",
          headers: authHeaders(),
          signal: controller.signal,
        },
      );

      const contentType = res.headers.get("content-type") || "";
      if (!res.ok || !res.body || contentType.includes("text/html")) {
        runBrowserScan(submissionId, onFinding, onDone);
        return;
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
        if (
          (err as Error)?.message?.includes("Failed to fetch") ||
          (err as Error)?.message?.includes("NetworkError") ||
          (err as Error)?.message?.includes("Load failed")
        ) {
          runBrowserScan(submissionId, onFinding, onDone);
          return;
        }
        onError(err as Error);
      }
    }
  })();

  return () => controller.abort();
}
