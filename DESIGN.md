---
name: INDIkit
description: An instrument-grade control surface for astronomical hardware, built to be read correctly at 3am.
colors:
  # Three schemes, one world. Light (`:root`) is the base; `.dark` overrides carry
  # a `-dark` suffix and `.night` a `-night` suffix. `.night` is applied *alongside*
  # `.dark`, never instead of it, so it only moves token values. The night chrome is
  # a red safelight; the four instrument states are byte-identical to `.dark`.
  background: "#f4f6f8"
  background-dark: "#0a0c0f"
  background-night: "#000000"
  foreground: "#12151a"
  foreground-dark: "#dfe4ea"
  foreground-night: "#e08585"
  card: "#ffffff"
  card-dark: "#16191f"
  card-night: "#140708"
  sidebar: "#eceef1"
  sidebar-dark: "#0d0f13"
  sidebar-night: "#050102"
  muted: "#f1f3f5"
  muted-dark: "#1b1f24"
  muted-night: "#200a0b"
  accent: "#e6e9ec"
  accent-dark: "#2b3138"
  accent-night: "#24090b"
  primary: "#1543ac"
  primary-dark: "#60a5fa"
  primary-night: "#e4afaf"
  primary-foreground: "#ffffff"
  primary-foreground-dark: "#0a0c0f"
  primary-foreground-night: "#1a0000"
  secondary: "#e6e9ec"
  secondary-dark: "#2b3138"
  secondary-night: "#24090b"
  secondary-foreground: "#12151a"
  secondary-foreground-dark: "#dfe4ea"
  secondary-foreground-night: "#e08585"
  muted-foreground: "#434a53"
  muted-foreground-dark: "#b9c2cb"
  muted-foreground-night: "#b06a6a"
  border: "#d3d8dd"
  border-dark: "#2b3138"
  border-night: "#5c1f22"
  input: "#6d7580"
  input-dark: "#79838f"
  input-night: "#ab5e5c"
  ring: "#0a0c0f"
  ring-dark: "#ffffff"
  ring-night: "#ff8f8f"
  destructive: "#a3120f"
  destructive-dark: "#c2321c"
  destructive-night: "#c0201b"
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
  state-alert-foreground-night: "#000000"
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
  chart-1-night: "#8a4442"
  chart-2-night: "#a85f5f"
  chart-3-night: "#c98b86"
  chart-4-night: "#6e3230"
  chart-5-night: "#4a2022"
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
    backgroundColor: "color-mix(in oklab, #1543ac 90%, transparent)"
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
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    typography: "{typography.body}"
    fontWeight: 600
    padding: "0 12px"
    height: "32px"
  button-command:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "32px"
---

# Design System: INDIkit

## Overview

**Creative North Star: "The Emission Spectrum"**

An operator is alone at 3am, a hundred miles from the instrument, and this interface is the
only thing that will tell them what is happening. That is the brief. What the system does
with it is narrower than "be legible": **hue is enumerated.** Six hues exist in the whole
product - four instrument states, one action, and the documentation site's link cyan - and
nothing outside that list may take one. Everything else is a continuum, in three renditions:
light is an absorption spectrum, dark marks on a bright ground; dark is an emission spectrum,
bright marks on a dark one; night is that same emission seen under a red observatory
safelight, where the continuum itself turns red and the four states do not.

The list is short because it was arrived at by subtraction. The palette before this one
carried a violet that sat 22.4 CIEDE2000 from the nearest state colour, and the one before
*that* an orange at 8.3 from Busy - the same mistake at two distances, an identity colour
that is a near-miss for a status colour. The answer was briefly to spend no chroma at all,
which read cleanly and cost more than it bought: with value carrying the whole hierarchy, the
Set button - the one control that writes to an instrument - measured 1.22:1 against the card
in light and read as a label rather than a control, disabled-looking beside an unselected
switch segment. So the rule became enumeration rather than absence. One hue was admitted, on
measurement rather than taste, and the door closed behind it. `--secondary` and `--ring` took
no hue and still hold none in light and dark: a raised surface and a focus indicator are not
things, and neither should claim a colour.

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
  (emission under a red observatory safelight, on a pure-black ground).
- Hue is enumerated: four states, one action, one documentation link. Nothing else may take
  one, and `--secondary` and `--ring` hold none in light or dark.
