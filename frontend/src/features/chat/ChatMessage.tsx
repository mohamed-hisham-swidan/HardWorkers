import { MarkdownRenderer } from "../../components/MarkdownRenderer";
import { cn } from "../../lib/utils";

interface Props {
  role: string;
  content: string;
  timestamp?: string;
}

export function ChatMessage({ role, content, timestamp }: Props) {
  const isUser = role === "user";
  return (
    <div
      className={cn("flex flex-col", isUser ? "items-end" : "items-start")}
    >
      <div
        className={cn(
          "chat-bubble",
          isUser ? "user" : "ai"
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : (
          <MarkdownRenderer content={content} />
        )}
      </div>
      {timestamp && (
        <span className="mt-1 px-1 text-[10px] text-[var(--text-muted2)]">
          {new Date(timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      )}
    </div>
  );
}
