import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Checkbox, Form, Input, InputNumber, Modal, Tooltip } from "antd";

import { adminApi } from "@/shared/api/client";
import type { KnowledgeSpace, KnowledgeSpaceChunkingUpdate } from "@/shared/api/types";
import { AppIcon } from "@/shared/icons";
import { RequestErrorAlert } from "@/shared/ui";

const chunkSizeHelp = "决定每个知识片段大约包含多少字符；系统会优先在段落边界切分。";
const chunkOverlapHelp = "下一片段会保留上一片段末尾的部分内容，避免上下文在切分处断开。";
const chunkSeparatorHelp = "默认 \\n\\n；支持 \\n、\\t 和自定义标识符，例如 ***。";
const fullWidthFieldStyle = { width: "100%" };

type Props = {
  canManage: boolean;
  space: KnowledgeSpace;
  tenantId: string;
  onUpdated: (space: KnowledgeSpace) => void;
};

export function KnowledgeChunkingSettings({ canManage, space, tenantId, onUpdated }: Props) {
  const [form] = Form.useForm<KnowledgeSpaceChunkingUpdate>();
  const [editing, setEditing] = useState(false);
  const update = useMutation({
    mutationFn: (payload: KnowledgeSpaceChunkingUpdate) =>
      adminApi.updateKnowledgeSpaceChunking(tenantId, space.id, payload),
    onSuccess: (updated) => {
      setEditing(false);
      onUpdated(updated);
    },
  });
  const openEditor = () => {
    form.setFieldsValue(chunkSettings(space));
    setEditing(true);
  };

  return (
    <section className="knowledge-chunking-settings" aria-labelledby="knowledge-chunking-heading">
      <div>
        <h3 id="knowledge-chunking-heading">内容处理设置</h3>
        <p>
          文档会优先按段落拆成便于检索的片段。目标长度决定每段大约多长；相邻重叠会保留跨段落的上下文。
          该设置只应用于之后新建或上传的文档。
        </p>
      </div>
      <dl className="knowledge-chunking-values">
        <div>
          <dt>
            <Tooltip title={chunkSeparatorHelp}>
              <span className="knowledge-chunking-help" tabIndex={0}>
                分段标识符
              </span>
            </Tooltip>
          </dt>
          <dd>{chunkSeparator(space)}</dd>
        </div>
        <div>
          <dt>
            <Tooltip title={chunkSizeHelp}>
              <span className="knowledge-chunking-help" tabIndex={0}>
                目标长度
              </span>
            </Tooltip>
          </dt>
          <dd>{space.chunk_size_chars.toLocaleString()} 字符</dd>
        </div>
        <div>
          <dt>
            <Tooltip title={chunkOverlapHelp}>
              <span className="knowledge-chunking-help" tabIndex={0}>
                相邻重叠
              </span>
            </Tooltip>
          </dt>
          <dd>{space.chunk_overlap_chars.toLocaleString()} 字符</dd>
        </div>
        <div>
          <dt>文本预处理</dt>
          <dd>{textProcessingSummary(space)}</dd>
        </div>
      </dl>
      {canManage ? (
        <Button
          ghost
          type="primary"
          icon={<AppIcon name="SettingTwo" size="md" />}
          onClick={openEditor}
        >
          调整切分配置
        </Button>
      ) : null}
      <ChunkingModal
        editing={editing}
        error={update.error}
        form={form}
        loading={update.isPending}
        onCancel={() => setEditing(false)}
        onSubmit={update.mutate}
      />
    </section>
  );
}

function ChunkingModal({
  editing,
  error,
  form,
  loading,
  onCancel,
  onSubmit,
}: {
  editing: boolean;
  error: Error | null;
  form: ReturnType<typeof Form.useForm<KnowledgeSpaceChunkingUpdate>>[0];
  loading: boolean;
  onCancel: () => void;
  onSubmit: (payload: KnowledgeSpaceChunkingUpdate) => void;
}) {
  return (
    <Modal
      title="调整切分配置"
      open={editing}
      confirmLoading={loading}
      destroyOnHidden
      width={640}
      onCancel={onCancel}
      onOk={() => void form.validateFields().then(onSubmit)}
    >
      <RequestErrorAlert error={error} fallback="保存切分配置失败" />
      <Alert showIcon type="info" message="当前文档保持原有版本快照，不会被自动重切。" />
      <Form className="admin-modal-form" form={form} layout="vertical">
        <ChunkingRulesSection />
        <TextProcessingSection />
      </Form>
    </Modal>
  );
}

