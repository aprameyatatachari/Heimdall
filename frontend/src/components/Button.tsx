import { forwardRef } from "react";

import { cx } from "@/lib/cx";

import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-gold text-on-gold hover:bg-gold-bright active:bg-gold-deep border border-transparent",
  secondary:
    "bg-transparent text-ink border border-line-strong hover:border-gold hover:text-gold",
  ghost:
    "bg-transparent text-ink-muted border border-transparent hover:text-ink hover:bg-surface-2",
  danger: "bg-transparent text-negative border border-negative hover:bg-negative-dim",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-10 px-5 text-sm gap-2",
  lg: "h-12 px-7 text-base gap-2.5",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** Disables the button and shows a spinner. The label stays for screen readers. */
  loading?: boolean;
  fullWidth?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    loading = false,
    fullWidth,
    className,
    children,
    disabled,
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      // A pending action stays disabled until the request settles, so a double
      // press cannot submit twice. AGENTS.md section 6.3.
      disabled={disabled ?? loading}
      aria-busy={loading || undefined}
      className={cx(
        "inline-flex items-center justify-center rounded-md font-medium tracking-wide",
        "transition-colors duration-[160ms] ease-[var(--ease-soft)]",
        "disabled:cursor-not-allowed disabled:opacity-45",
        VARIANTS[variant],
        SIZES[size],
        fullWidth && "w-full",
        className,
      )}
      {...rest}
    >
      {loading && <Spinner className="size-4" />}
      {children}
    </button>
  );
});
