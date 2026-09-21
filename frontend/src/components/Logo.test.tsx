import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Logo } from "./Logo";

describe("Logo", () => {
  it("announces the Latin name, not the runes", () => {
    render(<Logo variant="wordmark" />);
    // The artwork spells HEIMDALLR in Elder Futhark. Assistive technology, search
    // engines and a copied link must all get the readable word.
    expect(screen.getByAltText("Heimdall")).toBeInTheDocument();
  });

  it("stays silent when nearby text already names the product", () => {
    render(
      <p>
        <Logo variant="mark" decorative /> Heimdall
      </p>,
    );
    expect(screen.queryByAltText("Heimdall")).not.toBeInTheDocument();
    expect(screen.getByRole("presentation", { hidden: true })).toBeInTheDocument();
  });

  it("carries intrinsic dimensions so nothing shifts while it loads", () => {
    render(<Logo variant="full" />);
    const image = screen.getByAltText("Heimdall");
    expect(image).toHaveAttribute("width", "900");
    expect(image).toHaveAttribute("height", "538");
  });

  it("uses the light artwork by default and the dark one on request", () => {
    const { rerender } = render(<Logo variant="mark" />);
    expect(screen.getByAltText("Heimdall")).toHaveAttribute("src", "/brand/mark-white.webp");

    rerender(<Logo variant="mark" tone="dark" />);
    expect(screen.getByAltText("Heimdall")).toHaveAttribute("src", "/brand/mark-black.webp");
  });
});
