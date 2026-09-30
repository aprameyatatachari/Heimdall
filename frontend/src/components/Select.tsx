import { forwardRef, useId } from "react";

import { cx } from "@/lib/cx";

export interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  label: string;
  /** Shown below the control. Replaced by `error` when one is present. */
  hint?: string;
  error?: string;
}

/**
 * A labelled select.
 *
 * `forwardRef`, because these are registered with react-hook-form, and a plain
 * function component silently drops the `ref` React hands it — the field then
 * renders its first option instead of its value.
 *
 * The label is tied to the control with `htmlFor` rather than wrapping it, so
 * the accessible name is the label alone. Wrapping puts the hint inside the
 * label too, and the field ends up named "Confidence For Value at Risk and
 * expected shortfall", which is not what anyone would call it. The hint is tied
 * on separately with `aria-describedby`, where it belongs.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, children, className, ...rest },
  ref,
) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-ink-muted text-sm font-medium">
        {label}
      </label>
      <select
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cx(
          "border-line bg-surface-2 text-ink focus:border-gold h-10 rounded-md border px-3 text-sm outline-none",
          className,
        )}
        {...rest}
      >
        {children}
      </select>
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
