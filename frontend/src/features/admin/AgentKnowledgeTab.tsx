import type { TabsProps } from "antd";

import { AgentKnowledgeSection } from "@/features/admin/AgentKnowledgeSection";
import type { AdminAgent as Agent } from "@/shared/api/types";

type TabItem = NonNullable<TabsProps["items"]>[number];

type Options = {
  agent: Agent;
  canManage: boolean;
  canQuery: boolean;
  canRead: boolean;
  tenantId: string;
  usesKnowledge: boolean;
  onSuccessMessage: (content: string) => void;
};

export function createAgentKnowledgeTab({
  agent,
  canManage,
  canQuery,
  canRead,
  tenantId,
  usesKnowledge,
  onSuccessMessage,
}: Options): TabItem {
  return {
    key: "knowledge",
    label: "知识库",
    children: (
      <AgentKnowledgeSection
        agent={agent}
        canManage={canManage && canRead}
        canQuery={canQuery}
        canRead={canRead}
        tenantId={tenantId}
        usesKnowledge={usesKnowledge}
        onSaved={() => onSuccessMessage("知识库绑定已更新")}
      />
    ),
  };
}