- Four state hues (Idle / Ok / Busy / Alert), derived by search so every pair separates by at
  least 11.94 CIEDE2000 in the worst of normal, deuteranopic and protanopic vision - and
  **byte-identical in `.dark` and `.night`**, which is what makes the safelight safe.
- Colour never carries meaning on its own: every state is written out as well as coloured.
- Monospace throughout, so numeric readings align and never jitter.
- Flat surfaces, four tonal steps, and a hairline border that is faint by design (1.43:1
  light, 1.34 dark, 1.57 night against the card) rather than a drawn rule.
- Density over comfort. Cards are compact, the grid is tight, and the shell pins to the
  viewport.

## Colors

A neutral continuum in light and dark and a red one at night, carrying an enumerated set of
hues: the four instrument states, one action colour, and - on the documentation site only -
a link cyan.

### Primary

**This is the action colour, and it is the only hue in the panel's chrome.** It fills the Set
button, the momentary command button, and the selected member of a switch vector; it is set
as `text-primary` on the header's icon, the message log's device name and the link-variant
control.

Those three fills are the whole of the control vocabulary, and **shape is what separates
acting from reporting inside it**. A selected switch member is a *segment*: square corners,
edges shared with its neighbours, semibold, and it says "this is the live state". A button
is *standalone*, at the 10px control radius, and it says "press this and something goes on
the wire". One colour, two jobs, told apart by the same distinction the shape scale already
carries - which is what makes the pair legible where a second hue would have cost the
enumeration. What the *instrument* is doing is neither of them: that is the badge at the top
of the card, in one of the four state hues, and this blue clears the nearest of them by 19.2
CIEDE2000.

- **Instrument Blue** (`#1543ac` light, `#60a5fa` dark): admitted by measurement. `theme.css`
  records it at **19.2 CIEDE2000 from the nearest state** in the worst of normal,
  deuteranopic and protanopic vision, against the 8.3 the rejected orange sat from Busy - and
  the comparison is the argument: an action and a status are different objects in different
  places, and at 19 dE neither can be read as the other. As a fill it measures 8.64:1 against
  the light card and 6.92:1 against the dark one, with its label at 8.64:1 and 7.70:1. As
  text it is 8.64 / 7.98 / 7.43 / 7.09:1 light on card, background, sidebar and `--accent`.
  **Its dark values are the one place it does not clear AAA**: 6.92 on the card and 5.17 on
  `--accent`, both AA. Recorded rather than smoothed, because raising the blue walks it back
  up the lightness axis toward nothing useful and darkening it costs the label.
- **Pale Safelight Red** (`#e4afaf` night): the night scheme's action colour, and the palest
  thing on that screen (L\* 76.2, above the ring's 71.5 and the foreground's 65.2). See the
  Night Scheme below - being palest is the mechanism, not a compromise.

The reason it exists at all is a measurement of its own. `--secondary`, which used to carry
the Set button, sits **1.22:1 against the light card** (1.34 dark, 1.05 night). At that
distance it is not a filled control, it is a label printed on the card, and beside an
unselected switch segment it read as disabled. Value alone could not carry the hierarchy.

### Secondary

- **The raised step** (`#e6e9ec` light, `#2b3138` dark, `#24090b` night): a raised surface,
  and nothing more than that. It is one step up the ramp, 15.01:1 light and 10.27:1 dark
  under `--secondary-foreground` (7.03:1 night). It holds no hue of its own in light or dark
  - 1.9 and 5.4 Lab chroma - which is the point: a raised surface is not a thing and should
  not claim a colour. It **used** to fill the selected switch member, and 1.22:1 from the
  card is why it does not any more: see the Switch Vector Control.

### Tertiary

- **Destructive red** (`#a3120f` light, `#c2321c` dark, `#c0201b` night): destructive actions
  only. It is a true red where Alert is a rose, and `theme.css` records them 22.27 CIEDE2000
  apart in light and 15.44 in dark in the worst of normal, deuteranopic and protanopic
  vision; the night pair holds at 18.45 - related, as danger should be, without being
  confusable with an instrument in Alert. That separation is what made the token fixable at
  all: under the previous palette every red bright enough to work landed ~1.6 ΔE from the
  Alert of the day. Under the `text-white` the variant hardcodes it measures 7.92:1 light,
  5.57:1 dark and 6.06:1 night, on the button that deletes a saved configuration with no undo.
  Its 3.16:1 against the dark card is deliberate and sufficient - SC 1.4.11 governs a control
  identified by its *boundary*, and this one is identified by its label. **Destructive is not
  a seventh hue but the red end of the action slot**: it is the only variant of a button, it
  never labels a status, and the night scheme absorbs it into the safelight without moving it.
