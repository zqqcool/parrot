import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import { adminApi } from "@/shared/api/client";
import type {
  KnowledgeDocument,
  KnowledgeDocumentCreate,
  KnowledgeIngestion,
} from "@/shared/api/types";
import { saveDownloadedFile } from "@/shared/downloads";

export type IngestionJob = Pick<KnowledgeIngestion, "id"> & {
  spaceId: string;
  title: string;
  initial: KnowledgeIngestion;
};

export type IngestionQueueItem = IngestionJob & {
  status: string;
  errorCode: string | null;
  error: Error | null;
};

type Options = {
  tenantId: string;
  spaceId: string | undefined;
  canRead: boolean;
  query: string;
};

export function useKnowledgeDocuments({ tenantId, spaceId, canRead, query }: Options) {
  const client = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [replacing, setReplacing] = useState<KnowledgeDocument | null>(null);
  const [ingestionJobs, setIngestionJobs] = useState<IngestionJob[]>([]);
  const [dismissedJobIds, setDismissedJobIds] = useState<Set<string>>(new Set());
  const resolvedSpaceId = spaceId ?? "";
  const recoveredJobs = useActiveIngestionsQuery(tenantId, resolvedSpaceId, canRead);
  const currentIngestionJobs = mergeIngestionJobs(
    recoveredJobs.data ?? [],
    ingestionJobs,
    resolvedSpaceId,
    dismissedJobIds,
  );
  const { documentQueryKey, documents } = useDocumentsQuery(
    tenantId,
    resolvedSpaceId,
    canRead,
    query,
  );
  const ingestionItems = useIngestionQueries(tenantId, currentIngestionJobs);
  const { archive, create, download } = useDocumentMutations(
    tenantId,
    resolvedSpaceId,
    documentQueryKey,
    () => setCreating(false),
  );

  useRefreshDocumentsAfterIngestion(client, documentQueryKey, ingestionItems);

  return {
    archive,
    archivingDocumentId: pendingDocumentId(archive.isPending, archive.variables),
    create,
    creating,
    documentQueryKey,
    documents,
    download,
    downloadingDocumentId: pendingDocumentId(download.isPending, download.variables),
    ingestionItems,
    queueIngestion: (job: KnowledgeIngestion, title: string) => {
      setDismissedJobIds((current) => {
        const next = new Set(current);
        next.delete(job.id);
        return next;
      });
      setIngestionJobs((current) => [
        ...current.filter((item) => item.id !== job.id),
        { id: job.id, spaceId: resolvedSpaceId, title, initial: job },
      ]);
      setReplacing(null);
      void client.invalidateQueries({ queryKey: documentQueryKey });
    },
    refreshDocuments: () => client.invalidateQueries({ queryKey: documentQueryKey }),
    dismissIngestions: () => {
      setDismissedJobIds(
        (current) => new Set([...current, ...currentIngestionJobs.map((job) => job.id)]),
      );
      setIngestionJobs((current) => current.filter((job) => job.spaceId !== resolvedSpaceId));
    },
    setCreating,
    setReplacing,
    setUploading,
    uploading,
    replacing,
  };
}

function pendingDocumentId(isPending: boolean, document: KnowledgeDocument | undefined) {
  return isPending && document ? document.id : null;
}

function useActiveIngestionsQuery(tenantId: string, spaceId: string, canRead: boolean) {
  return useQuery({
    queryKey: ["admin", tenantId, "knowledge-spaces", spaceId, "active-ingestions"],
    queryFn: () => adminApi.listActiveKnowledgeIngestions(tenantId, spaceId),
    enabled: Boolean(spaceId) && canRead,
  });
}

function mergeIngestionJobs(
  recovered: KnowledgeIngestion[],
  local: IngestionJob[],
  spaceId: string,
  dismissed: Set<string>,
): IngestionJob[] {
  const jobs = new Map<string, IngestionJob>();
  for (const job of recovered) {
    if (!dismissed.has(job.id)) {
      jobs.set(job.id, { id: job.id, title: job.title, spaceId, initial: job });
    }
  }
  for (const job of local) {
    if (job.spaceId === spaceId && !dismissed.has(job.id)) jobs.set(job.id, job);
  }
  return [...jobs.values()];
}

function useDocumentsQuery(tenantId: string, spaceId: string, canRead: boolean, query: string) {
  const documentQueryKey = useMemo(
    () => ["admin", tenantId, "knowledge-spaces", spaceId, "documents", query],
    [query, spaceId, tenantId],
  );
  const documents = useQuery({
    queryKey: documentQueryKey,
    queryFn: () => adminApi.listKnowledgeDocuments(tenantId, spaceId, query),
    enabled: Boolean(spaceId) && canRead,
  });
  return { documentQueryKey, documents };
}

function useIngestionQueries(tenantId: string, jobs: IngestionJob[]): IngestionQueueItem[] {
  const queries = useQueries({
    queries: jobs.map((job) => ({
      queryKey: ["admin", tenantId, "knowledge-ingestions", job.id],
      queryFn: () => adminApi.getKnowledgeIngestion(tenantId, job.id),
      initialData: job.initial,
      refetchInterval: (query: { state: { data?: KnowledgeIngestion } }) =>
        isTerminalIngestion(query.state.data?.status) ? false : 2_000,
    })),
  });
  return jobs.map((job, index) => {
    const query = queries[index];
    const data = query?.data ?? job.initial;
    return {
      ...job,
      status: data.status,
      errorCode: data.error_code,
      error: query?.error instanceof Error ? query.error : null,
    };
  });
}

function useDocumentMutations(
  tenantId: string,
  spaceId: string,
  queryKey: readonly unknown[],
  onCreateSuccess: () => void,
) {
  const client = useQueryClient();
  const create = useMutation({
    mutationFn: (payload: KnowledgeDocumentCreate) =>
      adminApi.createKnowledgeDocument(tenantId, spaceId, payload),
    onSuccess: async () => {
      onCreateSuccess();
      await client.invalidateQueries({ queryKey });
    },
  });
  const archive = useMutation({
    mutationFn: (document: KnowledgeDocument) =>
      adminApi.archiveKnowledgeDocument(tenantId, document.id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey });
    },
  });
  const download = useMutation({
    mutationFn: async (document: KnowledgeDocument) => {
      const versions = await adminApi.listKnowledgeDocumentVersions(tenantId, document.id);
      const version = versions.find(
        (item) => item.version === document.current_version && item.status === "published",
      );
      if (!version) throw new Error("当前发布版本的源文件不可用");
      return adminApi.downloadKnowledgeDocumentVersion(tenantId, document.id, version.id);
    },
    onSuccess: saveDownloadedFile,
  });
  return { archive, create, download };
}

function useRefreshDocumentsAfterIngestion(
  client: ReturnType<typeof useQueryClient>,
  queryKey: readonly unknown[],
  items: IngestionQueueItem[],
) {
  const terminalJobs = items
    .filter((item) => isTerminalIngestion(item.status))
    .map((item) => item.id)
    .sort()
    .join(",");
  useEffect(() => {
    if (!terminalJobs) return;
    void client.invalidateQueries({ queryKey });
  }, [client, queryKey, terminalJobs]);
}

export function isTerminalIngestion(status: string | undefined) {
  return status === "succeeded" || status === "failed";
}
