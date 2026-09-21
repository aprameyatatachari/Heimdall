import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Wordmark } from "./Wordmark";

/**
 * The transmutation itself is pure CSS `:hover`, which jsdom has no engine to
 * evaluate. What these pin is the structure the effect depends on — if a cell
 * ever stops carrying both alphabets, or they stop corresponding position for
 * position, the hover reveals the wrong rune and no type checker would notice.
 */
describe("Wordmark", () => {
  it("reads in Latin letters by default", () => {
    const { container } = render(<Wordmark />);
    const latin = [...container.querySelectorAll(".hm-wordmark__latin")]
      .map((node) => node.textContent)
      .join("");
    expect(latin).toBe("HEIMDALL");
  });

  it("announces the product once, in Latin", () => {
    render(<Wordmark />);
    expect(screen.getAllByRole("img", { name: "Heimdall" })).toHaveLength(1);
  });

  it("stays silent when its link already names the destination", () => {
    render(<Wordmark decorative />);
    expect(screen.queryByRole("img", { name: "Heimdall" })).not.toBeInTheDocument();
  });

  it("pairs every Latin letter with the rune that replaces it", () => {
    const { container } = render(<Wordmark />);
    const cells = [...container.querySelectorAll(".hm-wordmark__cell")];

    expect(cells).toHaveLength(8);
    const latin = cells
      .map((c) => c.querySelector(".hm-wordmark__latin")?.textContent)
      .join("");
    const runic = cells.map((c) => c.querySelector(".hm-wordmark__rune")?.textContent).join("");

    expect(latin).toBe("HEIMDALL");
    // HEIMDALR, not HEIMDALL: the runic layer carries the Old Norse form, and
    // the face draws runes for these Latin letters rather than mapping the
    // Unicode runic block.
    expect(runic).toBe("HEIMDALR");
  });

  it("hides the runic layer from the reader", () => {
    const { container } = render(<Wordmark />);
    for (const rune of container.querySelectorAll(".hm-wordmark__rune")) {
      expect(rune).toHaveAttribute("aria-hidden", "true");
    }
    // The runes must not reach the accessible name; a reader hearing
    // "HEIMDALLHEIMDALR" would be worse off than one hearing nothing.
    expect(screen.getByRole("img").textContent).not.toContain("HEIMDALR");
  });

  it("gives each letter its own hover target", () => {
    const { container } = render(<Wordmark />);
    // One cell per letter is what lets the word transmute letter by letter
    // rather than all at once.
    expect(container.querySelectorAll(".hm-wordmark__cell")).toHaveLength(8);
  });
});
