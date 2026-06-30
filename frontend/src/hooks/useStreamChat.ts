import { useCallback, useRef } from "react";
import { toast } from "sonner";
import { useAuthStore } from "../store/authStore";
import { useChatStore } from "../store/chatStore";
import { WS_RECONNECT_DELAY_MS } from "../config/constants";
import type { WsEvent } from "../api/types/ws";

type ConnectionState = "idle" | "connecting" | "streaming" | "reconnecting";

export function useStreamChat() {
  const token = useAuthStore((s) => s.token);
  const WS_BASE = import.meta.env.VITE_WS_URL;
  const { appendChunk, finalizeStream, setStreaming } = useChatStore();
  const wsRef = useRef<WebSocket | null>(null);
  const stateRef = useRef<ConnectionState>("idle");
  const retryCountRef = useRef(0);
  const maxRetries = 3;

  const connect = useCallback(
    (message: string, chatId: number, modelId: string) => {
      if (wsRef.current) {
        wsRef.current.close();
      }

      stateRef.current = "connecting";
      const ws = new WebSocket(
        `${WS_BASE}/api/v1/ws/chat?token=${token}&chat_id=${chatId}&model_id=${encodeURIComponent(modelId)}`
      );

      ws.onopen = () => {
        stateRef.current = "streaming";
        retryCountRef.current = 0;
        setStreaming(true);
        ws.send(JSON.stringify({ message }));
      };

      ws.onmessage = (e) => {
        try {
          const data: WsEvent = JSON.parse(e.data);
          if (data.type === "chunk") {
            appendChunk(data.content);
          } else if (data.type === "done") {
            finalizeStream(data.elapsed_ms);
            setStreaming(false);
            stateRef.current = "idle";
            ws.close();
          } else if (data.type === "error") {
            toast.error(data.content);
            setStreaming(false);
            stateRef.current = "idle";
            ws.close();
          }
        } catch {
          toast.error("Received malformed response from server");
          ws.close();
        }
      };

      ws.onerror = () => {
        if (stateRef.current === "streaming") {
          toast.error("Connection lost — the response may be incomplete");
        }
        setStreaming(false);
        stateRef.current = "idle";
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (stateRef.current === "streaming") {
          retryCountRef.current += 1;
          if (retryCountRef.current <= maxRetries) {
            stateRef.current = "reconnecting";
            setTimeout(() => connect(message, chatId, modelId), WS_RECONNECT_DELAY_MS);
          }
        }
      };

      wsRef.current = ws;
    },
    [token, WS_BASE, appendChunk, finalizeStream, setStreaming]
  );

  const sendMessage = useCallback(
    (message: string, chatId: number, modelId: string) => {
      if (stateRef.current === "streaming" || stateRef.current === "connecting") {
        toast.error("A message is already being sent");
        return;
      }
      retryCountRef.current = 0;
      connect(message, chatId, modelId);
    },
    [connect]
  );

  const cancel = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    stateRef.current = "idle";
    retryCountRef.current = 0;
    setStreaming(false);
  }, [setStreaming]);

  return { sendMessage, cancel };
}
