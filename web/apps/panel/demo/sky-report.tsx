/**
 * The custom UI from `docs/guides/tutorial-open-meteo.md`: a dome wallboard.
 *
 * This is not a desktop dashboard. It is the screen bolted above the door of a
 * control room, and that changes almost every decision:
 *
 * - **It is read from four metres, not forty centimetres.** Type is sized in
 *   viewport units so the board fills whatever it is plugged into, and the one
 *   thing that matters - can we open? - is the largest thing on it by a wide
 *   margin.
 * - **Nobody touches it.** No hover, no tooltips, no controls, no scrolling.
 *   Everything is on one screen or it does not exist.
 * - **Stale data is dangerous.** A wallboard quietly showing last hour's numbers
 *   is worse than a blank one, so when the driver loses its source the readings
 *   blank out and the board says so, rather than leaving numbers up.
 * - **Colour is never the message.** The theme's Alert and Busy are ΔE 14.6
 *   apart for a reader with full colour vision and 5.7 under protanopia -
 *   indistinguishable across a room. Every state is spelled out in words at a
 *   size you can read from the door.
 *
 * Built from `@indi-nexus/react`: hooks for the data, the shadcn primitives it
 * re-exports for the chrome, and the drawn figures in `sky-visuals.tsx`.
 */

import {
  type IPState,
  Separator,
  useLight,
  useNumber,
  useProperty,
  useText,
} from "@indi-nexus/react";
import { bearingName, DaylightBar, MoonDisc, SiteMap, WindCompass } from "./sky-visuals";

const DEVICE = "Open-Meteo";

/** Border/text colour per state, from the theme's own tokens. */
const STATE_BAR: Record<IPState, string> = {
  Idle: "bg-state-idle",
  Ok: "bg-state-ok",
  Busy: "bg-state-busy",
  Alert: "bg-state-alert",
};

/** Read one number and its status light together. */
function useReading(element: string): { value?: number; state: IPState } {
  const value = useNumber(DEVICE, "WEATHER_PARAMETERS", element);
  const state = useLight(DEVICE, "WEATHER_STATUS", element);
  return { value, state: state ?? "Idle" };
}

/** The labels of every reading currently in Alert - the "why" behind a hold. */
function useAlerting(): string[] {
  const status = useProperty(DEVICE, "WEATHER_STATUS");
  if (status?.kind !== "light") return [];
  return status.elements
    .filter((light) => light.value === "Alert")
    .map((light) => light.label ?? light.name);
}

/** One big reading: label, number, and its state as a word. */
function Tile({
  label,
  value,
  unit,
  state,
  live,
}: {
  label: string;
  value?: number;
  unit: string;
  state: IPState;
  live: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col justify-between gap-[1vh]">
      <p className="truncate font-medium text-[clamp(0.7rem,1.05vw,1.15rem)] text-muted-foreground uppercase tracking-widest">
        {label}
      </p>
      <p className="font-semibold text-[clamp(1.6rem,3.4vw,3.75rem)] leading-none">
        {live && value !== undefined ? value : "--"}
        <span className="ml-1 text-[0.4em] text-muted-foreground">{unit}</span>
      </p>
      <div className="space-y-[0.6vh]">
        <div className={`h-[0.7vh] w-full rounded-full ${STATE_BAR[live ? state : "Idle"]}`} />
        {/* The state as a word: at four metres, and for a protanope at any
            distance, amber and red are the same colour. */}
        <p className="font-medium text-[clamp(0.65rem,0.95vw,1rem)] text-muted-foreground uppercase tracking-wider">
          {live ? state : "no data"}
        </p>
      </div>
    </div>
  );
}

