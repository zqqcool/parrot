import { describe, expect, it } from "vitest";

import { passwordHint, passwordRules } from "./passwordPolicy";

describe("password policy helpers", () => {
  it("uses the policy supplied by the session", () => {
    expect(passwordHint(14)).toBe("至少 14 个字符");
    expect(passwordRules(14)).toEqual([
      { required: true, message: "请输入密码" },
      { min: 14, message: "密码至少 14 个字符" },
    ]);
  });

  it("keeps validation usable while the session policy is unavailable", () => {
    expect(passwordHint(undefined)).toBeUndefined();
    expect(passwordRules(undefined)).toEqual([{ required: true, message: "请输入密码" }]);
  });
});
