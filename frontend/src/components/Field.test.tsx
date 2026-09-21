import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Field } from "./Field";

describe("Field", () => {
  it("ties its label to its input", () => {
    render(<Field label="Email" />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("describes the input with its hint", () => {
    render(<Field label="Password" hint="At least 12 characters." />);
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(
      "At least 12 characters.",
    );
  });

  it("replaces the hint with the error and marks the field invalid", () => {
    render(<Field label="Password" hint="At least 12 characters." error="Too short." />);

    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Too short.");
    expect(screen.queryByText("At least 12 characters.")).not.toBeInTheDocument();
  });

  it("gives every field a unique id even when labels repeat", () => {
    render(
      <>
        <Field label="Password" />
        <Field label="Password" />
      </>,
    );
    const [first, second] = screen.getAllByLabelText("Password");
    expect(first?.id).not.toBe(second?.id);
  });

  it("lets a password be revealed and hidden again", async () => {
    const user = userEvent.setup();
    render(<Field label="Password" type="password" />);

    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: /show password/i }));
    expect(input).toHaveAttribute("type", "text");

    await user.click(screen.getByRole("button", { name: /hide password/i }));
    expect(input).toHaveAttribute("type", "password");
  });
});
