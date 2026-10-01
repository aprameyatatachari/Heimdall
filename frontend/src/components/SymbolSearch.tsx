import { useEffect, useId, useRef, useState } from "react";

import { useAssetSearch } from "@/api/portfolios";
import { useDebounced } from "@/hooks/useDebounced";
import { cx } from "@/lib/cx";

/**
 * A symbol field with a real suggestion list.
 *
 * This replaced a native `<datalist>`, which looked like the simple answer and
 * was not. A datalist cannot be styled, announces inconsistently, shows the
 * option's label in some browsers and its value in others, and — the reason it
 * had to go — closes itself whenever its options change. Since the options here
 * arrive from a debounced request that fires as the user types, the list
 * collapsed on almost every keystroke.
 *
 * So this is the ARIA combobox pattern, written out: a text input that owns a
 * listbox, arrow keys to move through it, Enter to take the highlighted option,
 * Escape to close without changing anything, and `aria-activedescendant` so a
 * screen reader follows the highlight without the focus ever leaving the input.
 *
 * Typing is never blocked. The list is a suggestion, not a constraint: a symbol
 * the catalogue has not heard of can still be entered, because the catalogue
 * being incomplete is not a reason to refuse someone's holding.
 */
export interface SymbolSearchProps {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  hint?: string;
  error?: string;
  disabled?: boolean;
  required?: boolean;
  placeholder?: string;
  /** Restricts suggestions to one currency. Omit to suggest everything. */
  currency?: string;
  className?: string;
}

export function SymbolSearch({
  value,
  onChange,
  label = "Symbol",
  hint,
  error,
  disabled = false,
  required = false,
  placeholder = "AAPL",
  currency,
  className,
}: SymbolSearchProps) {
  const inputId = useId();
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  // Set while an option is being chosen, so the re-render that follows does not
  // immediately reopen the list on the new value.
  const justChose = useRef(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const query = useDebounced(value, 250);
  const search = useAssetSearch(disabled ? "" : query);

  const items = (search.data?.items ?? []).filter(
    (item) => !currency || item.currency === currency,
  );
  const showList = open && !disabled && items.length > 0;
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;

  // A click anywhere else is a dismissal. Pointerdown rather than click, so the
  // list is gone before a click on something behind it lands.
  useEffect(() => {
    if (!showList) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [showList]);

  useEffect(() => {
    if (justChose.current) {
      justChose.current = false;
      return;
    }
    setHighlighted(-1);
  }, [items.length]);

  const choose = (symbol: string) => {
    justChose.current = true;
    onChange(symbol);
    setOpen(false);
    setHighlighted(-1);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      // Closes the list and leaves the typed text alone. Only when the list is
      // open, so Escape still reaches the dialog that contains this field.
      if (showList) {
        event.stopPropagation();
        setOpen(false);
      }
      return;
    }
    if (!showList) {
      if (event.key === "ArrowDown" && items.length > 0) {
        event.preventDefault();
        setOpen(true);
        setHighlighted(0);
      }
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((index) => (index + 1) % items.length);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((index) => (index <= 0 ? items.length - 1 : index - 1));
      return;
    }
    if (event.key === "Enter" && highlighted >= 0) {
      // Only when something is highlighted: otherwise Enter submits the form,
      // which is what someone typing a symbol the catalogue lacks expects.
      event.preventDefault();
      const chosen = items[highlighted];
      if (chosen) choose(chosen.symbol);
      return;
    }
    if (event.key === "Tab" && highlighted >= 0) {
      const chosen = items[highlighted];
      if (chosen) choose(chosen.symbol);
    }
  };

  return (
    <div ref={containerRef} className={cx("relative flex flex-col gap-1.5", className)}>
      <label htmlFor={inputId} className="text-ink-muted text-sm font-medium">
        {label}
        {required && (
          <span className="text-negative ms-1" aria-hidden="true">
            *
          </span>
        )}
      </label>

      <div
        className={cx(
          "bg-surface-2 flex items-center rounded-md border px-3 transition-colors duration-[160ms]",
          "focus-within:border-gold",
          error ? "border-negative" : "border-line",
        )}
      >
        <input
          id={inputId}
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={
            showList && highlighted >= 0 ? `${listId}-${highlighted}` : undefined
          }
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          required={required}
          placeholder={placeholder}
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          className="text-ink placeholder:text-ink-faint h-10 w-full bg-transparent text-base outline-none disabled:opacity-60"
        />
        {search.isFetching && !disabled && (
          <span className="text-ink-dim text-xs" role="status">
            <span className="sr-only">Searching the instrument catalogue</span>
            <span aria-hidden="true">…</span>
          </span>
        )}
      </div>

      {/* Always rendered so a screen reader can find it by id; emptied rather
          than unmounted when there is nothing to show. */}
      <ul
        id={listId}
        role="listbox"
        aria-label="Matching instruments"
        className={cx(
          "border-line-strong bg-surface absolute top-full z-30 mt-1 max-h-64 w-full overflow-auto rounded-md border shadow-lg",
          showList ? "block" : "hidden",
        )}
      >
        {items.map((item, index) => (
          <li
            key={item.symbol}
            id={`${listId}-${index}`}
            role="option"
            aria-selected={index === highlighted}
            // Pointerdown, not click: a click fires after blur, by which point
            // the list has closed and the option is gone.
            onPointerDown={(event) => {
              event.preventDefault();
              choose(item.symbol);
            }}
            onMouseMove={() => setHighlighted(index)}
            className={cx(
              "cursor-pointer px-3 py-2 text-sm",
              index === highlighted ? "bg-surface-3 text-ink" : "text-ink-muted",
            )}
          >
            <span className="hm-numeric text-ink">{item.symbol}</span>
            {item.name && <span className="ms-2">{item.name}</span>}
            <span className="text-ink-dim ms-2 text-xs">
              {item.asset_type} · {item.currency}
              {item.exchange ? ` · ${item.exchange}` : ""}
            </span>
          </li>
        ))}
      </ul>

      {error ? (
        <p id={`${inputId}-error`} className="text-negative flex items-start gap-1.5 text-xs">
          <span aria-hidden="true">▲</span>
          <span>{error}</span>
        </p>
      ) : hint ? (
        <p id={`${inputId}-hint`} className="text-ink-dim text-xs">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
