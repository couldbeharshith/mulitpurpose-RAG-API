import { memo } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { citationMarker, passageLabel, type OpenCitation, type Passage } from "./sources";

type MarkdownNode = {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
};

function remarkAnswer(citations: Map<number, Passage>, interactive: boolean) {
  function replaceBreaks(node: MarkdownNode) {
    if (node.type === "link" || !node.children) return;
    node.children = node.children.flatMap(child => {
      if (child.type === "html" && /^<br\s*\/?\s*>$/i.test(child.value ?? "")) {
        return [{ type: "break" }];
      }
      if (interactive && child.type === "text" && child.value) {
        const matches = [...child.value.matchAll(citationMarker)];
        if (!matches.length) return [child];
        const parts: MarkdownNode[] = [];
        let offset = 0;
        for (const match of matches) {
          if (match.index > offset) parts.push({ type: "text", value: child.value.slice(offset, match.index) });
          const id = Number(match[1].normalize("NFKC"));
          const passage = citations.get(id);
          parts.push({
            type: "link", url: "#passage-" + id,
            children: [{ type: "text", value: passage ? passageLabel(passage) : "Source " + id }],
          });
          offset = match.index + match[0].length;
        }
        if (offset < child.value.length) parts.push({ type: "text", value: child.value.slice(offset) });
        return parts;
      }
      replaceBreaks(child);
      return [child];
    });
  }
  return replaceBreaks;
}

const components: Components = {
  img: () => null,
  table: ({ children }) => (
    <div className="answer-table" role="region" aria-label="Answer table" tabIndex={0}>
      <table>{children}</table>
    </div>
  ),
  th: ({ node, ...props }) => <th {...props} scope="col" />,
};

export const Answer = memo(function Answer({ content, citations = [], onCitation, turnIndex }: {
  content: string; citations?: Passage[]; onCitation?: OpenCitation; turnIndex?: number;
}) {
  const byId = new Map(citations.map(passage => [passage.id, passage]));
  const renderers: Components = {
    ...components,
    a: ({ node, href, children, ...props }) => {
      const reference = /^#passage-(\d+)$/.exec(href ?? "");
      if (reference && onCitation) {
        const id = Number(reference[1]);
        const passage = byId.get(id);
        return <button type="button" className="citation"
          onClick={() => onCitation(passage, passage ? undefined : id, turnIndex)}>{children}</button>;
      }
      return <a href={href} {...props}>{children}</a>;
    },
  };
  return <div className="answer">
    <Markdown remarkPlugins={[remarkGfm, () => remarkAnswer(byId, Boolean(onCitation))]} components={renderers}>{content}</Markdown>
  </div>;
});
