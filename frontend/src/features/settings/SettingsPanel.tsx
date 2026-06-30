import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import * as settingsService from "../../api/services/settingsService";
import { keys } from "../../lib/queryKeys";

export function SettingsPanel() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: keys.settings(),
    queryFn: () => settingsService.getSettings(),
  });

  const [json, setJson] = useState("");

  useEffect(() => {
    if (data) {
      setJson(JSON.stringify(data.settings, null, 2));
    }
  }, [data]);

  const mutation = useMutation({
    mutationFn: (patch: Record<string, unknown>) =>
      settingsService.updateSettings(patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.settings() });
    },
  });

  const handleSave = () => {
    try {
      const parsed = JSON.parse(json);
      mutation.mutate(parsed);
    } catch {
      // invalid JSON
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="text-lg font-semibold text-[var(--text-primary)]">
        Settings
      </h2>
      <textarea
        value={json}
        onChange={(e) => setJson(e.target.value)}
        className="min-h-[300px] w-full rounded-md border border-[var(--border)] bg-inputbg p-3 font-mono text-sm text-[var(--text-primary)] outline-none focus:border-primary"
      />
      <button
        onClick={handleSave}
        disabled={mutation.isPending}
        className="self-end rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
      >
        {mutation.isPending ? "Saving..." : "Save"}
      </button>
    </div>
  );
}
