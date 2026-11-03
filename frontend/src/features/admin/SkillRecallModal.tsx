import { AgentCapabilityRecallModal } from "@/features/admin/AgentCapabilityRecallModal";
import { SkillRecallResult } from "@/features/admin/SkillRecallResult";
import { adminApi } from "@/shared/api/client";
import type { AgentSkillRecall } from "@/shared/api/types";

type Props = {
  open: boolean;
  tenantId: string;
  canManageAgent: boolean;
  onClose: () => void;
};

export function SkillRecallModal(props: Props) {
  return (
    <AgentCapabilityRecallModal<AgentSkillRecall>
      canManageAgent={props.canManageAgent}
      infoMessage="按所选 Agent 的实际绑定召回候选，不会执行 Skill"
      open={props.open}
      queryPlaceholder="例如：我想登记入住，需要提供哪些信息？"
      renderResult={(result) => <SkillRecallResult result={result} />}
      search={adminApi.searchAgentSkills}
      tenantId={props.tenantId}
      title="Skill 召回验证"
      onClose={props.onClose}
    />
  );
}
