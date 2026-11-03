import { Form, Input, Modal, Select } from "antd";
import type { FormInstance } from "antd";

import { UserAvatarUpload } from "@/features/admin/UserAvatarUpload";
import type { User, UserUpdate } from "@/shared/api/types";
import { passwordHint, passwordRules } from "@/shared/auth/passwordPolicy";
import { useAuth } from "@/shared/auth/useAuth";
import { RequestErrorAlert } from "@/shared/ui";

type PasswordReset = { temporary_password: string };

type Props = {
  avatarFile: File | null;
  avatarUrl?: string;
  editing: User | null;
  editError: unknown;
  editForm: FormInstance<UserUpdate>;
  editLoading: boolean;
  resetting: User | null;
  resetError: unknown;
  resetForm: FormInstance<PasswordReset>;
  resetLoading: boolean;
  onCloseEdit: () => void;
  onCloseReset: () => void;
  onAvatarChange: (file: File | null) => void;
  onReset: (values: PasswordReset) => void;
  onUpdate: (values: UserUpdate) => void;
};

export function UserLifecycleModals({
  avatarFile,
  avatarUrl,
  editing,
  editError,
  editForm,
  editLoading,
  resetting,
  resetError,
  resetForm,
  resetLoading,
  onCloseEdit,
  onCloseReset,
  onAvatarChange,
  onReset,
  onUpdate,
}: Props) {
  const auth = useAuth();
  const passwordMinimumLength = auth.session?.password_min_length;
  return (
    <>
      <Modal
        title={`编辑用户 · ${editing?.username ?? ""}`}
        open={Boolean(editing)}
        confirmLoading={editLoading}
        onCancel={onCloseEdit}
        onOk={() => void editForm.validateFields().then(onUpdate)}
      >
        <RequestErrorAlert error={editError} fallback="更新用户失败，请稍后重试。" />
        <Form className="admin-modal-form" form={editForm} layout="vertical">
          <Form.Item
            className="admin-form-item-wide"
            label="头像"
            extra="支持 PNG、JPEG、WebP，最大 2 MB。选择后随本次保存上传。"
          >
            <UserAvatarUpload
              avatarUrl={avatarUrl}
              file={avatarFile}
              disabled={editLoading}
              onChange={onAvatarChange}
            />
          </Form.Item>
          <Form.Item
            name="display_name"
            label="姓名"
            rules={[{ required: true, message: "请输入姓名" }]}
          >
            <Input placeholder="输入用户姓名" />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}>
            <Select
              placeholder="选择用户状态"
              options={[
                { value: "active", label: "启用" },
                { value: "disabled", label: "禁用" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={`重置密码 · ${resetting?.username ?? ""}`}
        open={Boolean(resetting)}
        confirmLoading={resetLoading}
        onCancel={onCloseReset}
        onOk={() => void resetForm.validateFields().then(onReset)}
      >
        <RequestErrorAlert error={resetError} fallback="重置密码失败，请稍后重试。" />
        <Form className="admin-modal-form" form={resetForm} layout="vertical">
          <Form.Item
            name="temporary_password"
            label="新临时密码"
            extra={
              passwordMinimumLength
                ? `至少 ${passwordMinimumLength} 个字符。用户下次登录时必须修改密码。`
                : "用户下次登录时必须修改密码。"
            }
            rules={passwordRules(passwordMinimumLength)}
          >
            <Input.Password
              autoComplete="new-password"
              placeholder={passwordHint(passwordMinimumLength)}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
