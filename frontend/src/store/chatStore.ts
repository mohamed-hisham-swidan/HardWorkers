import { create } from "zustand";

interface ChatState {
  activeChatId: number | null;
  streamBuffer: string;
  isStreaming: boolean;
  elapsedMs: number | null;

  setActiveChat: (id: number | null) => void;
  appendChunk: (chunk: string) => void;
  finalizeStream: (elapsed: number) => void;
  setStreaming: (v: boolean) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  activeChatId: null,
  streamBuffer: "",
  isStreaming: false,
  elapsedMs: null,

  setActiveChat: (id) =>
    set({ activeChatId: id, streamBuffer: "", elapsedMs: null }),
  appendChunk: (c) =>
    set((s) => ({ streamBuffer: s.streamBuffer + c })),
  finalizeStream: (ms) =>
    set({ streamBuffer: "", elapsedMs: ms, isStreaming: false }),
  setStreaming: (v) => set({ isStreaming: v }),
}));
