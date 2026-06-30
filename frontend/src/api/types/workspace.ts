export interface Workspace {
  id: number;
  name: string;
  active_model: string;
  description: string;
  category: string;
  router_mode: string;
  memory_profile_id: number | null;
  memory_profile_name: string;
  created_at: string;
  updated_at: string;
}

export interface CreateWorkspaceRequest {
  name: string;
  active_model: string;
  description: string;
  category: string;
  router_mode: string;
  memory_profile_id: number | null;
}

export interface SwitchWorkspaceRequest {
  name: string;
}
