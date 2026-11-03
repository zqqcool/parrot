import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Form, InputNumber, Modal, Select, Switch, message } from "antd";

import {
  activeRerankerConfigs,
  completeMergeSettingsPayload,
  mergeSettingsFormValues,
} from "@/features/admin/knowledgeMergeSettingsForm";
import { adminApi } from "@/shared/api/client";
import type {
  KnowledgeMergeSettings,
  KnowledgeMergeSettingsUpdate,
  RerankerConfig,
} from "@/shared/api/types";

type Props = {
  open: boolean;
  tenantId: string;
  onClose: () => void;
};

export function KnowledgeMergeSettingsModal({ open, tenantId, onClose }: Props) {
  const client = useQueryClient();
  const [form] = Form.useForm<KnowledgeMergeSettingsUpdate>();
  const [messageApi, messageContext] = message.useMessage();
  const mergeRerankEnabled = Form.useWatch("merge_rerank_enabled", form);
  const settings = useQuery({
    queryKey: ["admin", tenantId, "knowledge-merge-settings"],
    queryFn: () => adminApi.getKnowledgeMergeSettings(tenantId),
    enabled: open,
  });
  const rerankers = useQuery({
    queryKey: ["admin", tenantId, "reranker-configs"],
    queryFn: () => adminApi.listRerankerConfigs(tenantId),
    enabled: open,
  });
  const save = useMutation({
    mutationFn: (payload: KnowledgeMergeSettingsUpdate) =>
      adminApi.updateKnowledgeMergeSettings(tenantId, payload),
    onSuccess: async (updated) => {
      await client.invalidateQueries({
        queryKey: ["admin", tenantId, "knowledge-merge-settings"],
      });
      form.setFieldsValue(mergeSettingsFormValues(updated));
      void messageApi.success("多库合并配置已保存");
      onClose();
    },
  });

  useEffect(() => {
    if (open && settings.data) form.setFieldsValue(mergeSettingsFormValues(settings.data));
  }, [form, open, settings.data]);

  const policy = settings.data?.policy;
  const formDisabled = settings.isLoading || save.isPending;
  const submitDisabled = isSubmitDisabled({
    formDisabled,
    settingsFailed: settings.isError,
    policyLoaded: Boolean(policy),
    mergeRerankEnabled: Boolean(mergeRerankEnabled),
    rerankersLoading: rerankers.isLoading,
    rerankersFailed: rerankers.isError,
  });

  return (
    <Modal
      destroyOnHidden
      open={open}
      title="多库合并配置"
      okText="保存"
      confirmLoading={save.isPending}
      loading={settings.isLoading}
      closable={!save.isPending}
      maskClosable={!save.isPending}
      cancelButtonProps={{ disabled: save.isPending }}
      okButtonProps={{ disabled: submitDisabled }}
      onCancel={onClose}
      onOk={() => form.submit()}
    >
      {messageContext}
      <MergePolicyNotice policy={policy} />
      <Form
        clearOnDestroy
        form={form}
        layout="vertical"
        disabled={formDisabled}
        onFinish={(values) => save.mutate(completeMergeSettingsPayload(values))}
      >
        <Form.Item name="merge_rerank_enabled" label="启用合并重排" valuePropName="checked">
          <Switch
            checkedChildren="开"
            unCheckedChildren="关"
            onChange={(enabled) => {
              if (!enabled) {
                form.setFieldsValue({
                  reranker_config_id: undefined,
                  min_rerank_score: undefined,
                });
              }
            }}
          />
        </Form.Item>
        <MergeSettingsFields
          enabled={Boolean(mergeRerankEnabled)}
          policy={policy}
          rerankers={rerankers.data}
          rerankersLoading={rerankers.isLoading}
        />
      </Form>
    </Modal>
  );
}

function MergePolicyNotice({ policy }: { policy: KnowledgeMergeSettings["policy"] | undefined }) {
  if (!policy) return null;
  return (
    <Alert
      showIcon
      type="info"
      style={{ marginBottom: 16 }}
      message={`仅当一次 Agent 检索中至少 ${policy.minimum_space_hits} 个已绑定知识库返回候选时，才用此处 reranker 对跨库 RRF 结果重排；每库最多取 ${policy.per_space_candidate_cap} 条候选，最终条数取 min(工具 limit, 最终 Top K)。启用表示授权当前及后续 Agent 绑定知识库的候选文本发送至所选重排服务，受限空间须先完成合规审批。`}
    />
  );
}

function MergeSettingsFields({
  enabled,
  policy,
  rerankers,
  rerankersLoading,
}: {
  enabled: boolean;
  policy: KnowledgeMergeSettings["policy"] | undefined;
  rerankers: RerankerConfig[] | undefined;
  rerankersLoading: boolean;
}) {
  if (!enabled || !policy) return null;
  return (
    <>
      <Form.Item
        name="reranker_config_id"
        label="重排序配置"
        rules={[{ required: true, message: "请选择重排序配置" }]}
      >
        <Select
          loading={rerankersLoading}
          options={activeRerankerConfigs(rerankers).map((config) => ({
            value: config.id,
            label: `${config.name} · ${config.model}`,
          }))}
          placeholder="选择已启用的重排序配置"
        />
      </Form.Item>
      <Form.Item
        name="rerank_top_n"
        label="送入重排候选 Top N"
        dependencies={["result_top_k"]}
        rules={[rerankTopNRule(policy)]}
      >
        <InputNumber
          min={policy.rerank_top_n_min}
          max={policy.rerank_top_n_max}
          precision={0}
          style={{ width: "100%" }}
        />
      </Form.Item>
      <Form.Item
        name="result_top_k"
        label="最终返回 Top K（合并后最多交给模型）"
        rules={[
          {
            required: true,
            type: "number",
            min: policy.result_top_k_min,
            max: policy.result_top_k_max,
          },
        ]}
      >
        <InputNumber
          min={policy.result_top_k_min}
          max={policy.result_top_k_max}
          precision={0}
          style={{ width: "100%" }}
        />
      </Form.Item>
      <Form.Item name="min_rerank_score" label="最低重排序分数（可选）">
        <InputNumber
          min={policy.min_rerank_score_min}
          max={policy.min_rerank_score_max}
          step={0.01}
          style={{ width: "100%" }}
        />
      </Form.Item>
    </>
  );
}

function isSubmitDisabled({
  formDisabled,
  settingsFailed,
  policyLoaded,
  mergeRerankEnabled,
  rerankersLoading,
  rerankersFailed,
}: {
  formDisabled: boolean;
  settingsFailed: boolean;
  policyLoaded: boolean;
  mergeRerankEnabled: boolean;
  rerankersLoading: boolean;
  rerankersFailed: boolean;
}): boolean {
  const rerankerUnavailable = mergeRerankEnabled && (rerankersLoading || rerankersFailed);
  return formDisabled || settingsFailed || !policyLoaded || rerankerUnavailable;
}

function rerankTopNRule(policy: KnowledgeMergeSettings["policy"]) {
  return ({ getFieldValue }: { getFieldValue: (name: string) => number }) => ({
    validator: (_: unknown, value: number | null) => {
      const resultTopK = getFieldValue("result_top_k");
      if (
        value !== null &&
        value >= policy.rerank_top_n_min &&
        value <= policy.rerank_top_n_max &&
        value >= resultTopK
      ) {
        return Promise.resolve();
      }
      return Promise.reject(
        new Error(`送入重排 Top N 须 ≥ 最终 Top K，且不超过 ${policy.rerank_top_n_max}`),
      );
    },
  });
}
