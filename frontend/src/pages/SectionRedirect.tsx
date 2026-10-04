import { Navigate } from "react-router-dom";

import { usePortfolios } from "@/api/portfolios";
import { Failed, Loading } from "@/components/states";
import { lastPortfolio, type PortfolioSection } from "@/lib/lastPortfolio";

/**
 * `/app/analytics` and its siblings.
 *
 * Each of these sections belongs to one portfolio, so the address resolves to
 * that section of the portfolio last opened, or of the first one. With no
 * portfolio at all there is nothing to analyse, and the reader is taken to the
 * place where one is created instead of being dropped back at the home page
 * with no explanation.
 */
export function SectionRedirect({ section }: { section: PortfolioSection }) {
  const portfolios = usePortfolios();

  if (portfolios.isPending) return <Loading label="Opening your portfolio" />;
  if (portfolios.isError) {
    return <Failed error={portfolios.error} onRetry={() => void portfolios.refetch()} />;
  }

  const items = portfolios.data.items;
  const remembered = lastPortfolio();
  const target = items.find((item) => item.id === remembered) ?? items[0];

  if (!target) return <Navigate to="/app/portfolios" replace />;
  return <Navigate to={`/app/portfolios/${target.id}/${section}`} replace />;
}
