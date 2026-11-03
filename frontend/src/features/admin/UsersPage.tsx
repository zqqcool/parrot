import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Form, Modal, message, Select } from "antd";

import { AssignmentEditor } from "@/features/admin/AssignmentEditor";
import { getRoleDisplayName } from "@/features/admin/roleLabels";
import { useTenantId } from "@/features/admin/useTenant";
import { UserCreateModal } from "@/features/admin/UserCreateModal";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { UserLifecycleModals } from "@/features/admin/UserLifecycleModals";
import { UsersTable } from "@/features/admin/UsersTable";
import { adminApi } from "@/shared/api/client";
import { endpoints } from "@/shared/api/endpoints";
import type { User, UserCreate, UserUpdate } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import {
  AdminPageHeader,
  CreateButton,
  RequestErrorAlert,
  SearchBar,
  useDebouncedValue,
} from "@/shared/ui";
import { uploadObject } from "@/shared/uploads";

function getAvatarUrl(tenantId: string, user: User | null): string | undefined {
  return user?.avatar_present ? endpoints.admin.userAvatar(tenantId, user.id) : undefined;
}

function isDisablingUser(user: User | null, values: UserUpdate): boolean {
  return user?.status === "active" && values.status === "disabled";
}

function filterUsers(users: User[] | undefined, statusFilter: "all" | "active" | "disabled") {
  return (users ?? []).filter((user) => statusFilter === "all" || user.status === statusFilter);
}

