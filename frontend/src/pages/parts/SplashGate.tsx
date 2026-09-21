import { useCallback, useEffect, useRef, useState } from "react";

import { Logo } from "@/components/Logo";
import { cx } from "@/lib/cx";

import { useGateDissolve } from "./useGateDissolve";

const IMAGE = "/images/splash/watchman-gate.webp";
const PLACEHOLDER = "/images/splash/watchman-gate-lqip.webp";

/** Pixels of gesture that carry the reveal from closed to open. */
const TRAVEL = 900;

/** How long the control takes to finish the reveal on its own. */
const ENTER_MS = 1100;

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
 * The landing page is behind this, already at the top of the document and
 * completely still, and the plate dissolves off it in place. An earlier version
 * gave the gate a scroll runway and let the page arrive in normal flow beneath
 * it, which meant the page slid up into view as the mist cleared rather than
 * being revealed by it.
 *
 * Holding the page still costs one deliberate trade: while the gate is open the
 * document does not scroll, and the gesture drives the reveal instead. That is
 * bounded — one screen, once per session, finished by any of scroll, swipe,
 * arrow, space, Escape or the control, and released for good afterwards.
 *
 * Progress lives in a ref and reaches the DOM as a custom property. Putting it
 * in React state would re-render the tree on every frame to move one number.
 */
export function SplashGate({ onEntered }: { onEntered: () => void }) {
  const plateRef = useRef<HTMLDivElement | null>(null);
  const progressRef = useRef(0);
  const enteredRef = useRef(false);
  const animationRef = useRef(0);

  const [open, setOpen] = useState(true);
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

  const publish = useCallback((value: number) => {
    const clamped = Math.min(Math.max(value, 0), 1);
    progressRef.current = clamped;
    document.documentElement.style.setProperty("--gate-progress", clamped.toFixed(4));
    return clamped;
  }, []);

  const finish = useCallback(() => {
    if (enteredRef.current) return;
    enteredRef.current = true;
    publish(1);
    document.documentElement.dataset.gate = "entered";
    setOpen(false);
    onEntered();
  }, [onEntered, publish]);

  /** Carry the reveal the rest of the way, for anyone who would rather not scrub. */
  const enter = useCallback(() => {
    if (reducedMotion) {
      finish();
      return;
    }
    cancelAnimationFrame(animationRef.current);
    const from = progressRef.current;
    const started = performance.now();

    const step = () => {
      const elapsed = (performance.now() - started) / ENTER_MS;
      // Exponential ease-out, continuing from wherever the gesture reached.
      const eased = 1 - Math.pow(2, -10 * Math.min(elapsed, 1));
      const value = from + (1 - from) * eased;
      if (elapsed >= 1 || value >= 0.999) {
        finish();
        return;
      }
      publish(value);
      animationRef.current = requestAnimationFrame(step);
    };
    animationRef.current = requestAnimationFrame(step);
  }, [finish, publish, reducedMotion]);

  // Hold the document still and take the gesture ourselves.
  useEffect(() => {
    if (!open) return;

    const root = document.documentElement;
    const body = document.body;
    // Compensate for the scrollbar about to be removed, so the page behind does
    // not shift by its width the moment the gate opens.
    const gutter = window.innerWidth - root.clientWidth;
    const previous = { overflow: body.style.overflow, paddingRight: body.style.paddingRight };
    body.style.overflow = "hidden";
    if (gutter > 0) body.style.paddingRight = `${gutter}px`;
    root.dataset.gate = "open";
    window.scrollTo(0, 0);
    publish(0);

    const advance = (delta: number) => {
      const next = publish(progressRef.current + delta / TRAVEL);
      if (next >= 0.999) finish();
    };

    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      advance(event.deltaY);
    };

    let touchY: number | null = null;
    const onTouchStart = (event: TouchEvent) => {
      touchY = event.touches[0]?.clientY ?? null;
    };
    const onTouchMove = (event: TouchEvent) => {
      const y = event.touches[0]?.clientY;
      if (y === undefined || touchY === null) return;
      event.preventDefault();
      // Swiping up is the gesture the plate asks for, and moves the reveal on.
      advance((touchY - y) * 2.2);
      touchY = y;
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (["ArrowDown", "PageDown", " ", "Spacebar"].includes(event.key)) {
        event.preventDefault();
        advance(TRAVEL / 6);
        return;
      }
      if (event.key === "ArrowUp" || event.key === "PageUp") {
        event.preventDefault();
        advance(-TRAVEL / 6);
        return;
      }
      if (event.key === "Escape" || event.key === "End") {
        event.preventDefault();
        enter();
      }
    };

    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("keydown", onKeyDown);

    return () => {
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("keydown", onKeyDown);
      body.style.overflow = previous.overflow;
      body.style.paddingRight = previous.paddingRight;
    };
  }, [open, publish, finish, enter]);

  // The marker outlives the plate by a moment; clearing it on unmount stops a
  // stale value leaving the page header faded on every other route.
  useEffect(() => {
    return () => {
      cancelAnimationFrame(animationRef.current);
      delete document.documentElement.dataset.gate;
      document.documentElement.style.removeProperty("--gate-progress");
    };
  }, []);

  if (!open) return null;

  return (
    <div
      ref={plateRef}
      data-static={!supported}
      className="gate-plate fixed inset-0 z-50 overflow-hidden"
    >
      {/* The photograph. The shader draws it when WebGL is available; the
          <img> is what everyone else sees, and what shows while the texture is
          still decoding. */}
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
        style={{ background: "linear-gradient(to bottom, rgba(4,9,12,0.85), rgba(4,9,12,0))" }}
      />
      <div
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 h-56"
        style={{ background: "linear-gradient(to top, rgba(4,9,12,0.9), rgba(4,9,12,0))" }}
      />

      {/* Everything above the photograph fades before the plate does, so the
          type is gone by the time the mist takes the frame. */}
      <div
        className="gate-content relative flex h-full flex-col px-5 py-6 md:px-10 md:py-8"
        style={{
          paddingTop: "max(1.5rem, env(safe-area-inset-top))",
          paddingBottom: "max(1.5rem, env(safe-area-inset-bottom))",
        }}
      >
        <div className="flex items-start justify-between gap-6">
          <p className="text-ink text-2xs tracking-[0.42em] uppercase">Heimdall</p>
          <p className="text-ink-muted text-2xs hidden tracking-[0.34em] uppercase sm:block">
            <span>Vision</span>
            <span className="mx-3 md:mx-5">Security</span>
            <span>Intelligence</span>
          </p>
        </div>

        <div className="flex flex-1 flex-col items-center justify-center text-center">
          <Logo variant="full" className="h-32 md:h-40 lg:h-48" />
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
          <p className="text-ink-dim text-2xs tracking-[0.18em] uppercase sm:tracking-[0.3em]">
            <span>Watch</span>
            <span className="mx-2 md:mx-3">Protect</span>
            <span>Anticipate</span>
          </p>
          <p className="text-ink-dim text-2xs tracking-[0.3em] uppercase">MMXXVI</p>
        </div>

        {/* Above the corner marks rather than between them, so it keeps the
            centre line at every width. */}
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
  );
}
