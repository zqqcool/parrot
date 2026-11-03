import "katex/dist/katex.min.css";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import remarkFrontmatter from "remark-frontmatter";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import "@/shared/ui/markdown-preview.css";
import { MarkdownCodeBlock } from "@/shared/ui/MarkdownCodeBlock";

type Props = {
  className?: string;
  highlightCode?: boolean;
  value: string;
};

/** Safe, reusable rendering for user-authored Markdown files. */
export function MarkdownPreview({ className, highlightCode = true, value }: Props) {
  return (
    <div
      className={["markdown-preview", className].filter(Boolean).join(" ")}
      aria-label="Markdown 预览"
    >
      <ReactMarkdown
        components={highlightCode ? { pre: MarkdownCodeBlock } : undefined}
        rehypePlugins={[rehypeRaw, rehypeSanitize, rehypeKatex]}
        remarkPlugins={[remarkFrontmatter, remarkGfm, remarkMath]}
      >
        {value}
      </ReactMarkdown>
    </div>
  );
}