function ChunkingRulesSection() {
  return (
    <section
      className="admin-form-section knowledge-chunking-form-section"
      aria-labelledby="chunking-rules-heading"
    >
      <h3 id="chunking-rules-heading">切分规则</h3>
      <p>设置新文档的切分边界与片段大小；较小片段更聚焦，较大片段保留更多上下文。</p>
      <div className="knowledge-chunking-form-grid">
        <Form.Item
          className="knowledge-chunking-form-field--wide"
          name="chunk_separator"
          label="分段标识符"
          extra={chunkSeparatorHelp}
          rules={[{ required: true, whitespace: true, max: 128 }]}
        >
          <Input placeholder="\\n\\n" />
        </Form.Item>
        <Form.Item
          name="chunk_size_chars"
          label="单块目标字符数"
          extra="范围 500–12,000。过小会割裂上下文，过大会降低检索精度。"
          rules={[{ required: true, type: "number", min: 500, max: 12000 }]}
        >
          <InputNumber
            min={500}
            max={12000}
            step={100}
            style={fullWidthFieldStyle}
            suffix="字符"
          />
        </Form.Item>
        <Form.Item
          name="chunk_overlap_chars"
          dependencies={["chunk_size_chars"]}
          label="相邻块重叠字符数"
          extra="用于保留跨段落上下文；必须小于目标字符数。"
          rules={[overlapRule]}
        >
          <InputNumber min={0} step={50} style={fullWidthFieldStyle} suffix="字符" />
        </Form.Item>
      </div>
    </section>
  );
}

function TextProcessingSection() {
  return (
    <section
      className="admin-form-section knowledge-chunking-form-section"
      aria-labelledby="text-processing-heading"
    >
      <h3 id="text-processing-heading">检索文本清洗</h3>
      <p>仅处理用于检索的文本，不会修改原始上传文件或已发布的历史版本。</p>
      <div className="knowledge-chunking-toggle-list">
        <Form.Item name={["text_processing", "normalize_whitespace"]} valuePropName="checked">
          <Checkbox aria-label="规整空白与段落">
            <span>
              <strong>规整空白与段落</strong>
              <small>移除多余空白、制表符和空行，同时保留段落边界。</small>
            </span>
          </Checkbox>
        </Form.Item>
        <Form.Item name={["text_processing", "remove_urls_and_emails"]} valuePropName="checked">
          <Checkbox aria-label="移除 URL 和邮箱">
            <span>
              <strong>移除 URL 和邮箱</strong>
              <small>避免链接、邮箱等噪声影响检索匹配。</small>
            </span>
          </Checkbox>
        </Form.Item>
      </div>
    </section>
  );
}

const overlapRule = ({ getFieldValue }: { getFieldValue: (name: string) => number }) => ({
  validator: (_: unknown, overlap: number | null) => {
    const size = getFieldValue("chunk_size_chars");
    if (overlap !== null && overlap >= 0 && overlap < size) return Promise.resolve();
    return Promise.reject(new Error("重叠字符数必须大于等于 0 且小于目标字符数"));
  },
});

function chunkSettings(space: KnowledgeSpace): KnowledgeSpaceChunkingUpdate {
  return {
    chunk_separator: chunkSeparator(space),
    chunk_size_chars: space.chunk_size_chars,
    chunk_overlap_chars: space.chunk_overlap_chars,
    text_processing: textProcessing(space),
  };
}

function textProcessingSummary(space: KnowledgeSpace) {
  const enabled = [
    textProcessing(space).normalize_whitespace ? "空白规整" : null,
    textProcessing(space).remove_urls_and_emails ? "移除链接/邮箱" : null,
  ].filter(Boolean);
  return enabled.length > 0 ? enabled.join("、") : "未启用";
}

function textProcessing(space: KnowledgeSpace) {
  return (
    space.text_processing ?? {
      normalize_whitespace: false,
      remove_urls_and_emails: false,
    }
  );
}

function chunkSeparator(space: KnowledgeSpace) {
  return space.chunk_separator || "\\n\\n";
}
