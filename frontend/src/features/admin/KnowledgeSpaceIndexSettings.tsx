import { Alert, Checkbox, Form, Input, InputNumber, Radio, Select } from "antd";

import type { EmbeddingConfig } from "@/shared/api/types";

type Props = {
  activeEmbeddings: EmbeddingConfig[];
  vectorEnabled: boolean;
};

const fullWidthFieldStyle = { width: "100%" };

export function KnowledgeSpaceIndexSettings({ activeEmbeddings, vectorEnabled }: Props) {
  return (
    <>
      <section aria-labelledby="knowledge-chunking-create-heading">
        <h3 id="knowledge-chunking-create-heading">分块设置</h3>
        <p className="knowledge-create-help">
          文档会优先按段落切分；设置只影响之后上传或录入的文档。
        </p>
        <div className="knowledge-create-grid">
          <Form.Item
            name="chunk_separator"
            label="分段标识符"
            extra="默认 \\n\\n；支持 \\n、\\t 和自定义标识符，例如 ***。"
            rules={[{ required: true, whitespace: true, max: 128 }]}
          >
            <Input placeholder="\\n\\n" />
          </Form.Item>
          <Form.Item
            name="chunk_size_chars"
            label="单块目标字符数"
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
            rules={[overlapRule]}
          >
            <InputNumber min={0} step={50} style={fullWidthFieldStyle} suffix="字符" />
          </Form.Item>
        </div>
      </section>
      <section aria-labelledby="knowledge-text-processing-create-heading">
        <h3 id="knowledge-text-processing-create-heading">文本预处理</h3>
        <p className="knowledge-create-help">
          处理仅作用于之后新建或上传的文档版本；原始上传文件始终保持不变。
        </p>
        <Form.Item name={["text_processing", "normalize_whitespace"]} valuePropName="checked">
          <Checkbox>规整多余空白、制表符和空行，同时保留段落边界</Checkbox>
        </Form.Item>
        <Form.Item name={["text_processing", "remove_urls_and_emails"]} valuePropName="checked">
          <Checkbox>从用于检索的文本中移除 URL 和邮箱</Checkbox>
        </Form.Item>
      </section>
      <section aria-labelledby="knowledge-index-create-heading">
        <h3 id="knowledge-index-create-heading">索引方式</h3>
        <p className="knowledge-create-help">
          Embedding 在创建时确定；创建后只调整 Top K、阈值和重排序等查询参数。选择 Embedding
          不会启用部署级向量检索运行时；运行时未启用或索引未完成时，召回会使用关键词检索。
        </p>
        <Form.Item name="retrieval_mode" rules={[{ required: true }]}>
          <Radio.Group className="knowledge-create-retrieval-options">
            <Radio value="vector" disabled={activeEmbeddings.length === 0}>
              <strong>高质量：向量 + 词法融合</strong>
              <span>
                按语义召回相关片段；需要选定 Embedding 配置、启用向量检索运行时并完成索引。
              </span>
            </Radio>
            <Radio value="lexical">
              <strong>经济：纯词法检索</strong>
              <span>不发送文本到外部 Embedding 服务；创建后保持纯词法模式。</span>
            </Radio>
          </Radio.Group>
        </Form.Item>
        {activeEmbeddings.length === 0 ? (
          <Alert
            showIcon
            type="warning"
            message="当前租户没有已启用的 Embedding 配置，只能创建纯词法知识库。"
          />
        ) : null}
        {vectorEnabled ? <EmbeddingSelection embeddings={activeEmbeddings} /> : null}
      </section>
    </>
  );
}

function EmbeddingSelection({ embeddings }: { embeddings: EmbeddingConfig[] }) {
  return (
    <>
      <Form.Item
        name="embedding_config_id"
        label="Embedding 配置"
        rules={[{ required: true, message: "请选择 Embedding 配置" }]}
      >
        <Select
          options={embeddings.map((config) => ({
            value: config.id,
            label: `${config.name} · ${config.model} (${config.embedding_dimension} 维)`,
          }))}
          placeholder="选择已启用的 Embedding 配置"
        />
      </Form.Item>
    </>
  );
}

const overlapRule = ({ getFieldValue }: { getFieldValue: (name: string) => number }) => ({
  validator: (_: unknown, overlap: number | null) => {
    const size = getFieldValue("chunk_size_chars");
    if (overlap !== null && overlap >= 0 && overlap < size) return Promise.resolve();
    return Promise.reject(new Error("重叠字符数必须大于等于 0 且小于目标字符数"));
  },
});
