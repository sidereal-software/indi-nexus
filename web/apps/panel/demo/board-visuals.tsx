/**
 * The drawn figures behind the observatory board.
 *
 * Pure functions of their props - no hooks, no INDI - so each can be reasoned
 * about and tested on its own. Every one uses the theme's own tokens
 * (`--color-state-*`, `--color-chart-3`, `--color-border`) rather than hard-coded
 * colour, so they follow light/dark and any retheme for free.
 *
 * Form choices, deliberately:
 *
 * - **A bearing is the one thing that gets a circle.** Dome azimuth and wind
 *   direction are angular, so a plan view and a compass are the honest forms.
 *   Nothing else here is radial: Stephen Few tested radial gauges against bullet
 *   graphs and found them worse on both speed and accuracy ("A great deal of the
 *   space that is used by these gauges tells us nothing whatsoever"), and Las
 *   Cumbres Observatory's own live board shows seven big numbers and not one
 *   gauge. Temperature, humidity, wind speed, cloud and pressure are numbers on
 *   the board, not dials here.
 * - **No ambient animation.** ISA/PAS High Performance HMI: "No animation except
 *   for specific alarm-related graphic behavior", naming spinning pumps and
 *   animated flames as noise. The one thing that moves is {@link DomePlan}'s
 *   aperture, and only while the dome is actually turning - that is the datum,
 *   not decoration - and it holds still under `prefers-reduced-motion`.
 * - **Status colour never carries meaning alone.** Red and amber are ΔE 4.4
 *   apart under deuteranopia, so every state these figures colour is also
 *   written out beside them, and each figure separates its states by *shape*
 *   (a gap in the wall, a dashed rim) as well as by hue.
 */

import type { IPState } from "@indikit/react";

/** The eight-point compass name for a bearing in degrees. */
export function bearingName(degrees: number): string {
  const points = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return points[Math.round((((degrees % 360) + 360) % 360) / 45) % 8] as string;
}

/** What is known about the shutter, in the board's own three words. */
export type ShutterPosition = "open" | "closed" | "unknown";

/** Props for {@link DomePlan}. */
export interface DomePlanProps {
  /**
   * Where the slit points, in degrees clockwise from north.
   *
   * Deliberately **not** normalised to [0, 360): the caller tracks the bearing
   * continuously so the CSS rotation takes the shortest arc, and a dome that has
   * gone the long way round several times legitimately arrives here at 1082.
   * `undefined` means the position is not known, which is drawn rather than
   * guessed.
   */
  bearing?: number;
  /** What the shutter is doing; a closed slit is drawn shut, not omitted. */
  shutter?: ShutterPosition;
  /** State of the shutter vector, for the aperture's colour. */
  state?: IPState;
  /** What the figure is, for a reader who cannot see it. */
  label: string;
  /** Tailwind sizing classes; a wallboard wants this very large. */
  className?: string;
}

const PLAN_SIZE = 200;
/** Centre of the plan, in drawing units. */
const PLAN_C = PLAN_SIZE / 2;
/** Radius of the dome wall. */
const WALL_R = 76;
/** Radius the cardinal letters sit at. */
const LETTER_R = 91;
/** Half the angular width of the slit, in degrees. */
const SLIT_HALF = 23;

/** A point on the plan's rim, measured clockwise from north. */
function onRim(degrees: number, radius: number): { x: number; y: number } {
  const radians = degrees * (Math.PI / 180);
  return {
    x: PLAN_C + radius * Math.sin(radians),
    y: PLAN_C - radius * Math.cos(radians),
  };
}

/**
 * The dome from above, with the aperture cut out of the wall.
 *
 * A plan view is the established idiom for this - MaxIm DL draws the dome "as
 * seen from above", and Rubin Observatory's LOVE control interface draws the
 * same figure in `DomeShutter.jsx` - so an observer already knows how to read
 * it. Three details are copied from Rubin's implementation:
 *
 * - the aperture rotates with `ABS_DOME_POSITION` rather than the rim rotating
 *   under a fixed slit, so north stays where north is;
 * - **the rotation takes the shortest angle.** A move from 359° to 1° is two
 *   degrees, and a naive `rotate()` swings 358° backwards through every other
 *   bearing on the way. The caller hands in a continuously tracked bearing for
 *   exactly this reason (see `bearing`);
 * - a *commanded* azimuth would be drawn behind the current one as a dashed
 *   ghost at `strokeOpacity 0.3`. This board draws none, because the drivers it
 *   reads publish only where the dome **is** - `ABS_DOME_POSITION` carries the
 *   current bearing and the target lives inside the driver. Inventing a target
 *   from a slew's direction would be the board claiming knowledge no device gave
 *   it.
 *
 * The transition is one second of linear rotation, which is the dome simulator's
 * own tick: what you see is the dome turning at the rate it reports, and it
 * stops dead the moment the reports do.
 */
