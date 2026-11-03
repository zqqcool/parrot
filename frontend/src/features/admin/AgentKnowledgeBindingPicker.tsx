import { Button, Popconfirm, Select } from "antd";

import type { KnowledgeSpace } from "@/shared/api/types";
import { AppIcon } from "@/shared/icons";

type Props = {
  anonymousDisclosure: boolean;
  disabled: boolean;
  loading: boolean;
  selectedSpaceId: string | undefined;
  spaces: KnowledgeSpace[];
  onBind: () => void;
  onSelect: (spaceId: string | undefined) => void;
};

export function AgentKnowledgeBindingPicker({
  anonymousDisclosure,
  disabled,
  loading,
  selectedSpaceId,
  spaces,
  onBind,
  onSelect,
}: Props) {
  const buttonDisabled = disabled || !selectedSpaceId;
  const button = (
    <Button disabled={buttonDisabled} loading={loading} type="primary" onClick={onBind}>
      添加绑定
    </Button>
  );

  return (
    <div className="agent-knowledge-binding-picker">
      <Select
        allowClear
        aria-label="搜索并选择要绑定的知识库"
        disabled={disabled}
        loading={loading}
        notFoundContent="没有可绑定的知识库"
        optionFilterProp="label"
        options={spaces.map((space) => ({
          label: `${space.name}（${classificationLabel(space.classification)} · ${space.slug}）`,
          value: space.id,
        }))}
        placeholder="搜索并选择要绑定的知识库"
        prefix={<AppIcon name="Search" size="sm" />}
        showSearch
        value={selectedSpaceId}
        onChange={onSelect}
      />
      {anonymousDisclosure ? (
        <Popconfirm
          cancelText="取消"
          description="绑定后，匿名访客可通过该 Agent 检索此知识空间。"
          disabled={buttonDisabled}
          okText="确认绑定"
          onConfirm={onBind}
          title="确认扩大公开知识范围？"
        >
          <Button disabled={buttonDisabled} loading={loading} type="primary">
            添加绑定
          </Button>
        </Popconfirm>
      ) : (
        button
      )}
    </div>
  );
}

function classificationLabel(value: string) {
  if (value === "standard") return "标准";
  if (value === "restricted") return "受限";
  return value;
}
