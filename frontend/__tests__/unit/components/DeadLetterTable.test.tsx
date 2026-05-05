import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DeadLetterTable } from "@/components/ops/DeadLetterTable";
import type { OpsDeadLetter } from "@/lib/api";

const baseItem: OpsDeadLetter = {
  id: "event:dead-letter-1",
  native_id: "dead-letter-1",
  kind: "event",
  organization_id: "org-1",
  run_id: null,
  status: "active",
  title: "projection failed",
  source: "os_projection_worker",
  event_type: "task.updated",
  event_id: "domain-event-1",
  reason: "handler failed",
  last_error: "ValueError",
  retry_count: 1,
  attempt_count: 1,
  created_at: "2026-05-05T00:00:00Z",
  last_seen_at: "2026-05-05T00:00:00Z",
  recovery_options: ["replay", "resolve"],
  actions: ["replay", "resolve"],
};

describe("DeadLetterTable", () => {
  it("renders backend dead-letter state and calls recovery handlers", async () => {
    const onReplay = jest.fn();
    const onResolve = jest.fn();

    render(<DeadLetterTable items={[baseItem]} onReplay={onReplay} onResolve={onResolve} />);

    expect(screen.getByText("projection failed")).toBeInTheDocument();
    expect(screen.getByText("handler failed")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /replay/i }));
    await userEvent.click(screen.getByRole("button", { name: /resolve/i }));

    expect(onReplay).toHaveBeenCalledWith(baseItem);
    expect(onResolve).toHaveBeenCalledWith(baseItem);
  });

  it("disables replay when the backend does not expose a replay action", () => {
    render(<DeadLetterTable items={[{ ...baseItem, actions: ["resolve"] }]} />);

    expect(screen.getByRole("button", { name: /replay/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /resolve/i })).toBeEnabled();
  });
});
