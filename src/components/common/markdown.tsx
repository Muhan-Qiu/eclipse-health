import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link } from "react-router-dom";
import { cn } from "cn";

export interface MarkdownTextProps {
  content: string;
  className?: string;
  /** 流式输出时在最后一段文字后显示闪烁光标。 */
  streaming?: boolean;
}

function isInternalLink(href: string | undefined): href is string {
  return Boolean(href && href.startsWith("/") && !href.startsWith("//"));
}

const linkClass = "text-primary underline underline-offset-2 hover:opacity-80";

/**
 * 助手消息的 Markdown 渲染。
 *
 * - 原始 HTML 默认不渲染（react-markdown 会转义），避免模型输出注入；
 * - 站内链接走 react-router，外链新窗口打开；
 * - 远程图片不加载，只显示替代文字，避免泄露本机 IP 或触发追踪像素。
 */
export function MarkdownText({ content, className, streaming }: MarkdownTextProps) {
  return (
    <div
      className={cn(
        "eh-markdown min-w-0 break-words",
        streaming && "eh-streaming",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="my-1.5">{children}</p>,
          h1: ({ children }) => (
            <h1 className="mt-3 mb-1.5 text-base font-semibold first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="mt-3 mb-1.5 text-[0.95rem] font-semibold first:mt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mt-2.5 mb-1 text-sm font-semibold first:mt-0">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="mt-2 mb-1 text-sm font-medium first:mt-0">{children}</h4>
          ),
          ul: ({ children }) => (
            <ul className="my-1.5 list-disc space-y-1 pl-5 marker:text-muted-foreground">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="my-1.5 list-decimal space-y-1 pl-5 marker:text-muted-foreground">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="pl-0.5 [&>p]:my-0">{children}</li>,
          strong: ({ children }) => (
            <strong className="font-semibold text-foreground">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          del: ({ children }) => <del className="text-muted-foreground">{children}</del>,
          a: ({ href, children }) =>
            isInternalLink(href) ? (
              <Link to={href} className={linkClass}>
                {children}
              </Link>
            ) : (
              <a
                href={href}
                target="_blank"
                rel="noreferrer noopener"
                className={linkClass}
              >
                {children}
              </a>
            ),
          img: ({ alt }) => (
            <span className="text-xs text-muted-foreground">[{alt || "image"}]</span>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-2 border-border pl-3 text-muted-foreground">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-3 border-border" />,
          code: ({ className: codeClassName, children }) => (
            <code
              className={cn(
                "rounded bg-subtle px-1 py-0.5 font-mono text-[0.85em]",
                codeClassName,
              )}
            >
              {children}
            </code>
          ),
          pre: ({ children }) => (
            <pre className="my-2 overflow-x-auto rounded-lg border border-border/60 bg-subtle/60 p-3 font-mono text-xs leading-5">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto rounded-lg border border-border/60">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-border/60 bg-subtle/60 px-2 py-1.5 text-left font-medium">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-border/40 px-2 py-1.5 align-top last:border-b-0">
              {children}
            </td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
