import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { adminApi } from "@/shared/api/client";
import type { KnowledgeSourceActivityPage } from "@/shared/api/types";

const SOURCE_ACTIVITY_PAGE_SIZE = 100;
const ACTIVE_SOURCE_STATUSES = new Set(["queued", "processing"]);

type Options = {
  tenantId: string;
  spaceId: string | undefined;
  canRead: boolean;
};

export function useKnowledgeSourceActivity({ tenantId, spaceId, canRead }: Options) {
  const client = useQueryClient();
  const resolvedSpaceId = spaceId ?? "";
  const queryPrefix = useMemo(
    () => ["admin", tenantId, "knowledge-spaces", resolvedSpaceId, "sources"] as const,
    [resolvedSpaceId, tenantId],
  );
  const query = useQuery({
    queryKey: [...queryPrefix, SOURCE_ACTIVITY_PAGE_SIZE],
    queryFn: () =>
      adminApi.listKnowledgeSources(tenantId, resolvedSpaceId, 1, SOURCE_ACTIVITY_PAGE_SIZE),
    enabled: Boolean(resolvedSpaceId) && canRead,
    refetchInterval: ({ state }) => (hasActiveSources(state.data) ? 2_000 : false),
  });
  const refresh = () => client.invalidateQueries({ queryKey: queryPrefix });
  const retryConfirmation = useMutation({
    mutationFn: (sourceId: string) =>
      adminApi.retryKnowledgeDocumentUploadConfirmation(tenantId, sourceId),
    onSuccess: refresh,
  });
  const cleanupStagingSource = useMutation({
    mutationFn: (sourceId: string) => adminApi.cleanupKnowledgeDocumentUpload(tenantId, sourceId),
    onSuccess: refresh,
  });

  return {
    query,
    refresh,
    retryConfirmation,
    cleanupStagingSource,
    pendingSourceId: retryConfirmation.isPending
      ? (retryConfirmation.variables ?? null)
      : cleanupStagingSource.isPending
        ? (cleanupStagingSource.variables ?? null)
        : null,
  };
}

function hasActiveSources(page: KnowledgeSourceActivityPage | undefined) {
  return page?.items.some((item) => ACTIVE_SOURCE_STATUSES.has(item.status)) ?? false;
}
