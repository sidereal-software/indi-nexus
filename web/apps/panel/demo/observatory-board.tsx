/**
 * The observatory board: one screen, two instruments, read from across a room.
 *
 * This is not a desktop dashboard. It is the screen bolted above the door of a
 * control room, and that changes almost every decision:
 *
 * - **It is read from four metres, not forty centimetres.** Type is sized in
 *   viewport units so the board fills whatever it is plugged into. MIL-STD-1472F
 *   §5.2.5.2.1 asks for a character height of at least 20 arcmin (10 arcmin as
 *   the floor) measured from the *longest* viewing distance, and about 30% more
 *   for coloured text than for monochrome. A web page cannot know its own
 *   physical size, so `clamp(...vw...)` is the approximation available, pushed
 *   toward the large end rather than the small one.
 * - **Nobody touches it.** No hover, no tooltips, no controls, with one
 *   exception: a light/dark toggle, because the board is read at 3am as well as
 *   at noon.
 * - **One screen or it does not exist**, above `lg`, where a wallboard actually
 *   lives. A phone is not a wallboard, so below that the same board reflows to
 *   one scrolling column rather than clipping half the readings away.
 * - **Stale data is dangerous.** A board quietly showing last hour's numbers is
 *   worse than a blank one, so a driver that is not connected, or whose source
 *   has stopped answering, blanks its readings and says so. Every reading gates
 *   itself on that, including the ones derived from two vectors: nothing here
 *   stays true only for as long as a driver sends its frames in lockstep.
 * - **The blank is one mark, and it is never announced.** `--` stands in for a
 *   reading everywhere on this board, and everywhere it is `aria-hidden`: it is
 *   a shape holding a reading's place, not a reading, and "dash dash" is not
 *   information - a screenful of them is not a screenful of it. Nothing is lost,
 *   because a dead board says what is missing in words anyway: "no data" under
 *   every tile, "Dome position unknown" and "Moon phase unknown" on the figures,
 *   "unknown" under the slit angle, and the header's own sentence. The figures
 *   need no such care - they are `role="img"`, so their innards are outside the
 *   accessibility tree already and their labels carry the whole reading.
 * - **Colour is never the message.** The theme's Alert and Busy are ΔE 4.4 apart
 *   under deuteranopia - indistinguishable across a room - which is
 *   `DESIGN.md`'s Never Colour Alone Rule and independently MIL-STD-1472F
 *   §5.4.6.8. Every state is spelled out in words at a size you can read from
 *   the door.
 *
 * The layout order is evidence too. Las Cumbres Observatory's live site board
 * leads with a column headed `OPEN?` - before the location, before a single
 * measurement - so the decision goes top-left and the shutter is the largest
 * text on the screen. The readings that argue for or against it come second, and
 * the almanac last.
 *
 * Built from `@indi-nexus/react`: hooks for the data, the shadcn primitives it
 * re-exports for the chrome, and the drawn figures in `board-visuals.tsx`.
 */

import {
  Button,
  displayLabel,
  type IPState,
  Separator,
  useLight,
  useNumber,
  useProperty,
  useSwitch,
  useText,
  type Vector,
} from "@indi-nexus/react";
import { Moon, Sun } from "lucide-react";
import { useRef } from "react";
import { useTheme } from "../src/use-theme";
import {
  bearingName,
  DaylightBar,
  DomePlan,
  MoonDisc,
  type ShutterPosition,
  WindCompass,
} from "./board-visuals";

const DOME = "Dome Simulator";
const WEATHER = "Open-Meteo";

/**
 * Wind speed at which the compass arrow reaches full length.
 *
 * Rubin's `WindDirection.jsx` scales its arrow against a configured maximum
 * rather than against whatever it has seen, so the figure means the same thing
 * on a calm night as on a bad one. This is the weather driver's own gust
 * ceiling - it raises an Alert above 35 - rounded up.
 */
const WIND_FULL_SCALE = 40;

/** Normalise an angle to the [0, 360) range. */
function range360(degrees: number): number {
  return ((degrees % 360) + 360) % 360;
}

