import { Form, Input, Modal } from "antd";
import type { FormInstance } from "antd";

import { UserAvatarUpload } from "@/features/admin/UserAvatarUpload";
import type { UserCreate } from "@/shared/api/types";
import { passwordHint, passwordRules } from "@/shared/auth/passwordPolicy";
import { useAuth } from "@/shared/auth/useAuth";
import { RequestErrorAlert } from "@/shared/ui";

type Props = {
  avatarFile: File | null;
  error: unknown;
  form: FormInstance<UserCreate>;
  loading: boolean;
  open: boolean;
  onAvatarChange: (file: File | null) => void;
  onClose: () => void;
  onSubmit: () => void;
};

export function UserCreateModal({
  avatarFile,
  error,
  form,
  loading,
  open,
  onAvatarChange,
  onClose,
  onSubmit,
}: Props) {
  const auth = useAuth();
  const passwordMinimumLength = auth.session?.password_min_length;
  return (
    <Modal
      destroyOnHidden
      title="新建用户"
      open={open}
      confirmLoading={loading}
      onCancel={onClose}
      onOk={onSubmit}
    >
      <RequestErrorAlert error={error} fallback="创建用户失败，请稍后重试。" />
      <Form className="admin-modal-form" form={form} layout="vertical">
        <Form.Item
          className="admin-form-item-wide"
          label="头像"
          extra="支持 PNG、JPEG、WebP，最大 2 MB。"
        >
          <UserAvatarUpload file={avatarFile} disabled={loading} onChange={onAvatarChange} />
        </Form.Item>
        <Form.Item
          name="username"
          label="用户名"
          rules={[
            { required: true, message: "请输入用户名" },
            { min: 3, message: "用户名至少 3 个字符" },
          ]}
        >
          <Input placeholder="输入登录用户名" />
        </Form.Item>
        <Form.Item
          name="display_name"
          label="姓名"
          rules={[{ required: true, message: "请输入姓名" }]}
        >
          <Input placeholder="输入用户姓名" />
        </Form.Item>
        <Form.Item name="email" label="邮箱">
          <Input type="email" placeholder="例如：name@example.com" />
        </Form.Item>
        <Form.Item
          className="admin-form-item-wide"
          name="temporary_password"
          label="临时密码"
          extra={
            passwordMinimumLength
              ? `至少 ${passwordMinimumLength} 个字符，用户首次登录后必须修改`
              : "用户首次登录后必须修改"
          }
          rules={passwordRules(passwordMinimumLength)}
        >
          <Input.Password placeholder={passwordHint(passwordMinimumLength)} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
