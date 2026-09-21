import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import { Star } from "@/components/Star";
import { Wordmark } from "@/components/Wordmark";
import { cx } from "@/lib/cx";

const LINKS = [
  { to: "/methodology", label: "Methodology" },
  { to: "/limitations", label: "Limitations" },
];

/**
 * Outer Realm header: transparent over the hero, gaining a surface and a
 * hairline after 80px of scroll. DESIGN.md section 8.1.
 */
export function PublicHeader() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 80);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cx(
        "fixed inset-x-0 top-0 z-40 transition-colors duration-[240ms]",
        scrolled ? "bg-abyss/95 border-line border-b backdrop-blur" : "bg-transparent",
      )}
    >
      <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-4 md:px-8 lg:px-16">
        <Link to="/" className="flex items-center gap-3">
          <Star className="text-gold size-4" />
          <Wordmark className="text-ink text-xl" />
        </Link>

        <nav aria-label="Main" className="hidden items-center gap-8 md:flex">
          {LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                cx(
                  "text-sm transition-colors",
                  isActive ? "text-gold" : "text-ink-muted hover:text-ink",
                )
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <Link
            to="/login"
            className="border-line-strong text-ink hover:border-gold hover:text-gold hidden h-9 items-center rounded-md border px-4 text-sm transition-colors sm:inline-flex"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className="bg-gold text-on-gold hover:bg-gold-bright inline-flex h-9 items-center rounded-md px-4 text-sm font-medium transition-colors"
          >
            Get started
          </Link>
        </div>
      </div>
    </header>
  );
}
