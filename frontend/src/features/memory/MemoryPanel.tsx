import { useFactsQuery } from "../../hooks/queries/useMemory";
import { FactCard } from "./FactCard";
import { AddFactForm } from "./AddFactForm";

export function MemoryPanel() {
  const { data } = useFactsQuery(0, 20);
  const facts = data?.items ?? [];

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-[var(--border)] p-3">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">
          Memory
        </h2>
      </div>
      <div className="border-b border-[var(--border)] p-3">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted2)]">
          Add Fact
        </p>
        <AddFactForm />
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted2)]">
          Stored Facts
        </p>
        {facts.length === 0 && (
          <p className="text-xs text-[var(--text-muted)]">No facts stored yet.</p>
        )}
        <div className="space-y-2">
          {facts.map((fact) => (
            <FactCard key={fact.id} fact={fact} />
          ))}
        </div>
      </div>
    </div>
  );
}
