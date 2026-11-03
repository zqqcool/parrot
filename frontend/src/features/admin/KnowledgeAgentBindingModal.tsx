import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Form, Modal, Select } from "antd";

import { adminApi } from "@/shared/api/client";
import type {
  AdminAgent,
  AgentType,
  KnowledgeSpace,
  KnowledgeSpaceAgentBindings,
} from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

import { KnowledgeAgentBindingsTable } from "./KnowledgeAgentBindingsTable";

type BindingChange = "bound" | "unbound";

type Props = {
  open: boolean;
  space: KnowledgeSpace | null;
  tenantId: string;
  onClose: () => void;
  onChanged: (change: BindingChange) => void;
};

type BindingForm = { agentId: string };
const EMPTY_AGENTS: AdminAgent[] = [];
const EMPTY_AGENT_IDS: string[] = [];

function knowledgeSpaceId(space: KnowledgeSpace | null) {
  return space ? space.id : "";
}

function agentItems(agents: AdminAgent[] | undefined) {
  return agents ?? EMPTY_AGENTS;
}

function bindingAgentIds(bindings: KnowledgeSpaceAgentBindings | undefined) {
  return bindings?.agent_ids ?? EMPTY_AGENT_IDS;
}

function canLoadBindings(open: boolean, spaceId: string) {
  return open && spaceId.length > 0;
}

function requestError(...errors: Array<Error | null>) {
  return errors.find((error): error is Error => error !== null) ?? null;
}

function canAddBinding(loading: boolean, bindingsFailed: boolean, availableCount: number) {
  if (loading || bindingsFailed) return false;
  return availableCount > 0;
}

function bindingButtonText(agent: AdminAgent | undefined) {
  return agent?.allow_anonymous ? "确认并扩大匿名检索范围" : "关联 Agent";
}

function selectableAgents(
  agents: AdminAgent[],
  agentTypes: AgentType[],
  boundAgentIds: Set<string>,
) {
  const knowledgeTypeKeys = new Set(
    agentTypes.filter((agentType) => agentType.uses_knowledge).map((agentType) => agentType.key),
  );
  return agents.filter(
    (agent) =>
      knowledgeTypeKeys.has(agent.agent_type_key) &&
      agent.published &&
      agent.status === "active" &&
      !boundAgentIds.has(agent.id),
  );
}

function bindingTitle(space: KnowledgeSpace | null) {
  return space ? `关联 Agent · ${space.name}` : "关联 Agent";
}

function bindingQueryKey(tenantId: string, spaceId: string | undefined) {
  return ["admin", tenantId, "knowledge-spaces", spaceId, "agents"] as const;
}

function BindingScopeNotice({ agent }: { agent: AdminAgent | undefined }) {
  if (agent?.allow_anonymous) {
    return (
      <Alert
        showIcon
        type="warning"
        message="该 Agent 允许匿名访问。关联后，匿名访客也可能通过该 Agent 检索当前知识库。"
      />
    );
  }
  return (
    <Alert
      showIcon
      type="info"
      message="只有已发布且启用的知识型 Agent 可新增关联；已有的停用或未发布 Agent 仍会显示，并可解除关联。"
    />
  );
}

