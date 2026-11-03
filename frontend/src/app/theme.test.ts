import { theme } from "antd";
import { describe, expect, it } from "vitest";

import { parrotTheme } from "@/app/theme";

describe("parrotTheme", () => {
  it("defines complete semantic palettes instead of deriving them from dark text colors", () => {
    const tokens = theme.getDesignToken(parrotTheme);

    expect(tokens.colorSuccessBg).toBe("#f0fdf4");
    expect(tokens.colorSuccessBorder).toBe("#86efac");
    expect(tokens.colorWarningBg).toBe("#fffbeb");
    expect(tokens.colorWarningBorder).toBe("#fcd34d");
    expect(tokens.colorErrorBg).toBe("#fff4f2");
    expect(tokens.colorErrorBorder).toBe("#f5b7ad");
  });
});
