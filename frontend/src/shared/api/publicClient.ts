import { endpoints } from "@/shared/api/endpoints";
import { http } from "@/shared/api/transport";
import type { Agent, PublicImChannel } from "@/shared/api/types";

export const publicApi = {
  listAgents: ({ offset = 0, limit = 10, search = "" } = {}) => {
    const query = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (search.trim()) query.set("search", search.trim());
    return http.get<Agent[]>(`${endpoints.public.agents}?${query.toString()}`);
  },
  getAgent: (slug: string) => http.get<Agent>(endpoints.public.agent(slug)),
  listAgentChannels: (slug: string) =>
    http.get<PublicImChannel[]>(endpoints.public.agentChannels(slug)),
};
