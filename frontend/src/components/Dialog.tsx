import { useCallback, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { cx } from "@/lib/cx";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Shown under the title. Also becomes the dialog's description. */
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg";
  /** Set for a destructive flow, so a stray click outside cannot dismiss it. */
  dismissOnBackdrop?: boolean;
}

const SIZES = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-3xl" } as const;

/**
 * A modal dialog.
 *
 * Hand-rolled rather than using the native `<dialog>` element, which jsdom does
 * not implement — a modal this much behaviour hangs off has to be testable.
 *
 * Focus moves in on open, is trapped while open, and returns to whatever opened
 * it on close. Escape closes. The page behind cannot scroll or be reached by
 * tab. DESIGN.md section 9.
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  dismissOnBackdrop = true,
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const restoreFocusTo = useRef<HTMLElement | null>(null);
  const id = useId();

  const focusFirst = useCallback(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const first = panel.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? panel).focus();
  }, []);

  useEffect(() => {
    if (!open) return;

    restoreFocusTo.current = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    focusFirst();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const panel = panelRef.current;
      if (!panel) return;
      const focusable = [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (element) => element.offsetParent !== null || element === document.activeElement,
      );
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.body.style.overflow = previousOverflow;
      // Returning focus matters most for keyboard users: without it focus falls
      // back to the document and they restart from the top of the page.
      restoreFocusTo.current?.focus?.();
    };
  }, [open, onClose, focusFirst]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Close dialog"
        tabIndex={-1}
        onClick={dismissOnBackdrop ? onClose : undefined}
        className="bg-void/80 absolute inset-0 cursor-default backdrop-blur-sm"
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        aria-describedby={description ? `${id}-description` : undefined}
        tabIndex={-1}
        className={cx(
          "hm-panel relative flex max-h-[85vh] w-full flex-col overflow-hidden p-0",
          SIZES[size],
        )}
      >
        <div className="border-line flex items-start justify-between gap-4 border-b p-6">
          <div>
            <h2 id={`${id}-title`} className="text-ink text-lg font-medium">
              {title}
            </h2>
            {description && (
              <p id={`${id}-description`} className="text-ink-muted mt-1 text-sm">
                {description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-ink-dim hover:text-ink hover:bg-surface-2 -me-2 -mt-2 rounded-md p-2 text-sm transition-colors"
          >
            <span aria-hidden="true">✕</span>
            <span className="sr-only">Close</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">{children}</div>

        {footer && (
          <div className="border-line bg-surface flex flex-wrap justify-end gap-3 border-t p-6">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
