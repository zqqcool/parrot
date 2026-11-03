import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button, Form, Input, Space } from "antd";

import { authApi } from "@/shared/api/client";
import { endpoints } from "@/shared/api/endpoints";
import type { CurrentUserProfileUpdate, Principal } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { RequestErrorAlert, UserAvatarUpload } from "@/shared/ui";
import { uploadObject } from "@/shared/uploads";

type Props = {
  principal: Principal | undefined;
  onClose: () => void;
  onLoadingChange: (loading: boolean) => void;
};

export function CurrentUserProfileForm({ principal, onClose, onLoadingChange }: Props) {
  const auth = useAuth();
  const [form] = Form.useForm<CurrentUserProfileUpdate>();
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const updateProfile = useMutation({ mutationFn: authApi.updateProfile });
  const attachAvatar = useMutation({ mutationFn: (file: File) => attachCurrentUserAvatar(file) });
  const loading = updateProfile.isPending || attachAvatar.isPending;

  useEffect(() => {
    form.setFieldsValue({ display_name: principal?.display_name });
    setAvatarFile(null);
  }, [form, principal]);

  useEffect(() => onLoadingChange(loading), [loading, onLoadingChange]);

  const save = async () => {
    const values = await form.validateFields();
    await updateProfile.mutateAsync(values);
    if (avatarFile) await attachAvatar.mutateAsync(avatarFile);
    await auth.refreshSession();
    setAvatarFile(null);
    onClose();
  };

  return (
    <Form className="admin-modal-form" form={form} layout="vertical" onFinish={() => void save()}>
      <RequestErrorAlert
        error={updateProfile.error ?? attachAvatar.error}
        fallback="保存个人资料失败，请稍后重试。"
      />
      <AvatarField
        file={avatarFile}
        loading={loading}
        principal={principal}
        onChange={setAvatarFile}
      />
      <Form.Item label="用户名">
        <Input disabled value={principal?.username ?? "-"} />
      </Form.Item>
      <Form.Item
        name="display_name"
        label="显示名称"
        rules={[{ required: true, message: "请输入显示名称" }]}
      >
        <Input maxLength={150} placeholder="输入显示名称" />
      </Form.Item>
      <Space>
        <Button disabled={loading} onClick={onClose}>
          取消
        </Button>
        <Button htmlType="submit" loading={loading} type="primary">
          保存
        </Button>
      </Space>
    </Form>
  );
}

function AvatarField({
  file,
  loading,
  principal,
  onChange,
}: {
  file: File | null;
  loading: boolean;
  principal: Principal | undefined;
  onChange: (file: File | null) => void;
}) {
  const avatarUrl =
    principal?.avatar_present && principal.tenant_id
      ? `${endpoints.auth.profileAvatar}?v=${encodeURIComponent(principal.request_id)}`
      : undefined;
  return (
    <Form.Item
      className="admin-form-item-wide"
      label="头像"
      extra={
        principal?.tenant_id ? "支持 PNG、JPEG、WebP，最大 2 MB。" : "请选择租户后再上传头像。"
      }
    >
      <UserAvatarUpload
        avatarUrl={avatarUrl}
        disabled={loading || !principal?.tenant_id}
        file={file}
        onChange={onChange}
      />
    </Form.Item>
  );
}

async function attachCurrentUserAvatar(file: File) {
  const grant = await uploadObject({
    file,
    requestGrant: authApi.issueCurrentUserAvatarUploadGrant,
  });
  await authApi.attachCurrentUserAvatar({ object_key: grant.object_key });
}
