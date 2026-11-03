import { endpoints } from "@/shared/api/endpoints";
import { http } from "@/shared/api/transport";

export const imApi = {
  downloadKnowledgeMedia: (interactionId: string, assetId: string) =>
    http.getFile(endpoints.im.knowledgeMediaContent(interactionId, assetId)),
};
