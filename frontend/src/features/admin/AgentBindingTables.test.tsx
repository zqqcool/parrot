import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { SkillSection } from "@/features/admin/AgentBindingTables";
import type { Skill } from "@/shared/api/types";

const instructionSkill = {
  id: "skill_instruction",
  tenant_id: "tenant_test",
  name: "Reference guide",
  description: "Provides response guidance.",
  status: "published",
  version: 1,
  manifest: {},
  instructions: "Use the guide.",
} as Skill;

const executableSkill = {
  id: "skill_executable",
  tenant_id: "tenant_test",
  name: "Promotion executor",
  description: "Executes a promotion script.",
  status: "published",
  version: 1,
  manifest: { runtime: { type: "python", entrypoint: "main.py" } },
  instructions: "",
} as Skill;

describe("SkillSection", () => {
  it("clears the row loading indicator once the Skill authorization mutation settles", () => {
    const { rerender, unmount } = render(
      <MemoryRouter>
        <SkillSection
          restrictsExecutableSkills={false}
          canManage
          error={null}
          ids={[]}
          items={[instructionSkill]}
          onClearIncompatible={vi.fn()}
          onToggle={vi.fn()}
          saving
          savingSkillId={instructionSkill.id}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: "授权 Reference guide" })).toHaveClass(
      "ant-btn-loading",
    );

    rerender(
      <MemoryRouter>
        <SkillSection
          restrictsExecutableSkills={false}
          canManage
          error={null}
          ids={[instructionSkill.id]}
          items={[instructionSkill]}
          onClearIncompatible={vi.fn()}
          onToggle={vi.fn()}
          saving={false}
          savingSkillId={instructionSkill.id}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: "取消授权 Reference guide" })).not.toHaveClass(
      "ant-btn-loading",
    );
    unmount();
  });

  it("only offers instruction-only Skills to a knowledge Agent and clears legacy bindings", async () => {
    const user = userEvent.setup();
    const clearIncompatible = vi.fn();

    render(
      <MemoryRouter>
        <SkillSection
          restrictsExecutableSkills
          canManage
          error={null}
          ids={[instructionSkill.id, executableSkill.id]}
          items={[instructionSkill, executableSkill]}
          onClearIncompatible={clearIncompatible}
          onToggle={vi.fn()}
          saving={false}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Reference guide")).toBeInTheDocument();
    expect(screen.queryByText("Promotion executor")).not.toBeInTheDocument();
    expect(screen.getByText(/历史可执行 Skill 绑定/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "解除不兼容绑定" }));

    expect(clearIncompatible).toHaveBeenCalledOnce();
    expect(clearIncompatible).toHaveBeenCalledWith([instructionSkill.id]);
  });
});
