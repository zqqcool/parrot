import { Button, Space } from "antd";

import type { User } from "@/shared/api/types";
import { AppIcon } from "@/shared/icons";
import { BinaryStatusTag, DataTable, UserIdentity } from "@/shared/ui";

type Props = {
  canManage: boolean;
  canManageRoles: boolean;
  loading: boolean;
  resetPaginationKey?: string;
  tenantId: string;
  users: User[] | undefined;
  onEdit: (user: User) => void;
  onResetPassword: (user: User) => void;
  onRoles: (user: User) => void;
};

export function UsersTable({
  canManage,
  canManageRoles,
  loading,
  resetPaginationKey,
  tenantId,
  users,
  onEdit,
  onResetPassword,
  onRoles,
}: Props) {
  return (
    <DataTable
      rowKey="id"
      loading={loading}
      dataSource={users}
      resetPaginationKey={resetPaginationKey}
      columns={[
        {
          title: "用户",
          render: (_: unknown, user: User) => <UserIdentity tenantId={tenantId} user={user} />,
        },
        { title: "用户名", dataIndex: "username" },
        { title: "邮箱", dataIndex: "email", render: (value: string | null) => value ?? "-" },
        {
          title: "状态",
          dataIndex: "status",
          render: (value: string) => (
            <BinaryStatusTag active={value === "active"} activeLabel="启用" inactiveLabel="禁用" />
          ),
        },
        {
          title: "密码状态",
          dataIndex: "must_change_password",
          render: (value: boolean) => (value ? "需修改" : "正常"),
        },
        ...(canManageRoles
          ? [
              {
                title: "权限配置",
                render: (_: unknown, user: User) => (
                  <Button
                    size="small"
                    icon={<AppIcon name="Permissions" size="sm" />}
                    onClick={() => onRoles(user)}
                  >
                    角色
                  </Button>
                ),
              },
            ]
          : []),
        ...(canManage
          ? [
              {
                title: "账号操作",
                width: 210,
                render: (_: unknown, user: User) => (
                  <Space size={4}>
                    <Button size="small" type="link" onClick={() => onEdit(user)}>
                      编辑
                    </Button>
                    <Button size="small" type="link" onClick={() => onResetPassword(user)}>
                      重置密码
                    </Button>
                  </Space>
                ),
              },
            ]
          : []),
      ]}
    />
  );
}
