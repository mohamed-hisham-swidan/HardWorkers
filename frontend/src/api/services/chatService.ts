import api from "../client";
import { CHATS } from "../endpoints";
import type {
  ChatSession,
  ChatSessionCreate,
  ChatSessionRename,
  ChatSessionPin,
  Message,
  SendMessageRequest,
  SendMessageResponse,
  PaginatedResponse,
} from "../types/chat";

export async function listChats(
  workspaceId: number,
  offset = 0,
  limit = 50
): Promise<PaginatedResponse<ChatSession>> {
  const res = await api.get<PaginatedResponse<ChatSession>>(CHATS.BASE, {
    params: { offset, limit },
  });
  return res.data;
}

export async function createChat(
  data: ChatSessionCreate
): Promise<ChatSession> {
  const res = await api.post<ChatSession>(CHATS.BASE, data);
  return res.data;
}

export async function getChat(id: number): Promise<ChatSession> {
  const res = await api.get<ChatSession>(CHATS.BY_ID(id));
  return res.data;
}

export async function renameChat(
  id: number,
  data: ChatSessionRename
): Promise<ChatSession> {
  const res = await api.patch<ChatSession>(CHATS.RENAME(id), data);
  return res.data;
}

export async function pinChat(
  id: number,
  data: ChatSessionPin
): Promise<ChatSession> {
  const res = await api.patch<ChatSession>(CHATS.PIN(id), data);
  return res.data;
}

export async function deleteChat(id: number): Promise<void> {
  await api.delete(CHATS.BY_ID(id));
}

export async function getMessages(
  chatId: number,
  offset = 0,
  limit = 50
): Promise<PaginatedResponse<Message>> {
  const res = await api.get<PaginatedResponse<Message>>(
    CHATS.MESSAGES(chatId),
    { params: { offset, limit } }
  );
  return res.data;
}

export async function clearMessages(chatId: number): Promise<void> {
  await api.delete(CHATS.MESSAGES(chatId));
}

export async function sendMessage(
  chatId: number,
  data: SendMessageRequest
): Promise<SendMessageResponse> {
  const res = await api.post<SendMessageResponse>(CHATS.SEND(chatId), data);
  return res.data;
}
