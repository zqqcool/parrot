import { useQuery } from "@tanstack/react-query";
import { Tag } from "antd";

import { adminApi } from "@/shared/api/client";

export function KnowledgeMergeSettingsSummary({ tenantId }: { tenantId: string }) {
  const settings = useQuery({
    queryKey: ["admin", tenantId, "knowledge-merge-settings"],
    queryFn: () => adminApi.getKnowledgeMergeSettings(tenantId),
  });
  if (!settings.data) return null;
  if (!settings.data.merge_rerank_enabled) {
    return <Tag>合并重排：关</Tag>;
  }
  return <Tag color="blue">合并重排：开 · TopK={settings.data.result_top_k}</Tag>;
}