/** The dome wallboard for the Open-Meteo device. */
export function SkyReport() {
  const conditions = useText(DEVICE, "SKY", "CONDITIONS");
  const daylight = useText(DEVICE, "SKY", "DAYLIGHT");
  const sunrise = useText(DEVICE, "ALMANAC", "SUNRISE");
  const sunset = useText(DEVICE, "ALMANAC", "SUNSET");
  const moon = useText(DEVICE, "ALMANAC", "MOON_PHASE");
  const latitude = useNumber(DEVICE, "GEOGRAPHIC_COORD", "LAT");
  const longitude = useNumber(DEVICE, "GEOGRAPHIC_COORD", "LONG");

  const temperature = useReading("TEMPERATURE");
  const feelsLike = useNumber(DEVICE, "WEATHER_PARAMETERS", "FEELS_LIKE");
  const cloud = useReading("CLOUD_COVER");
  const humidity = useReading("HUMIDITY");
  const wind = useReading("WIND_SPEED");
  const gust = useReading("WIND_GUST");
  const pressure = useReading("PRESSURE");
  const direction = useNumber(DEVICE, "WEATHER_PARAMETERS", "WIND_DIRECTION");

  const parameters = useProperty(DEVICE, "WEATHER_PARAMETERS");
  const overall: IPState = useProperty(DEVICE, "WEATHER_STATUS")?.state ?? "Idle";
  // The driver parks its readings at Idle when the source stops answering, so
  // "not Idle" is the honest test for "these numbers mean something now".
  const live = parameters !== undefined && parameters.state !== "Idle";
  const alerting = useAlerting();

  const verdict = !live ? "NO DATA" : overall === "Ok" ? "OPEN" : "HOLD";
  const because = !live
    ? "Weather source is not answering"
    : alerting.length > 0
      ? alerting.join(" · ")
      : "All readings within limits";

  const phase = moon?.match(/\(([\d.]+)\)/)?.[1];

  return (
    <div className="flex h-dvh w-full flex-col gap-[2vh] overflow-hidden bg-background p-[3vh]">
      {/* Top rail. Right-padded so the demo's view switcher never sits on it;
          a real board has no switcher. */}
      <header className="flex shrink-0 items-baseline justify-between gap-6 pr-[20rem] text-[clamp(0.7rem,1vw,1.05rem)] text-muted-foreground uppercase tracking-widest">
        <span className="font-medium">Sky conditions</span>
        <span className="tabular-nums">
          {latitude?.toFixed(2) ?? "--"}, {longitude?.toFixed(2) ?? "--"}
        </span>
      </header>

      {/* The one thing the board exists to say. */}
      <section className="flex min-h-0 flex-1 items-stretch gap-[3vw]">
        <div className="flex min-w-0 flex-[3] flex-col justify-center gap-[1.5vh]">
          <div className="flex items-center gap-[1.5vw]">
            <div
              className={`h-[12vh] w-[1.2vw] shrink-0 rounded-full ${STATE_BAR[live ? overall : "Idle"]}`}
            />
            <p className="font-semibold text-[clamp(3rem,10vw,11rem)] leading-[0.9] tracking-tight">
              {verdict}
            </p>
          </div>
          <p className="text-[clamp(1rem,2.1vw,2.25rem)] text-muted-foreground leading-tight">
            {because}
          </p>
          <p className="text-[clamp(0.9rem,1.6vw,1.75rem)]">
            {conditions || "Waiting for data"}
            <span className="text-muted-foreground"> · {daylight || "--"}</span>
          </p>
        </div>

        <Separator orientation="vertical" className="hidden lg:block" />

        <div className="flex min-w-0 flex-[2] flex-col justify-center gap-[2vh]">
          <div className="flex items-center justify-between gap-[2vw]">
            <div>
              <p className="font-semibold text-[clamp(2.5rem,6vw,6.5rem)] leading-none">
                {live && temperature.value !== undefined ? temperature.value : "--"}
                <span className="align-top text-[0.4em] text-muted-foreground">°</span>
              </p>
              {live && feelsLike !== undefined && (
                <p className="mt-[1vh] text-[clamp(0.8rem,1.3vw,1.4rem)] text-muted-foreground">
                  feels like {feelsLike}°
                </p>
              )}
            </div>
            <div className="flex flex-col items-center gap-[0.8vh]">
              <MoonDisc phase={phase === undefined ? undefined : Number(phase)} size={96} />
              <p className="text-center text-[clamp(0.7rem,1vw,1.05rem)] text-muted-foreground">
                {moon?.replace(/\s*\([\d.]+\)/, "") ?? "--"}
              </p>
            </div>
          </div>
          <div className="space-y-[1vh]">
            <p className="text-[clamp(0.7rem,1vw,1.05rem)] text-muted-foreground uppercase tracking-widest">
              Daylight
            </p>
            <DaylightBar sunrise={sunrise} sunset={sunset} />
          </div>
          <div className="flex min-h-0 flex-1 items-center justify-center opacity-70">
            <SiteMap latitude={latitude} longitude={longitude} />
          </div>
        </div>
      </section>

      <Separator className="shrink-0" />

      {/* The numbers behind the verdict, plus where the wind is coming from. */}
      <section className="grid shrink-0 grid-cols-[repeat(5,minmax(0,1fr))_auto] items-end gap-[2vw] pb-[1vh]">
        <Tile label="Cloud" value={cloud.value} unit="%" state={cloud.state} live={live} />
        <Tile label="Humidity" value={humidity.value} unit="%" state={humidity.state} live={live} />
        <Tile label="Wind" value={wind.value} unit="mph" state={wind.state} live={live} />
        <Tile label="Gust" value={gust.value} unit="mph" state={gust.state} live={live} />
        <Tile
          label="Pressure"
          value={pressure.value}
          unit="hPa"
          state={pressure.state}
          live={live}
        />
        <div className="flex flex-col items-center gap-[0.8vh]">
          <WindCompass
            direction={live ? direction : undefined}
            speed={live ? wind.value : undefined}
            gust={live ? gust.value : undefined}
            state={wind.state}
            size="h-[22vh] w-[22vh]"
          />
          <p className="font-medium text-[clamp(0.65rem,0.95vw,1rem)] text-muted-foreground uppercase tracking-wider">
            {live && direction !== undefined ? `from ${bearingName(direction)}` : "wind"}
          </p>
        </div>
      </section>
    </div>
  );
}
