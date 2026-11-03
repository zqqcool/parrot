import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ImChannelBindingsTable } from "@/features/admin/ImChannelBindingsTable";
import { ImChannelCreateModal } from "@/features/admin/ImChannelCreateModal";
import { ImChannelToolbar } from "@/features/admin/ImChannelToolbar";
import { adminApi } from "@/shared/api/client";
import type { AdminAgent } from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

type Props = {
  agent: AdminAgent;
  canManage: boolean;
  tenantId: string;
  onSaved: (message: string) => void;
};

export function AgentWebsocketSection({ agent, canManage, tenantId, onSaved }: Props) {
  const client = useQueryClient();
  const [selectedChannelId, setSelectedChannelId] = useState<string>();
  const [createOpen, setCreateOpen] = useState(false);
  const channels = useQuery({
    queryKey: ["admin", tenantId, "im", "channels"],
    queryFn: () => adminApi.listImChannels(tenantId),
  });
  const channelTypes = useQuery({
    queryKey: ["admin", tenantId, "im", "channel-types"],
    queryFn: () => adminApi.listImChannelTypes(tenantId),
  });
  const bindings = useQuery({
    queryKey: ["admin", tenantId, "agents", agent.id, "im-bindings"],
    queryFn: () => adminApi.listAgentImBindings(tenantId, agent.id),
  });
  const invalidate = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["admin", tenantId, "im", "channels"] }),
      client.invalidateQueries({
        queryKey: ["admin", tenantId, "agents", agent.id, "im-bindings"],
      }),
    ]);
  };
  const bind = useMutation({
    mutationFn: (channelId: string) => adminApi.bindImChannel(tenantId, channelId, agent.id),
    onSuccess: async () => {
      await invalidate();
      setSelectedChannelId(undefined);
      onSaved("渠道已绑定到当前智能体");
    },
  });
  const boundChannelIds = new Set(bindings.data?.map((item) => item.channel_id));
  const selectableChannels = (channels.data ?? []).filter(
    (channel) => !boundChannelIds.has(channel.id),
  );

  return (
    <section className="agent-tab-panel agent-websocket-panel">
      <div className="agent-tab-heading">
        <div>
          <h2>IM 渠道</h2>
          <p>渠道由人工创建并绑定到当前 Agent；当前仅 WebSocket 适配器可用。</p>
        </div>
        <ImChannelToolbar
          canManage={canManage}
          createDisabled={channelTypes.isPending || Boolean(channelTypes.error)}
          bindPending={bind.isPending}
          onCreate={() => setCreateOpen(true)}
          onBind={() => selectedChannelId && bind.mutate(selectedChannelId)}
          onSelect={setSelectedChannelId}
          selectableChannels={selectableChannels}
          selectedChannelId={selectedChannelId}
        />
      </div>
      <div className="agent-websocket-table-section">
        <RequestErrorAlert error={bindings.error} fallback="加载渠道绑定失败" />
        <ImChannelBindingsTable
          bindings={bindings.data ?? []}
          channels={channels.data ?? []}
          channelTypes={channelTypes.data ?? []}
          loading={bindings.isPending}
        />
        <RequestErrorAlert error={bind.error} fallback="关联渠道失败" />
      </div>
      <RequestErrorAlert error={channelTypes.error} fallback="加载渠道类型失败" />
      <ImChannelCreateModal
        agentId={agent.id}
        channelTypes={channelTypes.data ?? []}
        channelTypesLoading={channelTypes.isPending}
        open={createOpen}
        tenantId={tenantId}
        onClose={() => setCreateOpen(false)}
        onCreated={async () => {
          await invalidate();
          onSaved("渠道已创建并绑定到当前智能体");
        }}
      />
      <RequestErrorAlert error={channels.error} fallback="加载渠道失败" />
    </section>
  );
}
