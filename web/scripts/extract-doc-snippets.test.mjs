/**
 * The guard on the doc-snippet extractor: an unclaimed fence has to fail the build.
 *
 * The generated modules themselves are checked by `tsc`, so what needs testing here
 * is the part that has no other witness - the manifest check that forces somebody to
 * decide where a newly added fence belongs.
 */

import { describe, expect, it } from "vitest";
import { matchSnippets, parseFences, renderSnippet } from "./extract-doc-snippets.mjs";

const MARKDOWN = [
  "# A page",
  "",
  "```tsx",
  "export const First = () => <p>one</p>;",
  "```",
  "",
  "```bash",
  "npm install @indi-nexus/react",
  "```",
  "",
  "```ts",
  "const second = 2;",
  "```",
  "",
].join("\n");

describe("parseFences", () => {
  it("returns every fence with its language and opening line", () => {
    expect(parseFences(MARKDOWN)).toEqual([
      { lang: "tsx", line: 3, body: "export const First = () => <p>one</p>;" },
      { lang: "bash", line: 7, body: "npm install @indi-nexus/react" },
      { lang: "ts", line: 11, body: "const second = 2;" },
    ]);
  });

  it("keeps the body verbatim, blank lines and all", () => {
    const [fence] = parseFences(["```ts", "const a = 1;", "", "const b = 2;", "```"].join("\n"));
    expect(fence.body).toBe("const a = 1;\n\nconst b = 2;");
  });

  it("refuses a document whose fence is never closed", () => {
    expect(() => parseFences("```ts\nconst a = 1;\n")).toThrow(/unterminated code fence/);
  });
});

describe("matchSnippets", () => {
  const fences = parseFences(MARKDOWN);

  it("pairs each entry with its fence and ignores other languages", () => {
    const pairs = matchSnippets("page.md", fences, [
      { name: "first", match: "First" },
      { name: "second", match: "second" },
    ]);
    expect(pairs.map(({ snippet, fence }) => [snippet.name, fence.line])).toEqual([
      ["first", 3],
      ["second", 11],
    ]);
  });

  it("fails when a TypeScript fence is claimed by no entry", () => {
    expect(() => matchSnippets("page.md", fences, [{ name: "first", match: "First" }])).toThrow(
      /the TypeScript fence at line 11 is not in the manifest/,
    );
  });

  it("fails when an entry matches nothing", () => {
    expect(() =>
      matchSnippets("page.md", fences, [
        { name: "first", match: "First" },
        { name: "second", match: "second" },
        { name: "gone", match: "Third" },
      ]),
    ).toThrow(/"gone" matches nothing/);
  });

  it("fails when an entry matches more than one fence", () => {
    expect(() => matchSnippets("page.md", fences, [{ name: "loose", match: "const" }])).toThrow(
      /"loose" matches line 3, line 11/,
    );
  });

  it("fails when two entries claim the same fence", () => {
    expect(() =>
      matchSnippets("page.md", fences, [
        { name: "a", match: "First" },
        { name: "b", match: "one" },
        { name: "c", match: "second" },
      ]),
    ).toThrow(/at line 3 is claimed by a and b/);
  });
});

describe("renderSnippet", () => {
  const fence = {
    lang: "tsx",
    line: 3,
    body: 'import { X } from "@indi-nexus/react";\nconst a = 1;',
  };

  it("names the source file and line, and points the import inside the package", () => {
    const code = renderSnippet("docs/page.md", { name: "s", match: "a" }, fence);
    expect(code).toContain("Generated from docs/page.md line 3");
    expect(code).toContain('import { X } from "../../index";');
  });

  it("exports a top-level declaration nothing in the fence uses", () => {
    const code = renderSnippet("docs/page.md", { name: "s", match: "a" }, fence);
    expect(code).toContain("export const a = 1;");
  });

  it("drops the stylesheet import, which nothing declares a type for", () => {
    const withCss = { ...fence, body: 'import "@indi-nexus/react/styles.css";\nconst a = 1;' };
    expect(renderSnippet("docs/page.md", { name: "s", match: "a" }, withCss)).not.toContain(
      "styles.css",
    );
  });

  it("indents a wrapped fragment between its wrapper without touching its tokens", () => {
    const fragment = { lang: "ts", line: 9, body: "const live = value !== undefined;" };
    const code = renderSnippet(
      "docs/page.md",
      {
        name: "s",
        match: "live",
        wrap: {
          before: ["export function isLive(value: number | undefined) {"],
          after: ["  return live;", "}"],
        },
      },
      fragment,
    );
    expect(code).toContain("\n  const live = value !== undefined;\n");
    expect(code).not.toContain("export const live");
  });
});
