import { useEffect, useRef } from "react";

/**
 * Reveal an element the first time it enters the viewport.
 *
 * Content never animates out on scroll-up: a user scrolling back must not watch
 * text leave. Under a reduced-motion preference the element is simply visible
 * from the start. DESIGN.md section 7.3.
 */
export function useReveal<T extends HTMLElement>(delayMs = 0) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    if (reduced || typeof IntersectionObserver === "undefined") {
      node.dataset.revealed = "true";
      return;
    }

    node.style.transitionDelay = `${delayMs}ms`;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          (entry.target as HTMLElement).dataset.revealed = "true";
          observer.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -20% 0px", threshold: 0.1 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [delayMs]);

  return ref;
}
