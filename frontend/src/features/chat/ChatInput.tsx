import { useState, useRef, useEffect, type KeyboardEvent, type ChangeEvent } from "react";
import { toast } from "sonner";
import { useChatStore } from "../../store/chatStore";
import { useModelStore } from "../../store/modelStore";
import { useStreamChat } from "../../hooks/useStreamChat";
import { ModelSelector } from "../models/ModelSelector";
import { MAX_MESSAGE_LENGTH } from "../../config/constants";

export function ChatInput() {
  const [text, setText] = useState("");
  const [pastedImage, setPastedImage] = useState<string | null>(null);
  const [isListening, setIsListening] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const activeChatId = useChatStore((s) => s.activeChatId);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const selectedModel = useModelStore((s) => s.selectedModelName);
  const { sendMessage, cancel } = useStreamChat();

  // ── Image paste via Clipboard API ──
  useEffect(() => {
    const handlePaste = async (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      for (const item of Array.from(items)) {
        if (item.type.startsWith("image/")) {
          e.preventDefault();
          const file = item.getAsFile();
          if (!file) continue;
          const reader = new FileReader();
          reader.onload = () => {
            setPastedImage(reader.result as string);
          };
          reader.readAsDataURL(file);
          return;
        }
      }
    };
    document.addEventListener("paste", handlePaste);
    return () => document.removeEventListener("paste", handlePaste);
  }, []);

  // ── Voice via Web Speech API ──
  const SpeechRecognitionAPI =
    (window as unknown as Record<string, unknown>).SpeechRecognition ||
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition;

  const toggleVoice = () => {
    if (!SpeechRecognitionAPI) {
      toast.error("Voice input not supported in this browser");
      return;
    }
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }
    const recognition = new (SpeechRecognitionAPI as new () => SpeechRecognition)();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.continuous = false;

    recognition.onresult = (e: SpeechRecognitionEvent) => {
      const transcript = e.results[0][0].transcript;
      setText((prev) => prev + transcript);
      setIsListening(false);
    };
    recognition.onerror = () => {
      toast.error("Voice input error");
      setIsListening(false);
    };
    recognition.onend = () => setIsListening(false);

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  };

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed && !pastedImage) return;
    if (!activeChatId || !selectedModel || isStreaming) return;
    if (trimmed.length > MAX_MESSAGE_LENGTH) {
      toast.error("Message too long");
      return;
    }
    let finalText = trimmed;
    if (pastedImage) {
      finalText += `\n![attached image](${pastedImage})`;
    }
    setText("");
    setPastedImage(null);
    sendMessage(finalText, activeChatId, selectedModel);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!activeChatId) return null;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <div className="w-40 flex-shrink-0">
          <ModelSelector />
        </div>
      </div>
      {pastedImage && (
        <div className="flex items-center gap-2 rounded-md border border-[var(--border)] bg-surface p-2">
          <img
            src={pastedImage}
            alt="pasted"
            className="h-10 w-10 rounded object-cover"
          />
          <span className="text-xs text-[var(--text-muted)]">Image attached</span>
          <button
            onClick={() => setPastedImage(null)}
            className="ml-auto text-xs text-[var(--error)] hover:opacity-80"
          >
            Remove
          </button>
        </div>
      )}
      <div className="flex items-end gap-2">
        <button
          onClick={toggleVoice}
          title={isListening ? "Stop recording" : "Voice input"}
          className={`flex h-10 w-10 items-center justify-center rounded-md border border-[var(--border)] bg-surface text-sm transition-colors ${
            isListening
              ? "text-[var(--error)] border-[var(--error)]"
              : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          }`}
        >
          {isListening ? "◉" : "🎤"}
        </button>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message... (Ctrl+V to paste image)"
          rows={1}
          className="max-h-32 min-h-[40px] flex-1 resize-none rounded-md border border-[var(--border)] bg-inputbg px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted2)] outline-none focus:border-primary"
        />
        {isStreaming ? (
          <button
            onClick={cancel}
            className="flex h-10 items-center gap-1.5 rounded-md bg-[var(--error)] px-4 text-sm font-medium text-white hover:opacity-90"
          >
            Stop
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!text.trim() && !pastedImage}
            className="flex h-10 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}
