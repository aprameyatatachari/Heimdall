import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { AnalysisRunRequest } from "@/api/analytics";
import { ApiError } from "@/api/errors";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Select } from "@/components/Select";
import type { RunParameters } from "@/lib/metrics";

import { CoverageWarning } from "./CoverageWarning";

/**
 * The parameters of an analysis.
 *
 * Every one of these changes what the numbers mean, so none of them is hidden
 * behind a preset. Submitting creates a **new** run: a stored run is a record of
 * what was computed and when, and quietly recomputing one under the same
 * identity would make every report that cites it wrong. AGENTS.md section 6.7.
 */
const CONFIDENCE_CHOICES = [
  { value: "0.9", label: "90%" },
  { value: "0.95", label: "95%" },
  { value: "0.99", label: "99%" },
];

const schema = z
  .object({
    start: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Choose a start date."),
    end: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Choose an end date."),
    confidence: z.string(),
    var_method: z.enum(["historical", "parametric"]),
    frequency: z.enum(["daily", "weekly", "monthly"]),
    // Entered as a percentage, because that is how a rate is quoted.
    risk_free_percent: z
      .string()
      .trim()
      .refine((value) => value === "" || Number.isFinite(Number(value)), "Enter a number.")
      .refine(
        (value) => value === "" || (Number(value) >= -50 && Number(value) <= 100),
        "Enter a rate between -50% and 100%.",
      ),
    benchmark_symbol: z.string().trim().max(32).optional(),
    minimum_observations: z
      .string()
      .trim()
      .refine(
        (value) => value === "" || (Number.isInteger(Number(value)) && Number(value) >= 2),
        "Use a whole number of at least 2.",
      )
      .refine((value) => value === "" || Number(value) <= 2520, "Use 2520 or fewer."),
  })
  .refine((values) => values.start <= values.end, {
    path: ["end"],
    message: "The end date cannot be before the start date.",
  });

type FormValues = z.input<typeof schema>;

const FIELDS: (keyof FormValues)[] = [
  "start",
  "end",
  "confidence",
  "var_method",
  "frequency",
  "risk_free_percent",
  "benchmark_symbol",
  "minimum_observations",
];

/** A year to yesterday, which is what the backend itself defaults to. */
function defaultWindow(): { start: string; end: string } {
  const end = new Date();
  const start = new Date(end.getTime() - 365 * 86_400_000);
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
}

function initialValues(previous: RunParameters | undefined): FormValues {
  const fallback = defaultWindow();
  return {
    start: previous?.start ?? fallback.start,
    end: previous?.end ?? fallback.end,
    confidence: previous?.confidence ? String(previous.confidence) : "0.95",
    var_method: previous?.varMethod === "parametric" ? "parametric" : "historical",
    frequency:
      previous?.frequency === "weekly"
        ? "weekly"
        : previous?.frequency === "monthly"
          ? "monthly"
          : "daily",
    risk_free_percent:
      previous?.annualRiskFreeRate === null || previous?.annualRiskFreeRate === undefined
        ? ""
        : String(Number((previous.annualRiskFreeRate * 100).toFixed(4))),
    benchmark_symbol: previous?.benchmarkSymbol ?? "",
    minimum_observations:
      previous?.minimumObservations === null || previous?.minimumObservations === undefined
        ? ""
        : String(previous.minimumObservations),
  };
}

export interface AnalysisControlsProps {
  /** The parameters of the run on screen, so a re-run starts from them. */
  previous?: RunParameters;
  /** The portfolio's configured benchmark, shown as the placeholder. */
  portfolioBenchmark?: string | null;
  pending: boolean;
  error: unknown;
  onRun: (body: AnalysisRunRequest) => void;
  /** For the price-coverage check on the chosen window. */
  portfolioId: string;
}

export function AnalysisControls({
  previous,
  portfolioBenchmark,
  pending,
  error,
  onRun,
  portfolioId,
}: AnalysisControlsProps) {
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: initialValues(previous),
  });

  // A failed run must come back with exactly what was entered, and selecting a
  // different run must show that run's parameters rather than the last form
  // state. Both are the same requirement: the form follows the run on screen.
  useEffect(() => {
    reset(initialValues(previous));
  }, [previous, reset]);

  useEffect(() => {
    if (!(error instanceof ApiError)) {
      setFormError(error ? "The analysis could not be started." : null);
      return;
    }
    let attached = false;
    for (const [field, message] of Object.entries(error.fieldErrors())) {
      // The backend names its own fields; map the two the form renames.
      const key = field === "annual_risk_free_rate" ? "risk_free_percent" : field;
      if (FIELDS.includes(key as keyof FormValues)) {
        setError(key as keyof FormValues, { message });
        attached = true;
      }
    }
    setFormError(attached ? null : error.message);
  }, [error, setError]);

  const submit = handleSubmit((raw) => {
    setFormError(null);
    const values = schema.parse(raw);
    onRun({
      start: values.start,
      end: values.end,
      confidence: Number(values.confidence),
      var_method: values.var_method,
      frequency: values.frequency,
      annual_risk_free_rate:
        values.risk_free_percent === "" ? 0 : Number(values.risk_free_percent) / 100,
      benchmark_symbol: values.benchmark_symbol ? values.benchmark_symbol : null,
      minimum_observations:
        values.minimum_observations === "" ? null : Number(values.minimum_observations),
    });
  });

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5">
      {formError && <Alert title="The analysis could not be run">{formError}</Alert>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field
          label="Window start"
          type="date"
          error={errors.start?.message}
          {...register("start")}
        />
        <Field
          label="Window end"
          type="date"
          error={errors.end?.message}
          {...register("end")}
        />

        <Select
          label="Confidence"
          hint="For Value at Risk and expected shortfall"
          error={errors.confidence?.message}
          {...register("confidence")}
        >
          {CONFIDENCE_CHOICES.map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </Select>

        <Select
          label="Value at Risk to highlight"
          hint="Both methods are always computed"
          error={errors.var_method?.message}
          {...register("var_method")}
        >
          <option value="historical">Historical</option>
          <option value="parametric">Parametric</option>
        </Select>

        <Select
          label="Return frequency"
          hint="Sets the annualization factor"
          error={errors.frequency?.message}
          {...register("frequency")}
        >
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </Select>

        <Field
          label="Risk-free rate"
          inputMode="decimal"
          placeholder="0"
          hint="Percent a year, for the Sharpe ratio"
          error={errors.risk_free_percent?.message}
          {...register("risk_free_percent")}
        />

        <Field
          label="Benchmark"
          placeholder={portfolioBenchmark ?? "None configured"}
          hint={
            portfolioBenchmark
              ? `Leave empty to use ${portfolioBenchmark}`
              : "Optional. A symbol to compare against"
          }
          error={errors.benchmark_symbol?.message}
          {...register("benchmark_symbol")}
        />

        <Field
          label="Minimum observations"
          inputMode="numeric"
          placeholder="30"
          hint="Below this, tail measures report unavailable"
          error={errors.minimum_observations?.message}
          {...register("minimum_observations")}
        />
      </div>

      {/* Checked against the window as it is typed, so the warning arrives
          before the run and its charts rather than as a footnote to them. */}
      <CoverageWarning
        portfolioId={portfolioId}
        start={watch("start")}
        end={watch("end")}
        what="analysis"
        autoFetch
      />

      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" loading={pending}>
          Run analysis
        </Button>
        <p className="text-ink-dim max-w-prose text-xs leading-relaxed">
          Running stores a new analysis rather than changing this one, so every figure on screen
          stays traceable to the parameters it was computed with.
        </p>
      </div>
    </form>
  );
}
