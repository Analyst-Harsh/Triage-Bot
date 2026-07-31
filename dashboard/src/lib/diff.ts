export type DiffLineType = "hunk" | "add" | "remove" | "context" | "meta";

export type DiffLine = { type: DiffLineType; content: string };

/**
 * Hand-rolled unified-diff line classifier -- the diff text is already a
 * plain string, one line per array entry after a split; no diff-parsing
 * dependency needed for just coloring lines by prefix. `meta` (file
 * headers) must be checked before `add`/`remove`, since `+++`/`---` also
 * start with `+`/`-`.
 */
export function parseDiff(diffText: string): DiffLine[] {
  return diffText.split("\n").map((line): DiffLine => {
    if (line.startsWith("@@")) {
      return { type: "hunk", content: line };
    }
    if (
      line.startsWith("+++") ||
      line.startsWith("---") ||
      line.startsWith("diff ") ||
      line.startsWith("index ")
    ) {
      return { type: "meta", content: line };
    }
    if (line.startsWith("+")) {
      return { type: "add", content: line };
    }
    if (line.startsWith("-")) {
      return { type: "remove", content: line };
    }
    return { type: "context", content: line };
  });
}
