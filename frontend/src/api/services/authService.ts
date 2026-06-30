import api from "../client";
import { AUTH } from "../endpoints";
import type { LoginRequest, TokenResponse, UserInfo } from "../types/auth";

export async function login(data: LoginRequest): Promise<TokenResponse> {
  const res = await api.post<TokenResponse>(AUTH.LOGIN, data);
  return res.data;
}

export async function refreshToken(): Promise<TokenResponse> {
  const res = await api.post<TokenResponse>(AUTH.REFRESH);
  return res.data;
}

export async function getMe(): Promise<UserInfo> {
  const res = await api.get<UserInfo>(AUTH.ME);
  return res.data;
}
