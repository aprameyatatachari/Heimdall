/**
 * Motion inside the application, on GSAP.
 *
 * The Inner Realm's allowance is small and this file is where it is enforced:
 * a fade of 160–200ms, no translation, nothing that loops, and no figure that
 * animates because its data changed. DESIGN.md section 7.1. Anything a caller
 * could get wrong is a constant here rather than an argument.
 *
 * Every animation is registered under a `prefers-reduced-motion: no-preference`
 * query through `gsap.matchMedia()`, so under a reduced-motion preference none
 * of it is created at all — the element is simply there. Nothing is ever hidden
 * by default and revealed by an animation, which means a tween that never runs
 * costs the reader nothing.
 */

import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useRef, type RefObject } from "react";

gsap.registerPlugin(useGSAP);

export const MOTION_ALLOWED = "(prefers-reduced-motion: no-preference)";

/** `--hm-dur-fast` and the Inner Realm fade, in GSAP's seconds. */
export const DURATION_FAST = 0.16;
export const DURATION_FADE = 0.2;

/** The closest built-in curve to `--hm-ease-soft`. */
export const EASE_SOFT = "power2.out";

/** Enough to read as a sequence, capped so a long list is not a slow one. */
const STAGGER_EACH = 0.04;
const STAGGER_MAX = 0.24;

/**
 * Fade an element in once, when it mounts.
 *
 * `autoAlpha` rather than `opacity`, and the inline styles are cleared when the
 * tween ends so the stylesheet owns the element again.
 */
export function useFadeIn<T extends HTMLElement>(): RefObject<T> {
  const ref = useRef<T>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add(MOTION_ALLOWED, () => {
        gsap.from(ref.current, {
          autoAlpha: 0,
          duration: DURATION_FADE,
          ease: EASE_SOFT,
          clearProps: "opacity,visibility",
        });
      });
    },
    { scope: ref },
  );

  return ref;
}

/**
 * Fade in the items of a list as they first appear, and only then.
 *
 * `keys` are the items currently rendered, each matched to an element carrying
 * the same value in `data-enter-key`. An item is animated the first time its key
 * is seen. A refetch that returns the same items animates nothing, which matters
 * on a screen that refetches every minute: a list that faded in again each time
 * would be a loop in all but name.
 */
export function useStaggeredEntrance<T extends HTMLElement>(keys: readonly string[]) {
  const scope = useRef<T>(null);
  const seen = useRef<Set<string>>(new Set());
  const signature = keys.join("|");

  useGSAP(
    () => {
      const fresh = keys.filter((key) => !seen.current.has(key));
      for (const key of keys) seen.current.add(key);
      if (fresh.length === 0 || !scope.current) return;

      const wanted = new Set(fresh);
      const targets = Array.from(
        scope.current.querySelectorAll<HTMLElement>("[data-enter-key]"),
      ).filter((node) => wanted.has(node.dataset.enterKey ?? ""));
      if (targets.length === 0) return;

      const mm = gsap.matchMedia();
      mm.add(MOTION_ALLOWED, () => {
        gsap.from(targets, {
          autoAlpha: 0,
          duration: DURATION_FADE,
          ease: EASE_SOFT,
          stagger: { amount: Math.min(STAGGER_MAX, STAGGER_EACH * (targets.length - 1)) },
          clearProps: "opacity,visibility",
          // One tween per property per target; a second batch arriving while the
          // first is still running must not fight it.
          overwrite: "auto",
        });
      });
    },
    { scope, dependencies: [signature] },
  );

  return scope;
}

/**
 * Fade an element out, then call `done`.
 *
 * Under reduced motion `done` is called at once. Use the `contextSafe` wrapper
 * from `useGSAP` when calling this from an event handler, so the tween is
 * reverted with the component.
 */
export function fadeOut(target: Element | null, done: () => void): void {
  const allowed =
    typeof window !== "undefined" && (window.matchMedia?.(MOTION_ALLOWED).matches ?? false);
  if (!target || !allowed) {
    done();
    return;
  }
  gsap.to(target, {
    autoAlpha: 0,
    duration: DURATION_FAST,
    ease: EASE_SOFT,
    onComplete: done,
  });
}

export { gsap, useGSAP };
