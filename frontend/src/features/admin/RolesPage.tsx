import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Flex, Form, Input, Modal, Select, Tag } from "antd";

import { getRoleDisplayName } from "@/features/admin/roleLabels";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { RoleCreate } from "@/shared/api/types";
import {
  AdminPageHeader,
  CreateButton,
  DataTable,
  MultiSelect,
  RequestErrorAlert,
  SearchBar,
  useDebouncedValue,
} from "@/shared/ui";

export function RolesPage() {
  const tenantId = useTenantId();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [typeFilter, setTypeFilter] = useState<"all" | "system" | "custom">("all");
  const [form] = Form.useForm<RoleCreate>();
  const selectedPermissions = Form.useWatch("permissions", form) ?? [];
  const roles = useQuery({
    queryKey: ["admin", tenantId, "roles", searchQuery],
    queryFn: () => adminApi.listRoles(tenantId ?? "", searchQuery),
    enabled: Boolean(tenantId),
  });
  const permissions = useQuery({
    queryKey: ["admin", "permissions"],
    queryFn: adminApi.listPermissions,
    enabled: Boolean(tenantId),
  });
  const create = useMutation({
    mutationFn: (values: RoleCreate) =>
      adminApi.createRole(tenantId ?? "", {
        ...values,
        description: values.description ?? "",
        permissions: values.permissions ?? [],
      }),
    onSuccess: async () => {
      setOpen(false);
      form.resetFields();
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "roles"] });
    },
  });
  if (!tenantId) return <TenantRequiredState />;
  const availablePermissionKeys = permissions.data?.map((permission) => permission.key) ?? [];
  const allPermissionsSelected =
    availablePermissionKeys.length > 0 &&
    availablePermissionKeys.every((key) => selectedPermissions.includes(key));
  const permissionDescriptions = new Map(
    permissions.data?.map((permission) => [permission.key, permission.description]),
  );
  const filteredRoles = (roles.data ?? []).filter(
    (role) => typeFilter === "all" || (typeFilter === "system" ? role.is_system : !role.is_system),
  );

  return (
    <section>
      <AdminPageHeader title="角色权限" description="管理可直接分配给用户或用户组的权限集合。" />
      <SearchBar
        actions={<CreateButton onClick={() => setOpen(true)} />}
        advancedFilters={
          <Select
            aria-label="按类型筛选角色"
            options={[
              { value: "all", label: "全部类型" },
              { value: "system", label: "系统内置" },
              { value: "custom", label: "自定义" },
            ]}
            value={typeFilter}
            onChange={setTypeFilter}
          />
        }
        hasActiveFilters={typeFilter !== "all"}
        placeholder="搜索角色名称、标识或权限"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => {
          setSearchValue("");
          setTypeFilter("all");
        }}
      />
      <RequestErrorAlert error={roles.error} fallback="加载角色失败，请稍后重试。" />
      <DataTable
        rowKey="id"
        loading={roles.isFetching}
        dataSource={filteredRoles}
        resetPaginationKey={`${searchQuery}:${typeFilter}`}
        columns={[
          { title: "角色名称", render: (_, role) => getRoleDisplayName(role) },
          { title: "角色标识", dataIndex: "key" },
          {
            title: "权限项",
            dataIndex: "permissions",
            render: (values: string[]) => (
              <div className="tag-list">
                {values.map((value) => (
                  <Tag key={value}>{permissionLabel(value, permissionDescriptions.get(value))}</Tag>
                ))}
              </div>
            ),
          },
          {
            title: "类型",
            dataIndex: "is_system",
            render: (value: boolean) => (value ? "系统内置" : "自定义"),
          },
        ]}
      />
      <Modal
        title="新建角色"
        open={open}
        width={620}
        confirmLoading={create.isPending}
        onCancel={() => setOpen(false)}
        onOk={() => void form.validateFields().then((values) => create.mutate(values))}
      >
        <RequestErrorAlert error={create.error} fallback="创建角色失败，请稍后重试。" />
        <Form
          className="admin-modal-form"
          form={form}
          layout="vertical"
          initialValues={{ description: "", permissions: [] }}
        >
          <Form.Item
            name="key"
            label="角色标识"
            rules={[{ required: true, message: "请输入角色标识" }]}
          >
            <Input placeholder="例如：support.viewer" />
          </Form.Item>
          <Form.Item
            name="name"
            label="角色名称"
            rules={[{ required: true, message: "请输入角色名称" }]}
          >
            <Input placeholder="例如：支持团队只读角色" />
          </Form.Item>
          <Form.Item className="admin-form-item-wide" name="description" label="说明">
            <Input placeholder="说明角色用途和授权边界" />
          </Form.Item>
          <Form.Item className="admin-form-item-wide" label="权限项">
            <Flex vertical gap={6}>
              <Flex align="center" justify="space-between">
                <span aria-live="polite">
                  已选 {selectedPermissions.length} / {availablePermissionKeys.length} 项
                </span>
                <Flex gap={4}>
                  <Button
                    type="link"
                    size="small"
                    disabled={availablePermissionKeys.length === 0 || allPermissionsSelected}
                    onClick={() => form.setFieldValue("permissions", availablePermissionKeys)}
                  >
                    全选全部权限
                  </Button>
                  <Button
                    type="link"
                    size="small"
                    disabled={selectedPermissions.length === 0}
                    onClick={() => form.setFieldValue("permissions", [])}
                  >
                    清空权限
                  </Button>
                </Flex>
              </Flex>
              <Form.Item noStyle name="permissions">
                <MultiSelect
                  aria-label="权限项"
                  placeholder="选择该角色包含的权限"
                  options={permissions.data?.map((item) => ({
                    value: item.key,
                    label: permissionLabel(item.key, item.description),
                  }))}
                />
              </Form.Item>
            </Flex>
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}

function permissionLabel(key: string, description: string | undefined) {
  return description ? `${description}（${key}）` : key;
}
