import { useState } from "react";

interface Props {
  language: string;
  code: string;
}

export function CodeBlock({ language, code }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-2 overflow-hidden rounded-md border border-[var(--border)]">
      <div className="flex items-center justify-between bg-[var(--bg-input)] px-3 py-1.5 text-xs text-[var(--text-muted)]">
        <span>{language}</span>
        <button
          onClick={handleCopy}
          className="hover:text-[var(--text-primary)]"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-sm leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}
