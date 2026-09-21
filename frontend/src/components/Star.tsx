import { cx } from "@/lib/cx";

/**
 * The four-pointed star: the smallest unit of the brand. Long vertical axis,
 * short horizontal. DESIGN.md section 4.2.
 */
export function Star({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      className={cx("shrink-0", className)}
    >
      <path
        d="M12 0 C12.4 7.6 13.6 10.6 16.4 11.4 L24 12 L16.4 12.6 C13.6 13.4 12.4 16.4 12 24 C11.6 16.4 10.4 13.4 7.6 12.6 L0 12 L7.6 11.4 C10.4 10.6 11.6 7.6 12 0 Z"
        fill="currentColor"
      />
    </svg>
  );
}
