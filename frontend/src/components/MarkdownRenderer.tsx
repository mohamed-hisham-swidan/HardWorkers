import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { CodeBlock } from "./CodeBlock";

interface Props {
  content: string;
}

export function MarkdownRenderer({ content }: Props) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={{
        code({ className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || "");
          const code = String(children).replace(/\n$/, "");
          if (match) {
            return <CodeBlock language={match[1]} code={code} />;
          }
          return (
            <code
              className="rounded-sm bg-[var(--bg-input)] px-1 py-0.5 text-sm"
              {...props}
            >
              {children}
            </code>
          );
        },
        pre({ children }) {
          return <>{children}</>;
        },
        a({ href, children }) {
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline hover:opacity-80"
            >
              {children}
            </a>
          );
        },
        p({ children }) {
          return <p className="mb-2 leading-relaxed">{children}</p>;
        },
        ul({ children }) {
          return <ul className="mb-2 list-disc pl-5">{children}</ul>;
        },
        ol({ children }) {
          return <ol className="mb-2 list-decimal pl-5">{children}</ol>;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
