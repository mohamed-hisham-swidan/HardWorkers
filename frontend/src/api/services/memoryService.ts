import api from "../client";
import { MEMORY } from "../endpoints";
import type {
  Fact,
  AddFactRequest,
  Summary,
  SearchMemoryRequest,
  SearchResult,
} from "../types/memory";
import type { PaginatedResponse } from "../types/chat";

export async function listFacts(
  offset = 0,
  limit = 50
): Promise<PaginatedResponse<Fact>> {
  const res = await api.get<PaginatedResponse<Fact>>(MEMORY.FACTS, {
    params: { offset, limit },
  });
  return res.data;
}

export async function addFact(data: AddFactRequest): Promise<Fact> {
  const res = await api.post<Fact>(MEMORY.FACTS, data);
  return res.data;
}

export async function deleteFact(id: number): Promise<void> {
  await api.delete(MEMORY.FACT_BY_ID(id));
}

export async function searchFacts(
  data: SearchMemoryRequest
): Promise<{ items: SearchResult[] }> {
  const res = await api.post<{ items: SearchResult[] }>(MEMORY.SEARCH, data);
  return res.data;
}

export async function listSummaries(
  chatId?: number,
  limit = 20
): Promise<{ items: Summary[] }> {
  const res = await api.get<{ items: Summary[] }>(MEMORY.SUMMARIES, {
    params: { chat_id: chatId, limit },
  });
  return res.data;
}

export async function getChatFacts(
  chatId: number
): Promise<{ chat_id: number; facts: Fact[] }> {
  const res = await api.get<{ chat_id: number; facts: Fact[] }>(
    MEMORY.CHAT_FACTS(chatId)
  );
  return res.data;
}
