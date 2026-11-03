import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Form, Input } from "antd";

import { authApi } from "@/shared/api/client";
import { useAuth } from "@/shared/auth/useAuth";
import { passwordHint, passwordRules } from "@/shared/auth/passwordPolicy";
import { RequestErrorAlert } from "@/shared/ui";

type PasswordForm = {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
};

export function CurrentUserPasswordForm({
  onChanged,
  onLoadingChange,
}: {
  onChanged: () => void;
  onLoadingChange: (loading: boolean) => void;
}) {
  const auth = useAuth();
  const passwordMinimumLength = auth.session?.password_min_length;
  const [form] = Form.useForm<PasswordForm>();
  const [submitting, setSubmitting] = useState(false);
  const changePassword = useMutation({
    mutationFn: (values: PasswordForm) =>
      authApi.changePassword(values.currentPassword, values.newPassword),
  });

  useEffect(() => onLoadingChange(submitting), [onLoadingChange, submitting]);

  const submit = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      await changePassword.mutateAsync(values);
      await clearRevokedSession(auth.logout);
      onChanged();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Form className="admin-modal-form" form={form} layout="vertical" onFinish={() => void submit()}>
      <Alert
        showIcon
        type="warning"
        message="修改密码后，所有已登录设备都会退出，需要使用新密码重新登录。"
      />
      <RequestErrorAlert error={changePassword.error} fallback="修改密码失败，请稍后重试。" />
      <PasswordFields minimumLength={passwordMinimumLength} submitting={submitting} />
    </Form>
  );
}

function PasswordFields({
  minimumLength,
  submitting,
}: {
  minimumLength: number | undefined;
  submitting: boolean;
}) {
  return (
    <>
      <Form.Item
        name="currentPassword"
        label="当前密码"
        rules={[{ required: true, message: "请输入当前密码" }]}
      >
        <Input.Password autoComplete="current-password" placeholder="输入当前密码" />
      </Form.Item>
      <Form.Item name="newPassword" label="新密码" rules={passwordRules(minimumLength)}>
        <Input.Password autoComplete="new-password" placeholder={passwordHint(minimumLength)} />
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
        <Input.Password autoComplete="new-password" placeholder="再次输入新密码" />
      </Form.Item>
      <Button danger htmlType="submit" loading={submitting} type="primary">
        修改密码并退出登录
      </Button>
    </>
  );
}

async function clearRevokedSession(logout: () => Promise<void>) {
  try {
    await logout();
  } catch {
    // The password endpoint already revoked this session before the local auth state is cleared.
  }
}
