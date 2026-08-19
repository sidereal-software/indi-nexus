---
name: INDINexus
description: An instrument-grade control surface for astronomical hardware, built to be read correctly at 3am.
colors:
  # Light mode is the base. Dark-mode overrides carry a `-dark` suffix.
  primary: "#3a2a70"
  primary-foreground: "#ffffff"
  primary-dark: "#a99ae4"
  primary-foreground-dark: "#121113"
  secondary: "#527575"
  secondary-foreground: "#ffffff"
  secondary-dark: "#38bcd6"
  secondary-foreground-dark: "#121113"
  background: "#ffffff"
  background-dark: "#121113"
  foreground: "#111827"
  foreground-dark: "#c1c1c1"
  card: "#ffffff"
  card-dark: "#121212"
  sidebar: "#f3f4f6"
  sidebar-dark: "#121212"
  muted: "#f3f4f6"
  muted-dark: "#222222"
  muted-foreground: "#474e59"
  muted-foreground-dark: "#b0b0b0"
  accent: "#eeeeee"
  accent-dark: "#333333"
  border: "#e5e7eb"
  border-dark: "#222222"
  input: "#86888c"
  input-dark: "#7d7d7d"
  destructive: "#dc2626"
  destructive-dark: "#ef4444"
  state-idle: "#9ca3af"
  state-idle-foreground: "#0f1319"
  state-ok: "#16a34a"
  state-ok-foreground: "#00250f"
  state-busy: "#d97706"
  state-busy-foreground: "#150e00"
  state-alert: "#ef4444"
  state-alert-foreground: "#280505"
  state-ok-ink: "#128a45"
  state-alert-ink: "#9b0000"
  state-idle-dark: "#6b7280"
  state-idle-foreground-dark: "#ffffff"
  state-ok-dark: "#22c55e"
  state-ok-foreground-dark: "#032010"
  state-busy-dark: "#f59e0b"
  state-busy-foreground-dark: "#1c1300"
  state-alert-dark: "#f87171"
  state-alert-foreground-dark: "#150303"
  state-ok-ink-dark: "#22c55e"
  state-alert-ink-dark: "#fc9797"
  chart-1: "#5f8787"
  chart-2: "#e78a53"
  chart-3: "#fbcb97"
  docs-link: "#4b3a91"
  docs-accent: "#0f7f96"
  docs-link-dark: "#a99ae4"
  docs-accent-dark: "#38bcd6"
typography:
  display:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "clamp(3rem, 10vw, 11rem)"
    fontWeight: 600
    lineHeight: 0.9
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "clamp(2.5rem, 6vw, 6.5rem)"
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
    backgroundColor: "color-mix(in oklab, #3a2a70 90%, transparent)"
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
    height: "36px"
    width: "36px"
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
  badge-state-ok:
    backgroundColor: "{colors.state-ok}"
    textColor: "{colors.state-ok-foreground}"
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

# Design System: INDINexus

## Overview

**Creative North Star: "The Night Watch"**

An operator is alone at 3am, a hundred miles from the instrument, and this interface is the
only thing that will tell them what is happening. That is the whole brief. Every decision in
this system answers to it: the interface is not here to be liked, it is here to be read
correctly by someone tired, in the dark, possibly on a phone, with nobody else to ask.

The register is instrument-grade, dense and professional. This is closer to a control desk
than to a consumer app. Information density is a feature rather than a failure of restraint,
because the operator is an expert and slowing them down for the sake of breathing room costs
them the night. The whole interface is set in monospace, so a column of readings aligns by
default and a value never shifts as its digits change. Chrome recedes. Colour is rationed and
almost never decorative: four hues are reserved for instrument state and are effectively
frozen, which means every other surface has to earn attention some other way.

What makes this system unusual is that its palette was not chosen by eye. Nearly every colour
token in `theme.css` carries its measured contrast ratio and a note on the value it replaced
and why that one failed. The brand violet exists because an earlier orange measured 3.12:1
under white text and sat only 8.3 CIEDE2000 from the Busy amber, which made the brand colour a
near-miss for a status colour. That is the standard: a value is defended by measurement, and
taste does not overrule a ratio. Future work inherits the obligation, not just the values.

