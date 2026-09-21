import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { ApiError } from "@/api/errors";
import { useCreatePortfolio, useUpdatePortfolio } from "@/api/portfolios";
import type { PortfolioResponse } from "@/api/types";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Dialog } from "@/components/Dialog";
import { Field } from "@/components/Field";

// ISO 4217 codes are three letters. The backend is the authority on which of
// them it will actually accept.
const schema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Give the portfolio a name.")
    .max(120, "Use 120 characters or fewer."),
  description: z.string().trim().max(2000, "Use 2000 characters or fewer.").optional(),
  base_currency: z
    .string()
    .trim()
    .regex(/^[A-Za-z]{3}$/, "Use a three-letter currency code, such as USD.")
    .transform((value) => value.toUpperCase()),
  benchmark_symbol: z.string().trim().max(32).optional(),
});

type FormValues = z.input<typeof schema>;

const FIELDS: (keyof FormValues)[] = [
  "name",
  "description",
  "base_currency",
  "benchmark_symbol",
];

export function PortfolioFormDialog({
  open,
  onClose,
  portfolio,
}: {
  open: boolean;
  onClose: () => void;
  /** Present when editing. Absent when creating. */
  portfolio?: PortfolioResponse;
}) {
  const editing = Boolean(portfolio);
  const navigate = useNavigate();
  const create = useCreatePortfolio();
  const update = useUpdatePortfolio(portfolio?.id ?? "");
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      description: "",
      base_currency: "USD",
      benchmark_symbol: "",
    },
  });

  // Re-seed whenever the dialog opens, so editing never shows the previous
  // portfolio's values for a frame and creating never shows the last edit.
  useEffect(() => {
    if (!open) return;
    setFormError(null);
    reset({
      name: portfolio?.name ?? "",
      description: portfolio?.description ?? "",
      base_currency: portfolio?.base_currency ?? "USD",
      benchmark_symbol: portfolio?.benchmark_symbol ?? "",
    });
  }, [open, portfolio, reset]);

  const onSubmit = handleSubmit(async (raw) => {
    setFormError(null);
    const values = schema.parse(raw);
    const body = {
      name: values.name,
      description: values.description || null,
      benchmark_symbol: values.benchmark_symbol || null,
    };

    try {
      if (portfolio) {
        await update.mutateAsync(body);
        onClose();
      } else {
        // Base currency is fixed at creation: every stored amount is denominated
        // in it, so changing it later would silently reinterpret history.
        const created = await create.mutateAsync({
          ...body,
          base_currency: values.base_currency,
        });
        onClose();
        navigate(`/app/portfolios/${created.id}`);
      }
    } catch (error) {
      if (error instanceof ApiError) {
        let attached = false;
        for (const [field, message] of Object.entries(error.fieldErrors())) {
          if (FIELDS.includes(field as keyof FormValues)) {
            setError(field as keyof FormValues, { message });
            attached = true;
          }
        }
        // A detail naming a field the form does not have would otherwise vanish.
        if (!attached) setFormError(error.message);
        return;
      }
      setFormError("Could not reach Heimdall. Your changes were not saved.");
    }
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={editing ? "Edit portfolio" : "New portfolio"}
      description={
        editing
          ? "Rename it, change its description, or pick a different benchmark."
          : "Name it and choose the currency its values are reported in."
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" form="portfolio-form" loading={isSubmitting}>
            {editing ? "Save changes" : "Create portfolio"}
          </Button>
        </>
      }
    >
      <form id="portfolio-form" onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
        {formError && <Alert tone="error">{formError}</Alert>}

        <Field
          label="Name"
          placeholder="Core portfolio"
          required
          error={errors.name?.message}
          {...register("name")}
        />

        <Field
          label="Description"
          placeholder="Optional"
          error={errors.description?.message}
          {...register("description")}
        />

        <Field
          label="Base currency"
          placeholder="USD"
          required
          disabled={editing}
          hint={
            editing
              ? "Fixed after creation: every stored amount is denominated in it."
              : "Three-letter code. Every value in this portfolio is reported in it."
          }
          error={errors.base_currency?.message}
          {...register("base_currency")}
        />

        <Field
          label="Benchmark symbol"
          placeholder="SPY"
          hint="Optional. Used to compare this portfolio against a reference index."
          error={errors.benchmark_symbol?.message}
          {...register("benchmark_symbol")}
        />
      </form>
    </Dialog>
  );
}
