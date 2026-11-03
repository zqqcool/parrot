import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { adminApi } from "@/shared/api/client";
import type { AdminAgent } from "@/shared/api/types";

type RecallRequest = {
  query: string;
  relevance_threshold?: number;
};

export type CapabilityRecallSearch<TResult> = (
  tenantId: string,
  agentId: string,
  payload: RecallRequest,
) => Promise<TResult>;

type Args<TResult> = {
  open: boolean;
  tenantId: string;
  canManageAgent: boolean;
  search: CapabilityRecallSearch<TResult>;
  onClose: () => void;
};

export function useCapabilityRecallController<TResult>(args: Args<TResult>) {
  const [agentId, setAgentId] = useState<string>();
  const [query, setQuery] = useState("");
  const [threshold, setThreshold] = useState<number | null>(null);
  const [configuredThreshold, setConfiguredThreshold] = useState<number | null>(null);
  const resources = useRecallResources({
    agentId,
    open: args.open,
    query,
    search: args.search,
    tenantId: args.tenantId,
    threshold,
    onThresholdSaved: setConfiguredThreshold,
  });
  const canSubmit = recallAllowed(agentId, query, threshold, resources.recall.isPending);
  const canSave = thresholdSaveAllowed(
    args.canManageAgent,
    agentId,
    threshold,
    configuredThreshold,
    resources.saveThreshold.isPending,
  );
  const actions = controllerActions({
    agents: resources.agents.data,
    canSubmit,
    onClose: args.onClose,
    recall: { mutate: resources.recall.mutate, reset: resources.recall.reset },
    save: { reset: resources.saveThreshold.reset },
    setAgentId,
    setConfiguredThreshold,
    setQuery,
    setThreshold,
  });
  return {
    agentId,
    agentOptions: (resources.agents.data ?? []).map((agent) => ({
      label: agent.name,
      value: agent.id,
    })),
    canSave,
    canSubmit,
    canManageAgent: args.canManageAgent,
    query,
    threshold,
    ...resources,
    ...actions,
  };
}

type ResourceArgs<TResult> = Pick<Args<TResult>, "open" | "search" | "tenantId"> & {
  agentId: string | undefined;
  query: string;
  threshold: number | null;
  onThresholdSaved: (value: number) => void;
};

function useRecallResources<TResult>(args: ResourceArgs<TResult>) {
  const client = useQueryClient();
  const queryKey = ["admin", args.tenantId, "agents", "capability-recall"] as const;
  const agents = useQuery({
    queryKey,
    queryFn: () => adminApi.listAgents(args.tenantId),
    enabled: args.open,
  });
  const recall = useMutation({
    mutationFn: () =>
      args.search(args.tenantId, args.agentId ?? "", {
        query: args.query.trim(),
        relevance_threshold: optionalThreshold(args.threshold),
      }),
  });
  const saveThreshold = useMutation({
    mutationFn: () =>
      adminApi.updateAgent(args.tenantId, args.agentId ?? "", {
        capability_relevance_threshold: optionalThreshold(args.threshold),
      }),
    onSuccess: (updated) => {
      args.onThresholdSaved(updated.capability_relevance_threshold);
      client.setQueryData<AdminAgent[]>(queryKey, (current) => replaceAgent(current, updated));
    },
  });
  return { agents, recall, saveThreshold };
}

type ActionArgs = {
  agents: AdminAgent[] | undefined;
  canSubmit: boolean;
  onClose: () => void;
  recall: { mutate: () => void; reset: () => void };
  save: { reset: () => void };
  setAgentId: (value: string | undefined) => void;
  setConfiguredThreshold: (value: number | null) => void;
  setQuery: (value: string) => void;
  setThreshold: (value: number | null) => void;
};

function controllerActions(args: ActionArgs) {
  const resetResults = () => {
    args.recall.reset();
    args.save.reset();
  };
  const selectAgent = (value: string) => {
    const selected = args.agents?.find((agent) => agent.id === value);
    const selectedThreshold = selected?.capability_relevance_threshold ?? null;
    args.setAgentId(value);
    args.setThreshold(selectedThreshold);
    args.setConfiguredThreshold(selectedThreshold);
    resetResults();
  };
  const changeThreshold = (value: number | null) => {
    args.setThreshold(value);
    resetResults();
  };
  const changeQuery = (value: string) => {
    args.setQuery(value);
    args.recall.reset();
  };
  const submit = () => {
    if (args.canSubmit) args.recall.mutate();
  };
  const close = () => {
    resetResults();
    args.setAgentId(undefined);
    args.setQuery("");
    args.setThreshold(null);
    args.setConfiguredThreshold(null);
    args.onClose();
  };
  return { changeQuery, changeThreshold, close, selectAgent, submit };
}

function optionalThreshold(value: number | null) {
  return value === null ? undefined : value;
}

function validThreshold(value: number | null) {
  return value !== null && value >= 0 && value <= 1;
}

function recallAllowed(
  agentId: string | undefined,
  query: string,
  threshold: number | null,
  pending: boolean,
) {
  return Boolean(agentId && query.trim() && validThreshold(threshold) && !pending);
}

function thresholdSaveAllowed(
  canManage: boolean,
  agentId: string | undefined,
  threshold: number | null,
  configuredThreshold: number | null,
  pending: boolean,
) {
  return Boolean(
    canManage &&
    agentId &&
    validThreshold(threshold) &&
    threshold !== configuredThreshold &&
    !pending,
  );
}

function replaceAgent(current: AdminAgent[] | undefined, updated: AdminAgent) {
  return current?.map((agent) => (agent.id === updated.id ? updated : agent));
}