**Key Characteristics:**

- Monospace throughout, so numeric readings align and never jitter.
- Four frozen state hues (Idle / Ok / Busy / Alert), tuned for separation under colour-vision
  deficiency and never adjusted for contrast.
- Colour never carries meaning on its own: every state is written out as well as coloured.
- Flat surfaces with hairline borders; four tonal surface steps do the work depth usually does.
- One accent for actions, one for identity, and a hard distance between both and every state hue.
- Density over comfort. Cards are compact, the grid is tight, and the shell pins to the viewport.
- Light and dark are equal citizens, each measured independently rather than derived.

## Colors

A low-chroma, viridis-anchored palette in which the identity colours deliberately stand as far
as possible from the four status colours, because a brand colour that can be mistaken for a
fault is a defect.

### Primary

- **Viridis Violet** (`#3a2a70` light, `#a99ae4` dark): identity. The wordmark, links, the
  device name in the message log, focus rings, the checked Switch's track, and the filled
  default button - which the panel draws only inside a modal; see Buttons. Anchored on
  viridis 0.15, the violet an astronomer has already looked at ten thousand times in a science
  plot, and shared byte-for-byte with the documentation chrome so the panel and the docs read
  as one product. It sits no closer than 22.4 CIEDE2000 to any of the four state colours. In
  dark mode it is the same hue lifted rather than reused, because it is read as text there as
  well as filled behind `primary-foreground`.

### Secondary

- **Signal Cyan** (`#527575` light, `#38bcd6` dark): the action vocabulary, and nothing else.
  It wears the Set button and the selected member of a switch vector. The dark value is the
  same cyan the documentation uses as its slate accent, which puts it 23.2 CIEDE2000 from the
  nearest state colour in the worst of normal, deuteranomalous and protanomalous vision.

### Tertiary

- **Fault Red** (`#dc2626` light, `#ef4444` dark): destructive actions only. Related to the
  Alert state as danger should be (11.3 CIEDE2000 apart in dark mode) without being the same
  swatch. The light value is darker than the dark value on purpose: the destructive button
  hardcodes white text, and the lighter red measured 3.76:1 under it.

### Neutral

- **Instrument Ink** (`#111827` light foreground): body text, headings, card titles.
- **Bezel Grey** (`#474e59` light, `#b0b0b0` dark): labels, secondary text, the connection
  strip, the timestamps in the log. It clears **AAA** on every surface it appears over -
  8.39 / 7.63 / 7.23 light on card, sidebar and accent; 8.64 / 7.34 dark on card and muted -
  which is the bar, because this is body-size text and AAA is reachable for it.
  **The tier belongs to the token, not to every label on screen.** The shadcn sidebar draws its
  group headings in `text-sidebar-foreground/70` instead, which is 6.29:1 light and 5.61:1 dark
  - AA and nothing more - so the shell passes `text-muted-foreground` at the one place it
  composes a group heading ("Devices"). Fixed there rather than corrected in `theme.css`
  because `color` is a real property and an unlayered rule on it would beat every state variant
  the element can be in; the shell owns this label and can simply say so. Anything else
  reaching for a secondary-text colour has to name this token to be on the tier.
- **Surface steps**: background (`#ffffff` / `#121113`), card (`#ffffff` / `#121212`), sidebar
  and muted (`#f3f4f6` / `#222222`), accent (`#eeeeee` / `#333333`). Four tones, used to
  separate regions that a shadow would otherwise separate.
- **Border** (`#e5e7eb` / `#222222`): applied to every element by the base layer, so a hairline
  is the default edge in this system rather than an addition. It is decorative separation and
  is *not* what tells you where a control is - that is Control Edge, below.
- **Control Edge** (`#86888c` / `#7d7d7d`): the `--input` token. The edge of an Input, of a
  switch-vector member, and the whole of the Switch's off-state track. It used to be
  byte-identical to Border at 1.24:1, which is invisible, and SC 1.4.11 asks 3:1 of anything
  that identifies a control. It now measures 3.55 / 3.23 / 3.06 light on card, sidebar and
  accent, and 4.55 / 3.07 dark on card and accent. **It is deliberately one token doing two
  jobs**, because it is also the 30% fill of the control it borders (`bg-input/30`), and the
  two pull opposite ways: at `#6e6e6e` the dark border reads 3.71:1 on the card but only
  2.68:1 against its own fill. Splitting it would leave the Switch behind entirely, because
  the Switch's track *is* `bg-input`.
