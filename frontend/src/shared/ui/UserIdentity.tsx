import { Avatar, Space } from "antd";

import { endpoints } from "@/shared/api/endpoints";
import type { UserReference } from "@/shared/api/types";
import { AppIcon } from "@/shared/icons";

type Props = {
  tenantId?: string | null;
  user?: UserReference | null;
  unknownLabel?: string;
};

export function UserIdentity({ tenantId, user, unknownLabel = "-" }: Props) {
  if (!user) return <span>{unknownLabel}</span>;
  const avatarUrl =
    tenantId && user.avatar_present ? endpoints.admin.userAvatar(tenantId, user.id) : undefined;
  return (
    <Space size={8}>
      <Avatar icon={<AppIcon name="User" size="sm" />} size="small" src={avatarUrl}>
        {user.display_name.slice(0, 1)}
      </Avatar>
      <span>{user.display_name}</span>
    </Space>
  );
}
