import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SearchBar } from "./SearchBar";

describe("SearchBar", () => {
  it("returns basic search input changes immediately", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SearchBarHarness onChange={onChange} />);

    await user.type(screen.getByRole("textbox", { name: "搜索名称" }), "模型");

    expect(onChange).toHaveBeenLastCalledWith("模型");
  });

  it("reveals advanced filters only after the user asks for them", async () => {
    const user = userEvent.setup();
    render(
      <SearchBar
        advancedFilters={
          <label>
            状态
            <input />
          </label>
        }
        onChange={vi.fn()}
        placeholder="搜索"
        value=""
      />,
    );

    expect(screen.queryByRole("textbox", { name: "状态" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "更多筛选" }));
    expect(screen.getByRole("button", { name: "收起筛选" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("textbox", { name: "状态" })).toBeVisible();
  });

  it("keeps page actions on the right side of the search controls", () => {
    const { container } = render(
      <SearchBar
        actions={<button type="button">新建</button>}
        onChange={vi.fn()}
        placeholder="搜索"
        value=""
      />,
    );

    expect(screen.getByRole("button", { name: "新建" })).toBeInTheDocument();
    expect(container.querySelector(".parrot-search-bar-actions")).toBeInTheDocument();
  });
});

function SearchBarHarness({ onChange }: { onChange: (value: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <SearchBar
      onChange={(nextValue) => {
        setValue(nextValue);
        onChange(nextValue);
      }}
      placeholder="搜索名称"
      value={value}
    />
  );
}
