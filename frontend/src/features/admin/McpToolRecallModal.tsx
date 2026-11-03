import { AgentCapabilityRecallModal } from "@/features/admin/AgentCapabilityRecallModal";
import { McpToolRecallResult } from "@/features/admin/McpToolRecallResult";
import { adminApi } from "@/shared/api/client";
import type { AgentMcpToolRecall } from "@/shared/api/types";

type Props = {
  open: boolean;
  tenantId: string;
  canManageAgent: boolean;
  onClose: () => void;
};

export function McpToolRecallModal(props: Props) {
  return (
    <AgentCapabilityRecallModal<AgentMcpToolRecall>
      canManageAgent={props.canManageAgent}
      infoMessage="验证会展示 Agent 可使用的查询和操作工具，但不会执行。实际变更或发送数据时，系统会先请求用户确认。"
      open={props.open}
      queryPlaceholder="例如：查询当前订单状态"
      renderResult={(result) => <McpToolRecallResult result={result} />}
      search={adminApi.searchAgentMcpTools}
      tenantId={props.tenantId}
      title="MCP 工具召回验证"
      onClose={props.onClose}
    />
  );
}
