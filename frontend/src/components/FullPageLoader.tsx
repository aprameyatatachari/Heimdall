import { Spinner } from "./Spinner";

/** A whole-page pending state with an announced status. */
export function FullPageLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div
      className="flex min-h-dvh flex-col items-center justify-center gap-4"
      role="status"
      aria-live="polite"
    >
      <Spinner className="text-gold size-8" />
      <p className="text-ink-dim text-sm">{label}</p>
    </div>
  );
}
