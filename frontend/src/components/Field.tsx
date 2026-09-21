import { forwardRef, useId, useState } from "react";

import { cx } from "@/lib/cx";

export interface FieldProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  /** Shown below the field. Replaced by `error` when one is present. */
  hint?: string;
  error?: string;
  /** Rendered inside the field, before the input. Decorative. */
  icon?: React.ReactNode;
}

/**
 * A labelled text input.
 *
 * The label is always a real `<label>` — never a placeholder standing in for
 * one, which disappears the moment a user starts typing. Errors are tied to the
 * field with `aria-describedby` and announced politely, and carry an icon as
 * well as colour. DESIGN.md sections 6.2 and 9.
 */
export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, hint, error, icon, className, type = "text", required, ...rest },
  ref,
) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  const [revealed, setRevealed] = useState(false);

  const isPassword = type === "password";
  const inputType = isPassword && revealed ? "text" : type;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink-muted">
        {label}
        {required && (
          <span className="text-negative ms-1" aria-hidden="true">
            *
          </span>
        )}
      </label>

      <div
        className={cx(
          "flex items-center gap-2.5 rounded-md border bg-surface-2 px-3",
          "transition-colors duration-[160ms]",
          "focus-within:border-gold",
          error ? "border-negative" : "border-line",
        )}
      >
        {icon && (
          <span className="text-ink-dim shrink-0" aria-hidden="true">
            {icon}
          </span>
        )}
        <input
          ref={ref}
          id={id}
          type={inputType}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cx(
            "h-10 w-full bg-transparent text-base text-ink outline-none",
            "placeholder:text-ink-faint",
            className,
          )}
          {...rest}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setRevealed((value) => !value)}
            className="text-ink-dim hover:text-ink shrink-0 rounded-sm p-1 text-xs"
            aria-pressed={revealed}
          >
            {revealed ? "Hide" : "Show"}
            <span className="sr-only"> password</span>
          </button>
        )}
      </div>

      {error ? (
        <p id={`${id}-error`} className="text-negative flex items-start gap-1.5 text-xs">
          <span aria-hidden="true">▲</span>
          <span>{error}</span>
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-ink-dim text-xs">
          {hint}
        </p>
      ) : null}
    </div>
  );
});
