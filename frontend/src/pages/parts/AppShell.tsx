import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/auth/useAuth";
import { Disclaimer } from "@/components/Disclaimer";
import { Wordmark } from "@/components/Wordmark";
import { cx } from "@/lib/cx";

// Phase 9 onward fills these in. They are listed now so the shell's navigation
// is real rather than a placeholder that has to be rebuilt later.
const NAV = [
  { to: "/app/portfolios", label: "Portfolios" },
  { to: "/app/analytics", label: "Analytics" },
  { to: "/app/stress", label: "Stress test" },
  { to: "/app/signals", label: "Signals" },
  { to: "/app/reports", label: "Reports" },
];

function navClass({ isActive }: { isActive: boolean }): string {
  return cx(
    "rounded-md px-3 py-2 text-sm transition-colors",
    isActive ? "text-gold bg-surface-2" : "text-ink-muted hover:text-ink hover:bg-surface-2",
  );
}

export function AppShell() {
  const { user, signOut } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement | null>(null);

  // A route change closes any open menu, so navigating never leaves a panel
  // hanging over the new page.
  useEffect(() => {
    setMenuOpen(false);
    setAccountOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!accountOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!accountRef.current?.contains(event.target as Node)) setAccountOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAccountOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [accountOpen]);

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-line bg-abyss/95 sticky top-0 z-40 border-b backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-4 px-4 md:px-8 lg:px-16">
          <Link to="/app" className="flex shrink-0 items-center">
            <Wordmark className="text-ink text-sm" />
          </Link>

          <nav aria-label="Main" className="hidden flex-1 items-center gap-1 lg:flex">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} className={navClass}>
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ms-auto flex items-center gap-2">
            <div className="relative" ref={accountRef}>
              <button
                type="button"
                onClick={() => setAccountOpen((open) => !open)}
                aria-expanded={accountOpen}
                aria-haspopup="menu"
                className="border-line-strong text-ink-muted hover:text-ink hover:border-gold flex h-9 items-center gap-2 rounded-md border px-3 text-sm transition-colors"
              >
                <span className="max-w-[16ch] truncate">{user?.email ?? "Account"}</span>
                <span aria-hidden="true" className="text-2xs">
                  ▾
                </span>
              </button>

              {accountOpen && (
                <div role="menu" className="hm-panel absolute end-0 top-11 z-50 w-56 p-2">
                  <p className="text-ink-dim truncate px-3 py-2 text-xs">{user?.email}</p>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => void signOut()}
                    className="text-ink-muted hover:bg-surface-2 hover:text-ink w-full rounded-md px-3 py-2 text-start text-sm transition-colors"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => setMenuOpen((open) => !open)}
              aria-expanded={menuOpen}
              aria-controls="app-mobile-nav"
              className="border-line-strong text-ink-muted hover:text-ink flex h-9 items-center rounded-md border px-3 text-sm lg:hidden"
            >
              Menu
            </button>
          </div>
        </div>

        {menuOpen && (
          <nav
            id="app-mobile-nav"
            aria-label="Main"
            className="border-line bg-abyss border-t px-4 py-3 lg:hidden"
          >
            <ul className="flex flex-col gap-1">
              {NAV.map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to} className={navClass}>
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </header>

      <main id="main" className="flex-1">
        <div className="mx-auto max-w-[1440px] px-4 py-10 md:px-8 lg:px-16">
          <Outlet />
        </div>
      </main>

      <footer className="border-line border-t">
        <div className="mx-auto max-w-[1440px] px-4 py-8 md:px-8 lg:px-16">
          <Disclaimer />
        </div>
      </footer>
    </div>
  );
}
