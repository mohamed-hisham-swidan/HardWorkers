import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import * as authService from "../api/services/authService";

export function useAuth() {
  const navigate = useNavigate();
  const { token, username, role, setToken, clearToken } = useAuthStore();

  const login = useCallback(
    async (username: string, password: string) => {
      const res = await authService.login({ username, password });
      setToken(res.access_token, username, "admin");
      navigate("/");
    },
    [setToken, navigate]
  );

  const logout = useCallback(() => {
    clearToken();
    navigate("/login");
  }, [clearToken, navigate]);

  const refresh = useCallback(async () => {
    try {
      const res = await authService.refreshToken();
      const user = await authService.getMe();
      setToken(res.access_token, user.username, user.role);
    } catch {
      clearToken();
      navigate("/login");
    }
  }, [setToken, clearToken, navigate]);

  return {
    isAuthenticated: !!token,
    token,
    username,
    role,
    login,
    logout,
    refresh,
  };
}
