import { StaticPage } from "./StaticPage";

export function MethodologyPage() {
  return (
    <StaticPage
      eyebrow="Methodology"
      title="How the numbers are produced"
      lede="Every figure Heimdall shows is computed from daily adjusted closing prices using stated, conventional methods. Nothing is a forecast."
      sections={[
        {
          heading: "Returns",
          body: [
            "Daily returns are simple returns on adjusted closing prices, so dividends and splits are already reflected. Annualized figures use 252 trading periods per year and say so wherever they appear.",
            "Portfolio returns are reconstructed by applying the portfolio's current weights to each asset's historical returns. This is an approximation: it assumes the portfolio was held in today's proportions throughout the period, which it was not. Heimdall states this caveat alongside every figure that depends on it.",
          ],
        },
        {
          heading: "Risk",
          body: [
            "Volatility is the standard deviation of daily returns, reported both daily and annualized. Value at Risk is reported at 95% confidence by two methods — historical simulation and a parametric normal estimate — and is expressed as a positive loss amount.",
            "Value at Risk is an estimate of a loss threshold over a stated horizon at a stated confidence. It is not a maximum possible loss, and Heimdall never presents it as one. Expected Shortfall reports the average loss in the cases that exceed that threshold.",
          ],
        },
        {
          heading: "Missing data",
          body: [
            "A metric that cannot be computed is returned as unavailable together with the reason, and the analysis run that contains it is marked partial. A missing value is never substituted with zero, an empty list or a placeholder.",
            "Where prices could not be obtained for a holding, that holding is listed as excluded rather than quietly dropped or treated as unaffected.",
          ],
        },
      ]}
    />
  );
}