- **The reserved line** (`#085b6f` light, `#7fd6e8` slate): the documentation site's links
  and accent, and **nothing in the panel**. Documentation earns one hue for a reason the panel
  does not have: a Read surface's primary interaction is following a link, and a link that is
  neither coloured nor underlined is not an affordance. Cyan is free - the nearest state is
  Idle at 9.91 CIEDE2000, and Ok, Busy and Alert are 13.7 to 43.2 away - and native to the
  world, an emission line rather than a decoration. 7.67:1 on white (7.04:1 on the light code
  block) and 9.56:1 on the slate ground (8.38:1 on slate code).
  **The docs header is not `--primary`.** It is `#12151a`, the panel's `--foreground`, at
  18.29:1 under white (`docs/stylesheets/palette.css`). The two surfaces share the neutral
  ground and the type, not the action colour; the panel's blue has no job on a Read surface.

### Neutral

- **Surface steps**: background (`#f4f6f8` / `#0a0c0f` / `#000000`), card (`#ffffff` /
  `#16191f` / `#140708`), muted (`#f1f3f5` / `#1b1f24` / `#200a0b`), sidebar (`#eceef1` /
  `#0d0f13` / `#050102`, always the darkest or the flattest step), accent (`#e6e9ec` /
  `#2b3138` / `#24090b`). Four tones, used to separate regions that a shadow would otherwise
  separate. The card sits only 1.08:1 from the background in light, 1.11 dark, 1.06 night, so
  the separation is a tone shift read at the edge rather than a contrast step.
- **Secondary text** (`#434a53` / `#b9c2cb` / `#b06a6a`): the `--muted-foreground` token -
  labels, the connection strip, log timestamps, group headings. In light and dark it clears
  **AAA on every surface it lands on**: 8.96 / 7.71 / 8.06 / 7.35 light on card, sidebar,
  muted and accent; 9.76 / 10.63 / 9.18 / 7.28 dark. That is the bar because this is
  body-size text and AAA is reachable for it. In night it lands 4.81 / 5.06 / 4.61 / 4.57 -
  AA, not AAA, which is the recorded consequence of that scheme's exemption rather than a
  miss. **The tier belongs to the token, not to every label on screen**: the shadcn sidebar
  draws its group headings in `text-sidebar-foreground/70`, which is AA and nothing more, so
  the shell passes `text-muted-foreground` at every group heading it composes. Fixed there
  rather than in `theme.css`, because `color` is a real property and an unlayered rule on it
  would beat every state variant the element can be in.
- **Border** (`#d3d8dd` / `#2b3138` / `#5c1f22`): applied to every element by the base layer,
  so a hairline is the default edge in this system rather than an addition - and it is a
  **faint** one by design, 1.43:1 against the light card, 1.34 dark, 1.57 night. It reads as
  the edge of a surface, not as a drawn rule. It is not load-bearing for any state or focus
  signal, which is why it is allowed to be this quiet; where separation has to be seen, the
  tone step or `--input` does it.
- **Control edge** (`#6d7580` / `#79838f` / `#ab5e5c`): the `--input` token. The border of an
  Input and of a switch-vector member, and the whole of the Switch's off-state track. It
  measures 4.66 light, 4.87 dark and 4.22 night on the card, 3.82 / 3.41 / 4.01 on `--accent`,
  and 3.19 / 3.02 / 3.06 against its own `bg-input/30` fill, which renders `#d3d6d9` light,
  `#343941` dark and `#412121` night. **It is deliberately one token doing two jobs** - it is
  both the control's border and the 30% fill of that same control - and the two pull opposite
  ways: a value dark enough to edge the control cleanly is too close to its own tinted fill.
  Splitting it would abandon the Switch entirely, because the Switch's track *is* `bg-input`.
