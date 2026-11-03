import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Popconfirm, Select, Space, Tag, message } from "antd";
import { useNavigate } from "react-router-dom";

import { KnowledgeAgentBindingModal } from "@/features/admin/KnowledgeAgentBindingModal";
import { KnowledgeMergeSettingsModal } from "@/features/admin/KnowledgeMergeSettingsModal";
import { KnowledgeMergeSettingsSummary } from "@/features/admin/KnowledgeMergeSettingsSummary";
import {
  embeddingSummary,
  indexStatus,
  retrievalPolicy,
} from "@/features/admin/KnowledgeSpaceRetrievalSummary";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { useTenantId } from "@/features/admin/useTenant";
import { adminApi } from "@/shared/api/client";
import type { KnowledgeSpace } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { formatDateTime } from "@/shared/time";
import {
  AdminPageHeader,
  CreateButton,
  DataTable,
  RequestErrorAlert,
  SearchBar,
  useDebouncedValue,
} from "@/shared/ui";

import "./knowledge-page.css";

type ClassificationFilter = "all" | "standard" | "restricted";

function canBindKnowledgeAgent(hasPermission: (permission: string) => boolean) {
  return (
    hasPermission("knowledge.spaces.manage") &&
    hasPermission("knowledge.spaces.read") &&
    hasPermission("agents.read") &&
    hasPermission("agents.manage")
  );
}