/** The smaller of the two angles between two bearings, in [0, 180]. */
function angleBetween(a: number, b: number): number {
  return 180 - Math.abs(Math.abs(range360(a) - range360(b)) - 180);
}

/** The member a switch vector currently reports On, if any. */
function onMember(vector: Vector | undefined): string | undefined {
  if (vector?.kind !== "switch") return undefined;
  return vector.elements.find((element) => element.value === "On")?.name;
}

/**
 * The unit each reading is captioned with.
 *
 * These are the board's, and that is forced rather than preferred. An INDI
 * element's label belongs to its `def`; a `set` carries values, and the store
 * merges nothing else - `PropertyStore` and `client/store.py` both copy only the
 * value onto the cached definition. So the unit `examples/openmeteo_device.py`
 * folds into its labels *after* its first fetch is a server-side edit that never
 * reaches a browser, and reading the label here would render an empty unit for
 * ever.
 *
 * They are still not guessed: these are the units `weather-sim.ts` asks the API
 * for (`temperature_unit=fahrenheit`, `wind_speed_unit=mph`, and Open-Meteo's
 * own defaults for the rest). Change the request and change these with it.
 * `CONCERNS.md` carries the underlying gap and what closing it would look like.
 */
const UNITS: Record<string, string> = {
  TEMPERATURE: "°F",
  HUMIDITY: "%",
  WIND_SPEED: "mph",
  WIND_GUST: "mph",
  CLOUD_COVER: "%",
  PRESSURE: "hPa",
};

/** One reading: its value, its unit, and its status light. */
function useReading(element: string): { value?: number; unit: string; state: IPState } {
  const value = useNumber(WEATHER, "WEATHER_PARAMETERS", element);
  const state = useLight(WEATHER, "WEATHER_STATUS", element);
  return { value, unit: UNITS[element] ?? "", state: state ?? "Idle" };
}

/**
 * The labels of every reading currently in Alert - the "why" behind a hold.
 *
 * What the wire says, ungated, exactly as {@link useReading} reports a value and
 * its light ungated. Liveness is applied where each is drawn.
 */
function useAlerting(): string[] {
  const status = useProperty(WEATHER, "WEATHER_STATUS");
  if (status?.kind !== "light") return [];
  return (
    status.elements
      .filter((light) => light.value === "Alert")
      // `displayLabel`, never `label ?? name`. INDI's label is optional in
      // practice as well as in the schema, and libindi ships elements whose label
      // is the empty string - which `??` treats as present, so the alert line
      // would name the fault with nothing at all. See `web/CLAUDE.md`.
      .map((light) => displayLabel(light))
  );
}

/**
 * Follow a bearing continuously, so a rotation drawn from it takes the short way.
 *
 * `ABS_DOME_POSITION` wraps, and CSS does not know that: a dome reporting 359
 * and then 1 has moved two degrees, while `rotate(359deg)` to `rotate(1deg)`
 * sweeps 358 degrees backwards through every other bearing on the way. This adds
 * the shortest signed step to a running total instead, so the number handed to
 * the figure grows past 360 and the rotation is always the move the dome made.
 * Rubin's `DomeShutter.jsx` hit the same thing and solves it the same way.
 *
 * The ref is written during render, which is safe here precisely because the
 * update is idempotent: a second pass sees the bearing it has already recorded,
 * takes a zero step, and returns the same total. That is what keeps it correct
 * under `StrictMode`, which renders everything twice.
 */
function useContinuousBearing(bearing: number | undefined): number | undefined {
  const tracked = useRef<{ wrapped: number; continuous: number } | null>(null);

  if (bearing === undefined) {
    tracked.current = null;
    return undefined;
  }
  const previous = tracked.current;
  if (previous === null) {
    tracked.current = { wrapped: bearing, continuous: bearing };
    return bearing;
  }
  if (previous.wrapped === bearing) return previous.continuous;

  // Into (-180, 180]. The +540 keeps the operand positive, because JavaScript's
  // `%` follows the sign of its left-hand side.
  const step = ((bearing - previous.wrapped + 540) % 360) - 180;
  const continuous = previous.continuous + step;
  tracked.current = { wrapped: bearing, continuous };
  return continuous;
}

