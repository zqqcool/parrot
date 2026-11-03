import { Button } from "antd";

import type { KnowledgeSpace } from "@/shared/api/types";
import { AppIcon } from "@/shared/icons";

type Props = {
  canManage: boolean;
  canQuery: boolean;
  space: KnowledgeSpace;
  onOpenAdd: () => void;
  onOpenSearch: () => void;
};

export function KnowledgeDocumentsHeading({
  canManage,
  canQuery,
  space,
  onOpenAdd,
  onOpenSearch,
}: Props) {
  return (
    <div className="knowledge-documents-heading">
      <div>
        <h2 id="knowledge-documents-heading">{space.name} · 文档</h2>
        <p>上传文件或录入文本；文档归档后会立即停止被 Agent 检索。</p>
      </div>
      <div className="knowledge-documents-actions">
        {canQuery ? (
          <Button
            ghost
            type="primary"
            icon={<AppIcon name="Search" size="md" />}
            onClick={onOpenSearch}
          >
            检索测试
          </Button>
        ) : null}
        {canManage ? (
          <Button
            type="primary"
            icon={<AppIcon name="FileAddition" size="md" />}
            onClick={onOpenAdd}
          >
            添加文档
          </Button>
        ) : null}
      </div>
    </div>
  );
}
