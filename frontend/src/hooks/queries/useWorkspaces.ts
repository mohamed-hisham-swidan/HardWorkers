import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { keys } from "../../lib/queryKeys";
import * as workspaceService from "../../api/services/workspaceService";
import type { CreateWorkspaceRequest, SwitchWorkspaceRequest } from "../../api/types/workspace";

function onError(err: unknown) {
  toast.error(err instanceof Error ? err.message : "Request failed");
}

export function useWorkspacesQuery() {
  return useQuery({
    queryKey: keys.workspaces(),
    queryFn: () => workspaceService.listWorkspaces(),
  });
}

export function useActiveWorkspace() {
  return useQuery({
    queryKey: keys.active(),
    queryFn: () => workspaceService.getActiveWorkspace(),
  });
}

export function useWorkspaceMutations() {
  const qc = useQueryClient();

  const createWorkspace = useMutation({
    mutationFn: (data: CreateWorkspaceRequest) =>
      workspaceService.createWorkspace(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.workspaces() });
      qc.invalidateQueries({ queryKey: keys.active() });
    },
    onError: onError,
  });

  const switchWorkspace = useMutation({
    mutationFn: (data: SwitchWorkspaceRequest) =>
      workspaceService.switchWorkspace(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.workspaces() });
      qc.invalidateQueries({ queryKey: keys.active() });
    },
    onError: onError,
  });

  return { createWorkspace, switchWorkspace };
}