/**
 * What a slit-to-wind angle means, in the words operations uses.
 *
 * Rubin tells observers to seek targets around 90° off the dominant wind, so the
 * crosswind case is the good one and both ends are the ones worth naming.
 */
function windGeometry(offWind: number): string {
  if (offWind < 30) return "head on";
  if (offWind > 150) return "downwind";
  if (offWind >= 60 && offWind <= 120) return "crosswind";
  return "quartering";
}

/** The one control on the board: light or dark, because 3am is the normal case. */
function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    // SC 2.5.5 wants 44x44; `size-11` is the real box, not an overlay, so the
    // hover tint and the focus ring grow with it. twMerge drops the variant's
    // own `size-9`.
    <Button
      variant="ghost"
      size="icon"
      className="size-11 shrink-0"
      onClick={toggle}
      aria-label="Toggle theme"
    >
      {theme === "dark" ? <Sun /> : <Moon />}
    </Button>
  );
}

/**
 * One big reading: caption with its unit, the number, and its state as a word.
 *
 * No dial and no gauge, and that is measured rather than preferred: Stephen Few
 * tested radial gauges against bullet graphs and found them worse on speed *and*
 * accuracy - "A great deal of the space that is used by these gauges tells us
 * nothing whatsoever" - and LCO's own board shows seven big numbers and not one
 * gauge. Only bearings get a circle here, in `board-visuals.tsx`.
 *
 * The unit rides in the small-caps caption and never in the number, which is
 * LCO's arrangement too ("AIR TEMP °C" over "23.6"): the number is what is read
 * from four metres, and a unit glued to it costs half its width.
 */
function Tile({
  caption,
  value,
  unit,
  state,
  live,
}: {
  caption: string;
  value?: number;
  unit: string;
  state: IPState;
  live: boolean;
}) {
  const blank = !live || value === undefined;
  return (
    <div className="flex min-w-0 flex-col gap-1 lg:gap-[0.8vh]">
      <p className="truncate font-medium text-[clamp(0.68rem,1.05vw,1.15rem)] text-muted-foreground uppercase tracking-widest">
        {caption}
        {unit && <span className="ml-1.5 normal-case tracking-normal">{unit}</span>}
      </p>
      {/* A blank is not a reading, so it is not set in reading ink. `UNKNOWN` is
          a neutral third state on this board, never an alarm and never dressed
          up as data - LCO renders its `?` in the same weight as Y and N, and
          Rubin's LOVE gives `invalid` and `unknown` one shared grey. */}
      <p
        className={`font-semibold text-[clamp(2rem,9vw,3.5rem)] leading-none tabular-nums lg:text-[clamp(2rem,4.4vw,5rem)] ${
          blank ? "text-muted-foreground" : ""
        }`}
      >
        {blank ? <span aria-hidden>--</span> : value}
      </p>
      {/* The bar carries the status light and nothing else, which is one bit of
          information for a lot of ink, and it stays that way on purpose. ISA's
          High Performance HMI guidance asks for an analog representation of a
          measurement "relative to normal, abnormal, and alarm conditions", and
          LCO draws its limits on every chart - but the limits are not on the
          wire. `WEATHER_PARAMETERS` defines its elements with a format and no
          `min`/`max` (`examples/openmeteo_device.py`), the safe range lives in
          the driver's own READINGS table and reaches a browser only as the
          light in `WEATHER_STATUS`, and INDI's min/max would be the range a
          client may *write* in any case, which is not a safe range and is
          meaningless on a read-only vector. Inventing one here would put a
          number no instrument published behind a safety readout, which is worse
          than a plain bar. See `CONCERNS.md`. */}
      <div
        data-indi-state={live ? state : "Idle"}
        className="h-1 w-full rounded-full bg-[var(--indi-state)] lg:h-[0.7vh]"
      />
      {/* The state as a word: at four metres, and for a deuteranope at any
          distance, amber and red are the same colour. */}
      <p className="font-medium text-[clamp(0.65rem,0.95vw,1rem)] text-muted-foreground uppercase tracking-wider">
        {live ? state : "no data"}
      </p>
    </div>
  );
}