export function DomePlan({
  bearing,
  shutter = "unknown",
  state = "Idle",
  label,
  className,
}: DomePlanProps) {
  const known = bearing !== undefined;
  const left = onRim(-SLIT_HALF, WALL_R);
  const right = onRim(SLIT_HALF, WALL_R);
  const sweep = `A ${WALL_R} ${WALL_R} 0 0 1 ${right.x} ${right.y}`;
  const arc = `M ${left.x} ${left.y} ${sweep}`;
  const corridor = `M ${PLAN_C} ${PLAN_C} L ${left.x} ${left.y} ${sweep} Z`;

  return (
    <svg
      viewBox={`0 0 ${PLAN_SIZE} ${PLAN_SIZE}`}
      className={className}
      role="img"
      aria-label={label}
    >
      <title>{label}</title>

      {/* The floor, then the wall. An unknown bearing dashes the wall and draws
          no slit at all: there is nothing to point at, and a solid ring with the
          aperture quietly left at north would read as a dome facing north - so
          solid-against-dashed is what separates the two, and the wall has to be
          visible for that to mean anything. It is `muted-foreground` rather than
          `border` for exactly that reason: in dark mode `--border` and `--muted`
          are the same value, so a bordered wall around a muted floor disappears
          and takes the aperture's whole "gap in the wall" reading with it. */}
      <circle cx={PLAN_C} cy={PLAN_C} r={WALL_R} className="fill-muted" />
      <circle
        cx={PLAN_C}
        cy={PLAN_C}
        r={WALL_R}
        strokeWidth={4}
        strokeDasharray={known ? undefined : "6 7"}
        className="fill-none stroke-muted-foreground"
      />

      {known && (
        <g
          className="transition-transform duration-1000 ease-linear motion-reduce:transition-none"
          style={{ transform: `rotate(${bearing}deg)`, transformOrigin: `${PLAN_C}px ${PLAN_C}px` }}
        >
          {shutter === "open" && (
            // The corridor the instrument looks down. Colour is the reinforcement
            // here, never the message: the board writes the shutter state out in
            // words at the top of the screen, and the aperture is a gap in the
            // wall whether or not a reader can separate the four state hues.
            <path
              d={corridor}
              data-indi-state={state}
              className="fill-[var(--indi-state)]"
              opacity={0.22}
            />
          )}
          {/* Where the slit is, in three readings that differ by *shape* before
              they differ by colour: open is a thick band in the state hue over a
              wall that is otherwise unbroken, closed is a solid shutter panel in
              foreground ink, and unknown is the same span dashed - the wall's
              condition there is not something the driver has told us.

              `data-indi-state` therefore rides only on the open band. It is the
              hook `theme.css` maps to `--indi-state`, so it is a claim about
              what the mark is painted in, and a closed or unknown band drawn in
              foreground or muted ink would be publishing a state it then
              ignores - a DOM that contradicts the drawing, for the next thing
              that reads the attribute to get wrong. */}
          <path
            d={arc}
            data-indi-state={shutter === "open" ? state : undefined}
            strokeLinecap={shutter === "unknown" ? "butt" : "round"}
            strokeWidth={shutter === "closed" ? 7 : 11}
            strokeDasharray={shutter === "unknown" ? "7 6" : undefined}
            className={
              shutter === "open"
                ? "fill-none stroke-[var(--indi-state)]"
                : shutter === "closed"
                  ? "fill-none stroke-foreground"
                  : "fill-none stroke-muted-foreground"
            }
          />
        </g>
      )}

      {/* The rim is fixed: the letters name real bearings, so they cannot turn
          with the dome. */}
      {(["N", "E", "S", "W"] as const).map((point, index) => {
        const at = onRim(index * 90, LETTER_R);
        return (
          <text
            key={point}
            x={at.x}
            y={at.y}
            textAnchor="middle"
            dominantBaseline="central"
            className="fill-muted-foreground font-medium text-[15px]"
          >
            {point}
          </text>
        );
      })}
    </svg>
  );
}

