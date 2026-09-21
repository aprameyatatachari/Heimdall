import { cx } from "@/lib/cx";

/**
 * The Heimdall wordmark.
 *
 * Latin letters by default. Hovering the mark turns the whole word into runes,
 * one letter after the next from left to right, and lets it settle back the
 * same way when the cursor leaves.
 *
 * No JavaScript. The cascade is eight transition delays derived from each
 * letter's index, so there is no pointer listener to throttle, no animation
 * frame to cancel, and nothing to leak when the mark unmounts.
 *
 * Two details the letterforms force:
 *
 * `HEIMDALR` is the Old Norse form and is deliberate, not a typo — the Latin
 * layer reads HEIMDALL, the runic layer reads HEIMDALR, and they correspond
 * position for position.
 *
 * The face maps rune shapes onto Latin letter positions rather than onto the
 * Unicode runic block, so the markup carries Latin letters and the font draws
 * runes. That keeps both layers real text rather than glyph codepoints nothing
 * can pronounce, and it is why the accessible name is simply "Heimdall".
 */

const LATIN = "HEIMDALL";
const RUNIC = "HEIMDALR";

export interface WordmarkProps {
  className?: string;
  /** Rendered inside a link or button that already names the destination. */
  decorative?: boolean;
}

export function Wordmark({ className, decorative = false }: WordmarkProps) {
  return (
    <span
      className={cx("hm-wordmark", className)}
      aria-hidden={decorative || undefined}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : "Heimdall"}
    >
      {LATIN.split("").map((latin, index) => (
        // `--i` is the letter's place in the cascade; the stylesheet turns it
        // into a transition delay so the word turns left to right.
        <span key={index} className="hm-wordmark__cell" style={{ ["--i" as string]: index }}>
          <span className="hm-wordmark__latin">{latin}</span>
          <span className="hm-wordmark__rune" aria-hidden="true">
            {RUNIC[index]}
          </span>
        </span>
      ))}
    </span>
  );
}
