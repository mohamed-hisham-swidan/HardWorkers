export interface ChatSession {
  id: number;
  workspace_id: number;
  name: string;
  pinned: boolean;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  tokens: number;
  timestamp: string;
}

export interface SendMessageRequest {
  message: string;
  model_id?: string;
}

export interface SendMessageResponse {
  message_id: number;
  content: string;
  role: string;
  tokens: number;
  elapsed_ms: number;
}

export interface ChatSessionCreate {
  name: string;
  pinned: boolean;
  workspace_id: number;
}

export interface ChatSessionRename {
  name: string;
}

export interface ChatSessionPin {
  pinned: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}
