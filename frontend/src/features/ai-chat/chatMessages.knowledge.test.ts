import { describe, expect, it } from "vitest";

import {
  completeAssistant,
  outputCitations,
  outputMedia,
  type ChatMessageModel,
} from "@/features/ai-chat/chatMessages";
import type { ImEnvelope } from "@/shared/api/generated/im";

describe("chat knowledge output parsing", () => {
  it("parses structured citations and media from completed events", () => {
    const event = {
      version: "1",
      type: "ai.output.completed",
      message_id: "msg_1",
      request_id: "req_1",
      interaction_id: "interaction_1",
      sequence: 3,
      occurred_at: null,
      data: {
        output_id: "output_1",
        content: "登录步骤如下。",
        citations: [
          {
            citation_id: "knowledge_chunk_a",
            title: "至尊宝APP操作手册",
            anchor: "slide-2",
            slide_no: 2,
          },
        ],
        media: [
          {
            citation_id: "knowledge_chunk_a",
            asset_id: "media_a",
            kind: "slide_render",
            role: "primary",
            alt: "第 2 页",
          },
        ],
      },
    } satisfies ImEnvelope;

    expect(outputCitations(event)).toEqual([
      {
        citation_id: "knowledge_chunk_a",
        title: "至尊宝APP操作手册",
        anchor: "slide-2",
        slide_no: 2,
      },
    ]);
    expect(outputMedia(event)).toEqual([
      {
        citation_id: "knowledge_chunk_a",
        asset_id: "media_a",
        kind: "slide_render",
        role: "primary",
        alt: "第 2 页",
      },
    ]);
  });

  it("attaches citations to the completed assistant message", () => {
    const current: ChatMessageModel[] = [
      { id: "output_1", role: "assistant", content: "临时", streaming: true },
    ];
    const next = completeAssistant(current, "output_1", "登录步骤如下。", {
      interactionId: "interaction_1",
      citations: [
        {
          citation_id: "knowledge_chunk_a",
          title: "至尊宝APP操作手册",
          anchor: "slide-2",
          slide_no: 2,
        },
      ],
      media: [],
    });
    expect(next[0]).toMatchObject({
      content: "登录步骤如下。",
      streaming: false,
      interactionId: "interaction_1",
      citations: [{ citation_id: "knowledge_chunk_a" }],
    });
  });
});
