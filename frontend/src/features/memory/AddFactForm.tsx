import { useState, type FormEvent } from "react";
import { useMemoryMutations } from "../../hooks/queries/useMemory";

export function AddFactForm() {
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const { addFact } = useMemoryMutations();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!key.trim() || !value.trim()) return;
    await addFact.mutateAsync({
      key: key.trim(),
      value: value.trim(),
      importance: 5,
    });
    setKey("");
    setValue("");
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <input
        type="text"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        placeholder="Fact key"
        className="w-full rounded-md border border-[var(--border)] bg-inputbg px-2 py-1.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted2)] outline-none focus:border-primary"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Fact value"
        className="w-full rounded-md border border-[var(--border)] bg-inputbg px-2 py-1.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted2)] outline-none focus:border-primary"
      />
      <button
        type="submit"
        disabled={addFact.isPending}
        className="w-full rounded-md bg-primary px-2 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
      >
        {addFact.isPending ? "Adding..." : "Add Fact"}
      </button>
    </form>
  );
}
