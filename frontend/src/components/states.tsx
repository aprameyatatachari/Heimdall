import { Link } from "react-router-dom";

import { ApiError, messageFor, NetworkError } from "@/api/errors";
import { cx } from "@/lib/cx";

import { Button } from "./Button";
import { Spinner } from "./Spinner";
import { Logo } from "./Logo";

/** A pending region. Announced, so a screen reader knows work is happening. */
export function Loading({
  label = "Loading",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cx("flex items-center justify-center gap-3 py-16", className)}
    >
      <Spinner className="text-gold size-5" />
      <span className="text-ink-dim text-sm">{label}</span>
    </div>
  );
}

/**
 * Nothing here yet.
 *
 * An empty state is not an error and is never styled as one: it is an
 * invitation to do the thing that fills it.
 */
export function Empty({
  title,
  body,
  action,
  className,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-col items-center px-6 py-16 text-center", className)}>
      <Logo variant="mark" decorative className="mb-5 h-7 opacity-30" />
      <h3 className="text-ink text-lg font-medium">{title}</h3>
      <p className="text-ink-muted mt-2 max-w-md text-sm leading-relaxed">{body}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

/**
 * A failed request.
 *
 * "Not yours" and "does not exist" are the same 404 and are rendered
 * identically, so the page never confirms that someone else's portfolio exists.
 * AGENTS.md section 1 rule 5.
 */
export function Failed({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const notFound = error instanceof ApiError && error.isNotFound;
  const offline = error instanceof NetworkError;

  return (
    <div
      role="alert"
      className={cx("flex flex-col items-center px-6 py-16 text-center", className)}
    >
      <h3 className="text-ink text-lg font-medium">
        {notFound ? "Not found" : offline ? "Could not reach Heimdall" : "Something went wrong"}
      </h3>
      <p className="text-ink-muted mt-2 max-w-md text-sm leading-relaxed">
        {notFound ? "This does not exist, or it is not yours to view." : messageFor(error)}
      </p>
      <div className="mt-6 flex gap-3">
        {notFound ? (
          <Link
            to="/app/portfolios"
            className="border-line-strong text-ink hover:border-gold hover:text-gold inline-flex h-10 items-center rounded-md border px-5 text-sm transition-colors"
          >
            Back to portfolios
          </Link>
        ) : (
          onRetry && (
            <Button variant="secondary" onClick={onRetry}>
              Try again
            </Button>
          )
        )}
      </div>
    </div>
  );
}
