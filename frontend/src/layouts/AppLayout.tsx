import { Outlet } from "react-router-dom";
import { Sidebar } from "../features/sidebar/Sidebar";
import { MemoryPanel } from "../features/memory/MemoryPanel";
import { ChatContainer } from "../features/chat/ChatContainer";
import { SettingsPanel } from "../features/settings/SettingsPanel";
import { useUiStore } from "../store/uiStore";

export function AppLayout() {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const memoryPanelOpen = useUiStore((s) => s.memoryPanelOpen);
  const activePanel = useUiStore((s) => s.activePanel);

  return (
    <div className="flex h-screen overflow-hidden bg-base">
      <Sidebar />
      <main
        className={`flex flex-1 flex-col transition-all duration-200 ${
          sidebarOpen ? "ml-[280px]" : "ml-0"
        }`}
      >
        {activePanel === "settings" ? <SettingsPanel /> : <ChatContainer />}
      </main>
      {memoryPanelOpen && activePanel !== "settings" && (
        <div className="w-[280px] flex-shrink-0 border-l border-[var(--border)] bg-panel">
          <MemoryPanel />
        </div>
      )}
      <Outlet />
    </div>
  );
}