export function UsersPage() {
  const tenantId = useTenantId();
  const queryClient = useQueryClient();
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "disabled">("all");
  const [roleUser, setRoleUser] = useState<User | null>(null);
  const [editing, setEditing] = useState<User | null>(null);
  const [resetting, setResetting] = useState<User | null>(null);
  const [createAvatarFile, setCreateAvatarFile] = useState<File | null>(null);
  const [editAvatarFile, setEditAvatarFile] = useState<File | null>(null);
  const [form] = Form.useForm<UserCreate>();
  const [editForm] = Form.useForm<UserUpdate>();
  const [resetForm] = Form.useForm<{ temporary_password: string }>();
  const [messageApi, messageContext] = message.useMessage();
  const canManage = auth.hasPermission("tenant.users.manage");
  const query = useQuery({
    queryKey: ["admin", tenantId, "users", searchQuery],
    queryFn: () => adminApi.listUsers(tenantId ?? "", searchQuery),
    enabled: Boolean(tenantId),
  });
  const create = useMutation({
    mutationFn: (payload: UserCreate) => adminApi.createUser(tenantId ?? "", payload),
  });
  const update = useMutation({
    mutationFn: (values: UserUpdate) =>
      adminApi.updateUser(tenantId ?? "", editing?.id ?? "", values),
  });
  const attachAvatar = useMutation({
    mutationFn: async ({ userId, file }: { userId: string; file: File }) => {
      const grant = await uploadObject({
        file,
        requestGrant: (metadata) =>
          adminApi.issueUserAvatarUploadGrant(tenantId ?? "", userId, metadata),
      });
      await adminApi.attachUserAvatar(tenantId ?? "", userId, { object_key: grant.object_key });
    },
  });
  const resetPassword = useMutation({
    mutationFn: ({ temporary_password }: { temporary_password: string }) =>
      adminApi.resetUserPassword(tenantId ?? "", resetting?.id ?? "", temporary_password),
    onSuccess: () => {
      setResetting(null);
      resetForm.resetFields();
    },
  });
  const roles = useQuery({
    queryKey: ["admin", tenantId, "roles"],
    queryFn: () => adminApi.listRoles(tenantId ?? ""),
    enabled: Boolean(tenantId) && auth.hasPermission("tenant.roles.manage"),
  });

  const invalidateUsers = () =>
    queryClient.invalidateQueries({ queryKey: ["admin", tenantId, "users"] });
  const closeCreate = () => {
    setOpen(false);
    setCreateAvatarFile(null);
    form.resetFields();
    create.reset();
  };
  const closeEdit = () => {
    setEditing(null);
    setEditAvatarFile(null);
    editForm.resetFields();
    update.reset();
    attachAvatar.reset();
  };
  const submitCreate = async () => {
    const values = await form.validateFields();
    const user = await create.mutateAsync(values);
    let avatarUploaded = true;
    if (createAvatarFile) {
      try {
        await attachAvatar.mutateAsync({ userId: user.id, file: createAvatarFile });
      } catch {
        avatarUploaded = false;
      }
    }
    closeCreate();
    await invalidateUsers();
    if (avatarUploaded) void messageApi.success("用户已创建");
    else void messageApi.warning("用户已创建，但头像上传失败；请在编辑用户中重试。");
  };
  const submitUpdate = async (values: UserUpdate) => {
    const user = await update.mutateAsync(values);
    try {
      if (editAvatarFile) await attachAvatar.mutateAsync({ userId: user.id, file: editAvatarFile });
    } finally {
      await invalidateUsers();
    }
    closeEdit();
    void messageApi.success(editAvatarFile ? "用户信息和头像已保存" : "用户信息已保存");
  };
  if (!tenantId) return <TenantRequiredState />;
  const users = filterUsers(query.data, statusFilter);

  return (
    <section>
      {messageContext}
      <AdminPageHeader
        title="用户管理"
        description="管理全局用户身份及其在当前租户中的成员关系。"
      />
      <SearchBar
        actions={canManage ? <CreateButton onClick={() => setOpen(true)} /> : null}
        advancedFilters={
          <Select
            aria-label="按状态筛选用户"
            options={[
              { value: "all", label: "全部状态" },
              { value: "active", label: "启用" },
              { value: "disabled", label: "禁用" },
            ]}
            value={statusFilter}
            onChange={setStatusFilter}
          />
        }
        hasActiveFilters={statusFilter !== "all"}
        placeholder="搜索姓名、用户名或邮箱"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => {
          setSearchValue("");
          setStatusFilter("all");
        }}
      />
      <RequestErrorAlert error={query.error} fallback="加载用户失败，请稍后重试。" />
      <UsersTable
        canManage={canManage}
        canManageRoles={auth.hasPermission("tenant.roles.manage")}
        loading={query.isFetching}
        resetPaginationKey={`${searchQuery}:${statusFilter}`}
        tenantId={tenantId}
        users={users}
        onEdit={(user) => {
          editForm.setFieldsValue({ display_name: user.display_name, status: user.status });
          setEditAvatarFile(null);
          setEditing(user);
        }}
        onResetPassword={setResetting}
        onRoles={setRoleUser}
      />
      {roleUser ? (
        <AssignmentEditor
          open
          title={`${roleUser.display_name} 的角色`}
          queryKey={["admin", tenantId, "users", roleUser.id, "roles"]}
          options={
            roles.data?.map((role) => ({ value: role.id, label: getRoleDisplayName(role) })) ?? []
          }
          load={() => adminApi.getUserRoles(tenantId, roleUser.id)}
          save={(ids) => adminApi.replaceUserRoles(tenantId, roleUser.id, ids)}
          onClose={() => setRoleUser(null)}
        />
      ) : null}
      <UserCreateModal
        avatarFile={createAvatarFile}
        error={create.error}
        form={form}
        loading={create.isPending || attachAvatar.isPending}
        open={open}
        onAvatarChange={setCreateAvatarFile}
        onClose={closeCreate}
        onSubmit={() => void submitCreate()}
      />
      <UserLifecycleModals
        avatarFile={editAvatarFile}
        avatarUrl={getAvatarUrl(tenantId, editing)}
        editing={editing}
        editError={update.error ?? attachAvatar.error}
        editForm={editForm}
        editLoading={update.isPending || attachAvatar.isPending}
        resetting={resetting}
        resetError={resetPassword.error}
        resetForm={resetForm}
        resetLoading={resetPassword.isPending}
        onAvatarChange={setEditAvatarFile}
        onCloseEdit={closeEdit}
        onCloseReset={() => setResetting(null)}
        onReset={(values) => resetPassword.mutate(values)}
        onUpdate={(values) => {
          if (isDisablingUser(editing, values)) {
            Modal.confirm({
              title: "确认禁用该用户？",
              content: "禁用后该用户的现有会话将失效，且无法再访问当前租户。",
              okText: "确认禁用",
              okButtonProps: { danger: true },
              cancelText: "取消",
              onOk: () => submitUpdate(values),
            });
            return;
          }
          void submitUpdate(values);
        }}
      />
    </section>
  );
}