- **Alert Ink** (`#9b0000` / `#fc9797`): the `--state-alert-ink` token, and the one place a
  status hue is set as *type* rather than as a fill. The Alert fill is tuned to be read behind
  its own foreground; as 12px text on the sidebar it is 3.42:1 in light mode. Alert Ink is the
  same hue taken until it clears AAA on every surface that line can land on. It is an ink,
  never a background.
- **Ok Ink** (`#128a45` / `#22c55e`): the `--state-ok-ink` token, the same idea for a status
  hue drawn as a bare *graphic*. The connection dots have no foreground of their own, so the
  fill is the whole object and SC 1.4.11 asks 3:1 of it - and Ok is the only one of the four
  that misses: 2.99:1 on the sidebar and 2.84:1 on accent, against 3.24 for Alert at its worst
  and more for Idle and Busy. So only this one needs an ink, and it clears with margin rather
  than by hundredths: 4.42 on the card, 4.02 on the sidebar, 3.81 on accent. **The dark value
  is deliberately the fill**, because against every dark surface the fill already clears (8.22
  on the card and the sidebar, 6.98 on muted, 5.54 on accent) and a second dark green would be
  a swatch with no measurement behind it.

### Instrument State

Four fills with matched foregrounds. These are not brand colours and they are not yours to
retune.

- **Standby Grey** (`#9ca3af` / `#6b7280`): Idle. Nothing is happening and nothing is wrong.
- **Nominal Green** (`#16a34a` / `#22c55e`): Ok. The last operation succeeded.
- **Working Amber** (`#d97706` / `#f59e0b`): Busy. The only state that means "still happening",
  and the only one that animates.
- **Fault Red** (`#ef4444` / `#f87171`): Alert. Something needs the operator.

### Named Rules

**The Measured Value Rule.** A colour token clears its bar on every surface it is used over, not
on the lightest one, and the bar is AAA wherever AAA is arithmetically reachable. `muted-foreground`
was `#6b7280`, which passed on a white card at 4.83:1 and failed on the sidebar at 4.39:1 and on
accent at 4.17:1, which is precisely where it labels the connection state; then `#616974`, which
cleared AA on all three and AAA on none. Re-measure against all of them or do not change it.

Three pairs in this palette clear their bar by under 5%, and each carries a re-measure note in
`theme.css` beside the value: Control Edge against accent in light (3.06) and in dark (3.07), and
the dark Switch track against its thumb (3.10). Move `--card`, `--accent` or `--foreground` and
those three have to be measured again before anything ships.

**The Brand Is Not A Status Rule.** An identity colour keeps a hard CIEDE2000 distance from all
four state fills, in normal, deuteranomalous and protanomalous vision. This is why the original
orange was rejected and why the current violet and cyan were chosen. A new accent that lands
near Busy amber or Alert red is disqualified regardless of how it looks.

**The Fill Is Frozen Rule.** The four state fills are tuned for separation from each other, so
contrast is fixed on the foreground and never on the fill. Darkening the fills enough to carry
white text squeezes all four into one band of lightness and collapses exactly the separation
they exist for: Busy against Alert fell from 7.0 to 3.3 CIEDE2000 under simulated deuteranopia
when it was tried. Change a foreground, not a fill.

The cost of that rule is exact and worth writing down, because PRODUCT.md commits to AAA
wherever it is reachable and on **half the state badges it is not reachable at all**. With the
fill frozen, the best any foreground can do is pure black or pure white on it:

| badge | foreground | ratio | best possible | AAA |
|---|---|---|---|---|
| light Idle | `#0f1319` | 7.34 | 8.27 (black) | yes |
| light Ok | `#00250f` | 5.01 | **6.37** (black) | unreachable |
| light Busy | `#150e00` | 6.02 | **6.59** (black) | unreachable |
| light Alert | `#280505` | 5.01 | **5.58** (black) | unreachable |
| dark Idle | `#ffffff` | 4.83 | **4.83** (white) | unreachable |
| dark Ok | `#032010` | 7.57 | 9.22 (black) | yes |
| dark Busy | `#1c1300` | 8.56 | 9.78 (black) | yes |
| dark Alert | `#150303` | 7.26 | 7.59 (black) | yes |

