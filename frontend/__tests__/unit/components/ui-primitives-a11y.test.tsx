import { render, screen } from "@testing-library/react";

import {
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  SearchInput,
  Select,
  SelectTrigger,
  SelectValue,
} from "@/components/ui";

describe("shared UI primitive accessibility sizing", () => {
  it("uses touch-safe default and icon button sizes", () => {
    render(
      <>
        <Button>Save</Button>
        <Button size="icon" aria-label="Open menu" />
      </>,
    );

    expect(screen.getByRole("button", { name: "Save" })).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveClass("size-11");
  });

  it("uses touch-safe input and clear-search controls", () => {
    render(<SearchInput value="invoice" onChange={jest.fn()} aria-label="Search records" />);

    expect(screen.getByRole("searchbox", { name: "Search records" })).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: /clear search/i })).toHaveClass("size-11");
  });

  it("uses touch-safe select triggers", () => {
    render(
      <Select>
        <SelectTrigger aria-label="Period">
          <SelectValue placeholder="Period" />
        </SelectTrigger>
      </Select>,
    );

    expect(screen.getByRole("combobox", { name: "Period" }).className).toContain("min-h-11");
  });

  it("keeps dialog content mobile-scrollable and safe", () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Long form</DialogTitle>
        </DialogContent>
      </Dialog>,
    );

    const dialog = screen.getByRole("dialog", { name: "Long form" });
    expect(dialog.className).toContain("max-h-[calc(100dvh-2rem)]");
    expect(dialog.className).toContain("overflow-y-auto");
    expect(dialog.className).toContain("overscroll-contain");
  });
});
