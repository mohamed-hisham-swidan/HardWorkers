import { useEffect, useRef } from "react";
import { useChatStore } from "../../store/chatStore";
import { useUiStore } from "../../store/uiStore";
import { ChatMessage } from "./ChatMessage";
import { StreamingMessage } from "./StreamingMessage";
import { ChatInput } from "./ChatInput";
import { WelcomeScreen } from "./WelcomeScreen";
import { useMessagesQuery } from "../../hooks/queries/useMessages";
import { useActiveWorkspace } from "../../hooks/queries/useWorkspaces";

export function ChatContainer() {
  const activeChatId = useChatStore((s) => s.activeChatId);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const setActivePanel = useUiStore((s) => s.setActivePanel);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: workspace } = useActiveWorkspace();
  const { data: messagesData } = useMessagesQuery(activeChatId ?? 0, 0);

  const messages = messagesData?.items ?? [];

  useEffect(() => {
    setActivePanel("chat");
  }, [setActivePanel]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming]);

  if (!activeChatId) {
    return <WelcomeScreen />;
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-4"
      >
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {messages.map((msg) => (
            <ChatMessage
              key={msg.id}
              role={msg.role}
              content={msg.content}
              timestamp={msg.timestamp}
            />
          ))}
          <StreamingMessage />
        </div>
      </div>
      <div className="border-t border-[var(--border)] p-4">
        <div className="mx-auto max-w-3xl">
          <ChatInput />
        </div>
      </div>
    </div>
  );
}
