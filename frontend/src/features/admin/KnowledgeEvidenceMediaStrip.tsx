import { useEffect, useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { Image, Spin } from "antd";

import { adminApi } from "@/shared/api/client";
import type { KnowledgeMediaRef } from "@/shared/api/types";
import {
  mediaGroupLabel,
  mediaRefLabel,
  orderMediaRefs,
} from "@/features/admin/knowledgeMediaOrder";

import "./knowledge-evidence-media-strip.css";

type Props = {
  mediaRefs: readonly KnowledgeMediaRef[];
  tenantId: string;
  slideNo?: number | null;
};

type LoadedBlob = {
  ref: KnowledgeMediaRef;
  blob: Blob;
};

export function KnowledgeEvidenceMediaStrip({ mediaRefs, tenantId, slideNo }: Props) {
  const ordered = useMemo(() => orderMediaRefs(mediaRefs), [mediaRefs]);
  if (ordered.length === 0) return null;
  return <KnowledgeEvidenceMediaGallery ordered={ordered} slideNo={slideNo} tenantId={tenantId} />;
}

function KnowledgeEvidenceMediaGallery({
  ordered,
  slideNo,
  tenantId,
}: {
  ordered: KnowledgeMediaRef[];
  slideNo?: number | null;
  tenantId: string;
}) {
  const loaded = useKnowledgeMediaBlobs(tenantId, ordered);
  const label = mediaGroupLabel(slideNo, ordered);

  return (
    <section aria-label={label} className="knowledge-evidence-media-strip">
      <header className="knowledge-evidence-media-strip-heading">
        <strong>{label}</strong>
        <span>{ordered.length} 张关联图</span>
      </header>
      {loaded.loading && loaded.items.length === 0 ? (
        <div className="knowledge-evidence-media-strip-loading">
          <Spin size="small" />
          <span>正在加载关联图</span>
        </div>
      ) : null}
      {loaded.items.length > 0 ? (
        <Image.PreviewGroup>
          <div className="knowledge-evidence-media-strip-grid">
            {loaded.items.map((item) => (
              <figure key={item.ref.asset_id} className="knowledge-evidence-media-strip-item">
                <BlobImage alt={mediaRefLabel(item.ref)} blob={item.blob} />
                <figcaption>{mediaRefLabel(item.ref)}</figcaption>
              </figure>
            ))}
          </div>
        </Image.PreviewGroup>
      ) : null}
    </section>
  );
}

function BlobImage({ alt, blob }: { alt: string; blob: Blob }) {
  // createObjectURL must live in an effect. useMemo + revoke in cleanup breaks under
  // React StrictMode: the effect cleanup revokes the memoized URL while the <img> still uses it.
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);
  if (!url) {
    return <div aria-hidden className="knowledge-evidence-media-strip-image-placeholder" />;
  }
  return <Image alt={alt} className="knowledge-evidence-media-strip-image" src={url} />;
}

function useKnowledgeMediaBlobs(tenantId: string, refs: KnowledgeMediaRef[]) {
  const queries = useQueries({
    queries: refs.map((ref) => ({
      queryKey: ["admin", tenantId, "knowledge-media", ref.asset_id] as const,
      queryFn: async (): Promise<LoadedBlob> => {
        const file = await adminApi.downloadKnowledgeMedia(tenantId, ref.asset_id);
        return {
          ref,
          blob: ensureImageBlob(file.blob),
        };
      },
      staleTime: 60_000,
      gcTime: 120_000,
      retry: false,
    })),
  });

  const items = queries.flatMap((query) => (query.data ? [query.data] : []));
  return {
    items,
    loading: queries.some((query) => query.isFetching),
  };
}

function ensureImageBlob(blob: Blob): Blob {
  if (blob.type.startsWith("image/")) return blob;
  return new Blob([blob], { type: "image/png" });
}