- **The chart ramp** (`#474c52` → `#c8ccd0` light; `#d9dbde` → `#4c5157` dark; `#8a4442` →
  `#4a2022` night): five steps, neutral in light and dark for the system's own reason. The
  previous ramp was a designer's palette that collided badly - one step sat 2.1 CIEDE2000 from
  dark Idle and another 2.5 from dark Ok, on the token the observatory wallboard draws its moon
  and its daylight band with. Every step in the two neutral ramps is at least 19.5 ΔE from Ok,
  Busy and Alert, and adjacent steps stay 9.1 ΔE apart so several series still separate from
  each other. Neutral costs nothing there: what these draw is illumination, and moonlight is
  colourless. **The night ramp is red like the rest of that chrome**, and it pays the
  scheme's price rather than escaping it: measured against the night states, `chart-2`
  (`#a85f5f`) sits 1.6 ΔE from Alert and `chart-1` 9.5, so a night chart mark is *not* safe to
  read as a status and must never be placed where one is expected. The middle steps sit near
  Idle by construction in every scheme, which is acceptable for a chart mark in a figure and
  never acceptable for a status colour.
- **Ok as a bare mark** (`--state-ok-ink`, `#215c1f` / `#88dd88` / `#88dd88`): the connection
  dots have no foreground of their own, so the fill is the whole object and SC 1.4.11 asks 3:1
  of it. **In every scheme this token equals `--state-ok`**, and for two different reasons:
  the light fill is dark enough to serve both roles (8.03 on the card, 6.91 on the sidebar,
  6.59 on `--accent`), and against every dark or night surface the fill already clears
  (10.68 / 11.64 / 10.05 / 7.97 dark on card, sidebar, muted and accent; 11.98 / 12.60 /
  11.49 / 11.39 night), so lifting it would darken nothing and put a second green in the
  palette with no measurement behind it. The token exists in all three schemes because the
  utility that reads it does, and it is kept separate because a mark and a badge are different
  jobs that only happen to agree here.
- **Alert as type** (`--state-alert-ink`, `#8e0b55` / `#fba7bc` / `#fba7bc`): the one place a
  status hue is set as *type* rather than as a fill - the protocol-mismatch line in
  `ConnectionStatus`, on the sidebar. Light equals the fill and is AAA everywhere it can land
  (9.02 card, 7.76 sidebar, 7.40 accent); dark and night lift to their own value because the
  dark fill as type reads 5.29:1 on the sidebar, where the ink reads 10.37 (9.52 card, 8.95
  muted). **It is an ink, never a background.**

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
also clears 3:1 against the card as a graphic in its own right (4.74 / 8.03 / 4.54 / 9.02).
The four state tokens are **byte-identical in `.dark` and `.night`**, and that is now the
load-bearing fact of the whole palette rather than a convenience: it is what lets the night
scheme spend its entire colour channel on chrome without spending status with it.

The four were derived by search rather than by eye, against one constraint the previous set
failed: every pair must separate under **both** deuteranopia and protanopia, not only the one
that was checked. The worst pair in light is 14.88 CIEDE2000 and the floor across the schemes
is 11.94, where the previous palette put dark Ok and dark Alert 2.3 apart - "fine" and "in
Alert" nearly one colour for a deuteranope, in the scheme used at night.

### The Night Scheme

`.night` is **not** a dimmed or desaturated version of `.dark`. Its entire chrome is red - an
observatory safelight - and the four instrument states are untouched. Ground, text, rules,
fields, focus and the action colour all sit on one red: background `#000000`, card `#140708`,
foreground `#e08585` (7.39:1 on the card), border `#5c1f22`, `--input` `#ab5e5c`, `--ring`
`#ff8f8f`, `--primary` `#e4afaf`. A grey Idle and a green connection dot on that field are
*more* legible as status, not less, because status is the one thing on screen that is still
itself.

**The action colour is the palest red on screen, and that is the mechanism.** In a scheme
where hue is spent, tone is the only hierarchy left, so the control that writes to an
instrument is the brightest thing in the chrome: `#e4afaf` at L\* 76.2, above the ring (71.5),
the foreground (65.2) and `--input` (48.8). It measures 10.39:1 as a fill against the card
with its label at 10.58:1. Its position was forced, not chosen: `theme.css` records a search
over every red at usable brightness finding **10 CIEDE2000 to be the ceiling** for separation
from all four states, because moving away from the amber Busy walks back toward the rose
Alert, and `#e4afaf` sits at that ceiling (17.2 from Alert, 22.7 from Busy).

**`.night` is exempt from the AAA/AA contrast commitment, by recorded product decision.** It
is a dark-site scheme meant to be read with the display dimmed, and forcing 7:1 on it would
defeat what it exists for, so it is held to a legibility floor instead and to every check that
is about safety rather than comfort - the state separations are untouched and destructive
stays 18.45 CIEDE2000 from Alert. In practice the floor lands well above AA on the type that
matters (foreground 7.86 background / 7.39 card / 7.03 accent) and at AA on secondary text
(4.57 to 5.12) and on the focus ring's own surfaces. PRODUCT.md carries the decision and its
**two accepted costs**, and both are costs rather than features:

