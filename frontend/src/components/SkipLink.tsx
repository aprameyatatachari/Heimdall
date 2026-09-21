/** The first tabbable element on every page. DESIGN.md section 9. */
export function SkipLink() {
  return (
    <a
      href="#main"
      className="bg-gold text-on-gold sr-only rounded-md px-4 py-2 text-sm font-medium focus:not-sr-only focus:absolute focus:start-4 focus:top-4 focus:z-50"
    >
      Skip to content
    </a>
  );
}