/** Props for {@link WindCompass}. */
export interface WindCompassProps {
  /** Bearing the wind blows *from*, in degrees clockwise from north. */
  direction?: number;
  /** Sustained speed, which sets the arrow's length. */
  speed?: number;
  /** Gust speed, drawn as a second tick on the rim. */
  gust?: number;
  /** Speed at which the arrow reaches its full length. */
  maxSpeed?: number;
  /** Unit shown under the speed. */
  unit?: string;
  /** State of the wind reading, for the arrow's colour. */
  state?: IPState;
  /** Tailwind sizing classes; a wallboard wants a much larger dial. */
  size?: string;
}

const COMPASS_SIZE = 168;
/** Rim radius of the compass. */
const COMPASS_R = 66;
/** Drawing units for the speed, which is read from the same distance as a tile
 *  number on the board and is sized to match it rather than to fit politely. */
const SPEED_SIZE = 33;
/** Font size of the unit under it. */
const UNIT_SIZE = 13;
/**
 * Half the width of the widest speed this can print, in drawing units.
 *
 * Four characters ("18.5"), because every reading on this board is monospaced
 * and a monospace advance is 0.6 em. It is measured rather than eyeballed
 * because {@link ARROW_MAX} is derived from it.
 */
const SPEED_HALF_WIDTH = (SPEED_SIZE * 0.6 * 4) / 2;
/** How far the arrow reaches inward when the wind is calm - short, but visible
 *  from across a room, because a bearing with no arrow on it says nothing. */
const ARROW_MIN = 11;
/**
 * How far it reaches at {@link WindCompassProps.maxSpeed}.
 *
 * Derived, not chosen: the arrow rides in the annulus the speed does not
 * occupy, so it stops five units short of the widest reading the middle can
 * hold. Anything longer collides with the digits at exactly the wind that
 * matters - a bearing near east or west puts the shaft straight through them -
 * and an arrow whose tip disappears behind the number has stopped encoding
 * speed at the top of its range. Growing the reading therefore shortens the
 * arrow, which is the trade this figure makes deliberately: the number is what
 * a decision is taken on, and the arrow is a bearing with a magnitude on it.
 */
const ARROW_MAX = COMPASS_R - SPEED_HALF_WIDTH - 5;

/**
 * A compass rose with the wind vector on it.
 *
 * Meteorological convention: the bearing is where the wind comes *from*, so the
 * arrow sits on that bearing and points inward, the way a weather vane does.
 *
 * **The arrow's length is the speed**, scaled against `maxSpeed`, which is how
 * Rubin's LOVE draws it (`WindDirection.jsx` computes its arrow height as
 * `windSpeed / MAX_WIND_SPEED_MS * 100`). That makes one figure carry both
 * variables without a second element, and it costs nothing: the speed is also
 * printed in the middle and captioned with its unit, so the length is a second
 * encoding rather than the only one.
 *
 * **The printed speed is sized against the board's tile numbers, not against
 * the dial.** Wind and gust are the readings that argue for closing a dome, so
 * the one figure devoted to them cannot carry the smallest number on the
 * screen. That ranks the two things inside the rim - see {@link ARROW_MAX} for
 * the arithmetic and for what the arrow gives up in exchange - and it is why
 * the caller sizes this figure in `vh` rather than leaving it at a default.
 */
