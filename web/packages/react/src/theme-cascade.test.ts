/**
 * The one test that compiles the stylesheet instead of reading strings out of it.
 *
 * Every accessibility fix in `theme.css` below the `[data-indi-state]` mapping is
 * an unlayered rule correcting a vendored shadcn primitive from outside it, and
 * the mechanism is entirely a cascade one: unlayered beats layered, so the
 * correction wins over the utility class the registry emits. jsdom implements
 * neither cascade layers nor `color-mix`, so every other test in this package
 * would stay green if a future Tailwind wrapped imported CSS in a layer, or if
 * somebody moved these rules into `@layer components` to tidy them up - and the
 * focus rings would quietly go back to 1.37:1 in the browser.
 *
 * So this one runs the workspace's own Tailwind over `styles.css` and reads the
 * output. It compiles **twice**, because the two outputs are different code
 * paths and only one of them ships: `@indikit/react/styles.css` is built by
 * `build:css` with `--minify`, which is Lightning CSS's minifier, while a
 * consumer importing `theme.css` into their own Tailwind gets the plain one.
 * The differences are not cosmetic - the minifier drops quotes from simple
 * attribute selectors, shortens `::before` to `:before`, and un-nests the
 * `@supports` fallback it generates around `color-mix` into a sibling rule - so
 * each selector is asserted in the form that build actually emits. It is the
 * only test here that shells out; each compile is about 100ms.
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { cwd } from "node:process";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

// Vitest runs each worker with its cwd at the project root - the directory
// holding `vitest.config.ts` - which is this package. `import.meta.url` is not
// usable here: under Vitest it is a served module URL, not a `file:` one.
const packageRoot = cwd();

/** Where the compiled stylesheets are written, so they can be removed afterwards. */
let outDir = "";

/** The plain compile, as a consumer's own Tailwind produces it. */
let css = "";

/** The `--minify` compile, which is the `dist/styles.css` that ships. */
let minified = "";

/**
 * The chain of block preludes enclosing each occurrence of `needle`.
 *
 * An empty chain means the occurrence is at the top level of the file, which is
 * what "unlayered" means and what every correction in `theme.css` depends on.
 * Brace counting is enough here because Tailwind's output carries exactly one
 * comment (its own banner, on line 1) and no brace inside a string.
 *
 * @param source - The compiled stylesheet.
 * @param needle - Literal text to locate, normally a selector or an at-rule.
 * @returns One entry per occurrence, each the outermost-first list of preludes.
 */
function enclosingBlocks(source: string, needle: string): string[][] {
  const found: string[][] = [];
  const stack: string[] = [];
  let prelude = "";
  for (let i = 0; i < source.length; i += 1) {
    if (source.startsWith(needle, i)) found.push([...stack]);
    const character = source[i];
    if (character === "{") {
      stack.push(prelude.trim());
      prelude = "";
    } else if (character === "}") {
      stack.pop();
      prelude = "";
    } else if (character === ";") {
      prelude = "";
    } else {
      prelude += character;
    }
  }
  return found;
}

/** One declaration in the compiled stylesheet, with what encloses it. */
interface Declaration {
  /** The block preludes enclosing it, outermost first. */
  chain: readonly string[];
  /** The declaration as `property:value`, whitespace normalised. */
  text: string;
}

/**
 * Every declaration in the stylesheet, each with its enclosing block preludes.
 *
 * The companion to {@link enclosingBlocks}: that one answers "where does this
 * selector sit", this one answers "what does the rule under it still say". The
 * separator's spacing is normalised away so a declaration reads the same in both
 * builds; the value's own spacing is not, because `--tw-ring-offset-shadow` is a
 * list and the minifier keeps it intact.
 *
 * @param source - The compiled stylesheet.
 * @returns One entry per declaration, in source order.
 */
function declarations(source: string): Declaration[] {
  const found: Declaration[] = [];
  const stack: string[] = [];
  let pending = "";
  const collapse = (text: string) => text.replace(/\s+/g, " ").trim();
  const flush = () => {
    const text = collapse(pending).replace(/\s*:\s*/, ":");
    pending = "";
    if (text !== "") found.push({ chain: [...stack], text });
  };
  for (const character of source) {
    if (character === "{") {
      stack.push(collapse(pending));
      pending = "";
    } else if (character === "}") {
      flush();
      stack.pop();
    } else if (character === ";") {
      flush();
    } else {
      pending += character;
    }
  }
  return found;
}

