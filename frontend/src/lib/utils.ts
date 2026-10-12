/**
 * Combines conditional class names into a single string.
 */
export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(" ");
}

/**
 * Formats an ISO date string into a user-friendly format.
 */
export function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  } catch {
    return dateString;
  }
}

/**
 * Formats a metric value with appropriate currency or unit symbols.
 */
export function formatMetricValue(
  value: number | string | null | undefined,
  unit?: string | null
): string {
  if (value === null || value === undefined || value === "") return "N/A";
  const num = typeof value === "number" ? value : Number(value);
  const isNumeric = !isNaN(num);

  const cleanUnit = (unit || "").trim().toLowerCase();

  if (isNumeric) {
    if (cleanUnit === "usd" || cleanUnit === "$") {
      return `$${num.toLocaleString()}`;
    }
    if (
      cleanUnit === "usd/mo" ||
      cleanUnit === "usd/month" ||
      cleanUnit === "$/mo" ||
      cleanUnit === "usd / month"
    ) {
      return `$${num.toLocaleString()} / month`;
    }
    if (cleanUnit === "customers") {
      return `${num.toLocaleString()} customers`;
    }
    if (cleanUnit === "months") {
      return `${num} months`;
    }
    if (cleanUnit === "%" || cleanUnit === "percent") {
      return `${num}%`;
    }
    if (cleanUnit === "ms" || cleanUnit === "milliseconds") {
      return `${num.toLocaleString()} ms`;
    }
    if (unit) {
      return `${num.toLocaleString()} ${unit}`;
    }
    return num.toLocaleString();
  }

  return `${value} ${unit || ""}`.trim();
}