- A protanope loses about **4.5 L\*** of this chrome that a normal observer sees.
  MIL-STD-1472F 5.2.1.5.6.2 asks that wavelengths above 650 nm be avoided where users include
  protanopes, and this scheme does not.
- The action colour clears the nearest state by **10 CIEDE2000**, where the other two schemes
  hold 15 and up. Ten is enough to tell a button from a badge in a different place on screen;
  it is not the margin the rest of the palette works to.

Both are **bounded to chrome**. The four states keep their own hues and their full pairwise
separation in this scheme, so nothing an instrument says is tinted, dimmed or narrowed. That
boundary is the trade, and it is the only reason the costs are acceptable at all: widen the
red past the chrome and neither of them stays bounded.

The luminance ceiling is still met, and still not by CSS. MIL-STD-1472F 5.2.1.5.6.3 caps at
10 cd/m², which on a 400-nit panel is a relative luminance of 0.025 - so even pure black
against that ceiling yields 1.5:1, and no stylesheet can reach the cap and stay readable.
Contrast is relative and survives dimming untouched; the ground is pure black so that almost
nothing emits, and the operator's brightness control does the rest.

### Named Rules

**The Enumerated Hue Rule.** Six hues exist in this product: four instrument states, one
action colour, and the documentation site's link cyan. **Nothing outside that list may take
one**, and the list does not grow by measurement - a new candidate is not admitted because it
measures far enough from the states, it is refused because the list is closed. `--secondary`
and `--ring` hold no hue in light or dark, because a raised surface and a focus indicator are
not things. This supersedes both the old "keep the brand far from the states" rule, which
managed the failure instead of removing it, and its successor "the brand spends no chroma",
which removed the failure and took the action hierarchy with it.

**The Safelight Tints The Chrome, Never The States Rule.** `.night` is the one scheme where
`--secondary` and `--ring` are not literally neutral, and that is not an exception to the rule
above but a property of the ground: the safelight tints everything the interface owns, so no
token there is claiming a hue of its own. The line it may not cross is the four `--state-*`
tokens, which are byte-identical to `.dark`. Anything that reports on the instrument keeps its
own colour; anything that is merely interface takes the red.

**The Measured Value Rule.** A colour token clears its bar on every surface it is used over,
not on the lightest one, and the bar is AAA wherever AAA is arithmetically reachable **in
light and dark**; `.night` is held to its legibility floor instead. Both schemes'
`--muted-foreground` broke this in draft and broke it the same way round: `#4a525c` cleared
AAA on card and sidebar and landed 6.5 on `--accent`, and `#a3adb8` cleared three of four and
failed `--accent` at 5.77. The check now runs over every surface rather than the obvious ones.
The tightest margins in the palette are `--input` against its own `bg-input/30` fill - 3.19
light, 3.02 dark, 3.06 night, clearing 3:1 by 6%, 1% and 2% - and each carries a re-measure
note in `theme.css` beside the value. Move `--card`, `--accent` or `--foreground` and those
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
| night Alert | `#fa385f` | `#000000` | 5.80 | **5.80** (black) | unreachable |

All twelve clear AA, and the night rows are identical to the dark ones because the tokens
are. The four that cannot reach 7:1 are stopped by arithmetic, not by effort, and PRODUCT.md
carries the long form of why two labels at AA is the right price for four states a
colour-blind operator can tell apart. Do not "fix" them by moving a fill.

**The One Reserved Line Rule.** Two non-state hues exist, and **each is reserved to one
surface**: the action blue to the panel, the link cyan to the documentation. Neither crosses.
The panel has no link problem to solve, and a Read surface has no control that writes to an
instrument, so a hue admitted for one job on one surface never becomes a general accent. What
the two surfaces do share is the neutral ground, the type and the header colour - `#12151a`,
which is the panel's `--foreground` and not its `--primary`.

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

