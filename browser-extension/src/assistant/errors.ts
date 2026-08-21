/**
 * Phase 34 · Unified error experience (frontend half).
 *
 * Every assistant failure — Chat, Streaming, Retry, Stop, Provider Settings,
 * Onboarding — is rendered through {@link safeErrorMessage}. The function is a
 * *closed* mapping: it only ever returns one of {@link SAFE_MESSAGES}. Backend
 * text, provider text, exception text and network text are used to *classify*
 * the failure, never to produce the string the user reads.
 *
 * That is what keeps the forbidden material out of the UI: stack traces,
 * internal paths, filesystem paths, API keys, Authorization headers, provider
 * secrets, raw provider responses, internal exception objects and database
 * connection strings can never survive a mapping whose entire output alphabet
 * is seven fixed sentences.
 *
 * The backend has the same vocabulary in ``app/assistant/errors.py``; this
 * module deliberately duplicates the strings instead of fetching them, so an
 * unreachable Bridge still produces a safe message.
 */

/** Fixed user-facing vocabulary. Nothing else is ever shown. */
export const SAFE_MESSAGES = {
  invalidKey: "Invalid API key",
  rateLimited: "Rate limit reached",
  providerUnavailable: "Provider unavailable",
  backendUnreachable: "Backend unreachable",
  streamingStopped: "Streaming stopped",
  notConfigured: "LLM provider is not configured",
  requestRejected: "Provider rejected the request",
} as const;

export type SafeErrorMessage = (typeof SAFE_MESSAGES)[keyof typeof SAFE_MESSAGES];

export const SAFE_MESSAGE_LIST: readonly SafeErrorMessage[] = Object.freeze(
  Object.values(SAFE_MESSAGES) as SafeErrorMessage[],
);

/** Machine-readable classification, used for styling and tests. */
export type SafeErrorKind =
  | "invalid_key"
  | "rate_limited"
  | "provider_unavailable"
  | "backend_unreachable"
  | "streaming_stopped"
  | "provider_not_configured"
  | "request_rejected";

export interface SafeError {
  kind: SafeErrorKind;
  message: SafeErrorMessage;
  /** HTTP status when one was observed, otherwise 0. */
  status: number;
}

const KIND_MESSAGE: Record<SafeErrorKind, SafeErrorMessage> = {
  invalid_key: SAFE_MESSAGES.invalidKey,
  rate_limited: SAFE_MESSAGES.rateLimited,
  provider_unavailable: SAFE_MESSAGES.providerUnavailable,
  backend_unreachable: SAFE_MESSAGES.backendUnreachable,
  streaming_stopped: SAFE_MESSAGES.streamingStopped,
  provider_not_configured: SAFE_MESSAGES.notConfigured,
  request_rejected: SAFE_MESSAGES.requestRejected,
};

/**
 * Backend error codes that carry their own meaning.
 *
 * ``provider_not_configured`` is reported by the assistant API with HTTP 400
 * (Phase 34) and by the Phase 31 ``/llm/chat`` gateway with 422; both are
 * accepted here so the frontend does not depend on which one arrives.
 */
const CODE_KIND: Record<string, SafeErrorKind> = {
  provider_not_configured: "provider_not_configured",
  unknown_provider: "request_rejected",
  unknown_model: "request_rejected",
  provider_unreachable: "backend_unreachable",
  context_consent_required: "request_rejected",
  context_source_rejected: "request_rejected",
  preference_rejected: "request_rejected",
  sandbox_violation: "request_rejected",
  provider_http_error: "provider_unavailable",
  assistant_error: "provider_unavailable",
};

/**
 * Codes that only mean "an HTTP call failed" and say nothing about *why*.
 *
 * For these the status is the specific signal, so it wins when one is present:
 * ``provider_http_error`` + 401 is an invalid key, + 429 is a rate limit. This
 * mirrors the backend's ``safe_message_for_http``. Their {@link CODE_KIND}
 * entry stays as the fallback for a failure that arrived without a status.
 */
const STATUS_FIRST_CODES: readonly string[] = ["provider_http_error", "assistant_error"];

/** Aborts are a user action, not a failure. */
const ABORT_NAMES = ["AbortError", "CanceledError"];

/** Network-level failure text produced by fetch implementations. */
const NETWORK_HINTS = [
  "failed to fetch",
  "networkerror",
  "network error",
  "load failed",
  "econnrefused",
  "err_connection",
  "fetch failed",
  "socket hang up",
  "and_unreachable",
];

export interface SafeErrorInput {
  /** HTTP status, when the failure came from a response. */
  status?: number;
  /** Backend error code (``code`` or the Phase 34 ``error`` field). */
  code?: string;
  /** Anything thrown. Used for classification only; never rendered. */
  error?: unknown;
  /** True when the user pressed Stop. */
  aborted?: boolean;
}

function statusKind(status: number): SafeErrorKind | null {
  if (status <= 0) return null;
  if (status === 401 || status === 403) return "invalid_key";
  if (status === 429) return "rate_limited";
  if (status >= 500) return "provider_unavailable";
  if (status >= 400) return "request_rejected";
  return null;
}

