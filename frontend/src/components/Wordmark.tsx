import { cx } from "@/lib/cx";

/**
 * The Heimdall wordmark, set in Elder Futhark runes.
 *
 * The runes are decoration. The accessible name is the Latin word, so assistive
 * technology, search engines and copy-paste all get "Heimdall" rather than
 * glyphs. DESIGN.md section 3.2 rule 3.
 *
 * The font must be self-hosted and licensed for web embedding. Until it is,
 * `--font-rune` falls back to the display serif and the mark still reads.
 */
const RUNES = "ᚺᛖᛁᛗᛞᚨᛚᛚ"; // ᚺᛖᛁᛗᛞᚨᛚᛚ

export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      role="img"
      aria-label="Heimdall"
      className={cx("hm-wordmark inline-block", className)}
    >
      <span aria-hidden="true">{RUNES}</span>
    </span>
  );
}