> **Both families are self-hosted, and that was a decision rather than a default.** They were
> named and not shipped at first, so both stacks fell through to whatever mono the machine
> had and the tokens described a system the page never received. They now ship as latin
> subsets in `packages/react/src/fonts/` - four weights of Geist Mono, one of JetBrains Mono
> - behind the opt-in `@indikit/react/fonts.css`, which the reference panel imports because
> the panel is an application and the one bundled into the wheel. Not a CDN link:
> PRODUCT.md's operating context has instruments at a dark site where connectivity is not
> guaranteed, and a `<link>` to a font host would make the typeface the only thing on that
> page needing the public internet. Both are OFL 1.1 and their licences travel beside the
> files. The wordmark's 400/700 split stays deliberately coarse anyway, since the fallback
> stack is still what a consumer who skips that import gets.

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
coloured. `kit` used to be `text-primary`, and it stays uncoloured now that `--primary` is a
hue again: the action colour is on the list because it marks *the control that writes to an
instrument*, and a wordmark writes to nothing. Colouring it would put a seventh hue in the
corner of every page and reduce the enumeration to a suggestion. The header's telescope icon
does take `text-primary`, which is the boundary: a mark that leads the action colour's own
surface, not the name of the product.

## Layout

The shell is pinned to the viewport (`h-svh`) rather than allowed to grow: the sidebar owns
device selection on the left, the property area scrolls in its own region, and the message
strip stays docked below it. An operator should never lose the log by scrolling.

**The sidebar has one list, and everything that belongs to a device hangs off that device.**
There is no server-wide anything in INDI - `indiserver` publishes no properties at all - so
a second flat group beside the device list has nothing true to be. Configuration is the case
that proved it: as a sibling of the device rows it was read as a third device, and moved out
to its own group it printed the selected device's name a second time as a heading while
still drawing the entry at the devices' own indent. It now sits in a `SidebarMenuSub` inside
its device's item, where the indent, the guide line and the list nesting say whose it is and
no heading has to. Anything the panel grows next that acts on one device goes in the same
place.

The property grid is one column, widening to two and then three. Those breaks are **container
queries, not viewport queries** (`@xl` at 36rem, `@4xl` at 56rem), measured against the panel's
own width. Docked siblings shrink that width, so a viewport query would promise a third column
the panel does not have room for. Grid rows use `items-start`, so a card is as tall as its own
contents rather than as tall as the tallest card in its row.

Density is deliberate and tight. The spacing scale runs 6px inside a field, 8px between fields,
12px between cards and between a group heading and its grid, 16px of card padding and shell
padding, and 24px between property groups. The header bar is 56px (as a `min-h`, so 200% text
zoom grows it rather than clipping it), the sidebar 16rem on desktop and 18rem in its mobile
drawer. A nested entry is 32px like the device row above it, over the primitive's own 28px,
so one column of rows keeps one rhythm.

The sidebar collapses **off-canvas**, not to the 3rem icon rail the primitive also offers,
and that is a decision rather than a default left standing: a rail can show a device's icon
but not the entries nested under it, and the registry hides a `SidebarMenuSub` outright in
that mode. Switching to the rail would silently take a device's configuration off screen.

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

**The system is flat, and its separation is border and tone rather than shadow.** The base
layer applies `--border` to every element, so a hairline is the default edge; the palette
carries four distinct surface tones; and the shadow scale is effectively invisible - light
mode tops out at 5% black through most of the ramp and reaches 13% only at `2xl`, and dark
runs the same shape at roughly double the alpha, which on a near-black ground is less
perceptible still. The hairline itself is deliberately faint (1.43:1 light, 1.34 dark, 1.57
night against the card): it marks where one surface ends, and the tone step beside it is what
actually carries the separation. Do not read the border as a drawn rule, and do not darken it
to make one - nothing in the system depends on seeing it.

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

**A momentary command does not take that exception, and the difference is load bearing.** It
is one button standing alone at the full 10px, because it belongs to no group and reports no
position - and because it shares the action colour with a selected member, the corners are
what keep "press this" and "this is the live state" apart. Squaring one off or rounding the
other collapses the distinction.

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
- **Primary:** the action colour with its inverse text, 8px by 16px of padding. **It means
  "this writes to the instrument."** The `Set` button on every writable property card is this
  variant, and so is the primary action of `DeviceConfigDialog` - "Save", and the confirming
  button of the Load / Restore dialogs. It carries the panel's only chrome hue, and that is
  the whole reason it exists: the same control drawn in `--secondary` measured 1.22:1 against
  the light card and read as a disabled label rather than a button. Fill against card 8.64 /
  6.92 / 10.39:1 with its label at 8.64 / 7.70 / 10.58:1.