Four of the eight can never reach 7:1 without moving a fill, and moving a fill is the one thing
this rule forbids. All eight clear AA. Dark Ok (from 6.54) and dark Alert (from 5.84) were the
two where AAA was reachable and unclaimed, and they have since been taken there. Do not "fix" the
other four; the arithmetic, not the effort, is what stops them.

> **Open direction.** PRODUCT.md records dark-adaptation preservation as a confirmed but unbuilt
> requirement. Dark mode is not night vision, and this palette does not yet answer it. A future
> red or luminance-ceiling mode is a third scheme, not an adjustment to these two.

## Typography

**Display Font:** Geist Mono (with `ui-monospace`, `monospace`)
**Body Font:** Geist Mono (with `ui-monospace`, `monospace`) - the interface has no proportional face
**Label/Mono Font:** JetBrains Mono (with `monospace`), for readouts and log output

**Character:** The entire interface is monospace, which is the loudest thing about it. It reads
as instrumentation rather than as an application, and it means a column of numbers aligns
without anyone asking it to. The two stacks divide by intent: the general UI stack carries
labels, titles and prose, while the readout stack carries values that are compared against each
other - telemetry, log lines, the raw wire names behind the debug toggle.

> **Neither family is actually loaded.** There is no `@font-face`, no font package, and no CDN
> link anywhere in the repository, so both stacks fall through to their fallbacks today: the UI
> resolves to the platform's `ui-monospace` (SF Mono, Cascadia, or the system default) and the
> readouts to generic `monospace`. On most platforms those are two different faces for what the
> tokens describe as one system. Ship the fonts or change the tokens; do not leave the file
> claiming a typeface the page never receives.

> **Open decision.** The monospace UI is deliberate and stays. Whether the prose surfaces -
> empty-state copy, the configuration dialog's explanations - move to a proportional face is
> explicitly undecided. Do not resolve it silently in either direction.

### Hierarchy

- **Display** (600, `clamp(3rem, 10vw, 11rem)`, 0.9, tracking `-0.025em`): the wallboard's
  headline reading. One per screen. Sized in viewport units because the wallboard is read from
  across a room rather than from a desk.
- **Headline** (600, `clamp(2.5rem, 6vw, 6.5rem)`, 1): the wallboard's secondary readings.
- **Title** (600, 0.875rem, 1): property card titles, rendered as level-3 headings. Small on
  purpose: it names a card in a grid of thirty, and shouting would defeat scanning.
- **Body** (400, 0.875rem, 1.25rem): the default. Almost everything.
- **Label** (500, 0.75rem, `+0.025em`, uppercase): group headings, the debug detail line, the
  driver-internals disclosure, the wallboard's field captions.
- **Reading** (400, 0.875rem, tabular figures): every numeric or wire-derived value.

### Named Rules

**The Tabular Rule.** Any number that updates while the operator is looking at it is set in
tabular figures. Telemetry arrives continuously, and proportional digits make a stable reading
appear to twitch, which reads as instability in the instrument rather than in the font.

**The Label Is Not The Name Rule.** Human-facing text always comes from the display label
helper, never from the raw INDI name. Wire names appear in exactly one place, the debug detail
line under a card title, and only when the operator has asked for them. The wire truth is
available; it is not the default reading.

## Layout

The shell is pinned to the viewport (`h-svh`) rather than allowed to grow: the sidebar owns
device selection on the left, the property area scrolls in its own region, and the message
strip stays docked below it. An operator should never lose the log by scrolling.

The property grid is one column, widening to two and then three. Those breaks are **container
queries, not viewport queries** (`@xl` at 36rem, `@4xl` at 56rem), measured against the panel's
own width. Docked siblings shrink that width, so a viewport query would promise a third column
the panel does not have room for.

