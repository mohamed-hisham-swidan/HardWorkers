import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { keys } from "../../lib/queryKeys";
import * as chatService from "../../api/services/chatService";
import type {
  ChatSessionCreate,
  ChatSessionRename,
  ChatSessionPin,
} from "../../api/types/chat";

function onMutationError(err: unknown) {
  const msg = err instanceof Error ? err.message : "Request failed";
  toast.error(msg);
}

export function useChatsQuery(workspaceId: number) {
  return useQuery({
    queryKey: keys.chats(workspaceId),
    queryFn: () => chatService.listChats(workspaceId),
  });
}

export function useChatQuery(id: number) {
  return useQuery({
    queryKey: keys.chat(id),
    queryFn: () => chatService.getChat(id),
    enabled: !!id,
  });
}

export function useChatMutations(workspaceId: number) {
  const qc = useQueryClient();

  const createChat = useMutation({
    mutationFn: (data: ChatSessionCreate) => chatService.createChat(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.chats(workspaceId) });
    },
    onError: onMutationError,
  });

  const renameChat = useMutation({
    mutationFn: ({ id, data }: { id: number; data: ChatSessionRename }) =>
      chatService.renameChat(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.chats(workspaceId) });
    },
    onError: onMutationError,
  });

  const pinChat = useMutation({
    mutationFn: ({ id, data }: { id: number; data: ChatSessionPin }) =>
      chatService.pinChat(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.chats(workspaceId) });
    },
    onError: onMutationError,
  });

  const deleteChat = useMutation({
    mutationFn: (id: number) => chatService.deleteChat(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.chats(workspaceId) });
    },
    onError: onMutationError,
  });

  return { createChat, renameChat, pinChat, deleteChat };
}
