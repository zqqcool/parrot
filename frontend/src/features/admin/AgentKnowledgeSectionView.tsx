import { useState } from "react";
import { Alert, Button, Popconfirm } from "antd";

import { AgentKnowledgeSearchTest } from "@/features/admin/AgentKnowledgeSearchTest";
import { AgentKnowledgeToolbar } from "@/features/admin/AgentKnowledgeToolbar";
import type { KnowledgeSpace } from "@/shared/api/types";
import { BinaryStatusTag, DataTable, RequestErrorAlert } from "@/shared/ui";

type Props = {
  agentId: string;
  anonymousDisclosure: boolean;
  availableSpaces: KnowledgeSpace[];
  bindingsHidden: boolean;
  boundSpaces: KnowledgeSpace[];
  canManage: boolean;
  canQuery: boolean;
  canUpdate: boolean;
  isBinding: boolean;
  isLoading: boolean;
  isUpdating: boolean;
  requestError: unknown;
  tenantId: string;
  unbindingSpaceId: string | undefined;
  updateError: unknown;
  usesKnowledge: boolean;
  onBind: (spaceId: string) => void;
  onUnbind: (spaceId: string) => void;
};

export function AgentKnowledgeSectionView(props: Props) {
  const [searchTestOpen, setSearchTestOpen] = useState(false);
  const bindingDisabled = !props.canUpdate || props.isUpdating;

  return (
    <section className="agent-tab-panel">
      <KnowledgeSectionHeading />
      <KnowledgeBindingNotices {...props} />
      <RequestErrorAlert error={props.requestError} fallback="加载知识库配置失败" />
      <AgentKnowledgeToolbar
        anonymousDisclosure={props.anonymousDisclosure}
        availableSpaces={props.availableSpaces}
        bindingDisabled={bindingDisabled}
        canManage={props.canManage}
        canQuery={props.canQuery}
        isBinding={props.isBinding}
        usesKnowledge={props.usesKnowledge}
        onBind={props.onBind}
        onOpenTest={() => setSearchTestOpen(true)}
      />
      <KnowledgeBindingsTable {...props} />
      <RequestErrorAlert error={props.updateError} fallback="更新知识库绑定失败" />
      <AgentKnowledgeSearchTest
        agentId={props.agentId}
        open={searchTestOpen}
        tenantId={props.tenantId}
        onClose={() => setSearchTestOpen(false)}
      />
    </section>
  );
}

function KnowledgeSectionHeading() {
  return (
    <div className="agent-tab-heading">
      <div>
        <h2>知识库绑定</h2>
        <p>知识型 Agent 会在全部已绑定空间中检索相关证据，再生成回答。</p>
      </div>
    </div>
  );
}

function KnowledgeBindingNotices({
  anonymousDisclosure,
  bindingsHidden,
  canManage,
  usesKnowledge,
}: Props) {
  return (
    <>
      {anonymousDisclosure ? (
        <Alert
          showIcon
          type="warning"
          message="该知识型 Agent 允许匿名访问。绑定的知识空间可被匿名访客通过该 Agent 检索。"
        />
      ) : null}
      {!usesKnowledge ? (
        <Alert
          showIcon
          type="info"
          message="当前类型不会读取知识库。绑定会保留，并在切换为知识型 Agent 后生效。"
        />
      ) : null}
      {!canManage ? (
        <Alert showIcon type="info" message="当前账号只能查看知识库绑定，没有修改权限。" />
      ) : null}
      {bindingsHidden ? (
        <Alert
          showIcon
          type="warning"
          message="当前账号没有查看该 Agent 全部知识库绑定的权限，已禁用绑定操作。"
        />
      ) : null}
    </>
  );
}

function KnowledgeBindingsTable(props: Props) {
  return (
    <DataTable<KnowledgeSpace>
      rowKey="id"
      loading={props.isLoading}
      dataSource={props.boundSpaces}
      locale={{ emptyText: "当前 Agent 尚未绑定知识库" }}
      columns={[
        { title: "名称", dataIndex: "name", width: 220, ellipsis: true },
        { title: "标识", dataIndex: "slug", width: 180, ellipsis: true },
        { title: "分类", dataIndex: "classification", width: 120, ellipsis: true },
        {
          title: "状态",
          dataIndex: "status",
          width: 100,
          render: (status: string) => (
            <BinaryStatusTag active={status === "active"} activeLabel="启用" inactiveLabel="停用" />
          ),
        },
        {
          title: "操作",
          key: "action",
          width: 120,
          align: "right",
          render: (_, item) => (
            <KnowledgeUnbindAction
              disabled={!props.canUpdate || props.isUpdating}
              loading={props.unbindingSpaceId === item.id}
              onChange={() => props.onUnbind(item.id)}
            />
          ),
        },
      ]}
    />
  );
}

function KnowledgeUnbindAction({
  disabled,
  loading,
  onChange,
}: {
  disabled: boolean;
  loading: boolean;
  onChange: () => void;
}) {
  return (
    <Popconfirm
      cancelText="取消"
      description="取消后，该 Agent 将不再从此知识空间检索内容。"
      disabled={disabled}
      okButtonProps={{ danger: true }}
      okText="确认取消"
      onConfirm={onChange}
      title="确认取消知识库绑定？"
    >
      <Button danger disabled={disabled} loading={loading} size="small" type="link">
        取消绑定
      </Button>
    </Popconfirm>
  );
}
