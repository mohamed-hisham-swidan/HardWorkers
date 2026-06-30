import { useActiveWorkspace, useWorkspacesQuery, useWorkspaceMutations } from "../../hooks/queries/useWorkspaces";
import { useChatStore } from "../../store/chatStore";

export function WorkspaceSelector() {
  const { data: active } = useActiveWorkspace();
  const { data: workspacesData } = useWorkspacesQuery();
  const { switchWorkspace } = useWorkspaceMutations();
  const setActiveChat = useChatStore((s) => s.setActiveChat);

  const workspaces = workspacesData?.items ?? [];

  const handleSwitch = async (name: string) => {
    await switchWorkspace.mutateAsync({ name });
    setActiveChat(null);
  };

  return (
    <select
      value={active?.name ?? ""}
      onChange={(e) => handleSwitch(e.target.value)}
      className="w-full rounded-md border border-[var(--border)] bg-inputbg px-2 py-1.5 text-sm text-[var(--text-primary)] outline-none focus:border-primary"
    >
      {workspaces.map((ws) => (
        <option key={ws.id} value={ws.name}>
          {ws.name}
        </option>
      ))}
    </select>
  );
}
