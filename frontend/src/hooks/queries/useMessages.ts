import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { keys } from "../../lib/queryKeys";
import * as chatService from "../../api/services/chatService";
import type { SendMessageRequest } from "../../api/types/chat";
import { PAGE_SIZE } from "../../config/constants";

export function useMessagesQuery(chatId: number, page = 0) {
  return useQuery({
    queryKey: keys.messages(chatId, page),
    queryFn: () =>
      chatService.getMessages(chatId, page * PAGE_SIZE, PAGE_SIZE),
    enabled: !!chatId,
  });
}

export function useSendMessage(chatId: number) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (data: SendMessageRequest) =>
      chatService.sendMessage(chatId, data),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: keys.messages(chatId, 0),
      });
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Failed to send message");
    },
  });
}
