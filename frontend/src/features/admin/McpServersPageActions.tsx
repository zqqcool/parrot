import { Button, Space } from "antd";

import { AppIcon } from "@/shared/icons";
import { CreateButton } from "@/shared/ui";

type McpServersPageActionsProps = {
  canManage: boolean;
  canRecall: boolean;
  onCreate: () => void;
  onRecall: () => void;
};

export function McpServersPageActions({
  canManage,
  canRecall,
  onCreate,
  onRecall,
}: McpServersPageActionsProps) {
  if (!canManage && !canRecall) return null;
  return (
    <Space>
      {canRecall ? (
        <Button
          color="primary"
          icon={<AppIcon name="Search" size="md" />}
          variant="outlined"
          onClick={onRecall}
        >
          召回验证
        </Button>
      ) : null}
      {canManage ? <CreateButton onClick={onCreate} /> : null}
    </Space>
  );
}
