import { render, screen } from "@testing-library/react";

import { Input } from "@/components/ui";

describe("Input", () => {
  it("defaults to autocomplete off for non-password fields", () => {
    render(<Input aria-label="plain-input" type="text" />);

    const input = screen.getByLabelText("plain-input");
    expect(input).toHaveAttribute("autocomplete", "off");
    expect(input).toHaveAttribute("data-lpignore", "true");
    expect(input).toHaveAttribute("data-1p-ignore", "true");
  });

  it("defaults to new-password for password fields", () => {
    render(<Input aria-label="password-input" type="password" />);

    expect(screen.getByLabelText("password-input")).toHaveAttribute("autocomplete", "new-password");
  });

  it("respects explicit autocomplete values", () => {
    render(<Input aria-label="username-input" type="email" autoComplete="username" />);

    const input = screen.getByLabelText("username-input");
    expect(input).toHaveAttribute("autocomplete", "username");
    expect(input).not.toHaveAttribute("data-lpignore");
    expect(input).not.toHaveAttribute("data-1p-ignore");
  });
});