- **Secondary:** the raised neutral step. Not an action, and since the selected switch member
  moved to the action colour, not a control fill at all - it is a surface.
- **Destructive:** destructive red with hardcoded white text. `ui/button.tsx` carries one
  marked `DEVIATION` here - the registry's `dark:bg-destructive/60` is dropped, so the dark fill
  is the token itself. That composite is the defect the palette closes: it rendered 2.48:1 under
  the previous palette, putting the most dangerous button in the product at its weakest in the
  scheme an operator uses at night. Not fixable from `theme.css`, because `background-color` is
  a real property and an unlayered rule would also beat `hover:bg-destructive/90`.
  **Exactly one control wears it: `Purge` in the configuration dialog.** That is the whole
  list on purpose - a destructive button deletes something with no way back, and it lives on
  a surface an operator opened deliberately, never on an instrument card beside a state
  badge. Label on fill 7.92 / 5.57 / 6.06:1.
- **Ghost / Outline:** chrome only - the theme toggle, the sidebar trigger, secondary dialog
  actions. Where the app owns the box it grows the control for real (`size-11`, 44px), so the
  hover tint and the focus ring grow with the target.
- **Hover:** primary composites its fill toward the surface at 90%; dark secondary keeps the
  registry's 80%. Light secondary and the **selected switch member** both hold their fill
  instead, so the cursor and the focus ring are the affordance. That is the right pairing for
  a different reason in each case: light secondary is a surface, and the selected member is
  already reporting the instrument's position, so neither has a press to acknowledge.
- **Focus:** a 3px ring at **75%** of the ring colour, held **2px off the control**, plus a
  border shift from `focus-visible:border-ring`. **Focus is never conveyed by the ring alone or
  by the border alone**, and that is not incidental: the corrections raise the ring by setting
  only custom properties, precisely so they cannot disturb the border shift beside them. 75%
  clears 3:1 on every surface either ring lands on, in all three schemes - 9.04 white / 8.74
  light background / 8.39 light sidebar / 8.14 light accent; 10.29 dark card / 11.00 dark
  background / 8.15 dark accent; 5.41 night card / 5.53 night background / 5.28 night accent.
  The night figures are lower because that ring is a red (`#ff8f8f`) on a red ground rather
  than a neutral on a neutral one; they still clear the 3:1 floor by three-quarters. The
  registry's own values do not: `/50` composites to 2.85 light and 2.75 dark, and the
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
- **Dark fill:** `bg-input/30`, which renders `#343941` with `--foreground` at 9.09:1 on it.
  The light equivalent renders `#d3d6d9` at 12.54:1, the night one `#412121` at 5.37:1.
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

- **Unselected:** transparent with the control border; hovers to the muted tone, which the
  selected member can never reach. The stock outline toggle drew selection with the accent
  tone and hovered to the accent tone too, so a hovered unselected member was identical to
  the selected one.
- **Selected:** the action colour at **semibold**, and it holds that appearance under the
  pointer. It wore `--secondary` while the palette spent no chroma at all, and at 1.22:1 from
  the card "which member is the instrument actually on" was a question you leaned in to
  answer. Labels measure 8.64 / 7.70 / 10.58:1 on the fill, and the fill stays clear of all
  four states: 18.18 CIEDE2000 in light and 18.75 in dark at the worst of normal,
  deuteranopic and protanopic vision, and 9.96 under the safelight, which is the ceiling that
  scheme is recorded as accepting rather than a slack threshold.
- **A segment is not a button, and the shape is what says so.** Sharing the action colour
  with the `Set` button beside it is safe because the two never share a shape: this one is a
  square-cornered segment welded to its neighbours, that one stands alone at the 10px control
  radius. Keep both halves - a segmented group that regains its corners, or a standalone
  control that loses them, collapses the only distinction holding the two meanings apart.

### Command Button

**A switch vector that is a command and not a selection is a push button.** INDI has one
switch type and uses it for two different objects, and the second has a shape the first
cannot take: a single member under `AtMostOne`, the rule that permits none-on. libindi's
stop commands are all built that way, and so is this panel's own `CONFIG_PROCESS`.

Drawn as a toggle it is a lie with a look to match. `aria-pressed="false"` claims a second
position the control does not have, and the appearance that goes with it is the transparent
outline of an *unselected* member - so on the dome's Main Control tab the one button that
stops the instrument sat beside the genuinely unpressed halves of `Connect` and `Park`,
identical to them and the palest thing on the tab, while the action colour was spent on
`Unpark` reporting that nothing was happening.

