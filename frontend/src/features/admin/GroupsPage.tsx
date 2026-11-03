import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Form, Input, Modal, Select, Space, Tag } from "antd";

import { AssignmentEditor } from "@/features/admin/AssignmentEditor";
import { getRoleDisplayName } from "@/features/admin/roleLabels";
import { useTenantId } from "@/features/admin/useTenant";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { adminApi } from "@/shared/api/client";
import type { Group, GroupCreate, Role, User } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { AppIcon } from "@/shared/icons";
import {
  AdminPageHeader,
  CreateButton,
  DataTable,
  RequestErrorAlert,
  SearchBar,
  useDebouncedValue,
} from "@/shared/ui";

type GroupActionsProps = {
  canManageMembers: boolean;
  canManageRoles: boolean;
  group: Group;
  onMembers: (group: Group) => void;
  onRoles: (group: Group) => void;
};

function GroupAssignmentActions(props: GroupActionsProps) {
  return (
    <Space>
      {props.canManageMembers ? (
        <Button
          size="small"
          icon={<AppIcon name="People" size="sm" />}
          onClick={() => props.onMembers(props.group)}
        >
          成员
        </Button>
      ) : null}
      {props.canManageRoles ? (
        <Button
          size="small"
          icon={<AppIcon name="Permissions" size="sm" />}
          onClick={() => props.onRoles(props.group)}
        >
          角色
        </Button>
      ) : null}
    </Space>
  );
}

type GroupEditorsProps = {
  tenantId: string;
  memberGroup: Group | null;
  roleGroup: Group | null;
  users?: User[];
  roles?: Role[];
  closeMembers: () => void;
  closeRoles: () => void;
};

function GroupAssignmentEditors(props: GroupEditorsProps) {
  return (
    <>
      {props.memberGroup ? (
        <MemberAssignmentEditor
          tenantId={props.tenantId}
          group={props.memberGroup}
          users={props.users}
          onClose={props.closeMembers}
        />
      ) : null}
      {props.roleGroup ? (
        <RoleAssignmentEditor
          tenantId={props.tenantId}
          group={props.roleGroup}
          roles={props.roles}
          onClose={props.closeRoles}
        />
      ) : null}
    </>
  );
}

function MemberAssignmentEditor(props: {
  tenantId: string;
  group: Group;
  users?: User[];
  onClose: () => void;
}) {
  return (
    <AssignmentEditor
      open
      title={`${props.group.name} 的成员`}
      queryKey={["admin", props.tenantId, "groups", props.group.id, "members"]}
      options={props.users?.map((user) => ({ value: user.id, label: user.display_name })) ?? []}
      load={() => adminApi.getGroupMembers(props.tenantId, props.group.id)}
      save={(ids) => adminApi.replaceGroupMembers(props.tenantId, props.group.id, ids)}
      onClose={props.onClose}
    />
  );
}

function RoleAssignmentEditor(props: {
  tenantId: string;
  group: Group;
  roles?: Role[];
  onClose: () => void;
}) {
  return (
    <AssignmentEditor
      open
      title={`${props.group.name} 的角色`}
      queryKey={["admin", props.tenantId, "groups", props.group.id, "roles"]}
      options={
        props.roles?.map((role) => ({ value: role.id, label: getRoleDisplayName(role) })) ?? []
      }
      load={() => adminApi.getGroupRoles(props.tenantId, props.group.id)}
      save={(ids) => adminApi.replaceGroupRoles(props.tenantId, props.group.id, ids)}
      onClose={props.onClose}
    />
  );
}

export function GroupsPage() {
  const tenantId = useTenantId();
  const client = useQueryClient();
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [typeFilter, setTypeFilter] = useState<"all" | "system" | "custom">("all");
  const [memberGroup, setMemberGroup] = useState<Group | null>(null);
  const [roleGroup, setRoleGroup] = useState<Group | null>(null);
  const [form] = Form.useForm<GroupCreate>();
  const query = useQuery({
    queryKey: ["admin", tenantId, "groups", searchQuery],
    queryFn: () => adminApi.listGroups(tenantId ?? "", searchQuery),
    enabled: Boolean(tenantId),
  });
  const create = useMutation({
    mutationFn: (values: GroupCreate) =>
      adminApi.createGroup(tenantId ?? "", { ...values, description: values.description ?? "" }),
    onSuccess: async () => {
      setOpen(false);
      form.resetFields();
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "groups"] });
    },
  });
  const users = useQuery({
    queryKey: ["admin", tenantId, "users"],
    queryFn: () => adminApi.listUsers(tenantId ?? ""),
    enabled: Boolean(tenantId) && auth.hasPermission("tenant.groups.manage"),
  });
  const roles = useQuery({
    queryKey: ["admin", tenantId, "roles"],
    queryFn: () => adminApi.listRoles(tenantId ?? ""),
    enabled: Boolean(tenantId) && auth.hasPermission("tenant.roles.manage"),
  });
  if (!tenantId) return <TenantRequiredState />;
  const groups = (query.data ?? []).filter(
    (group) =>
      typeFilter === "all" || (typeFilter === "system" ? group.is_system : !group.is_system),
  );
  return (
    <section>
      <AdminPageHeader title="用户组" description="组织租户成员并批量复用角色授权。" />
      <SearchBar
        actions={<CreateButton onClick={() => setOpen(true)} />}
        advancedFilters={
          <Select
            aria-label="按类型筛选用户组"
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
        placeholder="搜索用户组名称或说明"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => {
          setSearchValue("");
          setTypeFilter("all");
        }}
      />
      <RequestErrorAlert error={query.error} fallback="加载用户组失败，请稍后重试。" />
      <DataTable
        rowKey="id"
        loading={query.isFetching}
        dataSource={groups}
        resetPaginationKey={`${searchQuery}:${typeFilter}`}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "说明", dataIndex: "description" },
          { title: "成员数", dataIndex: "member_count" },
          {
            title: "类型",
            dataIndex: "is_system",
            render: (value: boolean) => <Tag>{value ? "系统内置" : "自定义"}</Tag>,
          },
          {
            title: "配置",
            render: (_: unknown, group: Group) => (
              <GroupAssignmentActions
                group={group}
                canManageMembers={auth.hasPermission("tenant.groups.manage")}
                canManageRoles={auth.hasPermission("tenant.roles.manage")}
                onMembers={setMemberGroup}
                onRoles={setRoleGroup}
              />
            ),
          },
        ]}
      />
      <GroupAssignmentEditors
        tenantId={tenantId}
        memberGroup={memberGroup}
        roleGroup={roleGroup}
        users={users.data}
        roles={roles.data}
        closeMembers={() => setMemberGroup(null)}
        closeRoles={() => setRoleGroup(null)}
      />
      <Modal
        title="新建用户组"
        open={open}
        confirmLoading={create.isPending}
        onCancel={() => setOpen(false)}
        onOk={() => void form.validateFields().then((values) => create.mutate(values))}
      >
        <RequestErrorAlert error={create.error} fallback="创建用户组失败，请稍后重试。" />
        <Form
          className="admin-modal-form"
          form={form}
          layout="vertical"
          initialValues={{ description: "" }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: "请输入用户组名称" }]}
          >
            <Input placeholder="例如：平台运维组" />
          </Form.Item>
          <Form.Item className="admin-form-item-wide" name="description" label="说明">
            <Input.TextArea rows={3} placeholder="说明该用户组的职责和适用范围" />
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}