Density is deliberate and tight. The spacing scale runs 6px inside a field, 8px between fields,
12px between cards and between a group heading and its grid, 16px of card padding and shell
padding, and 24px between property groups. The header bar is 56px, the sidebar 16rem on desktop
and 18rem in its mobile drawer, collapsing to a 3rem icon rail.

The sidebar becomes an off-canvas drawer below 768px, and every fixed edge grows by its safe-area
inset so the header clears a notch and the message strip clears a home indicator. Mobile is a
supported operating console here, not a courtesy breakpoint.

The wallboard is a distinct spatial mode rather than a page. Above `lg` it fills the viewport
exactly, never scrolls, and sizes everything in `vh` and `vw` so one screen holds one glance
from four metres away. Below `lg` it abandons that entirely and reflows to a scrolling column,
because a phone is not a wallboard and clipping a reading is worse than scrolling to it.

### Named Rules

**The Container Query Rule.** Column counts are measured from the container, never the viewport.
Any component that can sit beside a docked panel counts its own width.

**The Heading Chain Rule.** The outline is shell `h1`, group `h2`, card title `h3`, with no step
skipped. A property that carries no group still emits a visually hidden `h2`, because dropping
it would step `h1` straight to `h3` and break the outline that is the only fast way to navigate
thirty cards without a mouse.

## Elevation & Depth

**This is not adjudicated, and the file says so rather than inventing a doctrine.** The shadow
scale arrived with the shadcn theme preset and nobody has since decided what it is for. What is
observable: the shadows are effectively invisible - light mode tops out at 5% black through most
of the scale and reaches only 13% at `2xl` - while every element receives a hairline border from
the base layer and the palette carries four distinct surface tones. In practice the separation
you see between a card and the page is the border and the tone, not the shadow.

Two readings of that are available and neither has been chosen: the system is flat and the
shadows are vestigial, or the shadows are a deliberate sub-threshold lift. Record which, when
someone decides. Until then, treat the values below as observed rather than prescriptive, and do
not cite this section as authority for adding or removing depth.

### Shadow Vocabulary (as observed)

- **`2xs` / `xs`** (`0px 1px 4px 0px rgb(0 0 0 / 0.03)`): the input and outline-button lift.
- **`sm` / base** (`0px 1px 4px 0px rgb(0 0 0 / 0.05), 0px 1px 2px -1px rgb(0 0 0 / 0.05)`):
  every card.
- **`md` / `lg` / `xl`**: the same first layer with a progressively larger second one.
- **`2xl`** (`0px 1px 4px 0px rgb(0 0 0 / 0.13)`): the only step that is visible at all.
- Dark mode runs the same scale at roughly double the alpha (0.04 to 0.20), which on a near-black
  background is even less perceptible than its light counterpart.

## Shapes

A single 12px radius seeds the scale, and everything else is derived from it: 8px small, 10px
medium, 12px large, 16px extra-large. The system uses three of those in practice.

Cards are the softest thing on screen at 16px. Controls - buttons, inputs, toggles - all sit at
10px, so every interactive element shares one corner. Badges and status dots are fully round.

Switch members are the deliberate exception: each toggle drops its radius to zero and loses its
left border, and the group restores the outer corners at the two ends. The result is one
segmented control out of individually pressable buttons, which is the honest shape for a control
where each member is independently pressed and focus alone changes nothing.

Borders do the work elsewhere: a 1px hairline is the default edge on every element, and the
sidebar, header, message strip and driver-internals disclosure are all separated by a single
rule rather than by a gap or a shadow.

### Named Rules

**The Pill Means Readout Rule.** Fully round is reserved for things that report and cannot be
pressed - state badges, status dots, the unread count. Anything an operator can act on carries
the 10px control radius. Never round a control to a pill; it reads as a status.

## Components

### Buttons

- **Shape:** the shared control radius (10px), 36px tall at default and 32px at `sm`.
- **Primary:** Viridis Violet with white text, 8px by 16px of padding. Sparingly is an
  understatement, and it is worth naming where: **nothing on the panel's own surface is a
  primary button.** Every button an operator sees without opening something is secondary (the
  Set buttons, a pressed switch member), ghost or outline (the theme toggle, the sidebar
  trigger). The variant appears inside `DeviceConfigDialog` and nowhere else - "Save" is the
  modal's `primary` action, and the Load / Restore confirmations use it for their confirming
  button - which is the correct reading of it: violet marks *the* action of a surface an
  operator opened deliberately, and a screen of live instrument readings has no such action.
  Outside buttons, `--primary` reaches the panel as a fill on the checked Switch's track, and
  as text and the focus ring.