export function WindCompass({
  direction,
  speed,
  gust,
  maxSpeed = 40,
  unit = "",
  state = "Idle",
  size: sizeClass = "size-42",
}: WindCompassProps) {
  const c = COMPASS_SIZE / 2;
  const r = COMPASS_R;
  const known = direction !== undefined;
  const radians = ((direction ?? 0) - 90) * (Math.PI / 180);

  // The arrow: a triangle sitting on the rim and aimed at the centre - never
  // reaching it, see ARROW_MAX - as long as the wind is strong. A calm wind is
  // a stub rather than nothing, so the bearing is still readable at zero.
  const fraction = Math.min(1, Math.max(0, (speed ?? 0) / maxSpeed));
  const length = ARROW_MIN + fraction * (ARROW_MAX - ARROW_MIN);
  const tail = { x: c + r * Math.cos(radians), y: c + r * Math.sin(radians) };
  const tip = { x: c + (r - length) * Math.cos(radians), y: c + (r - length) * Math.sin(radians) };
  const perp = radians + Math.PI / 2;
  // Narrow the wings with the shaft, or a calm wind draws a squat wedge rather
  // than an arrow. A proportion rather than a capped constant, because the
  // length range is bounded either side and a fixed cap turned the calm end
  // into a hairline nobody could see from the door.
  const halfWidth = length * 0.3;
  const wing = (sign: number) => ({
    x: tail.x + sign * halfWidth * Math.cos(perp),
    y: tail.y + sign * halfWidth * Math.sin(perp),
  });
  const [a, b] = [wing(1), wing(-1)];

  const gustOuter = 78;

  return (
    <svg
      viewBox={`0 0 ${COMPASS_SIZE} ${COMPASS_SIZE}`}
      className={sizeClass}
      role="img"
      aria-label={
        known
          ? `Wind from ${Math.round(direction)} degrees, ${bearingName(direction)}, ${speed ?? "unknown"} ${unit}`
          : "Wind direction unknown"
      }
    >
      <title>
        {known ? `Wind from ${bearingName(direction)} (${Math.round(direction)}°)` : "No wind data"}
      </title>

      {/* Rim and cardinal ticks: one ink, separated by weight and by length
          rather than by tone. They were drawn in `border`, which is the
          decorative hairline token - 1.24:1 against the light background, and
          in dark mode `#222222` on a `#121113` page, which is not a line
          anybody reads from four metres. That was survivable while the dial was
          small enough to be a glyph; at the size the speed now demands, the rim
          *is* the thing the arrow is read against, so it takes the same ink the
          letters already wear and the hierarchy moves into the stroke. */}
      <circle cx={c} cy={c} r={r} className="fill-none stroke-muted-foreground" strokeWidth={2} />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => {
        const t = (deg - 90) * (Math.PI / 180);
        const major = deg % 90 === 0;
        const inner = major ? r - 9 : r - 5;
        return (
          <line
            key={deg}
            x1={c + inner * Math.cos(t)}
            y1={c + inner * Math.sin(t)}
            x2={c + r * Math.cos(t)}
            y2={c + r * Math.sin(t)}
            className="stroke-muted-foreground"
            strokeWidth={major ? 3 : 1.5}
          />
        );
      })}
      {(["N", "E", "S", "W"] as const).map((label, index) => {
        const t = (index * 90 - 90) * (Math.PI / 180);
        return (
          <text
            key={label}
            x={c + (r + 12) * Math.cos(t)}
            y={c + (r + 12) * Math.sin(t)}
            textAnchor="middle"
            dominantBaseline="central"
            className="fill-muted-foreground font-medium text-[13px]"
          >
            {label}
          </text>
        );
      })}

      {known && (
        <>
          {gust !== undefined && speed !== undefined && gust > speed && (
            <line
              x1={c + (r + 2) * Math.cos(radians)}
              y1={c + (r + 2) * Math.sin(radians)}
              x2={c + gustOuter * Math.cos(radians)}
              y2={c + gustOuter * Math.sin(radians)}
              className="stroke-muted-foreground"
              strokeWidth={2}
              strokeLinecap="round"
            />
          )}
          <path
            d={`M ${tip.x} ${tip.y} L ${a.x} ${a.y} L ${b.x} ${b.y} Z`}
            data-indi-state={state}
            className="fill-[var(--indi-state)]"
          />
        </>
      )}

      {/* The reading itself, in text tokens - never the mark's colour. The two
          baselines put the number and its unit either side of the centre, so
          the block is optically centred in the rim rather than the number
          alone, and the unit rides in the caption and never in the number, as
          it does on every tile. A blank is drawn in the muted ink the tiles use
          for the same thing: it is not a reading, so it is not in reading ink.

          `fontSize` rather than a `text-[...]` class, because the sizes are
          constants that ARROW_MAX is derived from, and Tailwind scans source
          text - a class built from an interpolated value compiles to nothing at
          all. */}
      <text
        x={c}
        y={c + 4}
        fontSize={SPEED_SIZE}
        textAnchor="middle"
        className={`font-semibold tabular-nums ${
          speed === undefined ? "fill-muted-foreground" : "fill-foreground"
        }`}
      >
        {speed ?? "--"}
      </text>
      <text
        x={c}
        y={c + 21}
        fontSize={UNIT_SIZE}
        textAnchor="middle"
        className="fill-muted-foreground"
      >
        {unit}
      </text>
    </svg>
  );
}

/** Props for {@link MoonDisc}. */
export interface MoonDiscProps {
  /** Open-Meteo's phase fraction: 0 and 1 are new, 0.5 is full. */
  phase?: number;
  /** Drawing units; also the rendered size unless `className` overrides it. */
  size?: number;
  /** Tailwind sizing classes, so the disc can grow with the breakpoint. */
  className?: string;
}

