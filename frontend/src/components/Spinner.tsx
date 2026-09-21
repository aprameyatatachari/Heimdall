import { cx } from "@/lib/cx";

/**
 * The loading indicator is the brand star, turning slowly.
 * Decorative: the surrounding element carries the accessible status text.
 */
export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      className={cx("animate-spin", className)}
      style={{ animationDuration: "1.6s" }}
    >
      <path
        d="M12 0 L13.2 10.8 L24 12 L13.2 13.2 L12 24 L10.8 13.2 L0 12 L10.8 10.8 Z"
        fill="currentColor"
      />
    </svg>
  );
}
