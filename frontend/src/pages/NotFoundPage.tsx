import { Link } from "react-router-dom";

import { Star } from "@/components/Star";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

export function NotFoundPage() {
  useDocumentTitle("Not found");
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 text-center">
      <Star className="text-ink-faint mb-6 size-8" />
      <p className="hm-eyebrow mb-4">404</p>
      <h1 className="font-display text-ink text-[length:var(--text-2xl)] font-light">
        The path stops here
      </h1>
      <p className="text-ink-muted mt-3 max-w-md text-sm">
        This page does not exist, or it is not yours to view.
      </p>
      <Link
        to="/"
        className="border-line-strong text-ink hover:border-gold hover:text-gold mt-8 inline-flex h-10 items-center rounded-md border px-5 text-sm transition-colors"
      >
        Return to the start
      </Link>
    </div>
  );
}
