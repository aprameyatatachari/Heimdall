import { cx } from "@/lib/cx";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-wrap items-end justify-between gap-4", className)}>
      <div>
        {eyebrow && <p className="hm-eyebrow mb-3">{eyebrow}</p>}
        <h1 className="font-display text-ink text-[length:var(--text-2xl)] leading-tight font-light">
          {title}
        </h1>
        {description && <p className="text-ink-muted mt-2 text-sm">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
    </div>
  );
}
