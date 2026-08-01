import { describe, expect, it } from "vitest";
import { parseDiff } from "./diff";

const SAMPLE_DIFF = `diff --git a/calc.py b/calc.py
index abc123..def456 100644
--- a/calc.py
+++ b/calc.py
@@ -1,3 +1,4 @@
 def add(a, b):
-    return a + b
+    return a + b  # fixed
+def percentage(value, percent):
     pass`;

describe("parseDiff", () => {
  it("classifies file header/index lines as meta, before add/remove prefix matching", () => {
    const lines = parseDiff(SAMPLE_DIFF);
    expect(lines[0]).toEqual({ type: "meta", content: "diff --git a/calc.py b/calc.py" });
    expect(lines[1]).toEqual({ type: "meta", content: "index abc123..def456 100644" });
    expect(lines[2]).toEqual({ type: "meta", content: "--- a/calc.py" });
    expect(lines[3]).toEqual({ type: "meta", content: "+++ b/calc.py" });
  });

  it("classifies hunk headers", () => {
    const lines = parseDiff(SAMPLE_DIFF);
    expect(lines[4]).toEqual({ type: "hunk", content: "@@ -1,3 +1,4 @@" });
  });

  it("classifies added and removed lines", () => {
    const lines = parseDiff(SAMPLE_DIFF);
    expect(lines[6]).toEqual({ type: "remove", content: "-    return a + b" });
    expect(lines[7]).toEqual({ type: "add", content: "+    return a + b  # fixed" });
    expect(lines[8]).toEqual({ type: "add", content: "+def percentage(value, percent):" });
  });

  it("classifies unchanged context lines", () => {
    const lines = parseDiff(SAMPLE_DIFF);
    expect(lines[5]).toEqual({ type: "context", content: " def add(a, b):" });
    expect(lines[9]).toEqual({ type: "context", content: "     pass" });
  });

  it("handles an empty diff", () => {
    expect(parseDiff("")).toEqual([{ type: "context", content: "" }]);
  });
});
