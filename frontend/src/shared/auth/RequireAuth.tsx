import { Result, Spin } from "antd";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/shared/auth/useAuth";

export function RequireAuth() {
  const auth = useAuth();
  const location = useLocation();
  if (auth.loading)
    return (
      <div className="center-state">
        <Spin size="large" />
      </div>
    );
  if (!auth.session) return <Navigate to="/admin/login" replace state={{ from: location }} />;
  return <Outlet />;
}

export function RequirePermission({ permission }: { permission: string }) {
  const auth = useAuth();
  if (!auth.hasPermission(permission)) {
    return <Result status="403" title="无权访问" subTitle="当前账号的角色未包含此页面所需权限。" />;
  }
  return <Outlet />;
}

export function RequirePasswordChanged() {
  const auth = useAuth();
  const location = useLocation();
  if (
    auth.session?.principal.must_change_password &&
    location.pathname !== "/admin/change-password"
  ) {
    return <Navigate to="/admin/change-password" replace />;
  }
  return <Outlet />;
}
