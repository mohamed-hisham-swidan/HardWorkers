import { NewChatButton } from "./NewChatButton";
import { ChatList } from "./ChatList";
import { WorkspaceSelector } from "./WorkspaceSelector";
import { useUiStore } from "../../store/uiStore";

export function Sidebar() {
  const toggleMemoryPanel = useUiStore((s) => s.toggleMemoryPanel);
  const memoryPanelOpen = useUiStore((s) => s.memoryPanelOpen);
  const setActivePanel = useUiStore((s) => s.setActivePanel);
  const activePanel = useUiStore((s) => s.activePanel);

  return (
    <aside className="fixed left-0 top-0 flex h-full w-[280px] flex-col border-r border-[var(--border)] bg-panel">
      <div className="flex items-center justify-between border-b border-[var(--border)] p-3">
        <h1 className="text-sm font-semibold text-[var(--text-primary)]">
          HardWorkers
        </h1>
        <div className="flex items-center gap-1">
          <button
            onClick={toggleMemoryPanel}
            title={memoryPanelOpen ? "Close memory" : "Open memory"}
            className={`rounded-md p-1.5 text-sm transition-colors ${
              memoryPanelOpen
                ? "text-[var(--accent)] bg-[var(--accent)]/10"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-surface"
            }`}
          >
            🧠
          </button>
          <button
            onClick={() =>
              setActivePanel(activePanel === "settings" ? "chat" : "settings")
            }
            title="Settings"
            className={`rounded-md p-1.5 text-sm transition-colors ${
              activePanel === "settings"
                ? "text-[var(--accent)] bg-[var(--accent)]/10"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-surface"
            }`}
          >
            ⚙
          </button>
        </div>
      </div>
      <div className="border-b border-[var(--border)] p-3">
        <WorkspaceSelector />
      </div>
      <div className="border-b border-[var(--border)] p-3">
        <NewChatButton />
      </div>
      <div className="flex-1 overflow-y-auto">
        <ChatList />
      </div>
    </aside>
  );
}
