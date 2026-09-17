import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

const LANGUAGE_MAP: Record<string, string> = {
  python: "python",
  javascript: "javascript",
  typescript: "typescript",
  java: "java",
  c: "c",
  cpp: "cpp",
  sql: "sql",
  html: "markup",
  css: "css",
  json: "json",
  yaml: "yaml",
  toml: "toml",
  markdown: "markdown",
  shell: "bash",
};

export function CodeViewer({
  content,
  language,
  highlightRange,
}: {
  content: string;
  language: string | null;
  highlightRange?: { start: number; end: number };
}) {
  const prismLang = (language && LANGUAGE_MAP[language]) || "text";

  return (
    <SyntaxHighlighter
      language={prismLang}
      style={oneDark}
      showLineNumbers
      wrapLines
      lineProps={(lineNumber) => {
        const isHighlighted =
          highlightRange && lineNumber >= highlightRange.start && lineNumber <= highlightRange.end;
        return {
          style: isHighlighted
            ? { display: "block", backgroundColor: "rgba(99, 102, 241, 0.18)" }
            : { display: "block" },
        };
      }}
      customStyle={{ margin: 0, background: "transparent", fontSize: "13px", height: "100%" }}
    >
      {content}
    </SyntaxHighlighter>
  );
}
