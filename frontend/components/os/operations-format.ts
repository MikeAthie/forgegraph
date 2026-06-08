const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const USD_INTEGER_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const COMPACT_NUMBER_FORMATTER = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export const formatCurrency = (value: number) => (value >= 100 ? USD_INTEGER_FORMATTER : USD_FORMATTER).format(value);

export const formatCompactNumber = (value: number) => COMPACT_NUMBER_FORMATTER.format(value);

export const formatDateTime = (value: string | null | undefined) => {
  if (!value) {
    return "Not available";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
};

export const formatDuration = (value: number | null | undefined) => {
  if (value === null || value === undefined) {
    return "Pending";
  }
  if (value < 1_000) {
    return `${value}ms`;
  }

  const seconds = Math.floor(value / 1_000);
  if (seconds < 60) {
    return `${seconds}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds}s`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
};

export const statusTone = (status: string) => {
  switch (status.toLowerCase()) {
    case "running":
    case "active":
    case "approved":
    case "succeeded":
    case "success":
    case "resolved":
    case "fresh":
      return "emerald";
    case "idle":
    case "created":
    case "claimed":
    case "queued":
    case "pending":
    case "waiting":
      return "slate";
    case "paused":
    case "waiting_for_decision":
    case "retry_scheduled":
    case "stale":
    case "rebuilding":
      return "amber";
    case "error":
    case "failed":
    case "dead_lettered":
    case "cancelled":
    case "rejected":
    case "attention":
    case "degraded":
      return "rose";
    default:
      return "slate";
  }
};