/**
 * The declarations a rule with this exact selector carries.
 *
 * The minifier splits one authored rule into three - the `color-mix` fallback is
 * hoisted into a sibling `@supports` - so a selector's declarations are gathered
 * from every block that names it rather than from the first one found.
 *
 * @param source - The compiled stylesheet.
 * @param selector - The rule's selector, exactly as that build emits it.
 * @returns The matching declarations, innermost prelude first.
 */
function declarationsFor(source: string, selector: string): Declaration[] {
  return declarations(source).filter((declaration) => declaration.chain.at(-1) === selector);
}

/**
 * Compile `styles.css` and return the output.
 *
 * @param minify - Whether to pass `--minify`, as `build:css` does.
 * @returns The compiled stylesheet.
 */
function compile(minify: boolean): string {
  const cli = join(packageRoot, "node_modules/.bin/tailwindcss");
  // A wrong cwd would otherwise surface as an unreadable spawn error.
  if (!existsSync(cli)) throw new Error(`no Tailwind CLI at ${cli}`);
  const out = join(outDir, minify ? "min.css" : "out.css");
  const args = ["-i", join(packageRoot, "src/styles.css"), "-o", out];
  if (minify) args.push("--minify");
  execFileSync(cli, args, { cwd: packageRoot, timeout: 30_000 });
  return readFileSync(out, "utf8");
}

beforeAll(() => {
  outDir = mkdtempSync(join(tmpdir(), "indikit-theme-"));
  css = compile(false);
  minified = compile(true);
}, 60_000);

afterAll(() => {
  if (outDir) rmSync(outDir, { recursive: true, force: true });
});

/**
 * Every correction selector, in the plain form and the minified form.
 *
 * Written out per build rather than derived by a normalising function: the
 * minifier's rewrites are the thing under test, and a transform that predicted
 * them would agree with itself when it was wrong.
 */
const CORRECTIONS: readonly [plain: string, minified: string, description: string][] = [
  [
    '[class~="focus-visible:ring-ring/50"]:focus-visible',
    '[class~="focus-visible:ring-ring/50"]:focus-visible',
    "focus ring, every control",
  ],
  [
    '[class~="focus-visible:ring-destructive/20"]:focus-visible',
    '[class~="focus-visible:ring-destructive/20"]:focus-visible',
    "focus ring, destructive",
  ],
  [
    '[data-slot="switch"]:not([class*="absolute"]):not([class*="fixed"])',
    "[data-slot=switch]:not([class*=absolute]):not([class*=fixed])",
    "switch positioning",
  ],
  ['[data-slot="switch"]::before', "[data-slot=switch]:before", "switch target size"],
  [
    '[data-slot="dialog-content"] > [class~="ring-offset-background"]::before',
    "[data-slot=dialog-content]>[class~=ring-offset-background]:before",
    "dialog close target size",
  ],
  [
    '[data-slot="sheet-content"] > [class~="ring-offset-background"]::before',
    "[data-slot=sheet-content]>[class~=ring-offset-background]:before",
    "sheet close target size",
  ],
  [
    '[data-mobile="true"] > [class~="ring-offset-background"]::before',
    "[data-mobile=true]>[class~=ring-offset-background]:before",
    "mobile drawer close target size",
  ],
  [
    "@media (prefers-reduced-motion: reduce)",
    "@media (prefers-reduced-motion:reduce)",
    "reduced motion",
  ],
  [
    "@media (prefers-reduced-motion: no-preference)",
    "@media (prefers-reduced-motion:no-preference)",
    "the busy pulse",
  ],
  ["@keyframes state-pulse", "@keyframes state-pulse", "the busy pulse keyframes"],
];

