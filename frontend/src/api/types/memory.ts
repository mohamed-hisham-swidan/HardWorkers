export interface Fact {
  id: number;
  key: string;
  value: string;
  importance: number;
  created_at: string;
}

export interface AddFactRequest {
  key: string;
  value: string;
  importance: number;
}

export interface Summary {
  id: number;
  chat_id: number;
  summary: string;
  source: string;
  created_at: string;
}

export interface SearchMemoryRequest {
  query: string;
  limit: number;
  threshold: number;
}

export interface SearchResult {
  key: string;
  value: string;
  score: number;
}
