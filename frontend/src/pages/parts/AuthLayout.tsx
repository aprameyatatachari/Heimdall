import { Link } from "react-router-dom";

import { Backdrop } from "@/components/Backdrop";
import { Disclaimer } from "@/components/Disclaimer";
import { Logo } from "@/components/Logo";
import { IMAGES } from "@/lib/images";

/**
 * The shared frame for sign-in and registration: a glass card centred over the
 * threshold-hall image. DESIGN.md sections 5.4 and 6.3.
 */
export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <div className="relative flex min-h-dvh flex-col">
      {/* The card carries its own contrast, so this backdrop takes a flat wash
          rather than a directional scrim. */}
      <Backdrop image={IMAGES.heroCitadel} scrim="flat" position="object-[58%_center]" />

      <header className="relative z-10 mx-auto flex h-16 w-full max-w-[1440px] items-center px-4 md:px-8">
        <Link to="/" className="flex items-center">
          <Logo variant="wordmark" className="h-5" />
        </Link>
      </header>

      <main
        id="main"
        className="relative z-10 flex flex-1 items-center justify-center px-4 py-10"
      >
        <div className="hm-glass w-full max-w-md p-8 sm:p-10">
          <div className="mb-8 text-center">
            <Logo variant="mark" decorative className="mx-auto mb-5 h-8" />
            <h1 className="font-display text-ink text-[length:var(--text-2xl)] leading-tight font-light">
              {title}
            </h1>
            <p className="text-ink-muted mt-2 text-sm">{subtitle}</p>
          </div>

          {children}

          <div className="text-ink-muted mt-8 text-center text-sm">{footer}</div>
        </div>
      </main>

      <footer className="relative z-10 mx-auto w-full max-w-[1440px] px-4 pb-8 md:px-8">
        <p className="hm-eyebrow text-ink-muted mb-4 text-center">
          Security · Intelligence · Discipline
        </p>
        <Disclaimer onImage className="mx-auto text-center" />
      </footer>
    </div>
  );
}
