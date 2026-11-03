import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Tabs } from "antd";

import { createAgentKnowledgeTab } from "@/features/admin/AgentKnowledgeTab";
import { AgentMcpSection } from "@/features/admin/AgentMcpSection";
import { AgentSchedulesSection } from "@/features/admin/AgentSchedulesSection";
import { AgentWebsocketSection } from "@/features/admin/AgentWebsocketSection";
import { LlmSection, SkillSection } from "@/features/admin/AgentBindingTables";
import { BasicSection, AccessSection, LoadState } from "@/features/admin/AgentBindingSections";
import { adminApi } from "@/shared/api/client";
import type { AdminAgent as Agent, AgentType } from "@/shared/api/types";

type Props = {
  tenantId: string;
  agent: Agent;
  agentType: AgentType;
  canManage: boolean;
  canManageSchedules: boolean;
  canQuery: boolean;
  canPublish: boolean;
  canReadKnowledge: boolean;
  canReadMcp: boolean;
  activeTab: string;
  onTabChange: (tab: string) => void;
  onSuccessMessage: (content: string) => void;
  onEditAnonymousAccess: () => void;
  onEditBasic: () => void;
  onEditSystemPrompt: () => void;
};

export function AgentBindingsEditor({
  tenantId,
  agent,
  agentType,
  canPublish,
  canManage,
  canManageSchedules,
  canQuery,
  canReadKnowledge,
  canReadMcp,
  activeTab,
  onTabChange,
  onSuccessMessage,
  onEditAnonymousAccess,
  onEditBasic,
  onEditSystemPrompt,
}: Props) {
  const client = useQueryClient();
  const [llmId, setLlmId] = useState<string>();
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const llms = useQuery({
    queryKey: ["admin", tenantId, "llm-configs"],
    queryFn: () => adminApi.listLlmConfigs(tenantId),
    enabled: activeTab === "llm",
  });
  const skills = useQuery({
    queryKey: ["admin", tenantId, "skills"],
    queryFn: () => adminApi.listSkills(tenantId),
    enabled: activeTab === "skills",
  });
  const llmBindings = useQuery({
    queryKey: ["admin", tenantId, "agents", agent.id, "llm-configs"],
    queryFn: () => adminApi.getAgentLlmBindings(tenantId, agent.id),
    enabled: activeTab === "llm",
  });
  const skillBindings = useQuery({
    queryKey: ["admin", tenantId, "agents", agent.id, "skills"],
    queryFn: () => adminApi.getAgentSkillBindings(tenantId, agent.id),
    enabled: activeTab === "skills",
  });
  useEffect(() => {
    if (llmBindings.data) {
      setLlmId(llmBindings.data.default_id ?? llmBindings.data.ids[0]);
    }
  }, [llmBindings.data]);
  useEffect(() => {
    if (skillBindings.data) setSkillIds([...skillBindings.data.ids]);
  }, [skillBindings.data]);

  const selectLlm = useMutation({
    mutationFn: ({ id }: { id: string }) =>
      adminApi.replaceAgentLlmBindings(tenantId, agent.id, {
        ids: [id],
        default_id: id,
      }),
    onMutate: ({ id }) => {
      const previousId = llmId;
      setLlmId(id);
      return { previousId };
    },
    onError: (_, __, context) => {
      setLlmId(context?.previousId);
    },
    onSuccess: (data) => {
      client.setQueryData(["admin", tenantId, "agents", agent.id, "llm-configs"], data);
      setLlmId(data.default_id ?? data.ids[0]);
      onSuccessMessage("模型配置已切换");
    },
  });
  const saveSkills = useMutation({
    mutationFn: ({ ids }: { ids: string[]; skillId?: string }) =>
      adminApi.replaceAgentSkillBindings(tenantId, agent.id, { ids }),
    onMutate: ({ ids }) => {
      const previousIds = skillIds;
      setSkillIds(ids);
      return { previousIds };
    },
    onError: (_, __, context) => {
      setSkillIds(context?.previousIds ?? []);
    },
    onSuccess: (data) => {
      client.setQueryData(["admin", tenantId, "agents", agent.id, "skills"], data);
      setSkillIds([...data.ids]);
      onSuccessMessage("Skill 授权已更新");
    },
  });
  const publish = useMutation({
    mutationFn: () => adminApi.updateAgent(tenantId, agent.id, { published: !agent.published }),
    onSuccess: async (updated) => {
      client.setQueryData<Agent[]>(["admin", tenantId, "agents"], (items) =>
        items?.map((item) => (item.id === updated.id ? updated : item)),
      );
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "dashboard"] });
      onSuccessMessage(updated.published ? "智能体已发布" : "智能体已下线");
    },
  });
  const updateStatus = useMutation({
    mutationFn: () =>
      adminApi.updateAgent(tenantId, agent.id, {
        status: agent.status === "active" ? "disabled" : "active",
      }),
    onSuccess: (updated) => {
      client.setQueryData<Agent[]>(["admin", tenantId, "agents"], (items) =>
        items?.map((item) => (item.id === updated.id ? updated : item)),
      );
      onSuccessMessage(updated.status === "active" ? "智能体已启用" : "智能体已停用");
    },
  });
  const queries =
    activeTab === "llm"
      ? [llms, llmBindings]
      : activeTab === "skills"
        ? [skills, skillBindings]
        : [];
  const loadError = queries.find((query) => query.error)?.error;
  const loading = queries.some((query) => query.isPending);
  const onSkillToggle = (skillId: string) => {
    const ids = skillIds.includes(skillId)
      ? skillIds.filter((id) => id !== skillId)
      : [...skillIds, skillId];
    saveSkills.mutate({ ids, skillId });
  };
  const clearIncompatibleSkills = (ids: string[]) => saveSkills.mutate({ ids });

  return (
    <LoadState error={loadError} pending={loading}>
      <Tabs
        activeKey={activeTab}
        className="agent-workspace-tabs"
        onChange={onTabChange}
        items={[
          {
            key: "basic",
            label: "基础设定",
            children: (
              <BasicSection
                agent={agent}
                canManage={canManage}
                onEditBasic={onEditBasic}
                onEditSystemPrompt={onEditSystemPrompt}
              >
                <AccessSection
                  agent={agent}
                  canManage={canManage}
                  canPublish={canPublish}
                  publishPending={publish.isPending}
                  onPublish={() => publish.mutate()}
                  onEditAnonymousAccess={onEditAnonymousAccess}
                  onStatusChange={() => updateStatus.mutate()}
                  statusPending={updateStatus.isPending}
                />
              </BasicSection>
            ),
          },
          {
            key: "llm",
            label: "模型配置",
            children: (
              <LlmSection
                canManage={canManage}
                items={llms.data ?? []}
                selectedId={llmId}
                selectingId={selectLlm.variables?.id}
                error={selectLlm.error}
                onSelect={(id) => selectLlm.mutate({ id })}
              />
            ),
          },
          {
            key: "skills",
            label: "Skill",
            children: (
              <SkillSection
                restrictsExecutableSkills={agentType.restricts_executable_skills}
                canManage={canManage}
                items={skills.data ?? []}
                ids={skillIds}
                saving={saveSkills.isPending}
                savingSkillId={saveSkills.variables?.skillId}
                error={saveSkills.error}
                onClearIncompatible={clearIncompatibleSkills}
                onToggle={onSkillToggle}
              />
            ),
          },
          {
            key: "schedules",
            label: "定时任务",
            children: (
              <AgentSchedulesSection
                agent={agent}
                canManage={canManageSchedules}
                tenantId={tenantId}
              />
            ),
          },
          {
            key: "mcp",
            label: "MCP",
            children: (
              <AgentMcpSection
                agent={agent}
                canManage={canManage}
                canRead={canReadMcp}
                tenantId={tenantId}
                onSaved={() => onSuccessMessage("MCP 服务关联已更新")}
              />
            ),
          },
          createAgentKnowledgeTab({
            agent,
            usesKnowledge: agentType.uses_knowledge,
            canManage,
            canQuery,
            canRead: canReadKnowledge,
            tenantId,
            onSuccessMessage,
          }),
          {
            key: "integrations",
            label: "集成信息",
            children: (
              <AgentWebsocketSection
                agent={agent}
                canManage={canManage}
                tenantId={tenantId}
                onSaved={onSuccessMessage}
              />
            ),
          },
        ]}
      />
    </LoadState>
  );
}
