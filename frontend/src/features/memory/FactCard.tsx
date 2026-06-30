import type { Fact } from "../../api/types/memory";

interface Props {
  fact: Fact;
}

export function FactCard({ fact }: Props) {
  return (
    <div className="rounded-md border border-[var(--border)] bg-surface p-2">
      <p className="text-xs font-medium text-[var(--accent)]">{fact.key}</p>
      <p className="mt-0.5 text-xs text-[var(--text-primary)] line-clamp-2">
        {fact.value}
      </p>
      <p className="mt-1 text-[10px] text-[var(--text-muted2)]">
        importance: {fact.importance}
      </p>
    </div>
  );
}
