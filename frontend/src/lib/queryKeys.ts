export const keys = {
  chats: (wsId: number) => ["chats", wsId] as const,
  chat: (id: number) => ["chat", id] as const,
  messages: (chatId: number, page: number) =>
    ["messages", chatId, page] as const,
  models: () => ["models"] as const,
  available: () => ["models", "available"] as const,
  facts: () => ["memory", "facts"] as const,
  summaries: (chatId?: number) =>
    ["memory", "summaries", chatId] as const,
  workspaces: () => ["workspaces"] as const,
  active: () => ["workspaces", "active"] as const,
  settings: () => ["settings"] as const,
  health: () => ["health"] as const,
};
