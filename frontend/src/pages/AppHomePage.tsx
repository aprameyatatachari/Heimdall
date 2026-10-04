import { Link } from "react-router-dom";

import { usePortfolios } from "@/api/portfolios";
import { useAuth } from "@/auth/useAuth";
import { Button } from "@/components/Button";
import { Panel } from "@/components/Panel";
import { Empty, Failed, Loading } from "@/components/states";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { usePortfolioOverviews } from "@/hooks/usePortfolioOverviews";

import { HoldingsAcrossPortfolios, PortfolioCard } from "./parts/HomeOverview";

/**
 * The authenticated home.
 *
 * It answers "what am I watching, and how is it doing" without opening
 * anything: each portfolio carries its own value, profit or loss and open
 * signals, and below them everything held is added up across portfolios.
 *
 * Nothing here is converted between currencies. Portfolios in rupees and
 * portfolios in dollars are totalled separately, because there is no exchange
 * rate in this application and a sum of the two would have no unit.
 */
export function AppHomePage() {
  useDocumentTitle("Home");
  const { user } = useAuth();
  const portfolios = usePortfolios();

  const items = portfolios.data?.items ?? [];
  const overviews = usePortfolioOverviews(items);

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
        <>
          <section className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <h2 className="font-display text-ink text-lg font-light">
                {items.length === 1 ? "Your portfolio" : `Your ${items.length} portfolios`}
              </h2>
              <Link
                to="/app/portfolios"
                className="text-ink-muted hover:text-gold text-sm transition-colors"
              >
                Manage portfolios
              </Link>
            </div>

            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {overviews.map((overview) => (
                <li key={overview.portfolio.id}>
                  <PortfolioCard {...overview} />
                </li>
              ))}
            </ul>
          </section>

          <section className="flex flex-col gap-4">
            <h2 className="font-display text-ink text-lg font-light">Everything you hold</h2>
            <HoldingsAcrossPortfolios loaded={overviews} />
          </section>
        </>
      )}
    </div>
  );
}
