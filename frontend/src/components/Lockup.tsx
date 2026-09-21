import { cx } from "@/lib/cx";

import { Wordmark } from "./Wordmark";

/**
 * The mark above the wordmark, as one hover target.
 *
 * Hovering anywhere on it turns the word to runes and washes the mark gold in
 * the same direction, so the two read as one movement rather than two effects
 * that happen to fire together.
 *
 * The mark is drawn by masking its own artwork rather than by tinting the
 * image. The supplied file is white on transparent, so its alpha is the shape;
 * masking a coloured box with it gives exact control over the colour and lets
 * it animate, which no filter chain over a bitmap would do cleanly.
 *
 * Decorative throughout: the wordmark inside already carries the accessible
 * name, and a mark announced beside it would say "Heimdall" twice.
 */
export function Lockup({
  className,
  markClassName,
  wordmarkClassName,
}: {
  className?: string;
  markClassName?: string;
  wordmarkClassName?: string;
}) {
  return (
    <span className={cx("hm-lockup", className)}>
      <span className={cx("hm-lockup__mark", markClassName)} aria-hidden="true" />
      <Wordmark className={wordmarkClassName} />
    </span>
  );
}
