import { Button, Select, Space } from "antd";

import type { ImChannel } from "@/shared/api/types";

type Props = {
  bindPending: boolean;
  canManage: boolean;
  createDisabled: boolean;
  onBind: () => void;
  onCreate: () => void;
  onSelect: (channelId: string) => void;
  selectableChannels: ImChannel[];
  selectedChannelId: string | undefined;
};

export function ImChannelToolbar({
  bindPending,
  canManage,
  createDisabled,
  onBind,
  onCreate,
  onSelect,
  selectableChannels,
  selectedChannelId,
}: Props) {
  if (!canManage) return null;

  return (
    <Space>
      {selectableChannels.length ? (
        <>
          <Select
            aria-label="选择渠道"
            optionFilterProp="label"
            options={selectableChannels.map((channel) => ({
              value: channel.id,
              label: `${channel.name} · ${channel.status}`,
            }))}
            placeholder="关联已有渠道"
            value={selectedChannelId}
            onChange={onSelect}
            style={{ minWidth: 220 }}
          />
          <Button disabled={!selectedChannelId} loading={bindPending} onClick={onBind}>
            关联
          </Button>
        </>
      ) : null}
      <Button disabled={createDisabled} type="primary" onClick={onCreate}>
        创建渠道
      </Button>
    </Space>
  );
}