- **Every command is primary, including `Abort`, and there is no second variant.** Abort was
  drawn destructive for one release, on the true observation that stopping a moving dome
  leaves `DOME_SHUTTER` in Alert with its position unknown. True, and not a reason to spend
  a hue. Red here is the enumerated colour of a *destructive button in a dialog*; on an
  instrument card that can carry an Alert badge two inches away it asks an operator to tell
  "the instrument is in Alert" from "this button stops it" by hue, at 3am, which is the
  confusion this palette exists to prevent. The card's title and the button's label already
  say which command it is.
- **Destructive stays where the press destroys something the operator cannot get back**, and
  on this product that is `Purge` in the configuration dialog: a file deletion with no
  backup, behind a confirmation, on a surface an operator opened deliberately. An instrument
  command is not that, however urgent.
- **Feedback is the card's state badge, not the button.** A push button has no on-state and
  needs none - the driver answering Busy and then Ok is what says the command landed, which
  is the same channel every other control on this panel reports through. An abort that put
  the instrument into Alert says so there, in the state hue, where a state belongs.

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
schemes. `night` is named for what it delivers - a red safelight scheme meant to be read with
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
around the control; on a filled control the other neighbour is the control's own fill, and
there the ring is nearly flush - 1.05:1 light, 1.49 dark and 1.92 night on the primary button,
1.00:1 on destructive. Giving the action a hue did not fix this and was never going to: the
ring is neutral in light and dark and red at night, so it collides with whatever the fill is
doing regardless. Every ring is therefore offset 2px in the surface colour, which puts the
surface on both sides of it and leaves the fill separated by the control's own edge contrast
(8.64 primary light, 6.92 primary dark, 10.39 primary night, 7.92 destructive light, 5.57
destructive dark). It costs nothing structurally, because the offset is set through custom
properties, and Tailwind already grows the ring's spread by the offset so the ring itself is
still 3px.

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

- **Do** keep the hue list at six - four states, one action, one documentation link - and reach
  for tone, weight or shape when something new needs to stand out.
- **Do** keep `--primary` to the control vocabulary - what writes to an instrument and what
  reports its live position - and separate those two by shape, standalone against segment,
  never by reaching for a seventh hue.
- **Do** leave a state badge on the four state hues and never on `--primary`; a badge is not
  a control.
- **Do** draw a one-member `AtMostOne` switch as a push button, in the one action fill every
  other writing control wears.
- **Do** keep `--secondary` and `--ring` free of hue in light and dark, and let `.night` tint
  them along with the rest of the chrome.
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
- **Do** keep the panel and the documentation on the same neutral ground and type; the link
  cyan and the action blue are each reserved to one surface and do not cross.

### Don't:

- **Don't** add a seventh hue, however far it measures from the four states. The list is
  closed; distance is what got the sixth in, not what keeps the door open.
- **Don't** put the action colour on anything outside the control vocabulary - not the
  wordmark, not a state badge, not a heading that wants emphasis.
- **Don't** draw a momentary command as a toggle. `aria-pressed` on a control with one
  position is the same false claim the radio group made, and the look that comes with it is
  an unselected member's.
- **Don't** reach for `--destructive` to mark a control as urgent or consequential. It is
  the colour of a press that destroys something with no way back, and putting it on an
  instrument card sets it beside the Alert badge it must never be confused with. Urgency is
  the operator knowing where the control is, which position and label give it.
- **Don't** adjust a `--state-*` fill to fix a contrast problem. Change the foreground, and
  record the shortfall where the ceiling makes AAA unreachable.
- **Don't** let the safelight reach the four `--state-*` tokens. `.night`'s red is bounded to
  chrome, and that boundary is the only thing that makes its two accepted costs - about 4.5 L\*
  lost to a protanope, and an action colour 10 CIEDE2000 from the nearest state instead of 15 -
  acceptable at all.
- **Don't** hold `.night` to the AAA/AA commitment, or "fix" its ratios toward it. The
  exemption is a recorded product decision in PRODUCT.md, and forcing 7:1 defeats what the
  scheme exists for. It answers to its legibility floor and to the safety checks instead.
- **Don't** chase the night scheme's luminance ceiling with dim colours. The cap is met by a
  black ground and the operator's own brightness control; dimming loses the contrast and still
  misses the ceiling by more than tenfold.
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