- **Secondary:** Signal Cyan. This is the action colour and it means "this does something to the
  instrument": the Set button, and the selected member of a switch vector.
- **Destructive:** Fault Red with white text. `ui/button.tsx` is registry-exact - it used to
  carry a hand-edit raising this variant's ring - and the correction now lives in `theme.css`
  instead, applying to both the shared ring and this variant's own. See The Registry Is
  Corrected In CSS rule below.
- **Ghost / Outline:** chrome only. The theme toggle, the sidebar trigger, secondary dialog
  actions. The light outline variant's hairline is still 1.24:1 and `CONCERNS.md` says why it
  was not fixed here.
- **Hover:** primary composites its fill toward the surface at 90%. Secondary does **not**:
  in light mode the registry's 80% hover took white-on-secondary from 5.05:1 to 3.38:1, below
  AA on the control that writes to the instrument, so the fill is held and the cursor and the
  focus ring are the affordance - exactly as on a selected switch member. Dark keeps its hover,
  which measures 5.71:1 at 80%.
- **Focus:** a 3px ring at **75%** of the ring colour, held **2px off the control**, plus a
  border shift from `focus-visible:border-ring`. **Focus is never conveyed by the ring alone or
  by the border alone**, and that is not incidental: the theme raises the ring by setting only
  custom properties - `--tw-ring-color`, `--tw-ring-offset-*` - precisely so it cannot disturb
  the border shift beside it. A rule that set `border-color` instead was measured, found to beat
  `focus-visible:border-ring`, and rejected. 75% clears 3:1 on every surface either ring lands
  on - violet 5.69 on white, 5.40 on the sidebar, 4.73 on a dark background, 3.55 on dark
  accent; destructive 3.49 on white and 3.27 on a dark card. The registry's own values do not:
  `/50` composites to 2.85 light and 2.75 dark, and the destructive `/20` and `/40` to 1.37 and
  1.72. 66% was measured too and rejected, at 3.01 light and 2.76 dark.

### Cards

- **Corner Style:** 16px.
- **Background:** card over background; in light mode both are white and the border is what
  separates them.
- **Shadow Strategy:** the base card shadow, which is at the edge of perception. See Elevation.
- **Border:** a 1px hairline, which is the actual separation.
- **Internal Padding:** 16px horizontal, 16px vertical, with a 12px gap between header and
  content. Tighter than the primitive's default, because a device can publish thirty of these.
- **Structure:** a property card is a labelled group whose accessible name is the title *and*
  the state badge together, so it arrives as "Exposure, Alert" rather than as a title with a
  coloured shape floating near it.

### Inputs / Fields

- **Style:** transparent fill in light mode, 1px Control Edge border, 10px radius, 36px tall,
  readout typeface with tabular figures.
- **Dark fill:** `bg-input/30`, and raising Control Edge moved it more than anything else in
  the theme: the fill goes `#171717` -> `#323232` and its hover `#1a1a1a` -> `#484848`. A dark
  input was a near-invisible lift and is now a field with discernible edges. Nothing regresses
  on it - foreground 7.12:1 on the fill, placeholder 5.91:1, foreground 5.08:1 on the hover -
  and the same change moves the dark outline Button, which shares the token.
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

- **Unselected:** transparent with the control border; hovers to muted.
- **Selected:** Signal Cyan with semibold weight, and it holds that appearance under the pointer.
  The stock outline toggle drew selection with the accent tone and hovered to the accent tone
  too, which made a hovered unselected member identical to the selected one.

### State Badge and Status Dot

The state-to-colour mapping lives in exactly one place - a `data-indi-state` attribute the theme
resolves to a pair of custom properties - so the badge, the dots, the wallboard bars and the
drawn figures cannot drift apart. Busy is the only state that animates, and it animates by
ringing outward rather than by fading, held still under `prefers-reduced-motion`.

