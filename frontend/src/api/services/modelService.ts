import api from "../client";
import { MODELS } from "../endpoints";
import type {
  ModelConfig,
  ModelListItem,
  CreateModelRequest,
  TestConnectionResponse,
} from "../types/model";
import type { PaginatedResponse } from "../types/chat";

export async function listModels(): Promise<PaginatedResponse<ModelConfig>> {
  const res = await api.get<PaginatedResponse<ModelConfig>>(MODELS.BASE);
  return res.data;
}

export async function listAvailableModels(): Promise<{
  items: ModelListItem[];
}> {
  const res = await api.get<{ items: ModelListItem[] }>(MODELS.AVAILABLE);
  return res.data;
}

export async function createModel(
  data: CreateModelRequest
): Promise<ModelConfig> {
  const res = await api.post<ModelConfig>(MODELS.BASE, data);
  return res.data;
}

export async function getModel(id: number): Promise<ModelConfig> {
  const res = await api.get<ModelConfig>(MODELS.BY_ID(id));
  return res.data;
}

export async function deleteModel(id: number): Promise<void> {
  await api.delete(MODELS.BY_ID(id));
}

export async function testModel(id: number): Promise<TestConnectionResponse> {
  const res = await api.get<TestConnectionResponse>(MODELS.TEST(id));
  return res.data;
}

export async function pullModel(modelName: string): Promise<{
  status: string;
  message: string;
}> {
  const res = await api.post<{ status: string; message: string }>(
    MODELS.PULL,
    null,
    { params: { model_name: modelName } }
  );
  return res.data;
}

export async function setDefaultModel(
  modelName: string
): Promise<{ status: string; default_model: string }> {
  const res = await api.post<{ status: string; default_model: string }>(
    MODELS.DEFAULT,
    null,
    { params: { model_name: modelName } }
  );
  return res.data;
}
