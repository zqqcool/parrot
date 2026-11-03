import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";

import { AdminRouteTabs } from "@/layouts/AdminRouteTabs";

function LocationProbe() {
  return <output aria-label="当前路径">{useLocation().pathname}</output>;
}

describe("AdminRouteTabs", () => {
  beforeEach(() => sessionStorage.clear());
  afterEach(() => cleanup());

  it("tracks the current route, navigates tabs, and reloads on demand", async () => {
    const user = userEvent.setup();
    const onReload = vi.fn();
    const onToggleMaximize = vi.fn();
    render(
      <MemoryRouter initialEntries={["/admin/users"]}>
        <AdminRouteTabs maximized={false} onReload={onReload} onToggleMaximize={onToggleMaximize} />
        <LocationProbe />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("tab", { name: /用户管理/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("status", { name: "当前路径" })).toHaveTextContent("/admin/users");
    await user.click(screen.getByRole("button", { name: "重新加载当前页面" }));
    expect(onReload).toHaveBeenCalledWith();
    await user.click(screen.getByRole("button", { name: "最大化内容区" }));
    expect(onToggleMaximize).toHaveBeenCalledOnce();

    fireEvent.contextMenu(screen.getByText("用户管理"));
    expect(await screen.findByRole("menuitem", { name: "固定" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "最大化" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "重新加载" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "在新窗口打开" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "关闭其他标签页" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "工作台" }));
    await waitFor(() =>
      expect(screen.getByRole("status", { name: "当前路径" })).toHaveTextContent("/admin"),
    );
  });

  it("returns to the previous admin route from the global back control", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/admin", "/admin/users"]} initialIndex={1}>
        <AdminRouteTabs maximized={false} onReload={vi.fn()} onToggleMaximize={vi.fn()} />
        <LocationProbe />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: "返回上一页" }));
    await waitFor(() =>
      expect(screen.getByRole("status", { name: "当前路径" })).toHaveTextContent("/admin"),
    );
  });
});
