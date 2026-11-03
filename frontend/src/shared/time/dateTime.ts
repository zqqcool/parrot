const DATE_TIME_LOCALE = "zh-CN";
const EMPTY_TIME_VALUE = "-";

export function formatDateTime(value?: string | number | Date | null): string {
  const date = parseDate(value);
  return date ? date.toLocaleString(DATE_TIME_LOCALE, { hour12: false }) : EMPTY_TIME_VALUE;
}

export function formatDuration(start: string | number | Date, end: string | number | Date): string {
  const startDate = parseDate(start);
  const endDate = parseDate(end);
  if (!startDate || !endDate) return EMPTY_TIME_VALUE;

  const milliseconds = endDate.getTime() - startDate.getTime();
  if (milliseconds < 0) return EMPTY_TIME_VALUE;
  if (milliseconds < 1_000) return `${milliseconds}ms`;
  if (milliseconds < 60_000) return `${(milliseconds / 1_000).toFixed(1)}s`;
  return `${Math.floor(milliseconds / 60_000)}m ${Math.floor((milliseconds % 60_000) / 1_000)}s`;
}

export function toIsoDateTime(value: string): string {
  const date = parseDate(value);
  if (!date) throw new RangeError("Invalid date-time value");
  return date.toISOString();
}

export function toDateTimeLocalValue(value?: string | null): string | undefined {
  const date = parseDate(value);
  if (!date) return undefined;
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function parseDate(value?: string | number | Date | null): Date | null {
  if (value === undefined || value === null || value === "") return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}
