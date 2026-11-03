import { useEffect, useState } from "react";
import { Button } from "antd";

import { AgentKnowledgeBindingPicker } from "@/features/admin/AgentKnowledgeBindingPicker";
import type { KnowledgeSpace } from "@/shared/api/types";
import { AppIcon } from "@/shared/icons";

type Props = {
  anonymousDisclosure: boolean;
  availableSpaces: KnowledgeSpace[];
  bindingDisabled: boolean;
  canManage: boolean;
  canQuery: boolean;
  isBinding: boolean;
  usesKnowledge: boolean;
  onBind: (spaceId: string) => void;
  onOpenTest: () => void;
};

export function AgentKnowledgeToolbar({
  anonymousDisclosure,
  availableSpaces,
  bindingDisabled,
  canManage,
  canQuery,
  isBinding,
  usesKnowledge,
  onBind,
  onOpenTest,
}: Props) {
  const [selectedSpaceId, setSelectedSpaceId] = useState<string>();
  const testDisabled = !canQuery || !usesKnowledge;

  useEffect(() => {
    if (!selectedSpaceId || availableSpaces.some((space) => space.id === selectedSpaceId)) {
      return;
    }
    setSelectedSpaceId(undefined);
  }, [availableSpaces, selectedSpaceId]);

  return (
    <div className="agent-knowledge-toolbar">
      {canManage ? (
        <AgentKnowledgeBindingPicker
          anonymousDisclosure={anonymousDisclosure}
          disabled={bindingDisabled}
          loading={isBinding}
          selectedSpaceId={selectedSpaceId}
          spaces={availableSpaces}
          onBind={() => {
            if (selectedSpaceId) onBind(selectedSpaceId);
          }}
          onSelect={setSelectedSpaceId}
        />
      ) : null}
      <Button
        color="primary"
        disabled={testDisabled}
        icon={<AppIcon name="Search" size="sm" />}
        title={testDisabled ? searchTestDisabledReason(canQuery) : undefined}
        variant="outlined"
        onClick={onOpenTest}
      >
        真实检索测试
      </Button>
    </div>
  );
}

function searchTestDisabledReason(canQuery: boolean) {
  return canQuery ? "当前 Agent 类型不会读取知识库" : "当前账号没有执行知识库检索测试的权限";
}
