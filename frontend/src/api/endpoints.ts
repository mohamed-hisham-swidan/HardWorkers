export const AUTH = {
  LOGIN: "/auth/login",
  REFRESH: "/auth/refresh",
  ME: "/auth/me",
} as const;

export const CHATS = {
  BASE: "/chats",
  BY_ID: (id: number) => `/chats/${id}`,
  RENAME: (id: number) => `/chats/${id}/rename`,
  PIN: (id: number) => `/chats/${id}/pin`,
  MESSAGES: (id: number) => `/chats/${id}/messages`,
  SEND: (id: number) => `/chats/${id}/send`,
} as const;

export const MODELS = {
  BASE: "/models",
  AVAILABLE: "/models/available",
  BY_ID: (id: number) => `/models/${id}`,
  TEST: (id: number) => `/models/${id}/test`,
  PULL: "/models/pull",
  DEFAULT: "/models/default",
} as const;

export const MEMORY = {
  FACTS: "/memory/facts",
  FACT_BY_ID: (id: number) => `/memory/facts/${id}`,
  SEARCH: "/memory/facts/search",
  SUMMARIES: "/memory/summaries",
  CHAT_FACTS: (chatId: number) => `/memory/chat/${chatId}/facts`,
} as const;

export const WORKSPACES = {
  BASE: "/workspaces",
  ACTIVE: "/workspaces/active",
  BY_ID: (id: number) => `/workspaces/${id}`,
  SWITCH: "/workspaces/switch",
} as const;

export const SETTINGS = {
  BASE: "/settings",
} as const;

export const HEALTH = {
  BASE: "/health",
} as const;

export const TASKS = {
  BY_ID: (id: string) => `/tasks/${id}`,
} as const;