function readNumber(source: Record<string, unknown>, keys: string[]): number {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && /^\d{3}$/.test(value)) return Number(value);
  }
  return 0;
}

function readString(source: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value) return value;
  }
  return "";
}

/** Pull status/code/abort signals out of an arbitrary thrown value. */
function inspect(error: unknown): { status: number; code: string; aborted: boolean; text: string } {
  let status = 0;
  let code = "";
  let aborted = false;
  let text = "";

  if (typeof error === "string") {
    text = error;
  } else if (error && typeof error === "object") {
    const record = error as Record<string, unknown>;
    status = readNumber(record, ["status", "statusCode", "httpStatus"]);
    code = readString(record, ["code", "error"]);
    const name = readString(record, ["name"]);
    if (ABORT_NAMES.includes(name)) aborted = true;
    text = readString(record, ["message"]) || name;
    const body = record.body;
    if (body && typeof body === "object") {
      const nested = body as Record<string, unknown>;
      status = status || readNumber(nested, ["status", "statusCode", "httpStatus"]);
      code = code || readString(nested, ["code", "error"]);
    }
  }
  if (!status) {
    // Bridge client errors are plain ``Error("… failed: 429")`` values; the
    // status is read out but the text itself is never displayed.
    const match = /\b(4\d{2}|5\d{2})\b/.exec(text);
    if (match) status = Number(match[1]);
  }
  return { status, code, aborted, text };
}

/**
 * Classify a failure. Pure and total: it always returns a {@link SafeError}.
 */
export function classifyError(input: SafeErrorInput | unknown): SafeError {
  const normalized: SafeErrorInput =
    input && typeof input === "object" && ("error" in (input as object) || "aborted" in (input as object))
      ? (input as SafeErrorInput)
      : { error: input };

  const probe = inspect(normalized.error);
  const aborted = normalized.aborted === true || probe.aborted;
  if (aborted) {
    return { kind: "streaming_stopped", message: KIND_MESSAGE.streaming_stopped, status: 0 };
  }

  const code = (normalized.code || probe.code || "").toLowerCase();
  const status = normalized.status && normalized.status > 0 ? normalized.status : probe.status;

  if (code && CODE_KIND[code]) {
    // A generic HTTP-carrier code defers to the status (401 → invalid key,
    // 429 → rate limit); a semantic code keeps its own meaning.
    const kind = (STATUS_FIRST_CODES.includes(code) ? statusKind(status) : null) ?? CODE_KIND[code];
    return { kind, message: KIND_MESSAGE[kind], status };
  }

  const byStatus = statusKind(status);
  if (byStatus) return { kind: byStatus, message: KIND_MESSAGE[byStatus], status };

  const lowered = probe.text.toLowerCase();
  if (NETWORK_HINTS.some((hint) => lowered.includes(hint))) {
    return { kind: "backend_unreachable", message: KIND_MESSAGE.backend_unreachable, status: 0 };
  }

  // Unknown failure: the Bridge is the only thing between the UI and the
  // provider, so an unclassifiable error is reported as an unreachable Bridge
  // rather than by echoing whatever was thrown.
  return { kind: "backend_unreachable", message: KIND_MESSAGE.backend_unreachable, status };
}

/** The only string any surface may show for a failure. */
export function safeErrorMessage(input: SafeErrorInput | unknown): SafeErrorMessage {
  return classifyError(input).message;
}

/** True when the message is part of the fixed vocabulary. */
export function isSafeMessage(value: string): value is SafeErrorMessage {
  return (SAFE_MESSAGE_LIST as readonly string[]).includes(value);
}

/**
 * Patterns that must never reach the UI. Used by the security tests and as a
 * last-resort filter for status strings assembled elsewhere.
 */
export const FORBIDDEN_ERROR_PATTERNS: readonly RegExp[] = Object.freeze([
  /Traceback \(most recent call last\)/i,
  /\bat [\w$.]+ \(.*:\d+:\d+\)/,
  /File "[^"]+", line \d+/,
  /\b[A-Za-z]:\\\\?[\w\\/.-]+/, // Windows path
  /(^|\s)\/(usr|home|etc|var|opt|root)\//, // POSIX path
  /\bsk-[A-Za-z0-9_-]{8,}/,
  /Authorization\s*:/i,
  /\bBearer\s+[A-Za-z0-9._-]{8,}/i,
  /sqlite:\/\//i,
  /postgres(ql)?:\/\//i,
  /\bpassword\s*=/i,
  /<[A-Za-z]+Error\b/,
]);

/** Guard for status text that is not produced by {@link safeErrorMessage}. */
export function containsForbiddenDetail(value: string): boolean {
  return FORBIDDEN_ERROR_PATTERNS.some((pattern) => pattern.test(value));
}

/**
 * Final gate for any status line. Safe vocabulary passes through; anything
 * carrying forbidden detail is replaced, so a future caller cannot leak by
 * accident.
 */
export function sanitizeStatusText(value: string): string {
  if (!value) return "";
  if (isSafeMessage(value)) return value;
  if (containsForbiddenDetail(value)) return SAFE_MESSAGES.backendUnreachable;
  return value;
}
