import { useOutletContext } from "react-router-dom";

export interface PortfolioContext {
  portfolioId: string;
  /** The portfolio's own base currency. Never a hardcoded symbol. */
  currency: string;
}

export function usePortfolioContext(): PortfolioContext {
  return useOutletContext<PortfolioContext>();
}
