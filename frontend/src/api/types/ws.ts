export type WsEvent =
  | { type: "chunk"; content: string; chat_id: number }
  | { type: "done"; elapsed_ms: number; chat_id: number }
  | { type: "error"; content: string; chat_id: number };
