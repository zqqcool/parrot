import { Select, Space } from "antd";

import type { AdminAgent, User } from "@/shared/api/types";
import { SearchBar } from "@/shared/ui";

type Props = {
  agents: AdminAgent[];
  actorId: string | undefined;
  agentId: string | undefined;
  canReadUsers: boolean;
  loadingAgents: boolean;
  loadingUsers: boolean;
  searchValue: string;
  users: User[];
  onActorChange: (value: string | undefined) => void;
  onAgentChange: (value: string) => void;
  onReset: () => void;
  onSearchChange: (value: string) => void;
};

export function AgentMemorySearchControls({
  agents,
  actorId,
  agentId,
  canReadUsers,
  loadingAgents,
  loadingUsers,
  searchValue,
  users,
  onActorChange,
  onAgentChange,
  onReset,
  onSearchChange,
}: Props) {
  return (
    <SearchBar
      advancedFilters={
        <Space wrap>
          <Select
            aria-label="选择 Agent"
            loading={loadingAgents}
            options={agents.map((agent) => ({ value: agent.id, label: agent.name }))}
            placeholder="选择 Agent"
            value={agentId}
            onChange={onAgentChange}
          />
          {canReadUsers ? (
            <Select
              allowClear
              aria-label="选择用户"
              disabled={!agentId}
              loading={loadingUsers}
              options={users.map((user) => ({
                value: user.id,
                label: `${user.display_name} (${user.username})`,
              }))}
              placeholder="可选：选择用户"
              value={actorId}
              onChange={onActorChange}
            />
          ) : null}
        </Space>
      }
      hasActiveFilters={Boolean(agentId || actorId)}
      placeholder="输入关键词；留空则展示该 Agent 可见的全部记忆"
      value={searchValue}
      onChange={onSearchChange}
      onReset={onReset}
    />
  );
}
