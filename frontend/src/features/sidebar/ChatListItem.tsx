import { useState } from "react";
import { useChatStore } from "../../store/chatStore";
import type { ChatSession } from "../../api/types/chat";

interface Props {
  chat: ChatSession;
}

export function ChatListItem({ chat }: Props) {
  const activeChatId = useChatStore((s) => s.activeChatId);
  const setActiveChat = useChatStore((s) => s.setActiveChat);
  const isActive = activeChatId === chat.id;

  return (
    <button
      onClick={() => setActiveChat(chat.id)}
      className={`w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
        isActive
          ? "bg-[var(--accent)]/10 text-[var(--accent)]"
          : "text-[var(--text-muted)] hover:bg-surface hover:text-[var(--text-primary)]"
      }`}
    >
      <span className="line-clamp-1">{chat.name}</span>
    </button>
  );
}
