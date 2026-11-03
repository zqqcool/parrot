import { useEffect, useState } from "react";
import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { Alert, Descriptions, List, Pagination, Select, Tag } from "antd";

import { adminApi } from "@/shared/api/client";
import type {
  KnowledgeDocument,
  KnowledgeDocumentChunk,
  KnowledgeDocumentChunkPage,
  KnowledgeDocumentVersion,
} from "@/shared/api/types";
import { RequestErrorAlert } from "@/shared/ui";

const PAGE_SIZE = 20;

type Props = {
  document: KnowledgeDocument;
  tenantId: string;
};

export function KnowledgeDocumentChunkList({ document, tenantId }: Props) {
  const [page, setPage] = useState(1);
  const [selectedVersionId, setSelectedVersionId] = useState<string>();
  const versions = useQuery({
    queryKey: ["admin", tenantId, "knowledge-documents", document.id, "versions"],
    queryFn: () => adminApi.listKnowledgeDocumentVersions(tenantId, document.id),
  });
  const version = resolveVersion(versions.data, selectedVersionId);
  const chunks = useQuery({
    queryKey: ["admin", tenantId, "knowledge-document-versions", version?.id, "chunks", page],
    queryFn: () =>
      adminApi.listKnowledgeDocumentVersionChunks(
        tenantId,
        document.id,
        version?.id ?? "",
        page,
        PAGE_SIZE,
      ),
    enabled: Boolean(version),
  });

  useEffect(() => setPage(1), [selectedVersionId]);

  return (
    <>
      <DocumentMetadata document={document} />
      <RequestErrorAlert error={versions.error} fallback="加载文档版本失败" />
      {versions.isPending ? <p role="status">正在加载文档版本…</p> : null}
      {version ? (
        <DocumentChunks
          chunks={chunks}
          selectedVersionId={selectedVersionId}
          versions={versions.data}
          onPageChange={setPage}
          onVersionChange={setSelectedVersionId}
        />
      ) : versions.isSuccess ? (
        <Alert showIcon type="info" message="文档仍在处理中，暂时没有可查看的已发布版本。" />
      ) : null}
    </>
  );
}

function DocumentMetadata({ document }: { document: KnowledgeDocument }) {
  return (
    <>
      <div className="knowledge-document-detail-heading">
        <h2>{document.title}</h2>
        <p>展示已解析并切分后存入知识库正文的数据；不展示向量库中的 embedding 向量。</p>
      </div>
      <Descriptions className="knowledge-document-detail-meta" column={3} size="small">
        <Descriptions.Item label="当前版本">v{document.current_version}</Descriptions.Item>
        <Descriptions.Item label="分段数">{document.chunk_count}</Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={document.status === "active" ? "success" : "default"}>
            {document.status === "active" ? "启用" : "已归档"}
          </Tag>
        </Descriptions.Item>
      </Descriptions>
    </>
  );
}

type ChunksProps = {
  chunks: UseQueryResult<KnowledgeDocumentChunkPage, Error>;
  selectedVersionId: string | undefined;
  versions: KnowledgeDocumentVersion[] | undefined;
  onPageChange: (page: number) => void;
  onVersionChange: (versionId: string) => void;
};

function DocumentChunks({
  chunks,
  selectedVersionId,
  versions,
  onPageChange,
  onVersionChange,
}: ChunksProps) {
  const items = viewableVersions(versions);
  const selected = resolveVersion(versions, selectedVersionId);
  return (
    <>
      <Select
        aria-label="查看版本"
        className="knowledge-document-version-select"
        value={selected?.id}
        options={items.map((item) => ({
          value: item.id,
          label: `版本 ${item.version}${item.status === "published" ? "（当前可检索）" : "（历史版本）"}`,
        }))}
        onChange={onVersionChange}
      />
      <VersionExtractionSummary version={selected} />
      <section
        className="knowledge-document-chunks"
        aria-labelledby="knowledge-document-chunks-heading"
      >
        <h3 id="knowledge-document-chunks-heading">分段正文</h3>
        <RequestErrorAlert error={chunks.error} fallback="加载文档分段失败" />
        <List<KnowledgeDocumentChunk>
          dataSource={chunks.data?.items ?? []}
          loading={chunks.isPending}
          locale={{ emptyText: "当前版本尚未生成可查看的分段正文" }}
          renderItem={(chunk) => <ChunkItem chunk={chunk} />}
        />
        {chunks.data && chunks.data.total > PAGE_SIZE ? (
          <Pagination
            current={chunks.data.page}
            pageSize={chunks.data.page_size}
            showSizeChanger={false}
            total={chunks.data.total}
            onChange={onPageChange}
          />
        ) : null}
      </section>
    </>
  );
}

function VersionExtractionSummary({ version }: { version: KnowledgeDocumentVersion | undefined }) {
  if (!version) return null;
  const unitCount = version.slide_count || version.section_count || version.sheet_count || 0;
  return (
    <>
      <Descriptions column={3} size="small">
        <Descriptions.Item label="提取格式">
          {formatProfileLabel(version.format_profile)}
        </Descriptions.Item>
        <Descriptions.Item label="结构单元">{unitCount}</Descriptions.Item>
        <Descriptions.Item label="关联媒体">{version.media_count ?? 0}</Descriptions.Item>
      </Descriptions>
      {(version.skipped_media_count ?? 0) > 0 ? (
        <Alert
          showIcon
          type="warning"
          message={`有 ${version.skipped_media_count} 个媒体项未完整生成预览`}
          description="可能包含未渲染的图表、不支持的内嵌图片，或缺少 LibreOffice 时生成的降级缩略图。正文检索不受影响。"
        />
      ) : null}
    </>
  );
}

function ChunkItem({ chunk }: { chunk: KnowledgeDocumentChunk }) {
  return (
    <List.Item>
      <strong>分段 {chunk.ordinal}</strong>
      <span> · {chunk.content_chars} 字符</span>
      <pre className="knowledge-document-chunk-content">{chunk.content}</pre>
    </List.Item>
  );
}

function viewableVersions(versions: KnowledgeDocumentVersion[] | undefined) {
  return (versions ?? []).filter(
    (item) => item.status === "published" || item.status === "superseded",
  );
}

function resolveVersion(
  versions: KnowledgeDocumentVersion[] | undefined,
  selectedVersionId: string | undefined,
) {
  const items = viewableVersions(versions);
  return items.find((item) => item.id === selectedVersionId) ?? items[0];
}

function formatProfileLabel(value: string | undefined) {
  const labels: Record<string, string> = {
    docx: "Word",
    pdf: "PDF",
    plain_text: "文本",
    pptx: "PowerPoint",
    xlsx: "Excel",
  };
  return labels[value ?? "plain_text"] ?? value ?? "文本";
}
