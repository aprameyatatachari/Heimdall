import { StaticPage } from "./StaticPage";

export function LimitationsPage() {
  return (
    <StaticPage
      eyebrow="Limitations"
      title="What this tool cannot tell you"
      lede="Heimdall is an educational analysis tool. Knowing where its answers stop is part of using it well."
      sections={[
        {
          heading: "It does not predict",
          body: [
            "Every calculation looks backwards. A stress test applies what markets did during a past episode to what you hold today; it is a measure of sensitivity, not a statement about what will happen next.",
            "No screen in Heimdall forecasts a return, a price or a probability of loss in the future.",
          ],
        },
        {
          heading: "It does not advise",
          body: [
            "Heimdall never recommends buying, selling or holding anything, and never executes a trade. Where a signal suggests a next step, that step is analytical — reviewing a concentration, widening a period — never a transaction.",
          ],
        },
        {
          heading: "Models carry assumptions",
          body: [
            "Parametric Value at Risk assumes returns are normally distributed. Real returns are not: extreme moves happen more often than that model expects. Historical simulation avoids the assumption but can only reproduce episodes contained in the data it was given.",
            "Correlations measured over a calm period tend to understate how assets move together during a crisis. Treat any correlation figure as a description of the period it was measured over, which Heimdall always states.",
          ],
        },
      ]}
    />
  );
}
