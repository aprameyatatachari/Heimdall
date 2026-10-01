import { Link } from "react-router-dom";

import { usePortfolios } from "@/api/portfolios";
import { useAuth } from "@/auth/useAuth";
import { Button } from "@/components/Button";
import { Panel } from "@/components/Panel";
import { Empty, Failed, Loading } from "@/components/states";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { formatDate } from "@/lib/format";

/** What each section of a portfolio is for, in one line each. */
const SECTIONS = [
  {
    to: "",
    title: "Overview",
    body: "What the portfolio is worth now, against what it cost, and how current the prices are.",
  },
  {
    to: "holdings",
    title: "Holdings",
    body: "Add, edit and import positions. An unpriced holding stays visible, with its reason.",
  },
  {
    to: "analytics",
    title: "Analytics",
    body: "Return, volatility, drawdown and tail risk over a window you choose, stored as a run.",
  },
  {
    to: "stress",
    title: "Stress test",
    body: "What a historical or hypothetical set of price changes would imply, holding by holding.",
  },
  {
    to: "signals",
    title: "Signals",
    body: "Gjallarhorn early warnings: conditions observed in the portfolio, with their thresholds.",
  },
  {
    to: "reports",
    title: "Reports",
    body: "A PDF of a stored analysis run, with the assumptions that belong to it.",
  },
] as const;

/**
 * The authenticated home.
 *
 * It answers one question — what am I watching — and gets out of the way. The
 * portfolios are listed with the facts that need no extra request, and each
 * section of the application says in a line what it is for, because the names
 * alone do not distinguish "analytics" from "stress test" to someone arriving
 * for the first time.
 *
 * No figure here is computed. Market value, risk and signals all belong to a
 * portfolio and are shown where they are measured, rather than aggregated into
 * a headline number across portfolios in different currencies.
 */
export function AppHomePage() {
  useDocumentTitle("Home");
  const { user } = useAuth();
  const portfolios = usePortfolios();

  const items = portfolios.data?.items ?? [];
  const first = items[0];

  return (
    <div className="flex flex-col gap-8">
      <div>
        <p className="hm-eyebrow mb-3">Signed in</p>
        <h1 className="font-display text-ink text-[length:var(--text-2xl)] font-light">
          Your watch
        </h1>
        <p className="text-ink-muted mt-2 text-sm">{user?.email}</p>
      </div>

      {portfolios.isPending ? (
        <Loading label="Loading your portfolios" />
      ) : portfolios.isError ? (
        <Failed error={portfolios.error} onRetry={() => void portfolios.refetch()} />
      ) : items.length === 0 ? (
        <Panel>
          <Empty
            title="Nothing under watch yet"
            body="A portfolio is a set of holdings Heimdall can value, measure, stress test and report on. Create one and the rest of the application has something to work with."
            action={
              <Link to="/app/portfolios">
                <Button>Create your first portfolio</Button>
              </Link>
            }
          />
        </Panel>
      ) : (
        <section className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="font-display text-ink text-lg font-light">
              {items.length === 1 ? "Your portfolio" : `Your ${items.length} portfolios`}
            </h2>
            <Link
              to="/app/portfolios"
              className="text-ink-muted hover:text-gold text-sm transition-colors"
            >
              See all
            </Link>
          </div>

          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((portfolio) => (
              <li key={portfolio.id}>
                <Link
                  to={`/app/portfolios/${portfolio.id}`}
                  className="hm-panel hover:border-gold flex h-full flex-col p-5 transition-colors"
                >
                  <p className="text-ink text-base">{portfolio.name}</p>
                  {portfolio.description && (
                    <p className="text-ink-muted mt-1 line-clamp-2 text-xs leading-relaxed">
                      {portfolio.description}
                    </p>
                  )}
                  <p className="text-ink-dim mt-3 text-xs">
                    {portfolio.position_count}{" "}
                    {portfolio.position_count === 1 ? "holding" : "holdings"}
                    <span aria-hidden="true"> · </span>
                    {portfolio.base_currency}
                    {portfolio.benchmark_symbol && (
                      <>
                        <span aria-hidden="true"> · </span>
                        versus {portfolio.benchmark_symbol}
                      </>
                    )}
                  </p>
                  <p className="text-ink-faint mt-auto pt-3 text-xs">
                    Created {formatDate(portfolio.created_at)}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {first && (
        <section className="flex flex-col gap-4">
          <h2 className="font-display text-ink text-lg font-light">What you can do with one</h2>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {SECTIONS.map((section) => (
              <li key={section.title}>
                <Link
                  to={`/app/portfolios/${first.id}/${section.to}`}
                  className="hm-panel hover:border-gold flex h-full flex-col p-5 transition-colors"
                >
                  <p className="text-ink text-sm font-medium">{section.title}</p>
                  <p className="text-ink-muted mt-2 text-xs leading-relaxed">{section.body}</p>
                </Link>
              </li>
            ))}
          </ul>
          <p className="text-ink-dim text-xs">
            These open {first.name}. Every portfolio has the same six sections.
          </p>
        </section>
      )}
    </div>
  );
}