/** The observatory board: the dome and the weather station on one screen. */
export function ObservatoryBoard() {
  // -- the dome ------------------------------------------------------------- //
  // Every dome reading is gated on the driver's own CONNECTION. A disconnected
  // driver is not reporting the hardware, it is repeating the last thing it
  // heard, and a board that shows that as a position is the failure mode the
  // whole design is against.
  const domeLive = useSwitch(DOME, "CONNECTION", "CONNECT") === true;
  const rawAzimuth = useNumber(DOME, "ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION");
  const azimuth = domeLive ? rawAzimuth : undefined;
  const shutterVector = useProperty(DOME, "DOME_SHUTTER");
  const parkVector = useProperty(DOME, "DOME_PARK");

  /*
   * `UNKNOWN` is a first-class third state, neither omitted nor alarmed. LCO
   * renders `?` in the same weight as Y and N, Rubin's LOVE gives `invalid` and
   * `unknown` one shared grey style, and MaxIm DL prints "unknown" for a dome
   * without altitude. It is not hypothetical here either: aborting a shutter
   * move puts `DOME_SHUTTER` into Alert with the message "Shutter operation
   * aborted. Status: unknown." - at that moment the switch still reports the
   * position that was *commanded*, and repeating it would be the board making
   * something up.
   */
  const shutterState: IPState = domeLive ? (shutterVector?.state ?? "Idle") : "Idle";
  const shutter: ShutterPosition =
    !domeLive || shutterVector === undefined || shutterVector.state === "Alert"
      ? "unknown"
      : onMember(shutterVector) === "SHUTTER_OPEN"
        ? "open"
        : onMember(shutterVector) === "SHUTTER_CLOSE"
          ? "closed"
          : "unknown";

  const parked = onMember(parkVector);
  const parking = parkVector?.state === "Busy";
  const park =
    !domeLive || parkVector === undefined || parkVector.state === "Alert"
      ? "UNKNOWN"
      : parked === "PARK"
        ? parking
          ? "PARKING"
          : "PARKED"
        : parked === "UNPARK"
          ? parking
            ? "UNPARKING"
            : "UNPARKED"
          : "UNKNOWN";

  // -- the weather station -------------------------------------------------- //
  const conditions = useText(WEATHER, "SKY", "CONDITIONS");
  const daylight = useText(WEATHER, "SKY", "DAYLIGHT");
  const sunrise = useText(WEATHER, "ALMANAC", "SUNRISE");
  const sunset = useText(WEATHER, "ALMANAC", "SUNSET");
  const moon = useText(WEATHER, "ALMANAC", "MOON_PHASE");

  const temperature = useReading("TEMPERATURE");
  const humidity = useReading("HUMIDITY");
  const wind = useReading("WIND_SPEED");
  const gust = useReading("WIND_GUST");
  const cloud = useReading("CLOUD_COVER");
  const pressure = useReading("PRESSURE");
  const windFrom = useNumber(WEATHER, "WEATHER_PARAMETERS", "WIND_DIRECTION");

  const parameters = useProperty(WEATHER, "WEATHER_PARAMETERS");
  // The driver parks its readings at Idle when the source stops answering, so
  // "not Idle" is the honest test for "these numbers mean something now".
  const live = parameters !== undefined && parameters.state !== "Idle";
  const alerting = useAlerting();

  // -- derived -------------------------------------------------------------- //
  /*
   * One derived sentence, not a fused dial. Nothing in the field fuses dome
   * azimuth and wind bearing into a single instrument - not MaxIm DL, TheSkyX,
   * ACP, KStars/Ekos or Rubin - and the reason shows the moment you try: the two
   * angles are independent, so a combined dial has to be read twice anyway.
   * Rubin's precedent is to compute the derived quantity and label what it
   * means, which is what this is. The compass stays a separate figure, exactly
   * as Rubin keeps it.
   */
  const offWind =
    azimuth !== undefined && live && windFrom !== undefined
      ? Math.round(angleBetween(azimuth, windFrom))
      : undefined;

  const displayBearing = useContinuousBearing(azimuth);
  const phase = moon?.match(/\(([\d.]+)\)/)?.[1];

  return (
    // A wallboard is one screen with no scrolling - but a phone is not a
    // wallboard, and clipping the readings off the bottom of one is worse than
    // scrolling. Below `lg` the board becomes a tall single column that scrolls;
    // from `lg` up it locks to the viewport and behaves as designed.
    <div className="flex min-h-dvh w-full flex-col gap-5 bg-background p-4 sm:p-6 lg:h-dvh lg:min-h-0 lg:gap-[1.8vh] lg:overflow-hidden lg:p-[2.5vh]">
      {/* The decision, top-left, before any reading - LCO leads with `OPEN?`
          ahead of the site name and every measurement. Baselines align at the
          bottom, which is also what keeps the identity block clear of the
          demo's own floating view switcher: from `lg` up the board is one
          locked screen that cannot scroll, so the switcher's 46px pill stays
          where it starts - ending 58px down - and the block hangs below the
          state word's cap height, far under it. That argument was worth
          nothing while the page scrolled underneath it, which is why below
          `lg` the demo now puts the switcher in normal flow above the board
          instead of over it - see `main.tsx`. The padding here is the board's
          own again, top and bottom alike; a real board has no switcher to
          reserve room for. */}
      <header className="flex shrink-0 flex-wrap items-end justify-between gap-x-8 gap-y-3 lg:flex-nowrap">
        {/* `shrink-0`: the state word is one unbreakable token, so a flex item
            allowed to shrink under it would overflow into the block beside it.
            That block truncates instead, which is the right order of sacrifice
            on a board whose whole point is the word. */}
        <h1 className="flex shrink-0 flex-col gap-1 lg:gap-[0.6vh]">
          <span className="font-medium text-[clamp(0.68rem,1.05vw,1.15rem)] text-muted-foreground uppercase tracking-widest">
            Shutter
          </span>
          <span className="font-semibold text-[clamp(2.75rem,13vw,5rem)] leading-[0.9] tracking-tight lg:text-[clamp(3rem,8.5vw,10rem)]">
            {shutter.toUpperCase()}
          </span>
        </h1>
        {/* Below `lg` the header wraps and this block gets a row of its own, so
            it fills that row and reads from the left margin like everything
            under it. On the board proper it is the right-hand end of one rail. */}
        <div className="flex w-full min-w-0 items-center justify-between gap-3 lg:w-auto lg:justify-end">
          <div className="flex min-w-0 flex-col gap-1 lg:gap-[0.5vh] lg:text-right">
            <p className="truncate font-medium text-[clamp(0.68rem,1.05vw,1.15rem)] text-muted-foreground uppercase tracking-widest">
              {DOME} · {WEATHER}
            </p>
            {/* A sentence saying there is no answer has to differ in *shape*
                from a sentence reporting one, because at 3am a glance reads
                shape before it reads words and "Weather source is not
                answering" is the same size, weight and place as "Clear sky ·
                Day". It gets the mark this board already uses for a reading it
                does not have - the same `--` standing in every tile at that
                moment - rather than a colour or an alarm: a dead feed is not a
                fault in the instrument, and every real board treats it that
                way. `aria-hidden` as every `--` here is, the sentence beside it
                being what a screen reader gets instead; see the note at the
                top. */}
            <p className="truncate text-[clamp(0.9rem,1.6vw,1.75rem)]">
              {live ? (
                <>
                  {conditions || <span aria-hidden>--</span>}
                  <span className="text-muted-foreground">
                    {" · "}
                    {daylight || <span aria-hidden>--</span>}
                  </span>
                </>
              ) : (
                <span className="text-muted-foreground">
                  <span aria-hidden className="tabular-nums">
                    --
                  </span>{" "}
                  <span>Weather source is not answering</span>
                </span>
              )}
            </p>
            {/* `state-alert-ink`, not the Alert fill: the fill is tuned to be
                read *behind* its own foreground and measures 3.42:1 as small
                light-mode type. The ink is the same hue taken until it clears
                AAA on every surface a line of text can land on, and it is the
                only place DESIGN.md lets a status hue be set as type.

                Gated on `live` like every other reading, and it is the one
                that had to be argued for rather than falling out: the lights
                are a second vector, so a driver parking `WEATHER_PARAMETERS`
                without clearing `WEATHER_STATUS` in the same breath leaves this
                line naming a fault over a tile reading "-- / no data" - the
                board contradicting itself in one frame, and precisely the
                stale reading the design is against. Both real drivers do clear
                the lights in the same handler, which is why nobody has seen it,
                but "honest for as long as two frames arrive in lockstep" is not
                the rule the rest of this screen follows. */}
            {live && alerting.length > 0 && (
              <p className="truncate font-medium text-[clamp(0.75rem,1.2vw,1.3rem)] text-state-alert-ink uppercase tracking-wider">
                Alert: {alerting.join(" · ")}
              </p>
            )}
          </div>
          <ThemeToggle />
        </div>
      </header>

      <section className="flex min-h-0 flex-col gap-5 lg:flex-1 lg:flex-row lg:gap-[2.5vw]">
        <div className="flex min-h-0 min-w-0 flex-col items-center gap-3 lg:flex-[5] lg:gap-[1.5vh]">
          <h2 className="sr-only">Dome</h2>
          <div className="flex h-56 min-h-0 w-full items-center justify-center sm:h-72 lg:h-auto lg:flex-1">
            <DomePlan
              bearing={displayBearing}
              shutter={shutter}
              state={shutterState}
              label={
                azimuth === undefined
                  ? "Dome position unknown"
                  : `Dome at ${Math.round(range360(azimuth))} degrees, ${bearingName(azimuth)}, shutter ${shutter}`
              }
              className="size-full"
            />
          </div>
          <div className="flex w-full shrink-0 items-end justify-center gap-8 lg:gap-[3vw]">
            <div className="flex flex-col items-center gap-1 lg:gap-[0.5vh]">
              <p className="font-medium text-[clamp(0.68rem,1.05vw,1.15rem)] text-muted-foreground uppercase tracking-widest">
                Azimuth
              </p>
              <p
                className={`font-semibold text-[clamp(1.75rem,3.6vw,3.25rem)] leading-none tabular-nums ${
                  azimuth === undefined ? "text-muted-foreground" : ""
                }`}
              >
                {azimuth === undefined ? (
                  <span aria-hidden>--</span>
                ) : (
                  `${Math.round(range360(azimuth))}°`
                )}
                {azimuth !== undefined && (
                  <span className="ml-2 text-[0.5em] text-muted-foreground">
                    {bearingName(azimuth)}
                  </span>
                )}
              </p>
            </div>
            <div className="flex flex-col items-center gap-1 lg:gap-[0.5vh]">
              <p className="font-medium text-[clamp(0.68rem,1.05vw,1.15rem)] text-muted-foreground uppercase tracking-widest">
                Park
              </p>
              <p className="font-semibold text-[clamp(1.75rem,3.6vw,3.25rem)] leading-none">
                {park}
              </p>
            </div>
          </div>
        </div>

        <Separator orientation="vertical" className="hidden lg:block" />
        <Separator className="lg:hidden" />

        <div className="flex min-w-0 flex-col justify-center lg:flex-[6]">
          <h2 className="sr-only">Weather</h2>
          {/*
           * Six readings in reading order, split where the meaning splits.
           *
           * The driver judges all six against a safe range and lights each one
           * the same way, so nothing on the wire says which of them an operator
           * acts on - and drawn identically, six tiles are six things to read
           * before triage can even start. The wind is what a dome is pointed
           * away from and what shuts it (it is the quantity the slit angle
           * below is computed against), and gust is the same reading at its
           * worst. Cloud and humidity end the observing rather than threaten
           * the building. Temperature and pressure are context for both and are
           * never themselves the reason a shutter moves.
           *
           * So the order leads with wind and gust, and one hairline separates
           * the four readings that can stop the night from the two that only
           * explain them. A rule and an ordering, deliberately not a colour:
           * the tiles already carry four status hues and a fifth meaning
           * "important" would be read as a fifth state. Not a size or a weight
           * either - that promotes two readings over four instead of grouping
           * them - and the muted ink this board keeps for a *missing* reading
           * rules out dimming the context pair, which would say "no data" about
           * two live numbers.
           *
           * The row gap is tighter than it was because the rule spends a row of
           * its own: at `3vh` the six tiles plus the rule outgrew the section
           * on a 900px board and rode up over the header.
           */}
          <div className="grid grid-cols-2 gap-x-6 gap-y-5 lg:gap-x-[2.5vw] lg:gap-y-[2.2vh]">
            <Tile
              caption="Wind"
              value={wind.value}
              unit={wind.unit}
              state={wind.state}
              live={live}
            />
            <Tile
              caption="Gust"
              value={gust.value}
              unit={gust.unit}
              state={gust.state}
              live={live}
            />
            <Tile
              caption="Cloud"
              value={cloud.value}
              unit={cloud.unit}
              state={cloud.state}
              live={live}
            />
            <Tile
              caption="Humidity"
              value={humidity.value}
              unit={humidity.unit}
              state={humidity.state}
              live={live}
            />
            <Separator className="col-span-2" />
            <Tile
              caption="Temperature"
              value={temperature.value}
              unit={temperature.unit}
              state={temperature.state}
              live={live}
            />
            <Tile
              caption="Pressure"
              value={pressure.value}
              unit={pressure.unit}
              state={pressure.state}
              live={live}
            />
          </div>
        </div>
      </section>

      <Separator className="shrink-0" />

      {/* The almanac, the wind, and the one thing derived from both instruments. */}
      <footer className="flex shrink-0 flex-col gap-5 sm:flex-row sm:items-center sm:gap-8 lg:gap-[2.5vw]">
        <h2 className="sr-only">Almanac and wind</h2>
        <div className="flex shrink-0 items-center gap-3 lg:gap-[1vw]">
          <MoonDisc
            phase={phase === undefined ? undefined : Number(phase)}
            size={96}
            className="size-14 lg:size-[9vh]"
          />
          <p className="text-[clamp(0.7rem,1.05vw,1.15rem)] text-muted-foreground">
            {/* The driver defines this text empty and fills it on the first
                fetch, so an empty string is "not yet" and needs the placeholder
                as much as `undefined` does. */}
            {moon ? moon.replace(/\s*\([\d.]+\)/, "") : <span aria-hidden>--</span>}
          </p>
        </div>

        {/* Sized against the tiles, not against the space left over. Wind and
            gust are the readings that close a dome, and at `16vh` this figure
            printed the smallest number on a board whose whole argument is that
            what matters is the big one: 26px against the tiles' 63px at
            1440x900. At `26vh` it prints 46px, and it is the ceiling rather
            than a preference - the figure would have to be about 400px, the
            size of the dome, before a four-character speed centred in it could
            match a tile, and see `board-visuals.tsx` for why the arrow cannot
            give up any more room than it already has.

            It still does not rival the dome plan, which is the centrepiece by
            design and draws half again the compass's diameter (259px against
            184 at that size). */}
        <WindCompass
          direction={live ? windFrom : undefined}
          speed={live ? wind.value : undefined}
          gust={live ? gust.value : undefined}
          maxSpeed={WIND_FULL_SCALE}
          unit={wind.unit}
          state={wind.state}
          size="size-40 shrink-0 lg:size-[26vh]"
        />

        <div className="flex min-w-0 flex-1 flex-col gap-1 lg:gap-[0.6vh]">
          <p className="font-medium text-[clamp(0.68rem,1.05vw,1.15rem)] text-muted-foreground uppercase tracking-widest">
            Daylight
          </p>
          <DaylightBar sunrise={sunrise} sunset={sunset} />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-1 lg:gap-[0.6vh]">
          <p className="font-semibold text-[clamp(1.1rem,2.1vw,2.4rem)] leading-tight uppercase">
            Slit{" "}
            <span className="tabular-nums">
              {offWind === undefined ? <span aria-hidden>--</span> : `${offWind}°`}
            </span>{" "}
            off the wind
          </p>
          <p className="font-medium text-[clamp(0.65rem,0.95vw,1rem)] text-muted-foreground uppercase tracking-wider">
            {offWind === undefined ? "unknown" : windGeometry(offWind)}
          </p>
        </div>
      </footer>
    </div>
  );
}
