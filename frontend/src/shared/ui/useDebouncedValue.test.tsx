import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useDebouncedValue } from "./useDebouncedValue";

describe("useDebouncedValue", () => {
  it("publishes only the latest value after the delay", async () => {
    vi.useFakeTimers();
    const { rerender, result } = renderHook(({ value }) => useDebouncedValue(value, 300), {
      initialProps: { value: "" },
    });

    rerender({ value: "first" });
    rerender({ value: "final" });
    expect(result.current).toBe("");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(result.current).toBe("final");
    vi.useRealTimers();
  });
});
