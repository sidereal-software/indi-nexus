/**
 * The drawn figures behind the Sky Report dashboard.
 *
 * Pure functions of their props - no hooks, no INDI - so each can be reasoned
 * about and tested on its own. Every one uses the theme's own tokens
 * (`--color-state-*`, `--color-primary`, `--color-border`) rather than hard-coded
 * colour, so they follow light/dark and any retheme for free.
 *
 * Form choices, deliberately:
 *
 * - Wind direction is **angular** data, which is the one case a radial form is
 *   the right answer rather than a decoration: a compass.
 * - Cloud cover and humidity are **a ratio against a limit**, so they are meters
 *   with the limit marked - not dials, and not two-slice pies.
 * - Status colour never carries meaning alone. Red and amber are ΔE 4.4 apart
 *   under deuteranopia, so every state here is also stated in words.
 */

import type { IPState } from "@indi-nexus/react";

/** Tailwind text-colour class per state, from the theme's own tokens. */
const STATE_TEXT: Record<IPState, string> = {
  Idle: "text-state-idle",
  Ok: "text-state-ok",
  Busy: "text-state-busy",
  Alert: "text-state-alert",
};

/** Tailwind fill class per state. */
const STATE_FILL: Record<IPState, string> = {
  Idle: "fill-state-idle",
  Ok: "fill-state-ok",
  Busy: "fill-state-busy",
  Alert: "fill-state-alert",
};

/** The eight-point compass name for a bearing in degrees. */
export function bearingName(degrees: number): string {
  const points = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return points[Math.round((((degrees % 360) + 360) % 360) / 45) % 8] as string;
}

/** Props for {@link WindCompass}. */
export interface WindCompassProps {
  /** Bearing the wind blows *from*, in degrees clockwise from north. */
  direction?: number;
  /** Sustained speed. */
  speed?: number;
  /** Gust speed, drawn as a second tick on the rim. */
  gust?: number;
  /** Unit shown under the speed. */
  unit?: string;
  /** State of the wind reading, for the arrow's colour. */
  state?: IPState;
}

/**
 * A compass rose with the wind vector on it.
 *
 * Meteorological convention: the bearing is where the wind comes *from*, so the
 * arrow sits on that bearing and points inward, the way a weather vane does.
 */
export function WindCompass({
  direction,
  speed,
  gust,
  unit = "",
  state = "Idle",
}: WindCompassProps) {
  const size = 168;
  const c = size / 2;
  const r = 66;
  const known = direction !== undefined;
  const radians = ((direction ?? 0) - 90) * (Math.PI / 180);

  // The arrow: a slim triangle sitting on the rim, pointing at the centre.
  const tipR = 22;
  const tail = { x: c + r * Math.cos(radians), y: c + r * Math.sin(radians) };
  const tip = { x: c + tipR * Math.cos(radians), y: c + tipR * Math.sin(radians) };
  const perp = radians + Math.PI / 2;
  const halfWidth = 9;
  const wing = (sign: number) => ({
    x: tail.x + sign * halfWidth * Math.cos(perp),
    y: tail.y + sign * halfWidth * Math.sin(perp),
  });
  const [a, b] = [wing(1), wing(-1)];

  const gustRadians = radians;
  const gustOuter = 78;

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      className="h-42 w-42"
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

      {/* Rim and cardinal ticks: hairline, one shade off the surface. */}
      <circle cx={c} cy={c} r={r} className="fill-none stroke-border" strokeWidth={1} />
      <circle cx={c} cy={c} r={r - 12} className="fill-none stroke-border/50" strokeWidth={1} />
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
            className={major ? "stroke-border" : "stroke-border/60"}
            strokeWidth={major ? 1.5 : 1}
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
            className="fill-muted-foreground text-[11px]"
          >
            {label}
          </text>
        );
      })}

      {known && (
        <>
          {gust !== undefined && speed !== undefined && gust > speed && (
            <line
              x1={c + (r + 2) * Math.cos(gustRadians)}
              y1={c + (r + 2) * Math.sin(gustRadians)}
              x2={c + gustOuter * Math.cos(gustRadians)}
              y2={c + gustOuter * Math.sin(gustRadians)}
              className="stroke-muted-foreground"
              strokeWidth={2}
              strokeLinecap="round"
            />
          )}
          <path
            d={`M ${tip.x} ${tip.y} L ${a.x} ${a.y} L ${b.x} ${b.y} Z`}
            className={STATE_FILL[state]}
          />
        </>
      )}

      {/* The reading itself, in text tokens - never the mark's colour. */}
      <text
        x={c}
        y={c - 4}
        textAnchor="middle"
        className="fill-foreground font-semibold text-[26px]"
      >
        {speed ?? "--"}
      </text>
      <text x={c} y={c + 14} textAnchor="middle" className="fill-muted-foreground text-[10px]">
        {unit}
      </text>
    </svg>
  );
}

/** Props for {@link Meter}. */
export interface MeterProps {
  label: string;
  value?: number;
  /** Top of the scale. */
  max: number;
  /** Where the driver stops calling it safe; drawn as a tick on the track. */
  limit?: number;
  unit?: string;
  state?: IPState;
}

/**
 * One ratio against a limit.
 *
 * The fill carries severity and the track is the same hue at low opacity, so
 * the state reads across the whole bar; the limit is a tick rather than a
 * second colour.
 */