export function KnowledgeAgentBindingModal({ open, space, tenantId, onClose, onChanged }: Props) {
  const [form] = Form.useForm<BindingForm>();
  const client = useQueryClient();
  const agentId = Form.useWatch("agentId", form);
  const spaceId = knowledgeSpaceId(space);
  const queryKey = bindingQueryKey(tenantId, spaceId);
  const agents = useQuery({
    queryKey: ["admin", tenantId, "agents"],
    queryFn: () => adminApi.listAgents(tenantId),
    enabled: open,
  });
  const agentTypes = useQuery({
    queryKey: ["admin", "agent-types"],
    queryFn: () => adminApi.listAgentTypes(),
    enabled: open,
  });
  const bindings = useQuery({
    queryKey,
    queryFn: () => adminApi.getKnowledgeSpaceAgents(tenantId, spaceId),
    enabled: canLoadBindings(open, spaceId),
  });
  const boundAgentIds = useMemo(() => new Set(bindingAgentIds(bindings.data)), [bindings.data]);
  const availableAgents = useMemo(
    () => selectableAgents(agentItems(agents.data), agentTypes.data ?? [], boundAgentIds),
    [agents.data, agentTypes.data, boundAgentIds],
  );
  const agentById = useMemo(
    () => new Map(agentItems(agents.data).map((agent) => [agent.id, agent])),
    [agents.data],
  );
  const boundAgents = bindingAgentIds(bindings.data).flatMap((id) => {
    const agent = agentById.get(id);
    return agent ? [agent] : [];
  });
  const selectedAgent = availableAgents.find((agent) => agent.id === agentId);

  const updateBindingCache = (targetAgentId: string, include: boolean) => {
    client.setQueryData<KnowledgeSpaceAgentBindings>(queryKey, (current) => {
      const ids = new Set(current?.agent_ids ?? []);
      if (include) ids.add(targetAgentId);
      else ids.delete(targetAgentId);
      return { agent_ids: [...ids] };
    });
  };
  const bind = useMutation({
    mutationFn: (targetAgentId: string) =>
      adminApi.addAgentKnowledgeSpace(tenantId, targetAgentId, spaceId),
    onSuccess: (agentBindings, targetAgentId) => {
      client.setQueryData(
        ["admin", tenantId, "agents", targetAgentId, "knowledge-spaces"],
        agentBindings,
      );
      updateBindingCache(targetAgentId, true);
      form.resetFields();
      onChanged("bound");
    },
  });
  const unbind = useMutation({
    mutationFn: (targetAgentId: string) =>
      adminApi.removeAgentKnowledgeSpace(tenantId, targetAgentId, spaceId),
    onSuccess: (agentBindings, targetAgentId) => {
      client.setQueryData(
        ["admin", tenantId, "agents", targetAgentId, "knowledge-spaces"],
        agentBindings,
      );
      updateBindingCache(targetAgentId, false);
      onChanged("unbound");
    },
  });

  const close = () => {
    form.resetFields();
    bind.reset();
    unbind.reset();
    onClose();
  };
  const submit = () => {
    void form
      .validateFields()
      .then(({ agentId: targetAgentId }) => bind.mutate(targetAgentId))
      .catch(() => undefined);
  };
  const loading = agents.isPending || agentTypes.isPending || bindings.isPending;
  const bindingFailed = bindings.isError || agentTypes.isError;

  return (
    <Modal
      destroyOnHidden
      footer={<Button onClick={close}>关闭</Button>}
      open={open}
      title={bindingTitle(space)}
      width={720}
      onCancel={close}
    >
      <h3>已关联 Agent</h3>
      <KnowledgeAgentBindingsTable
        agents={boundAgents}
        loading={loading}
        unbinding={unbind.isPending}
        unbindingAgentId={unbind.variables}
        onUnbind={unbind.mutate}
      />
      <h3>新增关联</h3>
      <Form className="admin-modal-form" form={form} layout="vertical">
        <Form.Item
          label="目标 Agent"
          name="agentId"
          rules={[{ required: true, message: "请选择 Agent" }]}
        >
          <Select
            loading={agents.isPending || agentTypes.isPending}
            optionFilterProp="label"
            options={availableAgents.map((agent) => ({
              value: agent.id,
              label: `${agent.name}（${agent.slug}）`,
            }))}
            placeholder="选择尚未关联的已发布知识型 Agent"
            showSearch
          />
        </Form.Item>
        <Form.Item label="关联操作">
          <Button
            block
            type="primary"
            disabled={!canAddBinding(loading, bindingFailed, availableAgents.length)}
            loading={bind.isPending}
            onClick={submit}
          >
            {bindingButtonText(selectedAgent)}
          </Button>
        </Form.Item>
      </Form>
      <BindingScopeNotice agent={selectedAgent} />
      <RequestErrorAlert
        error={requestError(
          agents.error,
          agentTypes.error,
          bindings.error,
          bind.error,
          unbind.error,
        )}
        fallback="管理知识库 Agent 关联失败"
      />
    </Modal>
  );
}
