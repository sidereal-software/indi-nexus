---
name: INDIkit
description: An instrument-grade control surface for astronomical hardware, built to be read correctly at 3am.
colors:
  # Three schemes, one world. Light (`:root`) is the base; `.dark` overrides carry
  # a `-dark` suffix and `.night` a `-night` suffix. `.night` is applied *alongside*
  # `.dark`, never instead of it, so it only moves token values.
  background: "#fbfcfd"
  background-dark: "#0a0c0f"
  background-night: "#000000"
  foreground: "#12151a"
  foreground-dark: "#dfe4ea"
  foreground-night: "#a8b0b8"
  card: "#ffffff"
  card-dark: "#101216"
  card-night: "#050607"
  sidebar: "#f1f3f5"
  sidebar-dark: "#0d0f13"
  sidebar-night: "#020303"
  muted: "#f1f3f5"
  muted-dark: "#1b1f24"
  muted-night: "#121417"
  accent: "#e6e9ec"
  accent-dark: "#2b3138"
  accent-night: "#1b1e22"
  primary: "#12151a"
  primary-dark: "#dfe4ea"
  primary-night: "#aeb6bf"
  primary-foreground: "#ffffff"
  primary-foreground-dark: "#0a0c0f"
  primary-foreground-night: "#000000"
  secondary: "#e6e9ec"
  secondary-dark: "#2b3138"
  secondary-night: "#1b1e22"
  secondary-foreground: "#12151a"
  secondary-foreground-dark: "#dfe4ea"
  secondary-foreground-night: "#a8b0b8"
  muted-foreground: "#434a53"
  muted-foreground-dark: "#b9c2cb"
  muted-foreground-night: "#a1a9b2"
  border: "#7c8490"
  border-dark: "#737b87"
  border-night: "#636a74"
  input: "#6d7580"
  input-dark: "#79838f"
  input-night: "#6f7780"
  ring: "#0a0c0f"
  ring-dark: "#ffffff"
  ring-night: "#e8ecf0"
  destructive: "#a3120f"
  destructive-dark: "#c01b1b"
  destructive-night: "#c72623"
  state-idle: "#6b7480"
  state-idle-foreground: "#ffffff"
  state-idle-dark: "#78848f"
  state-idle-foreground-dark: "#000000"
  state-idle-night: "#78848f"
  state-idle-foreground-night: "#000000"
  state-ok: "#215c1f"
  state-ok-foreground: "#ffffff"
  state-ok-dark: "#88dd88"
  state-ok-foreground-dark: "#032010"
  state-ok-night: "#88dd88"
  state-ok-foreground-night: "#032010"
  state-busy: "#947100"
  state-busy-foreground: "#ffffff"
  state-busy-dark: "#ffab1f"
  state-busy-foreground-dark: "#1c1300"
  state-busy-night: "#ffab1f"
  state-busy-foreground-night: "#1c1300"
  state-alert: "#8e0b55"
  state-alert-foreground: "#ffffff"
  state-alert-dark: "#fa385f"
  state-alert-foreground-dark: "#000000"
  state-alert-night: "#fa385f"
  state-alert-foreground-night: "#150303"
  state-ok-ink: "#215c1f"
  state-ok-ink-dark: "#88dd88"
  state-ok-ink-night: "#88dd88"
  state-alert-ink: "#8e0b55"
  state-alert-ink-dark: "#fba7bc"
  state-alert-ink-night: "#fba7bc"
  chart-1: "#474c52"
  chart-2: "#687078"
  chart-3: "#8c939b"
  chart-4: "#adb2b8"
  chart-5: "#c8ccd0"
  chart-1-dark: "#d9dbde"
  chart-2-dark: "#b3b7bd"
  chart-3-dark: "#8c939b"
  chart-4-dark: "#687078"
  chart-5-dark: "#4c5157"
  chart-1-night: "#6f7780"
  chart-2-night: "#9aa2ab"
  chart-3-night: "#c3cad2"
  chart-4-night: "#545b63"
  chart-5-night: "#3d444b"
  docs-link: "#085b6f"
  docs-link-dark: "#7fd6e8"
typography:
  display:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "clamp(3rem, 8.5vw, 10rem)"
    fontWeight: 600
    lineHeight: 0.9
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "clamp(2rem, 4.4vw, 5rem)"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "normal"
  title:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "normal"
  body:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.25rem
    letterSpacing: "normal"
  label:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1rem
    letterSpacing: "0.025em"
  reading:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.25rem
    fontFeature: "tabular-nums"
rounded:
  sm: "8px"
  md: "10px"
  lg: "12px"
  xl: "16px"
  full: "9999px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "color-mix(in oklab, #12151a 90%, transparent)"
    textColor: "{colors.primary-foreground}"
  button-secondary:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.secondary-foreground}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "32px"
  button-secondary-hover:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.secondary-foreground}"
  button-destructive:
    backgroundColor: "{colors.destructive}"
    textColor: "#ffffff"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
    height: "36px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    height: "44px"
    width: "44px"
  card-property:
    backgroundColor: "{colors.card}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.xl}"
    padding: "16px"
  input-value:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    typography: "{typography.reading}"
    rounded: "{rounded.md}"
    padding: "4px 12px"
    height: "36px"
  badge-state-idle:
    backgroundColor: "{colors.state-idle}"
    textColor: "{colors.state-idle-foreground}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  badge-state-ok:
    backgroundColor: "{colors.state-ok}"
    textColor: "{colors.state-ok-foreground}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  badge-state-busy:
    backgroundColor: "{colors.state-busy}"
    textColor: "{colors.state-busy-foreground}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  badge-state-alert:
    backgroundColor: "{colors.state-alert}"
    textColor: "{colors.state-alert-foreground}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  toggle-switch-member:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    typography: "{typography.body}"
    rounded: "0px"
    padding: "0 12px"
    height: "32px"
  toggle-switch-member-on:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.secondary-foreground}"
    typography: "{typography.body}"
    padding: "0 12px"
    height: "32px"