The ring is an `outline` on an `::after`, scaling from 1 to 1.5 and fading from 0.6 to 0. **Its
first frame is visible**, which the earlier box-shadow version's was not: that one started at
spread 0, invisible, and grew. The ring now sits as a 2px line hugging the badge's outside edge
and expands from there, so a Busy badge reads as ringed even between pulses. An outline was
chosen over a border or a box-shadow because it paints entirely outside the pseudo-element's
box - which equals the badge's border box - so no animated pixel ever lands on the label,
whatever padding a consumer passes. Only `transform` and `opacity` animate, both composited.

### Message Log

A docked terminal tail: readout typeface at 0.75rem, newest at the bottom, following the tail as
entries arrive. Each entry stacks a timestamp and device name over the message body so wrapped
lines start at the margin rather than mid-row. The scrolling viewport is a polite, additions-only
live region and carries a tab stop, without which the history above the tail is unreachable by
keyboard.

### Named Rules

**The Never Colour Alone Rule.** Alert and Busy are 4.4 CIEDE2000 apart under deuteranopia, which
is not a reliable distinction. Every state is therefore written out in text as well as coloured:
the badge carries its own name, and the status dot is decorative and marked hidden because its
label sits beside it.

**The word has to be one a sighted reader can see.** The connection dots broke this rule for a
release by putting "connected" and "disconnected" in a visually hidden span - which serves a
screen reader and nobody else, while the only visible difference between a live panel and a dead
one was green against red, 1.08:1 apart under simulated deuteranopia. They now differ in shape
as well (a filled disc for connected, a hollow ring for offline) and the failing state is
written out on screen: "bridge offline", not a colour. The healthy state stays visually hidden,
because two permanent extra words in a 16rem sidebar for the state that is true almost always is
a cost paid every night for a reading nobody needs; the shape carries it, and only the alarm
takes space.

**The Ring Stands Off The Control Rule.** A focus ring is measured against **both** its
neighbours, not just the surface. The published ratios above are the ring against the surface
around the control; on a filled control the other neighbour is the control's own fill, and
because the ring is a tinted version of the same token the two sit on top of each other -
destructive 1.38:1 light and 1.32:1 dark, checked switch 2.05 light and 1.60 dark, primary
button 2.11 light. SC 2.4.13 asks 3:1 of an indicator against the colours it touches, and the
effect is plain beside an outline button: a violet ring on white is unmistakable while the
destructive ring has to be hunted for against its own red.

So every ring is offset 2px in the surface colour, which puts the surface on both sides of it and
leaves the fill separated by the control's own edge (12.03 primary light, 8.37 secondary dark,
4.83 destructive light). It costs nothing structurally - `--tw-ring-offset-width` and
`--tw-ring-offset-color` are custom properties, so the correction stays inside the rule below -
and Tailwind already grows the ring's spread by the offset, so the ring itself is still 3px.

**The destructive ring's offset is white rather than the surface**, and that is the one case the
surface could not carry. `dark:bg-destructive/60` composites to `#973030` on a near-black card,
2.48:1 from it, so a card-coloured gap is invisible against the fill and the ring reads as flush
again. White is the button's own text colour - the variant hardcodes `text-white` - which makes
the indicator two-tone, for the same reason a browser's default focus ring is: 7.55 white against
the fill, 5.74 ring against white, 3.27 ring against the card. In light mode white *is* the
surface, so one declaration serves both schemes and the rule needs no branch. Re-measure it if
`--destructive` or the dark surfaces move.

**The One Action Colour Rule.** Signal Cyan means "this acts on the instrument", and nothing else
may wear it. A selected switch member *is* the instrument's state, so mistaking it is a real
error rather than an aesthetic one; it therefore has to be a colour no unselected member can take
on, in any interaction state.

**The Confirmation Names The Consequence Rule.** A destructive confirmation names what it will do
- "Delete saved config" - and never says "OK". The button text is asserted by tests, because on
these controls the copy is the safety mechanism.

