import { useEffect, useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { Image, Spin } from "antd";

import type { ChatOutputCitation, ChatOutputMedia } from "@/features/ai-chat/chatMessages";
import { imApi } from "@/shared/api/imClient";

import "./chat-knowledge-sources.css";

type Props = {
  citations: readonly ChatOutputCitation[];
  interactionId: string | null;
  media: readonly ChatOutputMedia[];
};

export function ChatKnowledgeSources({ citations, interactionId, media }: Props) {
  if (citations.length === 0 && media.length === 0) return null;
  return (
    <section aria-label="信息来源" className="chat-knowledge-sources">
      {citations.length > 0 ? (
        <div className="chat-knowledge-source-cards">
          <header>信息来源</header>
          <ul>
            {citations.map((citation, index) => (
              <li key={citation.citation_id}>
                <span className="chat-knowledge-source-index">{index + 1}</span>
                <div>
                  <strong>{citation.title}</strong>
                  <p>{citationLabel(citation)}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {interactionId && media.length > 0 ? (
        <ChatKnowledgeMediaGallery interactionId={interactionId} media={media} />
      ) : null}
    </section>
  );
}

function citationLabel(citation: ChatOutputCitation) {
  if (citation.slide_no != null) return `第 ${citation.slide_no} 页 · ${citation.anchor}`;
  return citation.anchor;
}

function ChatKnowledgeMediaGallery({
  interactionId,
  media,
}: {
  interactionId: string;
  media: readonly ChatOutputMedia[];
}) {
  const loaded = useInteractionMediaBlobs(interactionId, media);
  return (
    <div className="chat-knowledge-media">
      <header>相关配图</header>
      {loaded.loading && loaded.items.length === 0 ? (
        <div className="chat-knowledge-media-loading">
          <Spin size="small" />
          <span>正在加载配图</span>
        </div>
      ) : null}
      {loaded.items.length > 0 ? (
        <Image.PreviewGroup>
          <div className="chat-knowledge-media-grid">
            {loaded.items.map((item) => (
              <figure key={item.media.asset_id}>
                <BlobImage alt={item.media.alt || item.media.kind} blob={item.blob} />
                <figcaption>{item.media.alt || item.media.kind}</figcaption>
              </figure>
            ))}
          </div>
        </Image.PreviewGroup>
      ) : null}
    </div>
  );
}

function BlobImage({ alt, blob }: { alt: string; blob: Blob }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);
  if (!url) return <div className="chat-knowledge-media-placeholder" />;
  return <Image alt={alt} src={url} />;
}

function useInteractionMediaBlobs(interactionId: string, media: readonly ChatOutputMedia[]) {
  const queries = useQueries({
    queries: media.map((item) => ({
      queryKey: ["im", "knowledge-media", interactionId, item.asset_id],
      queryFn: async () => {
        const file = await imApi.downloadKnowledgeMedia(interactionId, item.asset_id);
        return { media: item, blob: file.blob };
      },
      staleTime: Infinity,
    })),
  });
  const items = useMemo(
    () => queries.flatMap((query) => (query.data ? [query.data] : [])),
    [queries],
  );
  return {
    items,
    loading: queries.some((query) => query.isPending),
  };
}
