import { describe, expect, it } from "vitest";

import { formatDateTime, formatDuration, toDateTimeLocalValue, toIsoDateTime } from "@/shared/time";

describe("shared date-time helpers", () => {
  it("normalizes empty and invalid display values", () => {
    expect(formatDateTime(null)).toBe("-");
    expect(formatDateTime("not-a-date")).toBe("-");
  });

  it("formats durations consistently", () => {
    expect(formatDuration("2026-07-15T09:00:00Z", "2026-07-15T09:00:02.500Z")).toBe("2.5s");
    expect(formatDuration("2026-07-15T09:01:02Z", "2026-07-15T09:00:00Z")).toBe("-");
  });

  it("converts form and API date-time values through one boundary", () => {
    const local = "2026-07-15T09:30";
    const iso = toIsoDateTime(local);

    expect(toDateTimeLocalValue(iso)).toBe(local);
    expect(toDateTimeLocalValue("invalid")).toBeUndefined();
  });
});
