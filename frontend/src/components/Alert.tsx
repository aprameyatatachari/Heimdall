import { cx } from "@/lib/cx";

type Tone = "error" | "caution" | "info";

const TONES: Record<Tone, { border: string; text: string; glyph: string; label: string }> = {
  error: { border: "border-negative", text: "text-negative", glyph: "▲", label: "Error" },
  caution: { border: "border-caution", text: "text-caution", glyph: "◆", label: "Attention" },
  info: { border: "border-line-strong", text: "text-ink-muted", glyph: "●", label: "Note" },
};

/**
 * A message about the state of the application.
 *
 * Tone is carried by an icon and a word as well as by colour, so it survives
 * greyscale and colour blindness. DESIGN.md section 2.2 rule 4.
 *
 * `aria-live="polite"` — never "assertive". Nothing in this product is an
 * emergency. AGENTS.md section 9.
 */
export function Alert({
  tone = "error",
  title,
  children,
  className,
}: {
  tone?: Tone;
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const style = TONES[tone];
  return (
    <div
      role="alert"
      aria-live="polite"
      className={cx("rounded-md border bg-surface px-4 py-3 text-sm", style.border, className)}
    >
      <p className={cx("flex items-start gap-2 font-medium", style.text)}>
        <span aria-hidden="true">{style.glyph}</span>
        <span className="sr-only">{style.label}: </span>
        <span>{title ?? style.label}</span>
      </p>
      <div className="text-ink-muted mt-1 ps-6">{children}</div>
    </div>
  );
}
