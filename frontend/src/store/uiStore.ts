import { create } from "zustand";

interface UiState {
  sidebarOpen: boolean;
  memoryPanelOpen: boolean;
  theme: "dark" | "light";
  activePanel: "chat" | "settings" | null;

  toggleSidebar: () => void;
  setSidebarOpen: (v: boolean) => void;
  toggleMemoryPanel: () => void;
  setMemoryPanelOpen: (v: boolean) => void;
  setTheme: (t: "dark" | "light") => void;
  setActivePanel: (p: "chat" | "settings" | null) => void;
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  memoryPanelOpen: false,
  theme: "dark",
  activePanel: "chat",

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setSidebarOpen: (v) => set({ sidebarOpen: v }),
  toggleMemoryPanel: () =>
    set((s) => ({ memoryPanelOpen: !s.memoryPanelOpen })),
  setMemoryPanelOpen: (v) => set({ memoryPanelOpen: v }),
  setTheme: (t) => set({ theme: t }),
  setActivePanel: (p) => set({ activePanel: p }),
}));