/**
 * The moon, drawn at its actual illuminated fraction.
 *
 * The lit limb is a semicircle; the terminator is a half-ellipse whose x-radius
 * is `r·|cos 2πp|`, which is what makes a crescent bow one way and a gibbous the
 * other. Waning phases are the waxing construction mirrored.
 */
export function MoonDisc({ phase, size = 56, className }: MoonDiscProps) {
  const r = size / 2 - 1;
  if (phase === undefined) {
    return (
      <svg
        viewBox={`0 0 ${size} ${size}`}
        width={size}
        height={size}
        className={className}
        role="img"
        aria-label="Moon phase unknown"
      >
        <title>Moon phase unknown</title>
        <circle cx={size / 2} cy={size / 2} r={r} className="fill-muted stroke-border" />
      </svg>
    );
  }

  const waning = phase > 0.5;
  const p = waning ? 1 - phase : phase;
  const cos = Math.cos(2 * Math.PI * p);
  const rx = Math.abs(r * cos);
  const sweep = cos > 0 ? 0 : 1;
  const illumination = Math.round(((1 - Math.cos(2 * Math.PI * phase)) / 2) * 100);

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label={`Moon ${illumination}% illuminated`}
    >
      <title>{`${illumination}% illuminated`}</title>
      <g transform={waning ? `translate(${size}, 0) scale(-1, 1)` : undefined}>
        {/* The unlit disc is the dark one; the lit limb is drawn over it in
            the theme's warm tone. Two things matter here: painting it the
            other way round makes a gibbous moon read as a crescent, and the
            unlit disc has to be a translucent ink rather than `foreground` -
            in dark mode `foreground` is light, which would erase the phase
            entirely. */}
        <circle cx={size / 2} cy={size / 2} r={r} className="fill-foreground/20" />
        <path
          d={
            `M ${size / 2} ${size / 2 - r} ` +
            `A ${r} ${r} 0 0 1 ${size / 2} ${size / 2 + r} ` +
            `A ${rx} ${r} 0 0 ${sweep} ${size / 2} ${size / 2 - r} Z`
          }
          className="fill-chart-3"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          className="fill-none stroke-border"
          strokeWidth={1}
        />
      </g>
    </svg>
  );
}

/** Props for {@link DaylightBar}. */
export interface DaylightBarProps {
  /** ISO timestamps, as the driver publishes them ("2026-08-03 13:06"). */
  sunrise?: string;
  sunset?: string;
  /** Overridable so a test does not depend on the wall clock. */
  now?: Date;
}

/**
 * The daylight window, with now on it.
 *
 * The window runs from an hour before sunrise to an hour after sunset, so the
 * band is always legible; the times are the driver's, in UTC, and are labelled
 * as such rather than silently localised.
 */
export function DaylightBar({ sunrise, sunset, now }: DaylightBarProps) {
  const parse = (value?: string) => {
    if (!value) return undefined;
    const stamp = Date.parse(`${value.replace(" ", "T")}Z`);
    return Number.isNaN(stamp) ? undefined : stamp;
  };
  const rise = parse(sunrise);
  const set = parse(sunset);
  if (rise === undefined || set === undefined || set <= rise) {
    return <div className="h-2 w-full rounded-full bg-muted" aria-hidden />;
  }

  const pad = (set - rise) * 0.12;
  const start = rise - pad;
  const end = set + pad;
  const at = (stamp: number) => ((stamp - start) / (end - start)) * 100;
  const current = (now ?? new Date()).getTime();
  const nowPct = at(current);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="relative h-[1.2vh] min-h-2 w-full overflow-hidden rounded-full bg-foreground/15">
        <div
          className="absolute h-full rounded-full bg-chart-3"
          style={{ left: `${at(rise)}%`, width: `${at(set) - at(rise)}%` }}
        />
        {nowPct >= 0 && nowPct <= 100 && (
          <div
            className="absolute top-0 h-full w-1 rounded-full bg-foreground"
            style={{ left: `${nowPct}%` }}
            aria-hidden
          />
        )}
      </div>
      <div className="flex justify-between text-[clamp(0.7rem,1vw,1.05rem)] text-muted-foreground tabular-nums">
        <span>↑ {sunrise?.slice(11)} UTC</span>
        <span>{sunset?.slice(11)} UTC ↓</span>
      </div>
    </div>
  );
}