/**
 * The two rings that are offset, and the gap colour each one takes.
 *
 * The offset is half the focus fix: those contrast ratios are the ring against
 * the surface *around* the control, and on a filled control its other neighbour
 * is the control's own fill - a tinted version of the same token, so ring and
 * fill sit on top of each other (destructive 1.38:1 light, checked Switch 2.05).
 * The destructive gap is white rather than the surface because
 * `dark:bg-destructive/60` composites to `#973030` on a near-black card, 2.48:1
 * from it, so a card-coloured gap is invisible against the fill.
 *
 * Written out per build like {@link CORRECTIONS}, and for the same reason: the
 * minifier shortens `#ffffff` to `#fff`, which is exactly the kind of rewrite a
 * normalising function would agree with itself about when it was wrong.
 */
const RING_OFFSETS: readonly [
  description: string,
  selector: string,
  plain: string,
  minified: string,
][] = [
  [
    "every control, in the page background",
    '[class~="focus-visible:ring-ring/50"]:focus-visible',
    "var(--background)",
    "var(--background)",
  ],
  [
    "the destructive button, in white",
    '[class~="focus-visible:ring-destructive/20"]:focus-visible',
    "#ffffff",
    "#fff",
  ],
];

/**
 * The three declarations one offset ring is made of.
 *
 * The width and the colour are custom properties and so cost nothing under THE
 * RULE. The shadow has to be restated because only the `ring-offset-*` utility
 * would otherwise set it, and without it the other two are inert.
 *
 * @param color - The gap colour, as that build spells it.
 * @returns The declarations, normalised as {@link declarations} returns them.
 */
function ringOffset(color: string): string[] {
  return [
    "--tw-ring-offset-width:2px",
    `--tw-ring-offset-color:${color}`,
    "--tw-ring-offset-shadow:var(--tw-ring-inset,) 0 0 0 var(--tw-ring-offset-width) var(--tw-ring-offset-color)",
  ];
}

