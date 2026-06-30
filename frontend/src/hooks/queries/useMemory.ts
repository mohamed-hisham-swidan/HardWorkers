import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { keys } from "../../lib/queryKeys";
import * as memoryService from "../../api/services/memoryService";
import type { AddFactRequest, SearchMemoryRequest } from "../../api/types/memory";

function onError(err: unknown) {
  toast.error(err instanceof Error ? err.message : "Request failed");
}

export function useFactsQuery(offset = 0, limit = 50) {
  return useQuery({
    queryKey: [...keys.facts(), offset, limit],
    queryFn: () => memoryService.listFacts(offset, limit),
  });
}

export function useMemoryMutations() {
  const qc = useQueryClient();

  const addFact = useMutation({
    mutationFn: (data: AddFactRequest) => memoryService.addFact(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.facts() });
    },
    onError: onError,
  });

  const deleteFact = useMutation({
    mutationFn: (id: number) => memoryService.deleteFact(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.facts() });
    },
    onError: onError,
  });

  const searchFacts = useMutation({
    mutationFn: (data: SearchMemoryRequest) =>
      memoryService.searchFacts(data),
    onError: onError,
  });

  return { addFact, deleteFact, searchFacts };
}
