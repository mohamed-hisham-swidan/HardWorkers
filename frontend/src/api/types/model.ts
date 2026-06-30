export interface ModelConfig {
  id: number;
  name: string;
  provider: string;
  category: string;
  description: string;
  system_prompt: string;
  base_model: string;
  api_url: string;
  supports_vision: boolean;
  memory_mode: string;
  created_at: string;
  updated_at: string;
}

export interface ModelListItem {
  name: string;
  provider: string;
  category: string;
  is_available: boolean;
}

export interface CreateModelRequest {
  name: string;
  provider: string;
  category: string;
  description: string;
  system_prompt: string;
  base_model: string;
  api_url: string;
  api_key: string;
  api_password: string;
  supports_vision: boolean;
  memory_mode: string;
}

export interface TestConnectionResponse {
  ok: boolean;
  message: string;
  latency_ms: number;
}
