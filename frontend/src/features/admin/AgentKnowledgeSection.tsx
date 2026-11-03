import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert } from "antd";

import { AgentKnowledgeSectionView } from "@/features/admin/AgentKnowledgeSectionView";
import { adminApi } from "@/shared/api/client";
import type { AdminAgent as Agent } from "@/shared/api/types";

import "./agent-knowledge.css";

type Props = {
  agent: Agent;
  canManage: boolean;
  canQuery?: boolean;
  canRead: boolean;
  tenantId: string;
  usesKnowledge: boolean;
  onSaved: () => void;
};

type BindingChange = {
  bind: boolean;
  spaceId: string;
};

type MutationState = {
  binding: boolean;
  unbindingSpaceId: string | undefined;
};

function mutationState(isPending: boolean, change: BindingChange | undefined): MutationState {
  if (!isPending || !change) return { binding: false, unbindingSpaceId: undefined };
  if (change.bind) return { binding: true, unbindingSpaceId: undefined };
  return { binding: false, unbindingSpaceId: change.spaceId };
}

export function AgentKnowledgeSection({
  agent,
  canManage,
  canQuery = false,
  canRead,
  onSaved,
  tenantId,
  usesKnowledge,
}: Props) {
  const client = useQueryClient();
  const spaces = useQuery({
    queryKey: ["admin", tenantId, "knowledge-spaces"],
    queryFn: () => adminApi.listKnowledgeSpaces(tenantId),
    enabled: canRead,
  });
  const bindings = useQuery({
    queryKey: ["admin", tenantId, "agents", agent.id, "knowledge-spaces"],
    queryFn: () => adminApi.getAgentKnowledgeSpaces(tenantId, agent.id),
    enabled: canRead,
  });
  const update = useMutation({
    mutationFn: ({ bind, spaceId }: BindingChange) =>
      bind
        ? adminApi.addAgentKnowledgeSpace(tenantId, agent.id, spaceId)
        : adminApi.removeAgentKnowledgeSpace(tenantId, agent.id, spaceId),
    onSuccess: (data) => {
      client.setQueryData(["admin", tenantId, "agents", agent.id, "knowledge-spaces"], data);
      onSaved();
    },
  });

  if (!canRead) {
    return <Alert showIcon type="info" message="当前账号没有查看可绑定知识空间的权限。" />;
  }

  const allSpaces = spaces.data ?? [];
  const boundSpaceIds = bindings.data?.space_ids ?? [];
  const progress = mutationState(update.isPending, update.variables);
  return (
    <AgentKnowledgeSectionView
      agentId={agent.id}
      anonymousDisclosure={usesKnowledge && agent.allow_anonymous}
      availableSpaces={allSpaces.filter((space) => !boundSpaceIds.includes(space.id))}
      bindingsHidden={bindings.isError}
      boundSpaces={allSpaces.filter((space) => boundSpaceIds.includes(space.id))}
      canManage={canManage}
      canQuery={canQuery}
      canUpdate={canManage && bindings.isSuccess}
      isBinding={progress.binding}
      isLoading={spaces.isPending || bindings.isPending}
      isUpdating={update.isPending}
      requestError={spaces.error ?? bindings.error}
      tenantId={tenantId}
      unbindingSpaceId={progress.unbindingSpaceId}
      updateError={update.error}
      usesKnowledge={usesKnowledge}
      onBind={(spaceId) => update.mutate({ bind: true, spaceId })}
      onUnbind={(spaceId) => update.mutate({ bind: false, spaceId })}
    />
  );
}
