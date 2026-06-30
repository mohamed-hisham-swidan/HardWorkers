import api from "../client";
import { WORKSPACES } from "../endpoints";
import type {
  Workspace,
  CreateWorkspaceRequest,
  SwitchWorkspaceRequest,
} from "../types/workspace";

export async function listWorkspaces(): Promise<{
  items: Workspace[];
  total: number;
}> {
  const res = await api.get<{ items: Workspace[]; total: number }>(
    WORKSPACES.BASE
  );
  return res.data;
}

export async function getActiveWorkspace(): Promise<Workspace> {
  const res = await api.get<Workspace>(WORKSPACES.ACTIVE);
  return res.data;
}

export async function createWorkspace(
  data: CreateWorkspaceRequest
): Promise<Workspace> {
  const res = await api.post<Workspace>(WORKSPACES.BASE, data);
  return res.data;
}

export async function getWorkspace(id: number): Promise<Workspace> {
  const res = await api.get<Workspace>(WORKSPACES.BY_ID(id));
  return res.data;
}

export async function updateWorkspace(
  id: number,
  data: Partial<CreateWorkspaceRequest>
): Promise<Workspace> {
  const res = await api.patch<Workspace>(WORKSPACES.BY_ID(id), data);
  return res.data;
}

export async function deleteWorkspace(id: number): Promise<void> {
  await api.delete(WORKSPACES.BY_ID(id));
}

export async function switchWorkspace(
  data: SwitchWorkspaceRequest
): Promise<{ status: string; active_workspace: string }> {
  const res = await api.post<{ status: string; active_workspace: string }>(
    WORKSPACES.SWITCH,
    data
  );
  return res.data;
}
