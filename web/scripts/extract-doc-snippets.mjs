#!/usr/bin/env node
/**
 * Lift every TypeScript code fence in the documentation into a generated module,
 * so the owning package's `tsc --noEmit` compiles the markdown as it is written.
 *
 * The docs used to be mirrored by hand into `readme-snippets.ts`,
 * `readme-snippets.tsx` and `doc-snippets.tsx`. Those compiled, but nothing tied
 * them to the markdown, so the markdown could rot underneath them. This reads the
 * fences themselves.
 *
 * Every `ts`/`tsx` fence in a documented file must be claimed by exactly one
 * manifest entry, and every entry must match exactly one fence. Add a fence and
 * the extractor fails until somebody says where it belongs - which is the whole
 * point of it.
 *
 * Usage: `node web/scripts/extract-doc-snippets.mjs [--only=client|react]`.
 * `--only` narrows what is written to disk (each package regenerates its own
 * during `pnpm typecheck`); the manifest check always covers everything.
 */

import { mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

/** Where each package's generated modules land, relative to the repo root. */
const OUTPUT_DIRS = {
  client: "web/packages/client/src/__generated__/docs",
  react: "web/packages/react/src/__generated__/docs",
};

/** The file extension each package's snippets get (only React needs JSX). */
const OUTPUT_EXTENSIONS = { client: ".ts", react: ".tsx" };

/**
 * What a snippet imports instead of its package's published name.
 *
 * Both output directories sit two levels under `src/`, and a package cannot
 * resolve its own published name from inside `src/` without a built `dist/`.
 */
const SELF_IMPORT = "../../index";

/**
 * The documented fences, keyed by a distinctive substring of the fence body.
 *
 * Keyed by content rather than by index so that inserting a fence above another
 * does not silently re-point an entry at the wrong code.
 *
 * Per entry:
 * - `name` - the generated module's basename, and what a tsc error names first.
 * - `match` - a substring that appears in exactly one `ts`/`tsx` fence in `file`.
 * - `pkg` - which package compiles it; defaults to the file's `pkg`.
 * - `imports` - lines prepended above the fence body, for a fence that is written
 *   as an excerpt and names things it does not import.
 * - `wrap` - `before`/`after` lines for a fence that is a fragment rather than a
 *   module: the body is indented between them, otherwise verbatim.
 *
 * @type {{ file: string, pkg: "client" | "react", snippets: Array<{
 *   name: string, match: string, pkg?: "client" | "react",
 *   imports?: string[], wrap?: { before: string[], after: string[] },
 * }> }[]}
 */
export const MANIFEST = [
  {
    file: "web/packages/client/README.md",
    pkg: "client",
    snippets: [
      {
        name: "client-readme-usage",
        match: 'await client.waitFor("Mount", "CONNECTION"',
      },
      {
        name: "client-readme-cache",
        match: "client.devices(); // known device names",
        imports: ['import type { IndiClient } from "@indi-nexus/client";'],
        wrap: {
          before: ["export function readCache(client: IndiClient) {"],
          after: ["}"],
        },
      },
      {
        name: "client-readme-on-write",
        match: "const stop = client.onWrite(",
        imports: ['import type { IndiClient } from "@indi-nexus/client";'],
        wrap: {
          before: ["export function traceWrites(client: IndiClient) {"],
          after: ["}"],
        },
      },
    ],
  },
  {
    file: "web/packages/react/README.md",
    pkg: "react",
    snippets: [
      { name: "react-readme-app", match: "export const App = () => (" },
      { name: "react-readme-readout", match: "export const Readout = () => {" },
    ],
  },
  {
    file: "docs/guides/frontend.md",
    pkg: "react",
    snippets: [
      { name: "frontend-app", match: "export function App() {" },
      {
        name: "frontend-observatory",
        match: "function Observatory() {",
        imports: ['import { DevicePanel, useDevices } from "@indi-nexus/react";'],
      },
      { name: "frontend-dome-azimuth", match: "function DomeAzimuth() {" },
      {
        name: "frontend-shutter-buttons",
        match: "function ShutterButtons() {",
        imports: ['import { useIndiClient } from "@indi-nexus/react";'],
      },
      { name: "frontend-last-command", match: "function LastCommand() {" },
      {
        name: "frontend-wait-for",
        match: "await client.waitFor(",
        imports: ['import type { IndiClient } from "@indi-nexus/react";'],
        wrap: {
          before: ["export async function sequence(client: IndiClient) {"],
          after: ["}"],
        },
      },
      { name: "frontend-plain-client", match: 'from "@indi-nexus/client"', pkg: "client" },
    ],
  },
  {
    file: "docs/index.md",
    pkg: "react",
    snippets: [{ name: "index-flat-panel", match: '<DevicePanel device="Flat Panel" />' }],
  },
  {
    file: "README.md",
    pkg: "react",
    snippets: [{ name: "root-readme-app", match: '<DevicePanel device="Mount" />' }],
  },
  {
    file: "docs/guides/tutorial-open-meteo.md",
    pkg: "react",
    snippets: [
      {
        name: "tutorial-use-reading",
        match: "function useReading(element: string) {",
        imports: ['import { useLight, useNumber } from "@indi-nexus/react";'],
      },
      {
        name: "tutorial-use-alerting",
        match: "function useAlerting(): string[] {",
        imports: ['import { displayLabel, useProperty } from "@indi-nexus/react";'],
      },
      {
        name: "tutorial-live",
        match: "const live =",
        imports: ['import type { Vector } from "@indi-nexus/react";'],
        wrap: {
          before: ["export function isLive(parameters: Vector | undefined) {"],
          after: ["  return live;", "}"],
        },
      },
    ],
  },
];

/**
 * Directories the fence sweep never descends into, by basename or by relative path.
 *
 * Anything starting with a dot is skipped too. That is not only `.git`: a developer's
 * local `.claude/` or `.agents/` holds third-party markdown with code fences in it,
 * and none of it is this repository's documentation.
 */
const SWEEP_SKIP = new Set([
  "__pycache__",
  "dist",
  "node_modules",
  "site",
  join("docs", "reference", "typescript"),
]);

/** The fence languages a package can compile. */
const TYPESCRIPT_LANGS = new Set(["ts", "tsx", "typescript"]);

/**
 * Split a markdown document into its fenced code blocks.
 *
 * @param {string} markdown The document's full text.
 * @returns {{ lang: string, line: number, body: string }[]} Every fence, in order,
 *   with the 1-based line number of its opening delimiter.
 */
export function parseFences(markdown) {
  const lines = markdown.split("\n");
  const fences = [];
  let open = null;

  for (const [index, line] of lines.entries()) {
    if (open === null) {
      const start = /^```(\S*)/.exec(line);
      if (start !== null) {
        open = { lang: start[1], line: index + 1, body: [] };
      }
      continue;
    }
    if (/^```\s*$/.test(line)) {
      fences.push({ lang: open.lang, line: open.line, body: open.body.join("\n") });
      open = null;
      continue;
    }
    open.body.push(line);
  }

  if (open !== null) {
    throw new Error(`unterminated code fence opened at line ${open.line}`);
  }
  return fences;
}

/**
 * Pair a file's manifest entries with its TypeScript fences.
 *
 * @param {string} file The document's path, for error messages.
 * @param {{ lang: string, line: number, body: string }[]} fences Its parsed fences.
 * @param {{ name: string, match: string }[]} snippets Its manifest entries.
 * @returns {{ snippet: object, fence: object }[]} One pair per entry.
 * @throws {Error} If an entry matches other than exactly one fence, or a
 *   TypeScript fence is claimed by no entry or by more than one.
 */
export function matchSnippets(file, fences, snippets) {
  const typescript = fences.filter((fence) => TYPESCRIPT_LANGS.has(fence.lang));
  const claims = new Map(typescript.map((fence) => [fence, []]));
  const pairs = [];

  for (const snippet of snippets) {
    const hits = typescript.filter((fence) => fence.body.includes(snippet.match));
    if (hits.length !== 1) {
      const where = hits.map((fence) => `line ${fence.line}`).join(", ") || "nothing";
      throw new Error(
        `${file}: manifest entry "${snippet.name}" matches ${where}; its \`match\` has to ` +
          "pick out exactly one TypeScript fence.",
      );
    }
    claims.get(hits[0]).push(snippet.name);
    pairs.push({ snippet, fence: hits[0] });
  }

  for (const [fence, names] of claims) {
    if (names.length === 0) {
      throw new Error(
        `${file}: the TypeScript fence at line ${fence.line} is not in the manifest. Add an ` +
          "entry in web/scripts/extract-doc-snippets.mjs so it gets typechecked.",
      );
    }
    if (names.length > 1) {
      throw new Error(
        `${file}: the TypeScript fence at line ${fence.line} is claimed by ${names.join(" and ")}.`,
      );
    }
  }

  return pairs;
}

/**
 * Turn one fence into the text of its generated module.
 *
 * The body is verbatim apart from the transforms the compiler forces: the
 * published package name cannot resolve from inside that package's own `src/`,
 * nothing in the program declares a type for a `.css` import, and `noUnusedLocals`
 * rejects a top-level declaration the fence never uses.
 *
 * @param {string} file The source document's path.
 * @param {object} snippet Its manifest entry.
 * @param {object} fence The matched fence.
 * @returns {string} The module source.
 */
export function renderSnippet(file, snippet, fence) {
  let body = fence.body;
  if (snippet.wrap) {
    const indented = body.split("\n").map((line) => (line === "" ? "" : `  ${line}`));
    body = [...snippet.wrap.before, ...indented, ...snippet.wrap.after].join("\n");
  } else {
    // A fence shows a declaration and stops; nothing consumes it, so export it.
    body = body.replace(/^(async function |function |const |class )/gm, "export $1");
  }

  const source = [
    "/**",
    ` * Generated from ${file} line ${fence.line} - do not edit.`,
    " *",
    " * `web/scripts/extract-doc-snippets.mjs` lifts this out of the markdown on every",
    " * `pnpm typecheck`. An error here is an error in that fence: fix the markdown.",
    " */",
    "",
    ...(snippet.imports === undefined ? [] : [...snippet.imports, ""]),
    body,
    "",
  ].join("\n");

  return source
    .split("\n")
    .filter((line) => !/^import ["']@indi-nexus\/react\/styles\.css["'];?$/.test(line))
    .join("\n")
    .replaceAll(/from "@indi-nexus\/(react|client)"/g, `from "${SELF_IMPORT}"`);
}

/**
 * Resolve the whole manifest against a set of documents.
 *
 * @param {Map<string, string>} documents Path to full text, for every manifest file.
 * @returns {{ pkg: "client" | "react", name: string, file: string, code: string }[]}
 *   One generated module per fence.
 * @throws {Error} If any file fails its manifest check.
 */
export function collectSnippets(documents) {
  const collected = [];
  for (const entry of MANIFEST) {
    const markdown = documents.get(entry.file);
    if (markdown === undefined) {
      throw new Error(`${entry.file}: listed in the manifest but not read`);
    }
    const pairs = matchSnippets(entry.file, parseFences(markdown), entry.snippets);
    for (const { snippet, fence } of pairs) {
      collected.push({
        pkg: snippet.pkg ?? entry.pkg,
        name: snippet.name,
        file: entry.file,
        code: renderSnippet(entry.file, snippet, fence),
      });
    }
  }
  return collected;
}

/**
 * Find every markdown file under the repo that holds a TypeScript fence.
 *
 * The manifest check only sees the files it already lists, so this is what stops a
 * brand new page from arriving with an untypechecked fence on it.
 *
 * @param {string} root The repo root.
 * @returns {string[]} Repo-relative paths, sorted.
 */
function sweepForTypeScriptFences(root) {
  const found = [];

  const walk = (dir) => {
    for (const child of readdirSync(dir).sort()) {
      const absolute = join(dir, child);
      const rel = relative(root, absolute);
      if (child.startsWith(".") || SWEEP_SKIP.has(child) || SWEEP_SKIP.has(rel)) continue;
      if (statSync(absolute).isDirectory()) {
        walk(absolute);
      } else if (child.endsWith(".md")) {
        const fences = parseFences(readFileSync(absolute, "utf8"));
        if (fences.some((fence) => TYPESCRIPT_LANGS.has(fence.lang))) {
          found.push(rel.split(sep).join("/"));
        }
      }
    }
  };

  walk(root);
  return found;
}

/**
 * Regenerate the snippet modules on disk.
 *
 * @returns {void}
 */
function main() {
  const only = process.argv
    .find((argument) => argument.startsWith("--only="))
    ?.slice("--only=".length);
  if (only !== undefined && !(only in OUTPUT_DIRS)) {
    throw new Error(`--only must be one of ${Object.keys(OUTPUT_DIRS).join(", ")}, got "${only}"`);
  }

  const documents = new Map(
    MANIFEST.map((entry) => [entry.file, readFileSync(join(REPO_ROOT, entry.file), "utf8")]),
  );
  const snippets = collectSnippets(documents);

  const unlisted = sweepForTypeScriptFences(REPO_ROOT).filter((file) => !documents.has(file));
  if (unlisted.length > 0) {
    throw new Error(
      `${unlisted.join(", ")}: holds a TypeScript fence but is not in the manifest in ` +
        "web/scripts/extract-doc-snippets.mjs, so nothing typechecks it.",
    );
  }

  for (const [pkg, dir] of Object.entries(OUTPUT_DIRS)) {
    if (only !== undefined && only !== pkg) continue;
    const absolute = join(REPO_ROOT, dir);
    // Wipe first: a renamed or deleted snippet would otherwise keep compiling.
    rmSync(absolute, { recursive: true, force: true });
    mkdirSync(absolute, { recursive: true });
    for (const snippet of snippets.filter((candidate) => candidate.pkg === pkg)) {
      writeFileSync(join(absolute, `${snippet.name}${OUTPUT_EXTENSIONS[pkg]}`), snippet.code);
    }
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (error) {
    console.error(`extract-doc-snippets: ${error instanceof Error ? error.message : error}`);
    process.exit(1);
  }
}
