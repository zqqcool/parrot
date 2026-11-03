import { isValidElement, useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { HighlighterCore, ThemedToken } from "shiki/core";

const MAX_HIGHLIGHTED_CODE_LENGTH = 100_000;
const SHIKI_LANGUAGE_ALIASES: Record<string, string> = {
  js: "javascript",
  jsonc: "json",
  py: "python",
  shell: "bash",
  sh: "bash",
  ts: "typescript",
  yml: "yaml",
};
const HIGHLIGHTED_LANGUAGES = new Set([
  "bash",
  "javascript",
  "json",
  "python",
  "typescript",
  "yaml",
]);

let highlighterPromise: Promise<HighlighterCore> | undefined;

type CodeElementProps = {
  children?: ReactNode;
  className?: string;
};

type Highlight = {
  background?: string;
  foreground?: string;
  tokens: ThemedToken[][];
};

type Props = {
  children?: ReactNode;
};

/** Renders Shiki tokens as React nodes so highlighted code never requires raw HTML injection. */
export function MarkdownCodeBlock({ children }: Props) {
  const { code, language } = readCodeBlock(children);
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const canHighlight = code.length <= MAX_HIGHLIGHTED_CODE_LENGTH;

  useEffect(() => {
    let disposed = false;
    setHighlight(null);
    if (!canHighlight)
      return () => {
        disposed = true;
      };

    void getHighlighter()
      .then((highlighter) =>
        highlighter.codeToTokens(code, {
          lang: language,
          theme: "github-light",
          tokenizeMaxLineLength: 10_000,
          tokenizeTimeLimit: 500,
        }),
      )
      .then((result) => {
        if (!disposed) {
          setHighlight({
            background: result.bg,
            foreground: result.fg,
            tokens: result.tokens,
          });
        }
      })
      .catch(() => {
        // A plaintext fallback keeps previews usable when a language cannot be loaded.
      });

    return () => {
      disposed = true;
    };
  }, [canHighlight, code, language]);

  const style: CSSProperties | undefined = highlight
    ? { backgroundColor: highlight.background, color: highlight.foreground }
    : undefined;

  return (
    <pre className="markdown-code-block" style={style}>
      <code>
        {highlight ? renderTokens(highlight.tokens) : code}
        {!canHighlight ? (
          <span className="markdown-code-block__notice">代码块过大，已关闭高亮。</span>
        ) : null}
      </code>
    </pre>
  );
}

function readCodeBlock(children: ReactNode) {
  if (!isValidElement<CodeElementProps>(children)) {
    return { code: "", language: "text" };
  }
  const code = toText(children.props.children).replace(/\n$/, "");
  const className = children.props.className ?? "";
  const languageName = className.match(/(?:^|\s)language-([^\s]+)/)?.[1]?.toLowerCase();
  const resolvedLanguage = languageName
    ? (SHIKI_LANGUAGE_ALIASES[languageName] ?? languageName)
    : "text";
  return {
    code,
    language: HIGHLIGHTED_LANGUAGES.has(resolvedLanguage) ? resolvedLanguage : "text",
  };
}

async function getHighlighter() {
  highlighterPromise ??= createHighlighter();
  return highlighterPromise;
}

async function createHighlighter() {
  const [core, engine, theme, bash, javascript, json, python, typescript, yaml] = await Promise.all(
    [
      import("shiki/core"),
      import("shiki/engine/oniguruma"),
      import("@shikijs/themes/github-light"),
      import("@shikijs/langs/bash"),
      import("@shikijs/langs/javascript"),
      import("@shikijs/langs/json"),
      import("@shikijs/langs/python"),
      import("@shikijs/langs/typescript"),
      import("@shikijs/langs/yaml"),
    ],
  );
  return core.createHighlighterCore({
    engine: engine.createOnigurumaEngine(import("shiki/wasm")),
    langs: [
      bash.default,
      javascript.default,
      json.default,
      python.default,
      typescript.default,
      yaml.default,
    ],
    themes: [theme.default],
  });
}

function toText(value: ReactNode): string {
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(toText).join("");
  if (isValidElement<CodeElementProps>(value)) return toText(value.props.children);
  return "";
}

function renderTokens(lines: ThemedToken[][]) {
  return lines.map((line, lineIndex) => (
    <span className="markdown-code-block__line" key={lineIndex}>
      {line.map((token, tokenIndex) => (
        <span className="markdown-code-block__token" key={tokenIndex} style={tokenStyle(token)}>
          {token.content}
        </span>
      ))}
    </span>
  ));
}

function tokenStyle(token: ThemedToken): CSSProperties {
  return {
    backgroundColor: token.bgColor,
    color: token.color,
    fontStyle: token.fontStyle && token.fontStyle & 1 ? "italic" : undefined,
    fontWeight: token.fontStyle && token.fontStyle & 2 ? 700 : undefined,
    textDecoration: token.fontStyle && token.fontStyle & 4 ? "underline" : undefined,
  };
}