describe("the compiled theme", () => {
  it("still declares the layer order the corrections outrank", () => {
    // If a future Tailwind stops emitting this, or emits a different order, the
    // whole "unlayered beats layered" argument needs re-checking - and it should
    // fail here rather than in the field.
    expect(css).toContain("@layer theme, base, components, utilities;");
  });

  it("still orders the layers the corrections outrank, under --minify", () => {
    // The minifier deletes the order statement and lets physical order carry it
    // instead, which is the same guarantee written differently: it can only do
    // that because it has resolved every layer itself. So the assertion here is
    // on the sequence rather than on the declaration.
    let cursor = -1;
    for (const layer of ["@layer theme{", "@layer base{", "@layer utilities{"]) {
      const at = minified.indexOf(layer, cursor + 1);
      expect(at, `${layer} out of order or missing`).toBeGreaterThan(cursor);
      cursor = at;
    }
  });

  it.each(CORRECTIONS)("emits %s unlayered (%s)", (selector) => {
    const occurrences = enclosingBlocks(css, selector);
    expect(occurrences.length).toBeGreaterThan(0);
    for (const chain of occurrences) expect(chain).toEqual([]);
  });

  it.each(CORRECTIONS)("keeps %s unlayered under --minify (%s)", (_plain, selector) => {
    // Weaker than the assertion above on purpose, and the minifier is why: it
    // hoists the `@supports (color: color-mix(...))` fallback out of the rule it
    // was nested in, so a selector legitimately appears both at the top level
    // and one block deep. What has to hold either way is that no occurrence sits
    // inside a cascade layer, because that is the only nesting that would cost
    // the correction its precedence.
    const occurrences = enclosingBlocks(minified, selector);
    expect(occurrences.length).toBeGreaterThan(0);
    for (const chain of occurrences) {
      expect(chain.filter((prelude) => prelude.startsWith("@layer"))).toEqual([]);
    }
    expect(occurrences.some((chain) => chain.length === 0)).toBe(true);
  });

  it("un-hides the mobile drawer's close button from outside every layer", () => {
    // The correction that used to be a third `DEVIATION` in `ui/sidebar.tsx`.
    // Both halves have to be asserted together, because what is under test is
    // the relationship between two rules: the registry's `[&>button]:hidden`
    // landing in `@layer utilities`, and `display: revert` sitting outside every
    // layer so it outranks it. Either one alone is consistent with the drawer
    // having no way out again.
    //
    // It is deliberately not a CORRECTIONS row. `enclosingBlocks` matches by
    // prefix, and this selector is a prefix of its own `::before` (the 44px
    // target overlay), so a row would keep passing with the rule deleted.
    for (const [source, hidden, corrected] of [
      [
        css,
        ".\\[\\&\\>button\\]\\:hidden > button",
        '[data-mobile="true"] > [class~="ring-offset-background"]',
      ],
      [
        minified,
        ".\\[\\&\\>button\\]\\:hidden>button",
        "[data-mobile=true]>[class~=ring-offset-background]",
      ],
    ] as const) {
      expect(enclosingBlocks(source, hidden)).toEqual([["@layer utilities"]]);
      const carried = declarationsFor(source, corrected);
      expect(carried.map((declaration) => declaration.text)).toContain("display:revert");
      // `chain` ends with the rule's own selector, so what encloses it is
      // everything before that - and it has to be nothing at all, not merely no
      // `@layer`: this rule involves no `color-mix`, so the minifier has no
      // `@supports` to wrap it in either.
      for (const { chain } of carried) expect(chain.slice(0, -1)).toEqual([]);
    }
  });

  it("puts the pulse rule inside the motion query and nowhere else", () => {
    expect(enclosingBlocks(css, "[data-indi-pulse]::after")).toEqual([
      ["@media (prefers-reduced-motion: no-preference)"],
    ]);
    expect(enclosingBlocks(minified, "[data-indi-pulse]:after")).toEqual([
      ["@media (prefers-reduced-motion:no-preference)"],
    ]);
  });

  it.each(RING_OFFSETS)("offsets the focus ring on %s", (_description, selector, color) => {
    const carried = declarationsFor(css, selector).map((declaration) => declaration.text);
    expect(carried).toEqual(expect.arrayContaining(ringOffset(color)));
  });

  it.each(RING_OFFSETS)(
    "keeps the offset on %s under --minify",
    (_description, selector, _plain, color) => {
      const carried = declarationsFor(minified, selector).map((declaration) => declaration.text);
      expect(carried).toEqual(expect.arrayContaining(ringOffset(color)));
    },
  );

  it.each(RING_OFFSETS)(
    "leaves the offset on %s outside every layer",
    (_description, selector, plain, min) => {
      // Custom properties are safe unlayered under THE RULE, but only while they
      // *are* unlayered: from inside a layer the registry's own `ring-offset-*`
      // utility outranks them and the 2px gap silently goes back to nothing.
      for (const [source, expected] of [
        [css, ringOffset(plain)],
        [minified, ringOffset(min)],
      ] as const) {
        const offsets = declarationsFor(source, selector).filter((declaration) =>
          expected.includes(declaration.text),
        );
        expect(offsets).toHaveLength(expected.length);
        for (const { chain } of offsets) {
          expect(chain.filter((prelude) => prelude.startsWith("@layer"))).toEqual([]);
        }
      }
    },
  );

  it("carries the retuned ring opacity through both compiles", () => {
    // jsdom cannot evaluate `color-mix`, so this is the only place the 75% is
    // observable at all. Lightning CSS also generates the `@supports` fallback
    // around it, which is why the plain `var(--ring)` line sits above.
    for (const output of [css, minified]) {
      expect(output).toContain("color-mix(in oklab, var(--ring) 75%, transparent)");
    }
  });

  it("gives the destructive control the ordinary ring, never a tint of itself", () => {
    // A focus indicator says where the keyboard is; it is not a state and not a
    // warning. Measurement forced the point before taste reached it: a 75% tint
    // of `--destructive` measures 2.15:1 against the dark card and 1.65:1
    // against `--accent`, both under SC 1.4.11, because a red dark enough to
    // carry white text is too dark to be its own indicator. Raising the red to
    // fix the ring costs the label; tinting it lighter walks back toward
    // `--state-alert`. This asserts the whole class stays gone rather than
    // asserting one hex, so re-tinting it any shade fails here.
    for (const output of [css, minified]) {
      expect(output).not.toContain("var(--destructive) 75%");
      expect(output).not.toContain("var(--destructive)75%");
    }
  });
});
