import { useEffect, useId, useState } from "react";

import { ApiError } from "@/api/errors";
import { useAssetSearch, useCreatePosition, useUpdatePosition } from "@/api/portfolios";
import type { PositionResponse } from "@/api/types";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Dialog } from "@/components/Dialog";
import { Field } from "@/components/Field";
import { useDebounced } from "@/hooks/useDebounced";

/** A decimal the backend will accept: digits, one optional point, no sign. */
const DECIMAL = /^\d+(\.\d+)?$/;

export function PositionFormDialog({
  open,
  onClose,
  portfolioId,
  position,
}: {
  open: boolean;
  onClose: () => void;
  portfolioId: string;
  /** Present when editing an existing holding. */
  position?: PositionResponse;
}) {
  const editing = Boolean(position);
  const create = useCreatePosition(portfolioId);
  const update = useUpdatePosition(portfolioId);
  const listId = useId();

  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [averageCost, setAverageCost] = useState("");
  const [purchaseDate, setPurchaseDate] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  // The search fires on a settled value, not on every keystroke.
  const debouncedSymbol = useDebounced(symbol, 250);
  const search = useAssetSearch(editing ? "" : debouncedSymbol);

  useEffect(() => {
    if (!open) return;
    setErrors({});
    setFormError(null);
    setSymbol(position?.asset.symbol ?? "");
    setQuantity(position?.quantity ?? "");
    setAverageCost(position?.average_cost ?? "");
    setPurchaseDate(position?.purchase_date ?? "");
  }, [open, position]);

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!editing && !symbol.trim()) next.symbol = "Enter a symbol.";
    // Quantity and cost stay strings all the way to the server: parsing them
    // into JavaScript numbers is how a holding loses its last decimal places.
    if (!DECIMAL.test(quantity.trim()))
      next.quantity = "Enter a positive number, such as 12.5.";
    if (!DECIMAL.test(averageCost.trim())) {
      next.average_cost = "Enter a positive amount, such as 185.20.";
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    if (!validate()) return;

    try {
      if (position) {
        await update.mutateAsync({
          positionId: position.id,
          body: {
            quantity: quantity.trim(),
            average_cost: averageCost.trim(),
            purchase_date: purchaseDate || null,
          },
        });
      } else {
        await create.mutateAsync({
          symbol: symbol.trim().toUpperCase(),
          quantity: quantity.trim(),
          average_cost: averageCost.trim(),
          purchase_date: purchaseDate || null,
          // Merging keeps one row per asset, which is what the holdings table
          // and every weight calculation assume.
          on_duplicate: "merge",
        });
      }
      onClose();
    } catch (error) {
      if (error instanceof ApiError) {
        const fields = error.fieldErrors();
        if (Object.keys(fields).length > 0) setErrors(fields);
        else setFormError(error.message);
        return;
      }
      setFormError("Could not reach Heimdall. Your holding was not saved.");
    }
  }

  const pending = create.isPending || update.isPending;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={editing ? `Edit ${position?.asset.symbol}` : "Add a holding"}
      description={
        editing
          ? "Quantity and average cost are yours to correct at any time."
          : "Heimdall stores what you hold and what it cost you. Prices come from the provider."
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" form="position-form" loading={pending}>
            {editing ? "Save changes" : "Add holding"}
          </Button>
        </>
      }
    >
      <form id="position-form" onSubmit={submit} noValidate className="flex flex-col gap-5">
        {formError && <Alert tone="error">{formError}</Alert>}

        <div>
          <Field
            label="Symbol"
            required
            disabled={editing}
            list={editing ? undefined : listId}
            autoComplete="off"
            placeholder="AAPL"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value)}
            error={errors.symbol}
            hint={
              editing
                ? "The instrument cannot be changed. Remove the holding and add another instead."
                : "Start typing to search the instrument catalogue."
            }
          />
          {!editing && (
            <datalist id={listId}>
              {(search.data?.items ?? []).map((item) => (
                <option key={item.symbol} value={item.symbol}>
                  {item.name ?? item.symbol} · {item.asset_type} · {item.currency}
                </option>
              ))}
            </datalist>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Quantity"
            required
            inputMode="decimal"
            placeholder="100"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            error={errors.quantity}
          />
          <Field
            label="Average cost"
            required
            inputMode="decimal"
            placeholder="185.20"
            value={averageCost}
            onChange={(event) => setAverageCost(event.target.value)}
            error={errors.average_cost}
            hint="Per unit, in the portfolio's currency."
          />
        </div>

        <Field
          label="Purchase date"
          type="date"
          value={purchaseDate}
          onChange={(event) => setPurchaseDate(event.target.value)}
          error={errors.purchase_date}
          hint="Optional. Recorded for your reference; analysis uses the period you select."
        />
      </form>
    </Dialog>
  );
}
