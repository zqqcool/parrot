import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChangePasswordPage } from "@/features/auth/ChangePasswordPage";
import { authApi } from "@/shared/api/client";
import { AuthContext, type AuthContextValue } from "@/shared/auth/AuthContext";
import type { SessionData } from "@/shared/api/types";

const session: SessionData = {
  principal: {
    tenant_id: "tenant_test",
    subject_type: "user",
    subject_id: "user_test",
    username: "admin",
    display_name: "Administrator",
    avatar_present: false,
    permissions: [],
    tenants: [],
    must_change_password: true,
    request_id: "req_test",
  },
  csrf_token: "csrf_test",
  expires_at: "2027-07-12T20:00:00Z",
  password_min_length: 14,
  default_schedule_timezone: "Asia/Shanghai",
};

afterEach(() => vi.restoreAllMocks());

describe("ChangePasswordPage", () => {
  it("uses the session password policy and redirects after a successful change", async () => {
    const user = userEvent.setup();
    const logout = vi.fn().mockResolvedValue(undefined);
    const changePassword = vi.spyOn(authApi, "changePassword").mockResolvedValue({ changed: true });
    renderPage(logout);

    expect(screen.getByLabelText("新密码")).toHaveAttribute("placeholder", "至少 14 个字符");
    await submitPassword(user);

    await waitFor(() =>
      expect(changePassword).toHaveBeenCalledWith("temporary", "new-password-123"),
    );
    expect(logout).toHaveBeenCalledOnce();
    expect(screen.getByRole("heading", { name: "登录页" })).toBeInTheDocument();
  });

  it("shows a request error without leaving the page", async () => {
    const user = userEvent.setup();
    vi.spyOn(authApi, "changePassword").mockRejectedValue(new Error("request failed"));
    renderPage(vi.fn().mockResolvedValue(undefined));

    await submitPassword(user);

    expect(await screen.findByText("修改密码失败，请稍后重试。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "修改临时密码" })).toBeInTheDocument();
  });
});

async function submitPassword(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("当前密码"), "temporary");
  await user.type(screen.getByLabelText("新密码"), "new-password-123");
  await user.type(screen.getByLabelText("确认新密码"), "new-password-123");
  await user.click(screen.getByRole("button", { name: "修改密码" }));
}

function renderPage(logout: AuthContextValue["logout"]) {
  const value: AuthContextValue = {
    session,
    loading: false,
    login: vi.fn(),
    logout,
    refreshSession: vi.fn(),
    switchTenant: vi.fn(),
    hasPermission: () => false,
  };
  render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={["/admin/change-password"]}>
        <Routes>
          <Route path="/admin/change-password" element={<ChangePasswordPage />} />
          <Route path="/admin/login" element={<h1>登录页</h1>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}
