import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Form, Steps } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  KnowledgeSpaceConfigurationStep,
  type KnowledgeSpaceCreateForm,
} from "@/features/admin/KnowledgeSpaceConfigurationStep";
import { TenantRequiredState } from "@/features/admin/TenantRequiredState";
import { useTenantId } from "@/features/admin/useTenant";
import { KnowledgeSpaceUploadStep } from "@/features/admin/KnowledgeSpaceUploadStep";
import { adminApi } from "@/shared/api/client";
import type { KnowledgeSpace, KnowledgeSpaceCreate } from "@/shared/api/types";
import { useAuth } from "@/shared/auth/useAuth";
import { AdminPageHeader } from "@/shared/ui";

import "./knowledge-page.css";

export function KnowledgeSpaceCreatePage() {
  const tenantId = useTenantId();
  const client = useQueryClient();
  const navigate = useNavigate();
  const auth = useAuth();
  const [form] = Form.useForm<KnowledgeSpaceCreateForm>();
  const [step, setStep] = useState(0);
  const [createdSpace, setCreatedSpace] = useState<KnowledgeSpace | null>(null);
  const embeddings = useQuery({
    queryKey: ["admin", tenantId, "embedding-configs"],
    queryFn: () => adminApi.listEmbeddingConfigs(tenantId ?? ""),
    enabled: Boolean(tenantId),
  });
  const create = useMutation({
    mutationFn: (payload: KnowledgeSpaceCreate) =>
      adminApi.createKnowledgeSpace(tenantId ?? "", payload),
    onSuccess: async (space) => {
      await client.invalidateQueries({ queryKey: ["admin", tenantId, "knowledge-spaces"] });
      setCreatedSpace(space);
      setStep(2);
    },
  });
  const retrievalMode = Form.useWatch("retrieval_mode", form);
  const vectorEnabled = retrievalMode === "vector";
  const activeEmbeddings = (embeddings.data ?? []).filter((config) => config.status === "active");
  const next = () => {
    const names =
      step === 0
        ? ["name", "classification"]
        : ["chunk_separator", "chunk_size_chars", "chunk_overlap_chars"];
    void form.validateFields(names).then(() => setStep((current) => current + 1));
  };
  const submit = () => {
    void form.validateFields().then((values) => create.mutate(normalizeCreate(values)));
  };

  if (!tenantId) return <TenantRequiredState />;

  return (
    <section className="knowledge-create-page">
      <AdminPageHeader
        title="配置知识库"
        description="先确定分块与索引策略，再上传资料。Embedding 配置属于当前租户，创建后由知识库引用。"
      />
      <Steps
        className="knowledge-create-steps"
        current={step}
        items={[
          { title: "基础信息", description: "名称与管理分类" },
          { title: "分块与索引", description: "Embedding 配置" },
          { title: "上传资料", description: "文件或文本" },
        ]}
        size="small"
      />
      {step < 2 ? (
        <KnowledgeSpaceConfigurationStep
          activeEmbeddings={activeEmbeddings}
          createError={create.error}
          creating={create.isPending}
          embeddingError={embeddings.error}
          form={form}
          step={step}
          vectorEnabled={vectorEnabled}
          onBack={() => setStep(0)}
          onCancel={() => void navigate("/admin/knowledge")}
          onNext={next}
          onSubmit={submit}
        />
      ) : createdSpace ? (
        <KnowledgeSpaceUploadStep
          canManageDocuments={auth.hasPermission("knowledge.documents.manage")}
          canReadDocuments={auth.hasPermission("knowledge.documents.read")}
          space={createdSpace}
          tenantId={tenantId}
          onComplete={() => void navigate(`/admin/knowledge/${createdSpace.id}/documents`)}
        />
      ) : null}
    </section>
  );
}

function normalizeCreate(values: KnowledgeSpaceCreateForm): KnowledgeSpaceCreate {
  const { retrieval_mode: _mode, ...payload } = values;
  if (_mode === "vector") return payload;
  return {
    ...payload,
    embedding_config_id: undefined,
  };
}
