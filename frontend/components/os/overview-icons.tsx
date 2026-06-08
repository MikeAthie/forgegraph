import { AlertTriangle, ArrowUpRight, CheckCircle2, Clock3, Dot, PauseCircle, Wallet } from "lucide-react";

export const overviewIcons = {
  stable: <CheckCircle2 className="size-4" />,
  attention: <AlertTriangle className="size-4" />,
  paused: <PauseCircle className="size-4" />,
  timing: <Clock3 className="size-4" />,
  financial: <Wallet className="size-4" />,
  external: <ArrowUpRight className="size-4" />,
  separator: <Dot className="size-4" />,
};