---

# Design System: INDIkit

## Overview

**Creative North Star: "The Emission Spectrum"**

An operator is alone at 3am, a hundred miles from the instrument, and this interface is the
only thing that will tell them what is happening. That is the brief. What the system does
with it is narrower than "be legible": it spends its entire colour channel on one question.
Colour on this surface means what an instrument is doing, and nothing else. The chrome is a
neutral continuum in three renditions - light is an absorption spectrum, dark marks on a
bright ground; dark is an emission spectrum, bright marks on a dark one; night is emission
under a luminance ceiling - and hue appears only as narrow saturated marks at fixed
positions, which are the four INDI state badges.

That is why the brand has no colour at all. `--primary`, `--secondary` and `--ring` are pure
neutrals in all three schemes, and the wordmark separates its halves by weight rather than by
hue. This is a correction, not a starting position: the palette before this one carried a
violet that sat 22.4 CIEDE2000 from the nearest state colour, and the one before *that* an
orange at 8.3. Both were the same mistake at different distances - an identity colour with a
hue is a near-miss for a status colour - and removing the hue removes the class of failure
instead of managing it. The only reserved non-state hue in the whole product is the
documentation site's link cyan, and it never appears in the panel.

The register is instrument-grade, dense and professional, closer to a control desk than to a
consumer app. Information density is a feature: the operator is an expert and slowing them
down for breathing room costs them the night. The whole interface is monospace, so a column
of readings aligns by default and a value never shifts as its digits change. And the palette
was not chosen by eye. Nearly every colour token in `theme.css` carries its measured contrast
ratio, composited against the real ancestor surface, plus a note on the value it replaced and
why that one failed. A value is defended by measurement, and taste does not overrule a ratio.
Future work inherits the obligation, not just the values.

**Key Characteristics:**

