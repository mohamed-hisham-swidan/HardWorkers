interface Props {
  provider: string;
}

const colors: Record<string, string> = {
  ollama: "bg-blue-500/20 text-blue-400",
  openai: "bg-green-500/20 text-green-400",
  anthropic: "bg-purple-500/20 text-purple-400",
  deepseek: "bg-orange-500/20 text-orange-400",
  openrouter: "bg-pink-500/20 text-pink-400",
  groq: "bg-yellow-500/20 text-yellow-400",
  custom: "bg-gray-500/20 text-gray-400",
};

export function ModelBadge({ provider }: Props) {
  const cls = colors[provider] || colors.custom;
  return (
    <span
      className={`inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-medium ${cls}`}
    >
      {provider}
    </span>
  );
}