export function KnowledgePage() {
  const tenantId = useTenantId();
  const auth = useAuth();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [messageApi, messageContext] = message.useMessage();
  const [bindingSpace, setBindingSpace] = useState<KnowledgeSpace | null>(null);
  const [mergeSettingsOpen, setMergeSettingsOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const searchQuery = useDebouncedValue(searchValue.trim());
  const [classification, setClassification] = useState<ClassificationFilter>("all");
  const canManageSpaces = auth.hasPermission("knowledge.spaces.manage");
  const canConfigureMerge = canManageSpaces && auth.hasPermission("llm_configs.read");
  const canBindAgent = canBindKnowledgeAgent(auth.hasPermission);
  const spaces = useQuery({
    queryKey: ["admin", tenantId, "knowledge-spaces", searchQuery],
    queryFn: () => adminApi.listKnowledgeSpaces(tenantId ?? "", searchQuery),
    enabled: Boolean(tenantId),
  });
  const remove = useMutation({
    mutationFn: (space: KnowledgeSpace) => adminApi.deleteKnowledgeSpace(tenantId ?? "", space.id),
    onSuccess: async (_result, deletedSpace) => {
      if (bindingSpace?.id === deletedSpace.id) setBindingSpace(null);
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "knowledge-spaces"] });
      void messageApi.success(`知识库“${deletedSpace.name}”已删除`);
    },
  });

  if (!tenantId) return <TenantRequiredState />;

  const filteredSpaces = (spaces.data ?? []).filter(
    (space) => classification === "all" || space.classification === classification,
  );

  return (
    <section className="knowledge-page">
      {messageContext}
      <AdminPageHeader
        title="知识库"
        description="集中管理当前租户可访问的知识空间与文档；知识型 Agent 仅会检索在其工作台中实时绑定的知识空间。"
      />
      <Alert
        action={<KnowledgeMergeSettingsSummary tenantId={tenantId} />}
        className="knowledge-page-info"
        showIcon
        type="info"
        message="知识空间授权控制管理台访问；Agent 运行时读取范围由 Agent 的知识库绑定决定。"
      />
      <SearchBar
        actions={
          canManageSpaces ? (
            <Space>
              {canConfigureMerge ? (
                <Button onClick={() => setMergeSettingsOpen(true)}>多库合并配置</Button>
              ) : null}
              <CreateButton onClick={() => void navigate("/admin/knowledge/new")}>
                新建知识库
              </CreateButton>
            </Space>
          ) : null
        }
        advancedFilters={
          <Select
            aria-label="按分类筛选知识库"
            options={[
              { value: "all", label: "全部分类" },
              { value: "standard", label: "标准" },
              { value: "restricted", label: "受限" },
            ]}
            value={classification}
            onChange={setClassification}
          />
        }
        hasActiveFilters={classification !== "all"}
        placeholder="搜索知识库名称或分类"
        value={searchValue}
        onChange={setSearchValue}
        onReset={() => {
          setSearchValue("");
          setClassification("all");
        }}
      />
      <RequestErrorAlert error={spaces.error} fallback="加载知识库失败" />
      <DataTable<KnowledgeSpace>
        rowKey="id"
        loading={spaces.isFetching}
        dataSource={filteredSpaces}
        resetPaginationKey={`${searchQuery}:${classification}`}
        scroll={{ x: 1560 }}
        locale={{ emptyText: "当前账号暂无可管理的知识库" }}
        columns={[
          { title: "名称", dataIndex: "name", width: 180, ellipsis: true },
          { title: "分类", dataIndex: "classification", width: 88, render: classificationTag },
          {
            title: "检索策略",
            width: 150,
            render: (_: unknown, item: KnowledgeSpace) => retrievalPolicy(item),
          },
          {
            title: "Embedding",
            width: 230,
            render: (_: unknown, item: KnowledgeSpace) => embeddingSummary(item),
          },
          {
            title: "索引状态",
            width: 120,
            render: (_: unknown, item: KnowledgeSpace) => indexStatus(item),
          },
          { title: "候选 Top K", dataIndex: "candidate_top_k", width: 100, align: "right" },
          {
            title: "状态",
            dataIndex: "status",
            width: 88,
            render: spaceStatus,
          },
          { title: "访问版本", dataIndex: "access_revision", width: 96, align: "right" },
          { title: "创建时间", dataIndex: "created_at", width: 180, render: formatDateTime },
          {
            title: "操作",
            width: 110 + (canBindAgent ? 76 : 0) + (canManageSpaces ? 52 : 0),
            render: (_: unknown, item: KnowledgeSpace) => (
              <Space size={4}>
                <Button
                  size="small"
                  type="link"
                  onClick={() => void navigate(`/admin/knowledge/${item.id}/documents`)}
                >
                  查看文档
                </Button>
                {canBindAgent ? (
                  <Button size="small" type="link" onClick={() => setBindingSpace(item)}>
                    关联 Agent
                  </Button>
                ) : null}
                {canManageSpaces ? (
                  <Popconfirm
                    title={`删除知识库“${item.name}”？`}
                    description="仅无 Agent 关联且已清空文档与上传源的知识库可删除；删除后无法恢复。"
                    okText="确认删除"
                    cancelText="取消"
                    okButtonProps={{
                      danger: true,
                      loading: remove.isPending && remove.variables?.id === item.id,
                    }}
                    onConfirm={() => {
                      void remove.mutateAsync(item).catch(() => undefined);
                    }}
                  >
                    <Button
                      danger
                      disabled={remove.isPending && remove.variables?.id === item.id}
                      size="small"
                      type="link"
                    >
                      删除
                    </Button>
                  </Popconfirm>
                ) : null}
              </Space>
            ),
          },
        ]}
      />
      <KnowledgeAgentBindingModal
        open={Boolean(bindingSpace)}
        space={bindingSpace}
        tenantId={tenantId}
        onClose={() => setBindingSpace(null)}
        onChanged={(change) =>
          void messageApi.success(change === "bound" ? "Agent 关联成功" : "Agent 关联已解除")
        }
      />
      {canConfigureMerge ? (
        <KnowledgeMergeSettingsModal
          open={mergeSettingsOpen}
          tenantId={tenantId}
          onClose={() => setMergeSettingsOpen(false)}
        />
      ) : null}
    </section>
  );
}

function classificationTag(value: string) {
  return (
    <Tag color={value === "restricted" ? "orange" : "blue"}>
      {value === "restricted" ? "受限" : "标准"}
    </Tag>
  );
}

function spaceStatus(value: string) {
  return (
    <Tag color={value === "active" ? "success" : "default"}>
      {value === "active" ? "启用" : "停用"}
    </Tag>
  );
}
