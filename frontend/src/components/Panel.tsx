import { cx } from "@/lib/cx";

/** The Inner Realm surface. DESIGN.md section 5.3. */
export function Panel({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cx("hm-panel p-6", className)} {...rest}>
      {children}
    </div>
  );
}
