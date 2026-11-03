import { useState } from "react";
import { App, Button, Input } from "antd";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/shared/auth/useAuth";
import { ParrotLogo } from "@/shared/brand";
import { toUserErrorMessage } from "@/shared/http";
import { AppIcon, type AppIconName } from "@/shared/icons";

const platformCapabilities: Array<{
  description: string;
  icon: AppIconName;
  title: string;
}> = [
  {
    icon: "RobotOne",
    title: "智能体配置与发布",
    description: "集中维护模型、Skill 与接入方式。",
  },
  {
    icon: "Permissions",
    title: "组织权限管理",
    description: "通过租户与权限边界保障协作安全。",
  },
  {
    icon: "History",
    title: "运行追踪与审计",
    description: "持续掌握每次执行的状态与轨迹。",
  },
];

export function LoginPanel() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { message } = App.useApp();

  if (auth.session) return <Navigate to="/admin" replace />;

  const handleLogin = async () => {
    setSubmitting(true);
    try {
      await auth.login(username.trim(), password);
      const target = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
      void navigate(target ?? "/admin", { replace: true });
    } catch (nextError) {
      void message.error(toUserErrorMessage(nextError, "登录失败，请稍后重试。"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="login-panel" aria-labelledby="login-title">
      <div className="login-shell">
        <aside className="login-brand-pane" aria-label="Parrot 智能体平台">
          <div className="login-brand-lockup">
            <span className="login-logo-frame">
              <ParrotLogo size="large" />
            </span>
            <span>PARROT</span>
          </div>
          <div className="login-brand-copy">
            <p>Parrot 智能体平台</p>
            <h1 id="login-title">让智能体运营更有序</h1>
            <span>统一管理配置、权限与运行状态。</span>
            <ul className="login-capability-list">
              {platformCapabilities.map((capability) => (
                <li key={capability.title}>
                  <span className="login-capability-icon">
                    <AppIcon name={capability.icon} size="md" />
                  </span>
                  <span>
                    <strong>{capability.title}</strong>
                    <small>{capability.description}</small>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div className="login-security-note">
            <AppIcon name="Lock" size="md" />
            安全会话 · 租户隔离 · 全程审计
          </div>
        </aside>
        <div className="login-form-pane">
          <div className="login-form-heading">
            <span className="login-form-kicker">管理端登录</span>
            <h2>欢迎回来</h2>
            <p>登录后继续管理你的智能体与团队。</p>
          </div>
          <label className="login-field">
            <span className="login-field-label">用户名</span>
            <Input
              size="large"
              prefix={<AppIcon name="User" size="md" />}
              value={username}
              autoComplete="username"
              placeholder="请输入用户名"
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
          <label className="login-field">
            <span className="login-field-label">密码</span>
            <Input.Password
              size="large"
              prefix={<AppIcon name="Lock" size="md" />}
              value={password}
              autoComplete="current-password"
              placeholder="请输入密码"
              onChange={(event) => setPassword(event.target.value)}
              onPressEnter={() => void handleLogin()}
            />
          </label>
          <Button
            type="primary"
            size="large"
            block
            loading={submitting}
            disabled={!username.trim() || !password}
            onClick={() => void handleLogin()}
          >
            登录
          </Button>
          <p className="login-form-note">首次登录请按提示更新临时密码。</p>
        </div>
      </div>
    </section>
  );
}
