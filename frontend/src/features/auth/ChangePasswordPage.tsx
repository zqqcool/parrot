import { useState } from "react";
import { App, Button, Form, Input } from "antd";
import { useNavigate } from "react-router-dom";

import { authApi } from "@/shared/api/client";
import { useAuth } from "@/shared/auth/useAuth";
import { passwordHint, passwordRules } from "@/shared/auth/passwordPolicy";
import { toUserErrorMessage } from "@/shared/http";

type PasswordForm = { currentPassword: string; newPassword: string; confirmPassword: string };

export function ChangePasswordPage() {
  const auth = useAuth();
  const passwordMinimumLength = auth.session?.password_min_length;
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const { message } = App.useApp();
  const submit = async (values: PasswordForm) => {
    setLoading(true);
    try {
      await authApi.changePassword(values.currentPassword, values.newPassword);
      try {
        await auth.logout();
      } catch {
        /* The password endpoint already revoked the session. */
      }
      void navigate("/admin/login", { replace: true });
    } catch (nextError) {
      void message.error(toUserErrorMessage(nextError, "修改密码失败，请稍后重试。"));
    } finally {
      setLoading(false);
    }
  };
  return (
    <section className="password-page">
      <div className="surface-panel">
        <div className="panel-header">
          <div>
            <h1>修改临时密码</h1>
            <p className="panel-description">首次登录必须设置新密码，完成后才能进入管理控制台。</p>
          </div>
        </div>
        <div className="panel-body">
          <Form layout="vertical" onFinish={(values: PasswordForm) => void submit(values)}>
            <Form.Item
              name="currentPassword"
              label="当前密码"
              rules={[{ required: true, message: "请输入当前密码" }]}
            >
              <Input.Password placeholder="输入当前临时密码" />
            </Form.Item>
            <Form.Item
              name="newPassword"
              label="新密码"
              rules={passwordRules(passwordMinimumLength)}
            >
              <Input.Password placeholder={passwordHint(passwordMinimumLength)} />
            </Form.Item>
            <Form.Item
              name="confirmPassword"
              label="确认新密码"
              dependencies={["newPassword"]}
              rules={[
                { required: true, message: "请再次输入新密码" },
                ({ getFieldValue }) => ({
                  validator: (_, value: string) =>
                    value === getFieldValue("newPassword")
                      ? Promise.resolve()
                      : Promise.reject(new Error("两次输入的密码不一致")),
                }),
              ]}
            >
              <Input.Password placeholder="再次输入新密码" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              修改密码
            </Button>
          </Form>
        </div>
      </div>
    </section>
  );
}
