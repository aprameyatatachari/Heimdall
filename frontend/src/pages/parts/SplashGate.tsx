import { useCallback, useEffect, useRef, useState } from "react";

import { Logo } from "@/components/Logo";
import { cx } from "@/lib/cx";

import { useGateDissolve } from "./useGateDissolve";

const IMAGE = "/images/splash/watchman-gate.webp";
const PLACEHOLDER = "/images/splash/watchman-gate-lqip.webp";

/** One viewport of plate, one viewport of runway to dissolve it. */
const SECTION_HEIGHT = "200svh";

function ChevronUp({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className={className}>
      <path
        d="M6 14.5 12 8.5 18 14.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * The gate.
 *
 * A sticky plate over one viewport of scroll runway. Scrolling drives a
 * dissolve shader that takes the plate apart into its own weather; the landing
 * page is underneath the whole time, so nothing is hijacked, native momentum
 * and touch still work, and a keyboard user can leave with a single control.
 *
 * Progress lives in a ref and reaches the DOM as a custom property. Putting it
 * in React state would re-render the tree on every scroll frame to move one
 * number.
 */
export function SplashGate({ onEntered }: { onEntered: () => void }) {
  const sectionRef = useRef<HTMLDivElement | null>(null);
  const plateRef = useRef<HTMLDivElement | null>(null);
  const progressRef = useRef(0);
  const enteredRef = useRef(false);

  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return;
    setReducedMotion(query.matches);
    const onChange = (event: MediaQueryListEvent) => setReducedMotion(event.matches);
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, []);

  const { canvasRef, supported } = useGateDissolve(progressRef, {
    enabled: !reducedMotion,
    imageSrc: IMAGE,
    containerRef: plateRef,
  });

  useEffect(() => {
    const section = sectionRef.current;
    const plate = plateRef.current;
    if (!section || !plate) return;

    let frame = 0;

    const measure = () => {
      frame = 0;
      // Measured from the elements, never from window.innerHeight. The section
      // and the plate are sized in svh, which does not equal innerHeight on
      // every browser; mixing the two units made progress run half again too
      // fast and the reveal finish before the runway did.
      const runway = section.offsetHeight - plate.offsetHeight;
      const scrolled = -section.getBoundingClientRect().top;
      const progress = runway > 0 ? Math.min(Math.max(scrolled / runway, 0), 1) : 0;

      progressRef.current = progress;
      // Published on the document, not the plate: the page header reads the
      // same number to fade itself in as the gate goes.
      document.documentElement.style.setProperty("--gate-progress", progress.toFixed(4));

      // The plate stops taking pointer events well before it is fully gone, so
      // the last sliver of mist never blocks a click on the page beneath.
      plate.style.pointerEvents = progress > 0.65 ? "none" : "";

      if (progress >= 0.995 && !enteredRef.current) {
        enteredRef.current = true;
        document.documentElement.dataset.gate = "entered";
        onEntered();
      }
    };

    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(measure);
    };

    document.documentElement.dataset.gate = "open";
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    // Animation frames are throttled in a hidden tab, so progress stops being
    // written while the gate is out of sight. Re-measuring on return means the
    // first visible frame is the right one.
    document.addEventListener("visibilitychange", measure);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      document.removeEventListener("visibilitychange", measure);
      delete document.documentElement.dataset.gate;
      document.documentElement.style.removeProperty("--gate-progress");
    };
  }, [onEntered]);

  const enter = useCallback(() => {
    const section = sectionRef.current;
    const plate = plateRef.current;
    if (!section || !plate) return;
    const target = section.offsetTop + section.offsetHeight - plate.offsetHeight;
    window.scrollTo({ top: target, behavior: reducedMotion ? "auto" : "smooth" });
  }, [reducedMotion]);

  return (
    <div ref={sectionRef} style={{ height: SECTION_HEIGHT }} className="relative">
      <div
        ref={plateRef}
        data-static={!supported}
        className="gate-plate sticky top-0 h-svh overflow-hidden"
      >
        {/* The photograph. The shader draws it when WebGL is available; the
            <img> is what everyone else sees, and what shows while the texture
            is still decoding. */}
        <img
          src={IMAGE}
          alt=""
          width={1672}
          height={941}
          className={cx(
            "gate-photo absolute inset-0 size-full object-cover object-[58%_center]",
            supported && "opacity-0 transition-opacity duration-500",
          )}
          style={{ backgroundImage: `url(${PLACEHOLDER})`, backgroundSize: "cover" }}
          fetchPriority="high"
          decoding="async"
        />
        <canvas
          ref={canvasRef}
          aria-hidden="true"
          className={cx(
            "absolute inset-0 size-full",
            supported ? "opacity-100" : "pointer-events-none opacity-0",
          )}
        />

        {/* Readability. The centre of this photograph is bright cloud, and the
            lockup sits on top of it. */}
        <div
          aria-hidden="true"
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(60% 50% at 50% 42%, rgba(4,9,12,0.72) 0%, rgba(4,9,12,0.45) 45%, rgba(4,9,12,0) 78%)",
          }}
        />
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-40"
          style={{
            background: "linear-gradient(to bottom, rgba(4,9,12,0.85), rgba(4,9,12,0))",
          }}
        />
        <div
          aria-hidden="true"
          className="absolute inset-x-0 bottom-0 h-56"
          style={{
            background: "linear-gradient(to top, rgba(4,9,12,0.9), rgba(4,9,12,0))",
          }}
        />

        {/* Everything above the photograph fades before the plate does, so the
            type is gone by the time the mist takes the frame. */}
        <div className="gate-content relative flex h-full flex-col px-5 py-6 md:px-10 md:py-8">
          <div className="flex items-start justify-between gap-6">
            <p className="text-ink text-2xs tracking-[0.42em] uppercase">Heimdall</p>
            <p className="text-ink-muted text-2xs tracking-[0.34em] uppercase">
              <span>Vision</span>
              <span className="mx-3 md:mx-5">Security</span>
              <span>Intelligence</span>
            </p>
          </div>

          <div className="flex flex-1 flex-col items-center justify-center text-center">
            <Logo variant="full" className="h-28 md:h-40 lg:h-48" />
            <p className="text-ink mt-6 text-xs tracking-[0.62em] uppercase md:text-sm">
              See further
            </p>
            <p className="text-ink-muted mt-7 text-2xs leading-relaxed tracking-[0.26em] uppercase md:text-xs">
              A clearer tomorrow
              <br />
              through a wider horizon
            </p>
          </div>

          <div className="flex items-end justify-between gap-6">
            <p className="text-ink-dim text-2xs tracking-[0.3em] uppercase">
              <span>Watch</span>
              <span className="mx-2 md:mx-3">Protect</span>
              <span>Anticipate</span>
            </p>
            <p className="text-ink-dim text-2xs tracking-[0.3em] uppercase">MMXXVI</p>
          </div>

          {/* The control sits above the corner marks rather than between them,
              so it keeps the centre line at every width. */}
          <div className="pointer-events-none absolute inset-x-0 bottom-16 flex justify-center md:bottom-20">
            <button
              type="button"
              onClick={enter}
              className="text-ink-muted hover:text-gold pointer-events-auto group flex flex-col items-center gap-3 rounded-md px-4 py-2 transition-colors"
            >
              <span aria-hidden="true" className="bg-ink-faint h-12 w-px md:h-16" />
              <span className="border-ink-faint group-hover:border-gold flex size-11 items-center justify-center rounded-full border transition-colors">
                <ChevronUp className="size-5" />
              </span>
              <span className="text-2xs tracking-[0.3em] uppercase">
                Slide up
                <br />
                to enter
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
