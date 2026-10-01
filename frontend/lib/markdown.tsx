"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Streaming-friendly markdown article (headings, lists, tables, code). */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={className ? `bw-prose ${className}` : "bw-prose"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

export const FALLBACK_SUGGESTIONS = [
  "Give me a simpler example",
  "Quiz me again on this",
  "What should I study next?",
];

function cleanChunk(raw: string): string {
  return raw
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // links → text
    .replace(/[`*_~]/g, "")                  // inline emphasis / code markers
    .trim();
}

/** Parse the trailing "Want to go deeper?" bullet list out of the markdown (§8.5).
 *  Returns [] when the section is missing or empty → caller uses fallback chips. */
export function extractSuggestions(markdown: string): string[] {
  const marker = markdown.lastIndexOf("Want to go deeper?");
  if (marker === -1) return [];
  const tail = markdown.slice(marker + "Want to go deeper?".length);
  const out: string[] = [];
  let seenBullet = false;
  for (const line of tail.split("\n")) {
    const bullet = /^\s*(?:[-*+]|\d+[.)])\s+(.+)$/.exec(line);
    if (bullet) {
      const text = cleanChunk(bullet[1]);
      if (text) out.push(text);
      seenBullet = true;
      continue;
    }
    const heading = /^\s*#{1,6}\s/.test(line);
    if (heading && seenBullet) break; // next section ends the suggestion list
    if (line.trim() && seenBullet && !heading && out.length) break; // prose after bullets
  }
  return out.slice(0, 3); // spec: 2–3 suggestions
}