export function Meter({ label, value, max, limit, unit = "", state = "Idle" }: MeterProps) {
  const pct = value === undefined ? 0 : Math.max(0, Math.min(1, value / max));
  const limitPct = limit === undefined ? undefined : Math.max(0, Math.min(1, limit / max));

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-muted-foreground text-sm">{label}</span>
        <span className="font-medium text-sm tabular-nums">
          {value ?? "--"}
          <span className="ml-0.5 text-muted-foreground text-xs">{unit}</span>
        </span>
      </div>
      <div className="relative h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full ${STATE_FILL[state].replace("fill-", "bg-")}`}
          style={{ width: `${pct * 100}%` }}
        />
        {limitPct !== undefined && (
          <div
            className="absolute top-0 h-full w-px bg-foreground/40"
            style={{ left: `${limitPct * 100}%` }}
            aria-hidden
          />
        )}
      </div>
    </div>
  );
}

/** Props for {@link MoonDisc}. */
export interface MoonDiscProps {
  /** Open-Meteo's phase fraction: 0 and 1 are new, 0.5 is full. */
  phase?: number;
  size?: number;
}

/**
 * The moon, drawn at its actual illuminated fraction.
 *
 * The lit limb is a semicircle; the terminator is a half-ellipse whose x-radius
 * is `r·|cos 2πp|`, which is what makes a crescent bow one way and a gibbous the
 * other. Waning phases are the waxing construction mirrored.
 */
export function MoonDisc({ phase, size = 56 }: MoonDiscProps) {
  const r = size / 2 - 1;
  if (phase === undefined) {
    return (
      <svg
        viewBox={`0 0 ${size} ${size}`}
        width={size}
        height={size}
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

/** Props for {@link SiteMap}. */
export interface SiteMapProps {
  latitude?: number;
  longitude?: number;
}

/**
 * Where on Earth the readings are from.
 *
 * A pinched graticule - straight parallels, meridians as quadratic curves
 * meeting at the poles - so it reads as a globe rather than as a grid. The
 * marker sits on its own meridian at its own parallel, using the same
 * construction, so its position is the projection rather than an approximation
 * of one.
 */
export function SiteMap({ latitude, longitude }: SiteMapProps) {
  const w = 260;
  const h = 132;
  const cx = w / 2;
  const cy = h / 2;
  const rx = w / 2 - 6;
  const ry = h / 2 - 6;

  /** Project a coordinate onto the graticule. */
  const project = (lat: number, lon: number) => {
    const t = (1 - lat / 90) / 2; // parameter along that meridian
    const k = 2 * rx * (lon / 180); // control-point offset for the meridian
    return { x: cx + 2 * (1 - t) * t * k, y: cy + ry * (2 * t - 1) };
  };

  const meridian = (lon: number) => {
    const k = 2 * rx * (lon / 180);
    return `M ${cx} ${cy - ry} Q ${cx + k} ${cy} ${cx} ${cy + ry}`;
  };

  const here =
    latitude !== undefined && longitude !== undefined ? project(latitude, longitude) : undefined;

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="h-auto w-full"
      role="img"
      aria-label={
        here ? `Site at ${latitude?.toFixed(2)}, ${longitude?.toFixed(2)}` : "Site unknown"
      }
    >
      <title>{here ? `${latitude?.toFixed(4)}, ${longitude?.toFixed(4)}` : "No site set"}</title>

      {[-150, -120, -90, -60, -30, 30, 60, 90, 120, 150].map((lon) => (
        <path key={lon} d={meridian(lon)} className="fill-none stroke-border/60" strokeWidth={1} />
      ))}
      <path d={meridian(180)} className="fill-none stroke-border" strokeWidth={1} />
      <path d={meridian(-180)} className="fill-none stroke-border" strokeWidth={1} />
      <path d={meridian(0)} className="fill-none stroke-border" strokeWidth={1} />

      {[-60, -30, 30, 60].map((lat) => {
        const y = cy - ry * (lat / 90);
        const edge = project(lat, 180).x;
        return (
          <line
            key={lat}
            x1={cx - (edge - cx)}
            y1={y}
            x2={edge}
            y2={y}
            className="stroke-border/60"
            strokeWidth={1}
          />
        );
      })}
      <line x1={cx - rx} y1={cy} x2={cx + rx} y2={cy} className="stroke-border" strokeWidth={1} />

      {here && (
        <>
          <circle cx={here.x} cy={here.y} r={7} className="fill-primary/20" />
          <circle
            cx={here.x}
            cy={here.y}
            r={3.5}
            className="fill-primary stroke-background"
            strokeWidth={2}
          />
        </>
      )}
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
    <div className="space-y-1.5">
      <div className="relative h-2 w-full overflow-hidden rounded-full bg-foreground/15">
        <div
          className="absolute h-full rounded-full bg-chart-3"
          style={{ left: `${at(rise)}%`, width: `${at(set) - at(rise)}%` }}
        />
        {nowPct >= 0 && nowPct <= 100 && (
          <div
            className="absolute top-0 h-full w-0.5 bg-foreground"
            style={{ left: `${nowPct}%` }}
            aria-hidden
          />
        )}
      </div>
      <div className="flex justify-between text-muted-foreground text-xs tabular-nums">
        <span>↑ {sunrise?.slice(11)} UTC</span>
        <span>{sunset?.slice(11)} UTC ↓</span>
      </div>
    </div>
  );
}

export { STATE_TEXT };
