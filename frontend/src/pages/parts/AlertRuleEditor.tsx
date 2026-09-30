import { useEffect, useState } from "react";

import type { AlertRuleCatalogueItem, AlertRuleUpdateRequest } from "@/api/signals";
import { ApiError } from "@/api/errors";
import type { AlertRuleResponse } from "@/api/types";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { SeverityBadge } from "@/components/Severity";
import { cx } from "@/lib/cx";
import { ruleLabel, unitDescription } from "@/lib/signalUnits";
import {
  SEVERITIES,
  toThresholds,
  validateThresholds,
  type Thresholds,
} from "@/lib/thresholds";

/**
 * One alert rule, and everything about it a user can change.
 *
 * Thresholds are entered in the rule's own unit, and the unit is written next to
 * them — a concentration threshold of 0.3 is 30% of the portfolio, and typing 30
 * there would mean thirty times the portfolio. The form says so rather than
 * silently accepting it and never firing again.
 */
export function AlertRuleEditor({
  rule,
  catalogueItem,
  onSave,
  onDelete,
  saving,
  error,
}: {
  rule: AlertRuleResponse;
  catalogueItem: AlertRuleCatalogueItem | undefined;
  onSave: (body: AlertRuleUpdateRequest) => void;
  onDelete: () => void;
  saving: boolean;
  error: unknown;
}) {
  const unit = catalogueItem?.unit ?? "";
  const [expanded, setExpanded] = useState(false);
  const [thresholds, setThresholds] = useState<Thresholds>(() =>
    toThresholds(rule.severity_configuration),
  );
  const [cooldown, setCooldown] = useState(String(rule.cooldown_hours));
  const [localError, setLocalError] = useState<string | null>(null);

  // Follow the rule: after a save, after a restore-defaults, and whenever the
  // list refetches, the form shows what is stored rather than what was typed
  // into a previous version of it.
  useEffect(() => {
    setThresholds(toThresholds(rule.severity_configuration));
    setCooldown(String(rule.cooldown_hours));
  }, [rule]);

  const serverError = error instanceof ApiError ? error.message : null;

  const save = () => {
    const checked = validateThresholds(thresholds, unit);
    if (!checked.ok) {
      setLocalError(checked.message);
      return;
    }
    const cooldownHours = Number(cooldown);
    if (!Number.isInteger(cooldownHours) || cooldownHours < 0) {
      setLocalError("Cooldown must be a whole number of hours, or zero.");
      return;
    }
    setLocalError(null);

    const configuration: Record<string, number> = {};
    for (const severity of SEVERITIES) {
      const raw = thresholds[severity].trim();
      if (raw !== "") configuration[severity] = Number(raw);
    }
    onSave({ severity_configuration: configuration, cooldown_hours: cooldownHours });
  };

  return (
    <li className="hm-panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-ink text-sm font-medium">{ruleLabel(rule.rule_type)}</h3>
          <p className="text-ink-muted mt-1 max-w-prose text-xs leading-relaxed">
            {rule.description || catalogueItem?.description}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={rule.enabled}
              onChange={(event) => onSave({ enabled: event.target.checked })}
              className="accent-gold size-4"
            />
            <span className={rule.enabled ? "text-ink" : "text-ink-dim"}>
              {rule.enabled ? "Enabled" : "Disabled"}
            </span>
          </label>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setExpanded((open) => !open)}
            aria-expanded={expanded}
          >
            {expanded ? "Close" : "Thresholds"}
            <span className="sr-only"> for {ruleLabel(rule.rule_type)}</span>
          </Button>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs">
        {SEVERITIES.map((severity) => {
          const value = rule.severity_configuration?.[severity];
          if (value === undefined) return null;
          return (
            <span key={severity} className="flex items-center gap-2">
              <SeverityBadge severity={severity} showWord={false} />
              <span className="text-ink-dim">{severity}</span>
              <span className="hm-numeric text-ink">{value}</span>
            </span>
          );
        })}
        <span className="text-ink-dim">{unitDescription(unit)}</span>
      </div>

      {expanded && (
        <div className="border-line-soft mt-5 flex flex-col gap-4 border-t pt-5">
          {(localError ?? serverError) && (
            <Alert title="This rule was not saved">{localError ?? serverError}</Alert>
          )}

          <div className="grid gap-4 sm:grid-cols-3">
            {SEVERITIES.map((severity) => (
              <label key={severity} className="flex flex-col gap-1.5">
                <span className="text-ink-muted flex items-center gap-2 text-xs capitalize">
                  <SeverityBadge severity={severity} showWord={false} />
                  {severity} threshold
                </span>
                <input
                  value={thresholds[severity]}
                  onChange={(event) =>
                    setThresholds((current) => ({ ...current, [severity]: event.target.value }))
                  }
                  inputMode="decimal"
                  aria-label={`${severity} threshold for ${ruleLabel(rule.rule_type)}`}
                  className={cx(
                    "border-line bg-surface-2 text-ink focus:border-gold h-10 rounded-md border px-3 text-sm outline-none",
                  )}
                />
              </label>
            ))}
          </div>

          <p className="text-ink-dim text-xs">
            Thresholds are in {unitDescription(unit)}, and must increase with severity.
          </p>

          <label className="flex max-w-xs flex-col gap-1.5">
            <span className="text-ink-muted text-xs">Cooldown, hours</span>
            <input
              value={cooldown}
              onChange={(event) => setCooldown(event.target.value)}
              inputMode="numeric"
              aria-label={`Cooldown hours for ${ruleLabel(rule.rule_type)}`}
              className="border-line bg-surface-2 text-ink focus:border-gold h-10 rounded-md border px-3 text-sm outline-none"
            />
            <span className="text-ink-dim text-xs leading-relaxed">
              Cooldown limits how often this rule notifies you. It never stops the rule from
              recording the current risk state, so a muted rule still keeps its signal current.
            </span>
          </label>

          <div className="flex flex-wrap gap-3">
            <Button size="sm" onClick={save} loading={saving}>
              Save thresholds
            </Button>
            <Button variant="danger" size="sm" onClick={onDelete}>
              Delete rule
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}
