import { useState } from "react";
import { useChatStore } from "../../store/chatStore";
import { useActiveWorkspace } from "../../hooks/queries/useWorkspaces";
import { useChatMutations } from "../../hooks/queries/useChats";

export function NewChatButton() {
  const [loading, setLoading] = useState(false);
  const { data: workspace } = useActiveWorkspace();
  const wsId = workspace?.id ?? 0;
  const { createChat } = useChatMutations(wsId);
  const setActiveChat = useChatStore((s) => s.setActiveChat);

  const handleClick = async () => {
    if (!wsId || loading) return;
    setLoading(true);
    try {
      const chat = await createChat.mutateAsync({
        name: "New Chat",
        pinned: false,
        workspace_id: wsId,
      });
      setActiveChat(chat.id);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className="w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
    >
      {loading ? "Creating..." : "+ New Chat"}
    </button>
  );
}
