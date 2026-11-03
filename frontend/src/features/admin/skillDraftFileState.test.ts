import { describe, expect, it } from "vitest";

import {
  updateOpenedChecksums,
  withoutDirtyPathPrefix,
} from "@/features/admin/skillDraftFileState";

describe("skill draft file state", () => {
  it("updates all opened file checksums without discarding unsaved content", () => {
    const files = updateOpenedChecksums(
      {
        "main.py": {
          path: "main.py",
          content: "print('unsaved')",
          checksum: "old",
          editable: true,
          kind: "file",
          size_bytes: 16,
        },
        "SKILL.md": {
          path: "SKILL.md",
          content: "# Instructions",
          checksum: "old",
          editable: true,
          kind: "file",
          size_bytes: 14,
        },
      },
      "new",
    );

    expect(files["main.py"]).toMatchObject({ content: "print('unsaved')", checksum: "new" });
    expect(files["SKILL.md"]).toMatchObject({ content: "# Instructions", checksum: "new" });
  });

  it("removes a deleted entry and its descendants from the dirty set", () => {
    expect(withoutDirtyPathPrefix(new Set(["main.py", "docs/a.md", "docs/b.md"]), "docs")).toEqual(
      new Set(["main.py"]),
    );
  });
});
