import { useChatStore } from "../../store/chatStore";
import { MarkdownRenderer } from "../../components/MarkdownRenderer";
import { LoadingDots } from "../../components/LoadingDots";

export function StreamingMessage() {
  const { streamBuffer, isStreaming } = useChatStore();
  if (!isStreaming && !streamBuffer) return null;
  return (
    <div className="flex flex-col items-start">
      <div className="chat-bubble ai">
        {streamBuffer ? (
          <MarkdownRenderer content={streamBuffer} />
        ) : (
          <LoadingDots />
        )}
      </div>
    </div>
  );
}
