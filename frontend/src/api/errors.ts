/**
 * The backend's error envelope, and the client-side error types built on it.
 *
 * Every failure reaching a component is one of these. Nothing raw — no stack
 * trace, no response body, no exception message — ever reaches the UI.
 * See AGENTS.md section 7.4.
 */

export interface ApiErrorDetail {
  field?: string | null;
  message: string;
  code?: string | null;
  /** 1-based line number in an uploaded file, including the header row. */
  row?: number | null;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: ApiErrorDetail[] | null;
  request_id?: string | null;
}

/** A structured failure the backend described. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ApiErrorDetail[];
  readonly requestId: string | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details ?? [];
    this.requestId = body.request_id ?? null;
  }

  /**
   * "Not yours" and "does not exist" are the same 404 by design, and are
   * rendered identically. See AGENTS.md section 1 rule 5.
   */
  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isValidation(): boolean {
    return this.status === 422 || this.code === "validation_error";
  }

  get isRateLimited(): boolean {
    return this.status === 429 || this.code === "rate_limited";
  }

  /** Field-level messages keyed by the field path the backend reported. */
  fieldErrors(): Record<string, string> {
    const result: Record<string, string> = {};
    for (const detail of this.details) {
      if (!detail.field) continue;
      // The backend prefixes request-body paths; the form knows the leaf name.
      const key = detail.field.replace(/^body\./, "");
      if (!(key in result)) result[key] = detail.message;
    }
    return result;
  }
}

/** The request never reached Heimdall. Distinct information from a server failure. */
export class NetworkError extends Error {
  constructor(cause?: unknown) {
    super("Could not reach Heimdall. Check your connection and try again.");
    this.name = "NetworkError";
    this.cause = cause;
  }
}

const GENERIC_MESSAGE = "An unexpected error occurred. Please try again.";

/** Parse a failed response into an ApiError, whatever shape it actually has. */
export async function toApiError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = { code: "internal_error", message: GENERIC_MESSAGE };
  try {
    const parsed: unknown = await response.json();
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      "error" in parsed &&
      typeof (parsed as { error: unknown }).error === "object" &&
      (parsed as { error: unknown }).error !== null
    ) {
      const candidate = (parsed as { error: ApiErrorBody }).error;
      if (typeof candidate.message === "string" && typeof candidate.code === "string") {
        body = candidate;
      }
    }
  } catch {
    // A non-JSON error body tells the user nothing useful. Keep the generic message.
  }
  return new ApiError(response.status, body);
}

/** A message safe to show a user, for any thrown value. */
export function messageFor(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof NetworkError) return error.message;
  return GENERIC_MESSAGE;
}
