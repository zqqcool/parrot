import { afterEach, describe, expect, it, vi } from "vitest";

import { saveDownloadedFile } from "@/shared/downloads";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("saveDownloadedFile", () => {
  it("uses a temporary object URL and releases it after the browser click", () => {
    vi.useFakeTimers();
    const createObjectURL = vi.fn(() => "blob:knowledge-source");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);

    saveDownloadedFile({ blob: new Blob(["knowledge"]), filename: "guide.txt" });

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(document.querySelector('a[download="guide.txt"]')).toBeNull();
    vi.runAllTimers();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:knowledge-source");
  });
});
