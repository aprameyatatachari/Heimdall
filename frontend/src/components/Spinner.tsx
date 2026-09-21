import { cx } from "@/lib/cx";

/**
 * A pending indicator.
 *
 * Deliberately a plain ring rather than the logo: a brand mark spinning is the
 * kind of motion this product does not do, and the mark is wide rather than
 * square so it wobbles when rotated. Decorative — the surrounding element
 * carries the accessible status text.
 */
export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      className={cx("animate-spin", className)}
      style={{ animationDuration: "1.1s" }}
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="42 14"
        opacity="0.9"
      />
    </svg>
  );
}
