import { Alert, Button, Form, Input, Select } from "antd";
import type { FormInstance } from "antd";

import { KnowledgeSpaceIndexSettings } from "@/features/admin/KnowledgeSpaceIndexSettings";
import type { EmbeddingConfig, KnowledgeSpaceCreate } from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

export type KnowledgeSpaceCreateForm = KnowledgeSpaceCreate & {
  retrieval_mode: "lexical" | "vector";
};

type Props = {
  activeEmbeddings: EmbeddingConfig[];
  createError: Error | null;
  creating: boolean;
  embeddingError: Error | null;
  form: FormInstance<KnowledgeSpaceCreateForm>;
  step: number;
  vectorEnabled: boolean;
  onBack: () => void;
  onCancel: () => void;
  onNext: () => void;
  onSubmit: () => void;
};

export function KnowledgeSpaceConfigurationStep({
  activeEmbeddings,
  createError,
  creating,
  embeddingError,
  form,
  step,
  vectorEnabled,
  onBack,
  onCancel,
  onNext,
  onSubmit,
}: Props) {
  return (
    <div className="knowledge-create-layout">
      <Form
        className="knowledge-create-form"
        form={form}
        initialValues={{
          chunk_overlap_chars: 200,
          chunk_separator: "\\n\\n",
          chunk_size_chars: 4000,
          classification: "standard",
          retrieval_mode: "lexical",
          text_processing: {
            normalize_whitespace: false,
            remove_urls_and_emails: false,
          },
        }}
        layout="vertical"
      >
        <RequestErrorAlert error={createError ?? embeddingError} fallback="创建知识库失败" />
        {step === 0 ? (
          <Alert showIcon type="info" message="完成基础配置后，下一步设置分块与索引策略。" />
        ) : null}
        <Form.Item
          hidden={step !== 0}
          name="name"
          label="显示名称"
          extra="管理台展示名称，便于管理员在 Agent 工作台中选择。"
          rules={[{ required: true, whitespace: true }]}
        >
          <Input placeholder="例如：产品知识库" />
        </Form.Item>
        <Form.Item
          hidden={step !== 0}
          name="classification"
          label="管理分类"
          extra="仅用于管理台筛选和标记，不替代空间授权或 Agent 运行时范围。"
          rules={[{ required: true }]}
        >
          <Select
            options={[
              { value: "standard", label: "标准（常规资料）" },
              { value: "restricted", label: "受限（需额外标记的资料）" },
            ]}
          />
        </Form.Item>
        {step === 1 ? (
          <KnowledgeSpaceIndexSettings
            activeEmbeddings={activeEmbeddings}
            vectorEnabled={vectorEnabled}
          />
        ) : null}
        <div className="knowledge-create-actions">
          <Button onClick={onCancel}>取消</Button>
          {step === 1 ? <Button onClick={onBack}>上一步</Button> : null}
          <Button type="primary" loading={creating} onClick={step === 0 ? onNext : onSubmit}>
            {step === 0 ? "下一步" : "创建并进入上传"}
          </Button>
        </div>
      </Form>
      <aside className="knowledge-create-aside">
        <h3>创建后</h3>
        <ol>
          <li>在下一步上传或录入文档，按本页分块设置处理。</li>
          <li>向量模式会按所选 Embedding 配置建立索引。</li>
          <li>在 Agent 工作台绑定此知识库后，Agent 才可检索其中内容。</li>
        </ol>
      </aside>
    </div>
  );
}
