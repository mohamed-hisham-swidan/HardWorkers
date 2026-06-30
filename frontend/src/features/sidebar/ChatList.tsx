import { useActiveWorkspace } from "../../hooks/queries/useWorkspaces";
import { useChatsQuery } from "../../hooks/queries/useChats";
import { ChatListItem } from "./ChatListItem";
import { formatDate } from "../../lib/utils";
import type { ChatSession } from "../../api/types/chat";

function groupChats(chats: ChatSession[]): Map<string, ChatSession[]> {
  const groups = new Map<string, ChatSession[]>();
  const pinned = chats.filter((c) => c.pinned);
  const unpinned = chats.filter((c) => !c.pinned);

  if (pinned.length) groups.set("Pinned", pinned);

  for (const chat of unpinned) {
    const label = formatDate(chat.created_at);
    const existing = groups.get(label) || [];
    existing.push(chat);
    groups.set(label, existing);
  }

  return groups;
}

export function ChatList() {
  const { data: workspace } = useActiveWorkspace();
  const wsId = workspace?.id ?? 0;
  const { data } = useChatsQuery(wsId);
  const chats = data?.items ?? [];
  const groups = groupChats(chats);

  return (
    <div className="space-y-4 p-3">
      {Array.from(groups.entries()).map(([label, items]) => (
        <div key={label}>
          <p className="mb-1 px-2 text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted2)]">
            {label}
          </p>
          {items.map((chat) => (
            <ChatListItem key={chat.id} chat={chat} />
          ))}
        </div>
      ))}
    </div>
  );
}
