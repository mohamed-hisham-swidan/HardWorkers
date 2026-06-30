export function WelcomeScreen() {
  const suggestions = [
    "What can you help me with?",
    "Explain quantum computing in simple terms",
    "Write a Python script to sort a CSV file",
    "Summarize the latest AI research papers",
  ];

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-8 p-8">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-[var(--text-primary)]">
          HardWorkers AI
        </h1>
        <p className="mt-2 text-sm text-[var(--text-muted)]">
          Select or create a chat to get started
        </p>
      </div>
      <div className="grid max-w-lg grid-cols-2 gap-3">
        {suggestions.map((s) => (
          <button
            key={s}
            className="rounded-md border border-[var(--border)] bg-surface p-3 text-left text-sm text-[var(--text-muted)] transition-colors hover:border-primary hover:text-[var(--text-primary)]"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
