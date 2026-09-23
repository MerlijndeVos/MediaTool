import { memo, useEffect, useMemo, useState } from "react";
import { MAX_CODE_CHARS, languageFor, loadHighlighter, tokenizeLog, useSyntax } from "@/lib/syntax";
import { cn } from "@/lib/utils";

/**
 * A file's text, highlighted by its extension when code highlighting is on. Until highlight.js has
 * loaded (and for plain text, very long text, or when `active` is false) the text shows as it is.
 */
export function CodeBlock({
  text,
  path,
  active = true,
  suffix,
  always = false,
  className,
}: {
  text: string;
  /** The file name; its extension picks the language. */
  path: string;
  /** False while the block is out of sight (a closed <details>), so it is not highlighted yet. */
  active?: boolean;
  /** Plain text after the code, such as a "cut off" note. */
  suffix?: string;
  /** Highlight even when code highlighting is off (the scheme previews in Settings). */
  always?: boolean;
  className?: string;
}) {
  const enabled = useSyntax().code || always;
  const language = languageFor(path);
  const wanted = enabled && active && language !== null && text.length <= MAX_CODE_CHARS;
  const [html, setHtml] = useState<{ text: string; language: string; html: string } | null>(null);

  useEffect(() => {
    if (!wanted || !language || (html && html.text === text && html.language === language)) return;
    let cancelled = false;
    loadHighlighter()
      .then(({ highlightCode }) => {
        if (!cancelled) setHtml({ text, language, html: highlightCode(text, language) });
      })
      .catch(() => undefined); // stays plain
    return () => {
      cancelled = true;
    };
  }, [wanted, language, text, html]);

  const current = wanted && html && html.text === text && html.language === language ? html.html : null;

  return (
    <pre className={cn("font-mono", className)}>
      {current !== null ? <code dangerouslySetInnerHTML={{ __html: current }} /> : <code>{text}</code>}
      {suffix}
    </pre>
  );
}

/** One log line, split into coloured tokens when log highlighting is on. */
export const LogText = memo(function LogText({ text, always = false }: { text: string; always?: boolean }) {
  const enabled = useSyntax().logs || always;
  const tokens = useMemo(() => (enabled ? tokenizeLog(text) : null), [enabled, text]);
  if (!tokens) return <>{text}</>;
  return (
    <>
      {tokens.map((token, i) =>
        token.className ? (
          <span key={i} className={token.className}>
            {token.text}
          </span>
        ) : (
          token.text
        ),
      )}
    </>
  );
});
