import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { keys } from "../../lib/queryKeys";
import * as modelService from "../../api/services/modelService";

function onError(err: unknown) {
  toast.error(err instanceof Error ? err.message : "Request failed");
}

export function useModelsQuery() {
  return useQuery({
    queryKey: keys.models(),
    queryFn: () => modelService.listModels(),
  });
}

export function useAvailableModels() {
  return useQuery({
    queryKey: keys.available(),
    queryFn: () => modelService.listAvailableModels(),
    staleTime: 30_000,
  });
}

export function useModelMutations() {
  const qc = useQueryClient();

  const deleteModel = useMutation({
    mutationFn: (id: number) => modelService.deleteModel(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.models() });
    },
    onError: onError,
  });

  const pullModel = useMutation({
    mutationFn: (name: string) => modelService.pullModel(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.available() });
    },
    onError: onError,
  });

  const setDefault = useMutation({
    mutationFn: (name: string) => modelService.setDefaultModel(name),
    onError: onError,
  });

  return { deleteModel, pullModel, setDefault };
}
