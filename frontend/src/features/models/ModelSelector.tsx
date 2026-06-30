import { useAvailableModels } from "../../hooks/queries/useModels";
import { useModelStore } from "../../store/modelStore";
import { ModelBadge } from "./ModelBadge";
import type { ModelListItem } from "../../api/types/model";

export function ModelSelector() {
  const { data } = useAvailableModels();
  const { selectedModelName, setSelectedModel } = useModelStore();

  const models: ModelListItem[] = data?.items ?? [];

  return (
    <select
      value={selectedModelName}
      onChange={(e) => setSelectedModel(e.target.value)}
      className="w-full rounded-md border border-[var(--border)] bg-inputbg px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-primary"
    >
      {models.length === 0 && (
        <option value="">No models available</option>
      )}
      {models.map((m) => (
        <option key={m.name} value={m.name}>
          {m.name}
        </option>
      ))}
    </select>
  );
}