**The Registry Is Corrected In CSS, Not In Place Rule.** The shadcn primitives in
`web/packages/react/src/ui/` come from the CLI and stay registry-exact, so a `shadcn add` can
never silently revert an accessibility fix. Where the registry's contrast decisions are wrong,
they are overruled from `theme.css` by rules deliberately placed **outside every `@layer`**,
which outrank every layered rule regardless of specificity. Two constraints come with that and
neither is optional:

- **Hook the utility class, never `data-slot`.** `data-slot` does not survive `asChild` - the
  Slot merges the child's props over the parent's - so `<AlertDialogAction variant="destructive">`
  renders `data-slot="alert-dialog-action"` and a Tooltip-wrapped Button renders
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
behaviour: `scroll-area.tsx` spreads props onto the Root only, so nothing could give the
scrolling element a tab stop; and `sidebar.tsx`'s mobile drawer restored focus to a
`Dialog.Trigger` it does not have (dropping the keyboard on `<body>`), hid its own close button
with `[&>button]:hidden`, and mounted an invisible tooltip whose dismissable layer swallowed the
first Escape. No stylesheet can reach any of those. The test for the difference is simple: if a
rule in `theme.css` could fix it, it does not belong in `src/ui/`.

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

Not everything reaches 44px, and the exceptions are enumerated rather than hidden. Still at 32px:
the sidebar's device rows and the configuration dialog's trigger, the switch-vector members, the
Set button, and the configuration dialog's own action buttons. All are at least 24px, so SC 2.5.8
is met and only 2.5.5 is not. No registry `size` reaches 44px - `lg` is 40 - so closing this
means a new control size across the library, against a system that commits to density.

## Do's and Don'ts

### Do:

- **Do** re-measure a colour on every surface it appears over before changing it, and leave the
  measured ratio in a comment beside the value, as every existing token does.
- **Do** write every state out in text as well as colouring it, in text a sighted reader can
  see. A visually hidden word serves a screen reader and nobody who is merely colour-blind.
- **Do** use tabular figures for anything numeric that updates live.
- **Do** reach for a hairline border or one of the four surface tones when you need separation.
- **Do** count grid columns from the container's width, using container queries.
- **Do** keep the heading chain unbroken (h1 → h2 → h3), emitting a visually hidden heading rather
  than skipping a level.
- **Do** give every control the same 10px radius and the same 3px focus ring at 75% opacity,
  held 2px off the control so it never touches its own fill, and let the border shift beside it
  stand - focus is two signals, never one.
- **Do** correct a vendored primitive from `theme.css`, unlayered and hooked on the utility
  class it emits, rather than by editing `src/ui/`.
- **Do** grow fixed edges by their safe-area inset, and remember the underscore spacing Tailwind
  needs inside `calc()` around `env()`.
- **Do** keep the panel and the documentation on the same identity colours; they are one product
  and the values are shared deliberately.

### Don't:

- **Don't** adjust a `--state-*` fill to fix a contrast problem. Change the foreground.
- **Don't** introduce an accent that lands near Busy amber or Alert red under any simulated
  colour-vision deficiency, however good it looks in isolation.
- **Don't** animate by fading opacity on anything carrying text. Fading a badge to 0.5 measured
  1.75:1, and no fill colour survives it. Move the motion to a pseudo-element instead.
- **Don't** write an unlayered rule that sets a real property - `border-color`, `position`,
  `background-color` - without restating every state that property can be in, or narrowing the
  selector to something that cannot be in them. Custom properties are the safe case.
- **Don't** turn the switch control back into a radio group, or let an unselected member reach
  the selected member's colour on hover.
- **Don't** round a control to a pill or square off a badge; the two shapes carry the
  pressable/reportable distinction.
- **Don't** turn this into a data-visualisation dashboard. Wall-to-wall charts, sparklines on
  every reading and neon series colours on near-black are the confirmed anti-reference: INDI
  properties are mostly discrete state rather than time series, and drawing them as telemetry
  streams misrepresents what the instrument is saying.
- **Don't** cite the shadow scale as evidence of an elevation philosophy. It is inherited and
  undecided; see Elevation & Depth.
- **Don't** put colour in an architecture diagram. Those render on GitHub and the docs site in
  both schemes, and a hardcoded palette becomes unreadable in one of them.
