import { render, screen } from "@testing-library/react";

import { Input } from "@/components/ui";

describe("Input", () => {
  it("does not suppress autocomplete for non-password fields by default", () => {
    render(<Input aria-label="plain-input" type="text" />);

    const input = screen.getByLabelText("plain-input");
    expect(input).not.toHaveAttribute("autocomplete");
    expect(input).not.toHaveAttribute("data-lpignore");
    expect(input).not.toHaveAttribute("data-1p-ignore");
    expect(input).toHaveClass("min-h-11");
  });

  it("defaults to new-password for password fields", () => {
    render(<Input aria-label="password-input" type="password" />);

    const input = screen.getByLabelText("password-input");
    expect(input).toHaveAttribute("autocomplete", "new-password");
    expect(input).toHaveAttribute("data-lpignore", "true");
    expect(input).toHaveAttribute("data-1p-ignore", "true");
  });

  it("respects explicit autocomplete values", () => {
    render(<Input aria-label="username-input" type="email" autoComplete="username" />);

    const input = screen.getByLabelText("username-input");
    expect(input).toHaveAttribute("autocomplete", "username");
    expect(input).not.toHaveAttribute("data-lpignore");
    expect(input).not.toHaveAttribute("data-1p-ignore");
  });
});
