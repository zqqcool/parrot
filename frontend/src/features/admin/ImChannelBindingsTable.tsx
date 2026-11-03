import { Tag, Typography } from "antd";

import type { ImAgentBinding, ImChannel, ImChannelType } from "@/shared/api/types";
import { DataTable } from "@/shared/ui";

type Props = {
  bindings: ImAgentBinding[];
  channelTypes: ImChannelType[];
  channels: ImChannel[];
  loading: boolean;
};

export function ImChannelBindingsTable({ bindings, channelTypes, channels, loading }: Props) {
  const channelById = new Map(channels.map((channel) => [channel.id, channel]));
  const typeLabels = new Map(channelTypes.map((item) => [item.key, item.label]));

  return (
    <DataTable<ImAgentBinding>
      columns={[
        { dataIndex: "channel_name", key: "name", title: "渠道名称" },
        {
          key: "type",
          title: "类型",
          render: (_, binding) => channelTypeName(channelById.get(binding.channel_id), typeLabels),
        },
        {
          key: "status",
          title: "状态",
          render: (_, binding) => (
            <ChannelStatus binding={binding} channel={channelById.get(binding.channel_id)} />
          ),
        },
        {
          key: "origins",
          title: "允许 Origin",
          render: (_, binding) => <OriginList channel={channelById.get(binding.channel_id)} />,
        },
        {
          key: "address",
          title: "接入地址",
          render: (_, binding) => <ChannelAddress binding={binding} />,
        },
      ]}
      dataSource={bindings}
      loading={loading}
      locale={{ emptyText: "当前 Agent 尚未绑定渠道" }}
      pagination={false}
      rowKey="id"
      scroll={{ x: 960 }}
    />
  );
}

function channelTypeName(channel: ImChannel | undefined, labels: Map<string, string>): string {
  if (!channel) return "—";
  return labels.get(channel.channel_type) ?? channel.channel_type;
}

function ChannelStatus({
  binding,
  channel,
}: {
  binding: ImAgentBinding;
  channel: ImChannel | undefined;
}) {
  const enabled = binding.status === "enabled" && channel?.status === "enabled";
  return <Tag color={enabled ? "success" : "default"}>{enabled ? "启用" : "停用"}</Tag>;
}

function OriginList({ channel }: { channel: ImChannel | undefined }) {
  const text = channel?.allowed_origins.join(", ") ?? "";
  return text ? <Typography.Text ellipsis={{ tooltip: text }}>{text}</Typography.Text> : "—";
}

function ChannelAddress({ binding }: { binding: ImAgentBinding }) {
  const address = websocketUrl(binding.channel_public_key);
  return <Typography.Text copyable={{ text: address }}>{address}</Typography.Text>;
}

function websocketUrl(channelKey: string): string {
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${window.location.host}/api/v1/im/ws/${channelKey}`;
}