- Three schemes, each measured independently: light (absorption), dark (emission), and night
  (emission under MIL-STD-1472F's 10 cd/m² dark-adaptation ceiling).
- The brand spends no chroma. Every saturated pixel on the panel is an instrument talking.
- Four state hues (Idle / Ok / Busy / Alert), derived by search so every pair separates by at
  least 11.94 CIEDE2000 in the worst of normal, deuteranopic and protanopic vision.
- Colour never carries meaning on its own: every state is written out as well as coloured.
- Monospace throughout, so numeric readings align and never jitter.
- Flat surfaces with visible hairline borders; four tonal surface steps do the work depth
  usually does.
- Density over comfort. Cards are compact, the grid is tight, and the shell pins to the
  viewport.

## Colors

A neutral continuum carrying four saturated marks, in which the chrome deliberately holds no
hue at all so that anything coloured on screen is an instrument reporting its state.

### Primary

- **The continuum's extreme** (`#12151a` light, `#dfe4ea` dark, `#aeb6bf` night): identity
  and emphasis, at zero chroma. It wears the wordmark's icon, the filled default button -
  which the panel draws only inside a modal, see Buttons - and `text-primary` wherever a
  string needs to be the loudest thing in its line. It is read both as a fill behind
  `--primary-foreground` (18.29:1 light, 15.31:1 dark) and as text on the ground
  (17.81 / 16.45 / 15.01:1 light on background, sidebar and `--accent`; 15.31 / 15.00 / 10.27
  dark). Its distance from the nearest state colour is 15.72 CIEDE2000 light and 25.61 dark,
  and **that distance is structural rather than tuned**, because a neutral has no hue to
  collide with. The documentation site's header is the same value.

### Secondary

- **The raised step** (`#e6e9ec` light, `#2b3138` dark, `#1b1e22` night): the action
  vocabulary - the Set button, and the selected member of a switch vector. It is one step up
  the same neutral ramp, 15.01:1 light and 10.27:1 dark under `--secondary-foreground`. It
  was a cyan before this palette, and the cyan before *that* sat only ΔE 5.7 from
  `--state-idle` under deuteranomaly, which made the one element a client had turned On
  nearly indistinguishable from an Idle light. With no hue left to separate it, selection is
  carried by **weight as well as fill** - see the Switch Vector Control.

### Tertiary

- **Destructive red** (`#a3120f` light, `#c01b1b` dark, `#c72623` night): destructive actions
  only, and the one place the panel's own chrome is allowed a hue. It is a true red where
  Alert is a rose, and the two are 22.27 CIEDE2000 apart light and 15.44 dark in the worst of
  normal, deuteranopic and protanopic vision - related, as danger should be, without being
  confusable with an instrument in Alert. That separation is what made the token fixable at
  all: under the previous palette every red bright enough to work landed ~1.6 ΔE from the
  Alert of the day. 7.92:1 light and 6.15:1 dark under the `text-white` the variant hardcodes,
  on the button that deletes a saved configuration with no undo. Its 3.05:1 against the dark
  card is deliberate and sufficient - SC 1.4.11 governs a control identified by its
  *boundary*, and this one is identified by its label.
- **The reserved line** (`#085b6f` light, `#7fd6e8` slate): the documentation site's links
  and accent, and **nothing in the panel**. Documentation earns one hue for a reason the panel
  does not have: a Read surface's primary interaction is following a link, and a link that is
  neither coloured nor underlined is not an affordance. Cyan is free - the nearest state is
  Idle at 9.91 CIEDE2000, and Ok, Busy and Alert are 13.7 to 43.2 away - and native to the
  world, an emission line rather than a decoration. 7.67:1 on white (7.04:1 on the light code
  block) and 9.56:1 on the slate ground (8.38:1 on slate code).

### Neutral

- **Surface steps**: background (`#fbfcfd` / `#0a0c0f` / `#000000`), card (`#ffffff` /
  `#101216` / `#050607`), sidebar and muted (`#f1f3f5` / `#1b1f24` / `#121417`; the sidebar
  darkens further in the two dark schemes), accent (`#e6e9ec` / `#2b3138` / `#1b1e22`). Four
  tones, used to separate regions that a shadow would otherwise separate.
- **Secondary text** (`#434a53` / `#b9c2cb` / `#a1a9b2`): the `--muted-foreground` token -
  labels, the connection strip, log timestamps, group headings. It clears **AAA on every
  surface it lands on**: 8.96 / 8.06 / 8.06 / 7.35 light on card, sidebar, muted and accent;
  10.39 / 10.63 / 9.18 / 7.28 dark. That is the bar because this is body-size text and AAA is
  reachable for it. **The tier belongs to the token, not to every label on screen**: the
  shadcn sidebar draws its group headings in `text-sidebar-foreground/70`, which is 6.29:1
  light and 5.61:1 dark - AA and nothing more - so the shell passes `text-muted-foreground`
  at every group heading it composes. Fixed there rather than in `theme.css`, because `color`
  is a real property and an unlayered rule on it would beat every state variant the element
  can be in.
- **Border** (`#7c8490` / `#737b87` / `#636a74`): applied to every element by the base layer,
  so a hairline is the default edge in this system rather than an addition. It is genuinely
  visible now; the palette before this one drew it at 1.24:1, which was not.
- **Control edge** (`#6d7580` / `#79838f` / `#6f7780`): the `--input` token. The border of an
  Input and of a switch-vector member, and the whole of the Switch's off-state track. It
  measures 4.66 light and 4.87 dark on the card, 3.82 / 3.41 on `--accent`, and 3.19 / 3.25
  against its own `bg-input/30` fill, which renders `#d3d6d9` light and `#30343a` dark.
  **It is deliberately one token doing two jobs** - it is both the control's border and the
  30% fill of that same control - and the two pull opposite ways: a value dark enough to edge
  the control cleanly is too close to its own tinted fill. Splitting it would abandon the
  Switch entirely, because the Switch's track *is* `bg-input`.
- **The chart ramp** (`#474c52` → `#c8ccd0` light; `#d9dbde` → `#4c5157` dark; `#6f7780` →
  `#3d444b` night): five neutral steps, and neutral for the system's own reason. The previous
  ramp was a designer's palette that collided badly - one step sat 2.1 CIEDE2000 from dark
  Idle and another 2.5 from dark Ok, on the token the observatory wallboard draws its moon and
  its daylight band with. Every step here is at least 19.5 ΔE from Ok, Busy and Alert in the
  worst of normal, deuteranopic and protanopic vision, and adjacent steps stay 9.1 ΔE apart so
  several series still separate from each other. Neutral costs nothing: what these draw is
  illumination, and moonlight is colourless. The middle steps sit near Idle by construction
  (5.9 at the closest), which is acceptable for a chart mark in a figure and never acceptable
  for a status colour.
- **Ok as a bare mark** (`--state-ok-ink`, `#215c1f` / `#88dd88` / `#88dd88`): the connection
  dots have no foreground of their own, so the fill is the whole object and SC 1.4.11 asks 3:1
  of it. **In every scheme this token currently equals `--state-ok`**, and for two different
  reasons: the light fill is dark enough to serve both roles (8.03 on the card, 7.22 on the
  sidebar, 6.59 on `--accent`), and against every dark surface the fill already clears
  (11.38 card, 11.64 sidebar, 10.05 muted, 7.97 accent), so lifting it would darken nothing and
  put a second green in the palette with no measurement behind it. The token exists in both
  schemes because the utility that reads it does, and it is kept separate because a mark and a
  badge are different jobs that only happen to agree here.
- **Alert as type** (`--state-alert-ink`, `#8e0b55` / `#fba7bc` / `#fba7bc`): the one place a
  status hue is set as *type* rather than as a fill - the protocol-mismatch line in
  `ConnectionStatus`, on the sidebar. Light equals the fill and is AAA everywhere it can land
  (9.02 card, 8.11 sidebar, 7.40 accent); dark lifts to its own value because the dark fill
  reads 6.77:1 as type on the sidebar, which is AA and not the AAA PRODUCT.md asks for where
  it is reachable (7.59 on muted, 8.93 on the card). **It is an ink, never a background.**

### Instrument State

Four fills with matched foregrounds. These are not brand colours and they are not yours to
retune. They keep INDI's own names, which PRODUCT.md fixes as terminology rather than copy.

- **Idle** (`#6b7480` light, `#78848f` dark and night): nothing is happening and nothing is
  wrong.
- **Ok** (`#215c1f` / `#88dd88`): the last operation succeeded. Still a true green (hue 118);
  the separation was bought with lightness and by moving Alert to rose, not by surrendering
  the convention that Ok is green.
- **Busy** (`#947100` / `#ffab1f`): the only state that means "still happening", and the only
  one that animates.
- **Alert** (`#8e0b55` / `#fa385f`): something needs the operator. A rose rather than a red,
  so that Destructive can be the red.

Light mode is the absorption spectrum, so these are **dark fills carrying white labels** -
not the light fills with near-black ink that the two emission schemes use. Every light fill
also clears 3:1 against the card as a graphic in its own right. The state hues are
**unchanged between `.dark` and `.night`**, which is the whole reason the night ceiling is a
luminance rule and not a hue rule.

The four were derived by search rather than by eye, against one constraint the previous set
failed: every pair must separate under **both** deuteranopia and protanopia, not only the one
that was checked. The worst pair in light is 14.88 CIEDE2000 and the floor across the schemes
is 11.94, where the previous palette put dark Ok and dark Alert 2.3 apart - "fine" and "in
Alert" nearly one colour for a deuteranope, in the scheme used at night.

### Named Rules

**The Brand Spends No Chroma Rule.** `--primary`, `--secondary` and `--ring` are neutrals in
all three schemes, so hue on the panel only ever means instrument state. A new accent does not
get measured against the state colours and admitted if it is far enough away; it does not get a
hue at all. The one reserved non-state hue in the product is the documentation site's link
cyan, and it never appears in the panel. This supersedes the old "keep the brand far from the
states" rule, which managed the failure instead of removing it.

**The Measured Value Rule.** A colour token clears its bar on every surface it is used over,
not on the lightest one, and the bar is AAA wherever AAA is arithmetically reachable. Both
schemes' `--muted-foreground` broke this in draft and broke it the same way round: `#4a525c`
cleared AAA on card and sidebar and landed 6.5 on `--accent`, and `#a3adb8` cleared three of
four and failed `--accent` at 5.77. The check now runs over every surface rather than the
obvious ones. Two tokens clear their bar by under 10% and each carries a re-measure note in
`theme.css` beside the value: `--input` against its own `bg-input/30` fill, at 3.19 light
(6% of headroom) and 3.25 dark (8%). Move `--card`, `--accent` or `--foreground` and those
have to be measured again before anything ships.

**The Fill Is Frozen Rule.** The four state fills are tuned for separation from each other, so
contrast is fixed on the foreground and never on the fill. Compressing a fill down the
lightness axis to carry a darker label is exactly what collapsed the previous set to ΔE 2.3.
Change a foreground, not a fill.

The cost of that rule is exact and is recorded rather than smoothed. PRODUCT.md commits to AAA
wherever it is reachable, and on four of the twelve state badges it is not reachable at all:
with the fill frozen, the best any foreground can do is pure black or pure white on it.

| badge | fill | foreground | ratio | best possible | AAA |
|---|---|---|---|---|---|
| light Idle | `#6b7480` | `#ffffff` | 4.74 | **4.74** (white) | unreachable |
| light Ok | `#215c1f` | `#ffffff` | 8.03 | 8.03 (white) | yes |
| light Busy | `#947100` | `#ffffff` | 4.54 | **4.62** (black) | unreachable |
| light Alert | `#8e0b55` | `#ffffff` | 9.02 | 9.02 (white) | yes |
| dark Idle | `#78848f` | `#000000` | 5.50 | **5.50** (black) | unreachable |
| dark Ok | `#88dd88` | `#032010` | 10.46 | 12.74 (black) | yes |
| dark Busy | `#ffab1f` | `#1c1300` | 9.71 | 11.10 (black) | yes |
| dark Alert | `#fa385f` | `#000000` | 5.80 | **5.80** (black) | unreachable |
| night Idle | `#78848f` | `#000000` | 5.50 | **5.50** (black) | unreachable |
| night Ok | `#88dd88` | `#032010` | 10.46 | 12.74 (black) | yes |
| night Busy | `#ffab1f` | `#1c1300` | 9.71 | 11.10 (black) | yes |
| night Alert | `#fa385f` | `#150303` | 5.54 | **5.80** (black) | unreachable |

All twelve clear AA. The four that cannot reach 7:1 are stopped by arithmetic, not by effort,
and PRODUCT.md carries the long form of why two labels at AA is the right price for four
states a colour-blind operator can tell apart. Do not "fix" them by moving a fill. **One row
is a real gap rather than a ceiling**: night Alert is set to `#150303` where `.dark` uses
`#000000` on the identical fill, which leaves 0.26 on the table against its own ceiling for
no stated reason. Taking it to `#000000` costs nothing and matches the scheme it inherits
from.

**The One Reserved Line Rule.** Exactly one non-state hue exists in the product, it is the
documentation site's link cyan, and it lives on the docs site only. The panel and the docs
share the header colour, the ground and the type; the cyan is the one thing that does not
cross, because the panel has no link problem to solve and one exception in the corner of every
page is not a rule.

## Typography

**Display Font:** Geist Mono (with `ui-monospace`, `monospace`)
**Body Font:** Geist Mono (with `ui-monospace`, `monospace`) - the interface has no proportional face
**Label/Mono Font:** JetBrains Mono (with `monospace`), for readouts and log output

**Character:** The entire interface is monospace, which is the loudest thing about it, and it
is chosen for the world rather than for the look: instrument readouts, IAU circulars and
spectra are all set that way. It reads as instrumentation rather than as an application, and a
column of numbers aligns without anyone asking it to. The two stacks divide by intent - the UI
stack carries labels, titles and prose, the readout stack carries values that are compared
against each other: telemetry, log lines, the raw wire names behind the debug toggle.

> **Neither family is actually loaded.** There is no `@font-face`, no font package and no CDN
> link anywhere in the repository, so both stacks fall through to their fallbacks today: the UI
> resolves to the platform's `ui-monospace` (SF Mono, Cascadia, or the system default) and the
> readouts to generic `monospace`. On most platforms those are two different faces for what the
> tokens describe as one system. Ship the fonts or change the tokens; do not leave the file
> claiming a typeface the page never receives. The wordmark's 400/700 split is deliberately
> coarse for the same reason - a fallback face may have to synthesise the weight it lacks.

> **Open decision.** The monospace UI is deliberate and stays. Whether the prose surfaces -
> empty-state copy, the configuration dialog's explanations - move to a proportional face is
> explicitly undecided. Do not resolve it silently in either direction.

### Hierarchy

- **Display** (600, `clamp(3rem, 8.5vw, 10rem)`, 0.9, tracking `-0.025em`): the wallboard's
  headline reading. One per screen. Sized in viewport units because the wallboard is read from
  across a room rather than from a desk; below `lg` it drops to
  `clamp(2.75rem, 13vw, 5rem)` as the board reflows.
- **Headline** (600, `clamp(2rem, 4.4vw, 5rem)`, 1): the wallboard's secondary readings,
  `clamp(2rem, 9vw, 3.5rem)` below `lg`.
- **Title** (600, 0.875rem, 1): property card titles, rendered as level-3 headings. Small on
  purpose: it names a card in a grid of thirty, and shouting would defeat scanning.
- **Body** (400, 0.875rem, 1.25rem): the default. Almost everything.
- **Label** (500, 0.75rem, `+0.025em`, uppercase): group headings, the driver-internals
  disclosure, the debug detail line. The wallboard's own field captions are the same shape one
  notch wider (`+0.1em`) and sized in `vw`.
- **Reading** (400, 0.875rem, tabular figures): every numeric or wire-derived value.

### Named Rules

**The Tabular Rule.** Any number that updates while the operator is looking at it is set in
tabular figures. Telemetry arrives continuously, and proportional digits make a stable reading
appear to twitch, which reads as instability in the instrument rather than in the font.

**The Label Is Not The Name Rule.** Human-facing text always comes from the display label
helper, never from the raw INDI name. Wire names appear in exactly one place, the debug detail
line under a card title, and only when the operator has asked for them. The wire truth is
available; it is not the default reading.

**The Wordmark Separates By Weight Rule.** "INDI" is 400 and "kit" is 700, and neither half is
coloured. `kit` used to be `text-primary`, which worked while the brand had a hue; the theme
now spends none, so a coloured wordmark would be the single exception to the rule that hue
means instrument state - in the corner of every page.

## Layout

The shell is pinned to the viewport (`h-svh`) rather than allowed to grow: the sidebar owns
device selection on the left, the property area scrolls in its own region, and the message
strip stays docked below it. An operator should never lose the log by scrolling.

The property grid is one column, widening to two and then three. Those breaks are **container
queries, not viewport queries** (`@xl` at 36rem, `@4xl` at 56rem), measured against the panel's
own width. Docked siblings shrink that width, so a viewport query would promise a third column
the panel does not have room for. Grid rows use `items-start`, so a card is as tall as its own
contents rather than as tall as the tallest card in its row.

Density is deliberate and tight. The spacing scale runs 6px inside a field, 8px between fields,
12px between cards and between a group heading and its grid, 16px of card padding and shell
padding, and 24px between property groups. The header bar is 56px (as a `min-h`, so 200% text
zoom grows it rather than clipping it), the sidebar 16rem on desktop and 18rem in its mobile
drawer, collapsing to a 3rem icon rail.

The sidebar becomes an off-canvas drawer below 768px, and every fixed edge grows by its
safe-area inset so the header clears a notch and the message strip clears a home indicator.
Mobile is a supported operating console here, not a courtesy breakpoint.

The wallboard is a distinct spatial mode rather than a page. Above `lg` it fills the viewport
exactly, never scrolls, and sizes everything in `vh` and `vw` so one screen holds one glance
from four metres away. Below `lg` it abandons that entirely and reflows to a scrolling column,
because a phone is not a wallboard and clipping a reading is worse than scrolling to it.

### Named Rules

**The Container Query Rule.** Column counts are measured from the container, never the
viewport. Any component that can sit beside a docked panel counts its own width.

**The Heading Chain Rule.** The outline is shell `h1`, group `h2`, card title `h3`, with no
step skipped. A property group that carries no name still emits a visually hidden `h2`, because
dropping it would step `h1` straight to `h3` and break the outline that is the only fast way to
navigate thirty cards without a mouse. One state currently breaks it and `CONCERNS.md` records
the open question: with no devices connected there are no groups, so the page steps from `h1`
to the message strip's `h3`.

**The Docked Strip Pays For Itself Rule.** A strip that shares the viewport with the instrument
grid sizes to its content (`h-auto max-h-56`), never to a fixed height. A fixed 224px charged
the grid whether the log held two lines or two hundred, and the cut landed mid-outline: a group
heading sat one pixel above the strip with its card below the fold, reading as a label for the
log.

## Elevation & Depth

**The system is flat, and its separation is border and tone rather than shadow.** That is now
observable rather than arguable: `--border` is a genuinely visible hairline on every element by
default (the base layer applies it universally), the palette carries four distinct surface
tones, and the shadow scale is effectively invisible - light mode tops out at 5% black through
most of the ramp and reaches 13% only at `2xl`, and dark runs the same shape at roughly double
the alpha, which on a near-black ground is less perceptible still.

What remains undecided is the shadow scale's *purpose*. It arrived with the shadcn theme preset
and nobody has since decided whether it is vestigial or a deliberate sub-threshold lift. Record
which, when someone decides. Until then treat the values below as observed rather than
prescriptive, and do not cite this section as authority for adding or removing depth.

### Shadow Vocabulary (as observed)

- **`2xs` / `xs`** (`0px 1px 4px 0px rgb(0 0 0 / 0.03)`): the input and outline-button lift.
- **`sm` / base** (`0px 1px 4px 0px rgb(0 0 0 / 0.05), 0px 1px 2px -1px rgb(0 0 0 / 0.05)`):
  every card.
- **`md` / `lg` / `xl`**: the same first layer with a progressively larger second one.
- **`2xl`** (`0px 1px 4px 0px rgb(0 0 0 / 0.13)`): the only step that is visible at all.
- Dark and night run the same scale at 0.04 to 0.20 alpha.

## Shapes

A single 12px radius seeds the scale and everything else derives from it: 8px small, 10px
medium, 12px large, 16px extra-large. The system uses three of those in practice.

Cards are the softest thing on screen at 16px. Controls - buttons, inputs, toggles - all sit at
10px, so every interactive element shares one corner. Badges and status dots are fully round.

Switch members are the deliberate exception: each toggle drops its radius to zero and loses its
left border, and the group restores the outer corners at the two ends. The result is one
segmented control built out of individually pressable buttons, which is the honest shape for a
control where each member is independently pressed and focus alone changes nothing.

Borders do the work elsewhere: a 1px hairline is the default edge on every element, and the
sidebar, header, message strip and driver-internals disclosure are all separated by a single
rule rather than by a gap or a shadow.

### Named Rules

**The Pill Means Readout Rule.** Fully round is reserved for things that report and cannot be
pressed - state badges, status dots, the unread count. Anything an operator can act on carries
the 10px control radius. Never round a control to a pill; it reads as a status.

**The Shape Carries The State Rule.** Where a mark is the whole object, it differs in shape
before it differs in hue. The connection dots are a filled disc when live and a hollow ring
when not; the wallboard's three shutter readings are three shapes. Colour alone put the old
green and red 1.08:1 apart under simulated deuteranopia, which is the difference between a live
panel and a dead one.

## Components

### Buttons

- **Shape:** the shared control radius (10px), 36px tall at default and 32px at `sm`.
- **Primary:** the continuum's extreme with its inverse text, 8px by 16px of padding. It is
  worth naming where it appears: **nothing on the panel's own surface is a primary button.**
  Every button an operator sees without opening something is secondary (a Set button, a pressed
  switch member) or ghost/outline (the theme toggle, the sidebar trigger). The variant appears
  inside `DeviceConfigDialog` and nowhere else - "Save" is the modal's primary action, and the
  Load / Restore confirmations use it for their confirming button. That is the correct reading:
  a filled neutral marks *the* action of a surface an operator opened deliberately, and a screen
  of live instrument readings has no such action.
- **Secondary:** the raised neutral step. This is the action vocabulary and it means "this does
  something to the instrument": the Set button, and the selected member of a switch vector.
- **Destructive:** destructive red with hardcoded white text. `ui/button.tsx` carries one
  marked `DEVIATION` here - the registry's `dark:bg-destructive/60` is dropped, so the dark fill
  is the token itself. That composite is the defect the palette closes: it rendered 2.48:1 under
  the previous palette and would render 1.75:1 under this one, putting the most dangerous button
  in the product at its weakest in the scheme an operator uses at night. Not fixable from
  `theme.css`, because `background-color` is a real property and an unlayered rule would also
  beat `hover:bg-destructive/90`.
- **Ghost / Outline:** chrome only - the theme toggle, the sidebar trigger, secondary dialog
  actions. Where the app owns the box it grows the control for real (`size-11`, 44px), so the
  hover tint and the focus ring grow with the target.
- **Hover:** primary composites its fill toward the surface at 90%. Light secondary **holds its
  fill** instead, so the cursor and the focus ring are the affordance - the same behaviour the
  selected switch member has, which keeps the action vocabulary consistent; dark keeps the
  registry's 80% hover.
- **Focus:** a 3px ring at **75%** of the ring colour, held **2px off the control**, plus a
  border shift from `focus-visible:border-ring`. **Focus is never conveyed by the ring alone or
  by the border alone**, and that is not incidental: the corrections raise the ring by setting
  only custom properties, precisely so they cannot disturb the border shift beside them. 75%
  clears 3:1 on every surface either ring lands on, in all three schemes - 9.04 white / 8.93
  light background / 8.51 light sidebar / 8.14 light accent; 10.73 dark card / 11.00 dark
  background / 8.15 dark accent; 9.60 night card / 9.75 night background / 8.47 night accent.
  The registry's own values do not: `/50` composites to 2.85 light and 2.75 dark, and the
  destructive `/20` and `/40` to 1.37 and 1.72.

### Cards

- **Corner Style:** 16px.
- **Background:** card over background. The two differ by a hair in light mode; the border is
  what separates them.
- **Shadow Strategy:** the base card shadow, which is at the edge of perception. See Elevation.
- **Border:** a 1px hairline, which is the actual separation.
- **Internal Padding:** 16px horizontal and vertical, with a 12px gap between header and
  content. Tighter than the primitive's default, because a device can publish thirty of these.
- **Structure:** a property card is a labelled group whose accessible name is the title *and*
  the state badge together, so it arrives as "Exposure, Alert" rather than as a title with a
  coloured shape floating near it.

### Inputs / Fields

- **Style:** transparent fill in light mode, 1px control-edge border, 10px radius, 36px tall,
  readout typeface with tabular figures.
- **Dark fill:** `bg-input/30`, which renders `#30343a` with `--foreground` at 9.79:1 on it and
  6.89:1 on the `/50` hover. The light equivalent renders `#d3d6d9`, at 12.54:1 and 9.39:1.
- **Layout:** each element gets two deterministic lines - a header pairing the label with the
  live current value, then a full-width input for the requested new value underneath. Nothing
  competes for a single row, so a long label and a sexagesimal reading both fit.
- **Focus:** 3px ring at a 2px offset, plus border shift, matching every other control.
- **Disabled:** 50% opacity, pointer events off.

### Switch Vector Control

The signature component, and the one most easily broken by simplification. A switch vector is a
`fieldset` of independent toggle buttons styled to look joined, and it is deliberately **not** a
radio group. The ARIA radio pattern is selection-follows-focus, so arrowing from Disconnect to
Connect would announce that the selection had moved while nothing had gone on the wire. Nothing
is sent until a member is pressed, which is the right behaviour for a control that connects
hardware, and the markup has to say so.

- **Unselected:** transparent with the control border; hovers to the muted tone.
- **Selected:** the raised neutral step at **semibold**, and it holds that appearance under the
  pointer. The weight is load bearing here in a way it was not when this fill was a cyan: muted
  and secondary are adjacent steps on one neutral ramp, so hovered-unselected and selected are
  close in value, and the type weight plus `aria-pressed` are what actually separate them. The
  stock outline toggle drew selection with the accent tone and hovered to the accent tone too,
  which made a hovered unselected member identical to the selected one.

### State Badge and Status Dot

The state-to-colour mapping lives in exactly one place - a `data-indi-state` attribute the theme
resolves to a pair of custom properties - so the badge, the dots, the wallboard's bars and its
drawn figures cannot drift apart. Busy is the only state that animates, and it animates by
ringing outward rather than by fading, held still under `prefers-reduced-motion`.

The ring is an `outline` on an `::after`, scaling from 1 to 1.5 and fading from 0.6 to 0. **Its
first frame is visible**: the ring sits as a 2px line hugging the badge's outside edge and
expands from there, so a Busy badge reads as ringed even between pulses. An outline was chosen
over a border or a box-shadow because it paints entirely outside the pseudo-element's box -
which equals the badge's border box - so no animated pixel ever lands on the label, whatever
padding a consumer passes. Only `transform` and `opacity` animate, both composited.

### Message Log

A docked terminal tail: readout typeface at 0.75rem, newest at the bottom, following the tail as
entries arrive. Each entry stacks a timestamp and device name over the message body so wrapped
lines start at the margin rather than mid-row. The scrolling viewport is a polite,
additions-only live region and carries a tab stop, without which the history above the tail is
unreachable by keyboard.

### Theme Control

One icon button cycling **light → dark → night**, in the sidebar footer beside the debug toggle.
Its label says what pressing it *does* ("Switch to dark", "Switch to dimmed night", "Switch to
light"), because the control is an action and "Toggle theme" stopped being true at three
schemes. `night` is named for what it delivers - a luminance-capped scheme meant to be read with
the display dimmed - and never "night vision", which would promise dark adaptation no readable
screen keeps.

`.night` is applied **alongside** `.dark` on `<html>`, never instead of it, so every `dark:`
utility the primitives ship still resolves and the third scheme only moves token values. The
classes on `<html>` are the only state there is, so two theme controls on one page stay in step.

### Named Rules

**The Never Colour Alone Rule.** Every state is written out in text as well as coloured: the
badge carries its own name, and the status dot is decorative and marked hidden because its label
sits beside it. This holds independently of how well the states separate, and they now separate
far better than they did.

**The word has to be one a sighted reader can see.** A visually hidden word serves a screen
reader and nobody who is merely colour-blind. The connection dots therefore differ in shape as
well as hue and write the failing state out on screen - "bridge offline", not a colour. The
healthy state stays visually hidden, because two permanent extra words in a 16rem sidebar for
the state that is true almost always is a cost paid every night for a reading nobody needs; the
shape carries it, and only the alarm takes space.

**The Ring Stands Off The Control Rule.** A focus ring is measured against **both** its
neighbours, not just the surface. The published ratios above are the ring against the surface
around the control; on a filled control the other neighbour is the control's own fill, and with
a neutral ring on a neutral primary the two are nearly the same value - 1.06:1 light and 1.20:1
dark on the primary button, 1.00:1 on destructive in both schemes. **Removing the brand's hue
made this worse, not better, which is exactly why the offset is not optional.** Every ring is
therefore offset 2px in the surface colour, which puts the surface on both sides of it and
leaves the fill separated by the control's own edge contrast (18.29 primary light, 15.31 primary
dark, 7.92 destructive light, 6.15 destructive dark). It costs nothing structurally, because the
offset is set through custom properties, and Tailwind already grows the ring's spread by the
offset so the ring itself is still 3px.

**The destructive ring is the ordinary ring**, and that is a decision rather than an oversight.
A focus indicator says where the keyboard is; it is not a state and not a warning, and there is
no reason for the answer to that question to change colour with the button under it.
Measurement forced the point before taste got to it: a 75% tint of `--destructive` is 2.15:1
against the dark card and 1.65:1 against `--accent`, both under 3:1, because a red dark enough
to carry white text is too dark to be its own indicator - and raising the red to fix the ring
would cost the label. Its **offset** stays white rather than the surface, because on a filled
destructive control the gap's other neighbour is the red itself; white is the variant's own
hardcoded text colour and makes the indicator two-tone (7.55 white-against-fill, 5.74
ring-against-white, 3.27 ring-against-card). In light mode white *is* the surface, so one
declaration serves both schemes.

**The Registry Is Corrected In CSS, Not In Place Rule.** The shadcn primitives in
`web/packages/react/src/ui/` come from the CLI and stay registry-exact, so a `shadcn add` can
never silently revert an accessibility fix. Where the registry's decisions are wrong, they are
overruled from `theme.css` by rules deliberately placed **outside every `@layer`**, which
outrank every layered rule regardless of specificity. Two constraints come with that and neither
is optional:

- **Hook the utility class, never `data-slot`.** `data-slot` does not survive `asChild` - the
  Slot merges the child's props over the parent's - so a destructive `AlertDialogAction` renders
  `data-slot="alert-dialog-action"` and a Tooltip-wrapped Button renders
  `data-slot="tooltip-trigger"`. Those are exactly the two elements a `data-slot` hook would
  miss: the button that deletes a saved configuration, and the theme toggle. `className`
  concatenates, so the utility class is present in every composition.
- **An unlayered rule setting a real property beats everything on that element**, including the
  registry's own state variants and anything a consumer passes. So it must either restate every
  variant of that property the element can be in, or be narrowed to something that cannot be in
  those states. A custom property such as `--tw-ring-color` has no competitor and is always
  safe. `border-color`, `position` and `background-color` are not, and each has a rejected
  attempt behind it: a `border-color` correction destroyed the focus border shift, and a
  `position` correction on the dialog close beat the primitive's own `absolute` and moved the X.

`theme-cascade.test.ts` compiles the stylesheet - twice, plain and `--minify`, because only the
minified build ships and Lightning CSS rewrites selectors on the way - and asserts every
correction is outside every layer, because jsdom implements neither cascade layers nor
`color-mix` and no other test in the suite can see this mechanism at all.

**CSS reaches styling, and only styling.** Two primitives are edited in place, each marked
`DEVIATION` at the line and re-applied after a `shadcn add`, because what is wrong with them is
*behaviour*: `scroll-area.tsx` spreads props onto the Root only, so nothing could give the
scrolling element a tab stop; and `sidebar.tsx`'s mobile drawer restored focus to a
`Dialog.Trigger` it does not have, and mounted an invisible tooltip whose dismissable layer
swallowed the first Escape. No stylesheet can reach either. The test for the difference is
simple: if a rule in `theme.css` could fix it, it does not belong in `src/ui/`.

**The Target Is Bigger Than The Control Rule.** Every interactive target is 44x44 (SC 2.5.5),
and how it gets there depends on who owns the box. Where the app composes the control, it grows
for real in `className` - the theme toggle and the sidebar trigger are `size-11`, the sidebar
footer rows are `min-h-11` - so the hover tint and the focus ring grow with the target. Where the
box belongs to a published primitive, the theme adds a transparent `::before` overlay sized
`max(100%, 2.75rem)`, which is inert wherever the control is already big enough. The Switch's
track stays 32x18.4 because that is the control's design, and each modal close stays a 16px icon
where the registry anchored it; re-anchoring would couple the theme to four magic numbers to
avoid moving an X by 14px. **The overlay grows the target but not the feedback**: a pointer 20px
from a close button is inside the target with nothing visible confirming it.

Not everything reaches 44px, and the exceptions are enumerated rather than hidden. Still at
32px: the sidebar's device rows and the configuration dialog's trigger, the switch-vector
members, the Set button, and the configuration dialog's own action buttons. All are at least
24px, so SC 2.5.8 is met and only 2.5.5 is not. No registry `size` reaches 44px - `lg` is 40 -
so closing this means a new control size across the library, against a system that commits to
density.

## Do's and Don'ts

### Do:

- **Do** keep the chrome neutral. `--primary`, `--secondary` and `--ring` hold no chroma, so
  every saturated pixel on the panel is an instrument reporting its state.
- **Do** re-measure a colour on every surface it appears over before changing it, and leave the
  measured ratio in a comment beside the value, as every existing token does.
- **Do** write every state out in text as well as colouring it, in text a sighted reader can
  see, and give a bare mark a shape as well as a hue.
- **Do** use tabular figures for anything numeric that updates live.
- **Do** reach for a hairline border or one of the four surface tones when you need separation.
- **Do** count grid columns from the container's width, using container queries.
- **Do** keep the heading chain unbroken (h1 → h2 → h3), emitting a visually hidden heading
  rather than skipping a level.
- **Do** give every control the same 10px radius and the same 3px focus ring at 75% opacity,
  held 2px off the control so it never touches its own fill, and let the border shift beside it
  stand - focus is two signals, never one.
- **Do** correct a vendored primitive from `theme.css`, unlayered and hooked on the utility
  class it emits, rather than by editing `src/ui/`.
- **Do** grow fixed edges by their safe-area inset, and remember the underscore spacing Tailwind
  needs inside `calc()` around `env()`.
- **Do** apply `.night` alongside `.dark`, never instead of it.
- **Do** keep the panel and the documentation on the same neutral identity; they are one product
  and the values are shared deliberately.

### Don't:

- **Don't** give the brand a hue, however far it measures from the four states. The distance is
  not the rule; the absence is.
- **Don't** adjust a `--state-*` fill to fix a contrast problem. Change the foreground, and
  record the shortfall where the ceiling makes AAA unreachable.
- **Don't** chase the night scheme's luminance ceiling with dim greys. The cap is met by a black
  ground and the operator's own brightness control; dimming the colours loses the contrast and
  still misses the ceiling by more than tenfold.
- **Don't** animate by fading opacity on anything carrying text. Fading a badge to 0.5 measured
  1.75:1, and no fill colour survives it - solid black at 0.5 over white reaches only 3.95:1.
  Move the motion to a pseudo-element instead.
- **Don't** write an unlayered rule that sets a real property - `border-color`, `position`,
  `background-color` - without restating every state that property can be in, or narrowing the
  selector to something that cannot be in them. Custom properties are the safe case.
- **Don't** turn the switch control back into a radio group, or let an unselected member reach
  the selected member's appearance on hover.
- **Don't** round a control to a pill or square off a badge; the two shapes carry the
  pressable/reportable distinction.
- **Don't** put the documentation's link cyan on the panel, or add a second reserved hue
  anywhere.
- **Don't** turn this into a data-visualisation dashboard. Wall-to-wall charts, sparklines on
  every reading and neon series colours on near-black are the confirmed anti-reference: INDI
  properties are mostly discrete state rather than time series, and drawing them as telemetry
  streams misrepresents what the instrument is saying.
- **Don't** cite the shadow scale as evidence of an elevation philosophy. It is inherited and
  its purpose is undecided; see Elevation & Depth.
- **Don't** put colour in an architecture diagram. Those render on GitHub and the docs site in
  every scheme, and a hardcoded palette becomes unreadable in one of them.
