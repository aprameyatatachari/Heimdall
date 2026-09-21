import { Link } from "react-router-dom";

import { Backdrop } from "@/components/Backdrop";
import { Disclaimer } from "@/components/Disclaimer";
import { Star } from "@/components/Star";
import { Wordmark } from "@/components/Wordmark";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useReveal } from "@/hooks/useReveal";
import { IMAGES } from "@/lib/images";

import { PublicHeader } from "./parts/PublicHeader";

const CAPABILITIES = [
  {
    title: "Unified portfolio view",
    body: "Every holding, its weight and its cost basis in one place, with the date the prices came from always in view.",
  },
  {
    title: "Advanced analytics",
    body: "Return, volatility, drawdown, Value at Risk and Expected Shortfall — each with its unit, its period and its assumptions attached.",
  },
  {
    title: "Stress testing",
    body: "Apply historical market episodes, or shocks you define, and see the estimated effect on every position.",
  },
  {
    title: "Institutional-grade reports",
    body: "A dated PDF of the analysis you are looking at, reproducible from the run it was built from.",
  },
];

function Capability({ title, body, index }: { title: string; body: string; index: number }) {
  const ref = useReveal<HTMLDivElement>(index * 80);
  return (
    <div ref={ref} className="hm-reveal border-line border-t pt-5">
      <h3 className="text-ink text-lg font-medium">{title}</h3>
      <p className="text-ink-muted mt-2 text-sm leading-relaxed">{body}</p>
    </div>
  );
}

export function LandingPage() {
  useDocumentTitle("");
  const headline = useReveal<HTMLDivElement>(0);
  const principles = useReveal<HTMLDivElement>(0);

  return (
    <>
      <PublicHeader />

      <main id="main">
        {/* Hero. The left 45% stays dark so the headline keeps its contrast —
            PROMPTS.md section 2. The background image is decorative; every word
            here is live text. */}
        <section className="relative flex min-h-[92vh] items-center overflow-hidden">
          {/* The left scrim alone is what the 8.53:1 headline measurement assumes.
              Adding the bottom scrim on top of it darkens the whole frame at short
              viewport heights and hides the photograph entirely. */}
          <Backdrop image={IMAGES.heroCitadel} scrim="left" position="object-[62%_center]" />

          <div className="relative mx-auto w-full max-w-[1440px] px-4 py-24 md:px-8 lg:px-16">
            <div ref={headline} className="hm-reveal max-w-2xl">
              <p className="hm-eyebrow mb-6">
                Markets &nbsp;|&nbsp; Risk &nbsp;|&nbsp; Clarity
              </p>

              <h1 className="font-display text-ink text-[length:var(--text-4xl)] leading-[1.05] font-light">
                See further.
                <br />
                Invest smarter.
              </h1>

              <p className="text-ink-muted mt-6 max-w-xl text-lg leading-relaxed">
                Heimdall combines portfolio analytics, risk modelling and stress testing so you
                can understand what you hold — and what it would do under pressure.
              </p>

              <div className="mt-10 flex flex-wrap items-center gap-4">
                <Link
                  to="/register"
                  className="bg-gold text-on-gold hover:bg-gold-bright inline-flex h-12 items-center rounded-md px-7 text-base font-medium transition-colors"
                >
                  Get started
                </Link>
                <Link
                  to="/methodology"
                  className="border-line-strong text-ink hover:border-gold hover:text-gold inline-flex h-12 items-center rounded-md border px-7 text-base transition-colors"
                >
                  How it works
                </Link>
              </div>
            </div>
          </div>

          <p className="hm-eyebrow absolute bottom-8 end-4 hidden md:block lg:end-16">
            Built for a clearer tomorrow
          </p>
        </section>

        {/* Capabilities */}
        <section className="border-line border-t">
          <div className="mx-auto max-w-[1440px] px-4 py-24 md:px-8 lg:px-16">
            <p className="hm-eyebrow mb-10">What Heimdall does</p>
            <div className="grid gap-10 md:grid-cols-2 lg:grid-cols-4">
              {CAPABILITIES.map((capability, index) => (
                <Capability key={capability.title} index={index} {...capability} />
              ))}
            </div>
          </div>
        </section>

        {/* Principles. This section is the product's honesty, stated plainly. */}
        <section className="border-line bg-surface border-t">
          <div className="mx-auto max-w-[1440px] px-4 py-24 md:px-8 lg:px-16">
            <div ref={principles} className="hm-reveal max-w-3xl">
              <p className="hm-eyebrow mb-6">What Heimdall will not do</p>
              <h2 className="font-display text-ink text-[length:var(--text-2xl)] leading-tight font-light">
                It does not predict, and it does not advise.
              </h2>
              <div className="text-ink-muted mt-8 grid gap-6 text-sm leading-relaxed md:grid-cols-2">
                <p>
                  Every figure here is an estimate drawn from historical data and stated model
                  assumptions. A stress test shows sensitivity to an episode that already
                  happened — not a forecast of one that will.
                </p>
                <p>
                  A metric that cannot be computed is reported as unavailable, with the reason.
                  It is never quietly shown as zero. Where prices are stale, the date they came
                  from is on the screen.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-line border-t">
        <div className="mx-auto max-w-[1440px] px-4 py-12 md:px-8 lg:px-16">
          <div className="flex flex-wrap items-center justify-between gap-6">
            <Link to="/" className="flex items-center gap-3">
              <Star className="text-gold size-4" />
              <Wordmark className="text-ink text-lg" />
            </Link>
            <nav aria-label="Footer" className="text-ink-muted flex gap-6 text-sm">
              <Link to="/methodology" className="hover:text-gold">
                Methodology
              </Link>
              <Link to="/limitations" className="hover:text-gold">
                Limitations
              </Link>
            </nav>
          </div>
          <Disclaimer className="mt-8" />
        </div>
      </footer>
    </>
  );
}
