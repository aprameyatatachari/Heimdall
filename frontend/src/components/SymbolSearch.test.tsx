import { screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SymbolSearch } from "@/components/SymbolSearch";
import { API, signedInHandlers } from "@/test/handlers";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const RESULTS = {
  query: "re",
  source: "fixture",
  items: [
    {
      symbol: "RELIANCE.NS",
      name: "Reliance Industries Limited",
      asset_type: "equity" as const,
      exchange: "NSE",
      currency: "INR",
    },
    {
      symbol: "NVDA",
      name: "NVIDIA Corporation",
      asset_type: "equity" as const,
      exchange: "NASDAQ",
      currency: "USD",
    },
  ],
};

beforeEach(() => {
  server.use(
    ...signedInHandlers,
    http.get(`${API}/assets/search`, () => HttpResponse.json(RESULTS)),
  );
});

/** Controlled with real state, the way the dialog holds it. */
function Harness({
  currency,
  onPick,
}: {
  currency?: string;
  onPick?: (value: string) => void;
}) {
  const [value, setValue] = useState("");
  return (
    <SymbolSearch
      value={value}
      onChange={(next) => {
        setValue(next);
        onPick?.(next);
      }}
      {...(currency ? { currency } : {})}
    />
  );
}

describe("the symbol search", () => {
  it("suggests instruments as the symbol is typed", async () => {
    const { user } = renderApp(<Harness />);

    await user.type(screen.getByRole("combobox"), "re");

    // Await an option rather than the listbox: the list is always in the DOM
    // and only hidden by a class, which jsdom does not apply, so waiting for
    // the listbox would resolve before the search had answered.
    expect(await screen.findByRole("option", { name: /RELIANCE\.NS/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /NVDA/ })).toBeInTheDocument();
  });

  it("suggests only instruments the portfolio could hold", async () => {
    // A rupee portfolio cannot hold a dollar instrument, so offering one is
    // offering a holding the API will refuse.
    const { user } = renderApp(<Harness currency="INR" />);

    await user.type(screen.getByRole("combobox"), "re");

    expect(await screen.findByRole("option", { name: /RELIANCE\.NS/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /NVDA/ })).not.toBeInTheDocument();
  });

  it("moves through the suggestions with the arrow keys", async () => {
    const { user } = renderApp(<Harness />);
    const input = screen.getByRole("combobox");

    await user.type(input, "re");
    await screen.findByRole("option", { name: /RELIANCE\.NS/ });
    await user.keyboard("{ArrowDown}");

    // The focus never leaves the input; the highlight is announced through
    // aria-activedescendant instead.
    const first = input.getAttribute("aria-activedescendant");
    expect(first).toBeTruthy();
    expect(document.getElementById(first as string)).toHaveTextContent("RELIANCE.NS");

    await user.keyboard("{ArrowDown}");
    const second = input.getAttribute("aria-activedescendant");
    expect(document.getElementById(second as string)).toHaveTextContent("NVDA");

    // And wraps, rather than stopping at the end.
    await user.keyboard("{ArrowDown}");
    expect(input.getAttribute("aria-activedescendant")).toBe(first);
  });

  it("takes the highlighted suggestion on Enter", async () => {
    const onPick = vi.fn();
    const { user } = renderApp(<Harness onPick={onPick} />);

    await user.type(screen.getByRole("combobox"), "re");
    await screen.findByRole("option", { name: /RELIANCE\.NS/ });
    await user.keyboard("{ArrowDown}{Enter}");

    expect(onPick).toHaveBeenLastCalledWith("RELIANCE.NS");
    await waitFor(() =>
      expect(screen.getByRole("combobox")).toHaveAttribute("aria-expanded", "false"),
    );
  });

  it("takes a suggestion on click", async () => {
    const onPick = vi.fn();
    const { user } = renderApp(<Harness onPick={onPick} />);

    await user.type(screen.getByRole("combobox"), "re");
    await user.click(await screen.findByRole("option", { name: /NVDA/ }));

    expect(onPick).toHaveBeenLastCalledWith("NVDA");
  });

  it("lets Enter submit when nothing is highlighted", async () => {
    // Someone typing a symbol the catalogue has never heard of must still be
    // able to add it: an incomplete catalogue is not a reason to refuse a
    // holding. So Enter only takes a suggestion when one is highlighted.
    const onPick = vi.fn();
    const { user } = renderApp(<Harness onPick={onPick} />);

    await user.type(screen.getByRole("combobox"), "re");
    await screen.findByRole("option", { name: /RELIANCE\.NS/ });
    await user.keyboard("{Enter}");

    expect(onPick).not.toHaveBeenCalledWith("RELIANCE.NS");
  });

  it("closes on Escape without changing what was typed", async () => {
    const onPick = vi.fn();
    const { user } = renderApp(<Harness onPick={onPick} />);
    const input = screen.getByRole("combobox");

    await user.type(input, "re");
    await screen.findByRole("option", { name: /RELIANCE\.NS/ });
    await user.keyboard("{Escape}");

    await waitFor(() => expect(input).toHaveAttribute("aria-expanded", "false"));
    expect(onPick).toHaveBeenLastCalledWith("re");
  });

  it("announces itself as a combobox that owns its list", async () => {
    const { user } = renderApp(<Harness />);
    const input = screen.getByRole("combobox");

    expect(input).toHaveAttribute("aria-autocomplete", "list");
    expect(input).toHaveAttribute("aria-expanded", "false");

    await user.type(input, "re");
    const option = await screen.findByRole("option", { name: /RELIANCE\.NS/ });

    expect(input).toHaveAttribute("aria-controls", option.closest("ul")?.id ?? "");
    expect(input).toHaveAttribute("aria-expanded", "true");
  });

  it("stays out of the way when the search finds nothing", async () => {
    server.use(
      http.get(`${API}/assets/search`, () =>
        HttpResponse.json({ query: "zzz", source: "fixture", items: [] }),
      ),
      ...signedInHandlers,
    );
    const { user } = renderApp(<Harness />);

    await user.type(screen.getByRole("combobox"), "zzz");

    await waitFor(() =>
      expect(screen.getByRole("combobox")).toHaveAttribute("aria-expanded", "false"),
    );
  });
});
