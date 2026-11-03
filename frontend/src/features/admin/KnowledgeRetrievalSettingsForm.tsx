import { useEffect } from "react";
import { Alert, Button, Form, InputNumber, Select, Switch } from "antd";

import type { KnowledgeSpaceRetrievalUpdate, RerankerConfig } from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

type Props = {
  error: Error | null;
  initialValues: KnowledgeSpaceRetrievalUpdate;
  loading: boolean;
  rerankerError: Error | null;
  rerankers: RerankerConfig[];
  onSubmit: (payload: KnowledgeSpaceRetrievalUpdate) => void;
};

export function KnowledgeRetrievalSettingsForm({
  error,
  initialValues,
  loading,
  rerankerError,
  rerankers,
  onSubmit,
}: Props) {
  const [form] = Form.useForm<KnowledgeSpaceRetrievalUpdate>();
  const rerankEnabled = Form.useWatch("rerank_enabled", form);
  useEffect(() => form.setFieldsValue(initialValues), [form, initialValues]);

  return (
    <Form
      className="knowledge-retrieval-settings-form"
      form={form}
      initialValues={initialValues}
      layout="vertical"
      onFinish={(values) => onSubmit(completeRetrievalUpdate(initialValues, values))}
    >
      <RequestErrorAlert error={error} fallback="保存检索参数失败" />
      <RequestErrorAlert error={rerankerError} fallback="加载重排序配置失败" />
      <Alert
        className="knowledge-retrieval-settings-notice"
        showIcon
        type="info"
        message="本页与 Agent 共用这些检索参数。最低向量相似度只过滤向量候选，关键词候选仍可进入融合排序；结果展示的是融合排序分，不能与该阈值直接比较。"
      />
      <Form.Item name="candidate_top_k" label="候选 Top K" rules={[topKRule]}>
        <InputNumber min={1} max={60} precision={0} />
      </Form.Item>
      <Form.Item name="min_vector_score" label="最低向量相似度（可选）">
        <InputNumber min={0} max={1} step={0.01} />
      </Form.Item>
      <Form.Item label="多模态 Embedding（预留）">
        <Select disabled options={[]} placeholder="当前未启用；可继续使用文本 Embedding" />
      </Form.Item>
      <Form.Item name="rerank_enabled" label="启用重排序" valuePropName="checked">
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
      {rerankEnabled ? <RerankFields rerankers={rerankers} /> : null}
      <div className="knowledge-retrieval-settings-actions">
        <Button htmlType="submit" loading={loading} type="primary">
          保存检索参数
        </Button>
      </div>
    </Form>
  );
}

function RerankFields({ rerankers }: { rerankers: RerankerConfig[] }) {
  return (
    <>
      <Form.Item
        className="knowledge-retrieval-settings-form-wide"
        name="reranker_config_id"
        label="重排序配置"
        rules={[{ required: true, message: "请选择重排序配置" }]}
      >
        <Select
          options={rerankers.map((config) => ({
            value: config.id,
            label: `${config.name} · ${config.model}`,
          }))}
          placeholder="选择已启用的重排序配置"
        />
      </Form.Item>
      <Form.Item
        name="rerank_top_n"
        dependencies={["candidate_top_k"]}
        label="重排序 Top N"
        rules={[rerankTopNRule]}
      >
        <InputNumber min={1} max={60} precision={0} />
      </Form.Item>
      <Form.Item name="min_rerank_score" label="最低重排序分数（可选）">
        <InputNumber min={0} max={1} step={0.01} />
      </Form.Item>
    </>
  );
}

const topKRule = { required: true, type: "number" as const, min: 1, max: 60 };

function completeRetrievalUpdate(
  initialValues: KnowledgeSpaceRetrievalUpdate,
  values: KnowledgeSpaceRetrievalUpdate,
): KnowledgeSpaceRetrievalUpdate {
  const payload = { ...initialValues, ...values };
  if (payload.rerank_enabled) return payload;
  return {
    ...payload,
    reranker_config_id: null,
    min_rerank_score: null,
  };
}

const rerankTopNRule = ({ getFieldValue }: { getFieldValue: (name: string) => number }) => ({
  validator: (_: unknown, value: number | null) => {
    const candidateTopK = getFieldValue("candidate_top_k");
    if (value !== null && value >= 1 && value <= candidateTopK) return Promise.resolve();
    return Promise.reject(new Error("重排序 Top N 必须介于 1 和候选 Top K 之间"));
  },
});
