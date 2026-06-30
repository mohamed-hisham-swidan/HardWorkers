import api from "../client";
import { SETTINGS } from "../endpoints";

export async function getSettings(): Promise<{ settings: Record<string, unknown> }> {
  const res = await api.get<{ settings: Record<string, unknown> }>(SETTINGS.BASE);
  return res.data;
}

export async function updateSettings(
  patch: Record<string, unknown>
): Promise<{ settings: Record<string, unknown> }> {
  const res = await api.patch<{ settings: Record<string, unknown> }>(
    SETTINGS.BASE,
    { patch }
  );
  return res.data;
}
