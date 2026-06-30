import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  username: string | null;
  role: string | null;
  setToken: (token: string, username: string, role: string) => void;
  clearToken: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      role: null,
      setToken: (token, username, role) => set({ token, username, role }),
      clearToken: () =>
        set({ token: null, username: null, role: null }),
    }),
    { name: "hw-auth" }
  )
);
