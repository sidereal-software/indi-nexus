/**
 * The custom UI from `docs/guides/tutorial-open-meteo.md`.
 *
 * A purpose-built observing dashboard for the Open-Meteo driver, built entirely
 * from `@indi-nexus/react` - the hooks for the data, the shadcn primitives it
 * re-exports for the chrome, and the drawn figures in `sky-visuals.tsx`.
 *
 * The point it makes: the stock `DevicePanel` renders *anything*, which is right
 * for commissioning and wrong for 3 a.m. When you know the device, you can build
 * the screen the job actually wants - and it is still only hooks.
 *
 * Three things worth copying:
 *
 * - Every hook re-renders only its own reading. Changing the cloud cover
 *   repaints one meter, not the page.
 * - Every hook returns `undefined` until the driver has published, so the whole
 *   screen renders correctly before any data arrives.
 * - The safe/unsafe verdict is the driver's `WEATHER_STATUS` state, not a rule
 *   re-implemented here. One source of truth; every client agrees.
 */

import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  type IPState,
  Separator,
  StateBadge,
  useLight,
  useNumber,
  useProperty,
  useText,
} from "@indi-nexus/react";
import { bearingName, DaylightBar, Meter, MoonDisc, SiteMap, WindCompass } from "./sky-visuals";

const DEVICE = "Open-Meteo";

/** Read one number and its status light in one go. */
function useReading(element: string): { value?: number; state: IPState } {
  const value = useNumber(DEVICE, "WEATHER_PARAMETERS", element);
  const state = useLight(DEVICE, "WEATHER_STATUS", element);
  return { value, state: state ?? "Idle" };
}

/** The headline: what it is doing out there, and whether we can open. */
function Verdict() {
  const conditions = useText(DEVICE, "SKY", "CONDITIONS");
  const daylight = useText(DEVICE, "SKY", "DAYLIGHT");
  const temperature = useReading("TEMPERATURE");
  const feelsLike = useNumber(DEVICE, "WEATHER_PARAMETERS", "FEELS_LIKE");
  const overall = useProperty(DEVICE, "WEATHER_STATUS");
  const moon = useText(DEVICE, "ALMANAC", "MOON_PHASE");
  const phase = moon?.match(/\(([\d.]+)\)/)?.[1];

  const state: IPState = overall?.state ?? "Idle";
  const verdict =
    state === "Ok" ? "Safe to open" : state === "Idle" ? "No data" : "Not safe to open";

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-6">
        <div className="space-y-2">
          {/* Status is never colour alone: the badge carries the word too. */}
          <div className="flex items-center gap-2">
            <StateBadge state={state} />
            <span className="font-medium text-sm">{verdict}</span>
          </div>
          <p className="font-semibold text-2xl leading-tight">{conditions || "Waiting for data"}</p>
          <p className="text-muted-foreground text-sm">
            {daylight || "--"}
            {moon ? ` · ${moon.replace(/\s*\([\d.]+\)/, "")}` : ""}
          </p>
        </div>

        {/* The one hero figure on the page: proportional digits, not tabular. */}
        <div className="text-right">
          <p className="font-semibold text-6xl leading-none">
            {temperature.value ?? "--"}
            <span className="align-top text-2xl text-muted-foreground">°</span>
          </p>
          {feelsLike !== undefined && (
            <p className="mt-1 text-muted-foreground text-sm">feels like {feelsLike}°</p>
          )}
        </div>

        <MoonDisc phase={phase === undefined ? undefined : Number(phase)} />
      </CardContent>
    </Card>
  );
}

/** Wind: an angular reading, so a compass rather than another bar. */
function Wind() {
  const speed = useReading("WIND_SPEED");
  const gust = useReading("WIND_GUST");
  const direction = useNumber(DEVICE, "WEATHER_PARAMETERS", "WIND_DIRECTION");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Wind</CardTitle>
        {direction !== undefined && (
          <Badge variant="outline" className="tabular-nums">
            from {bearingName(direction)} {Math.round(direction)}°
          </Badge>
        )}
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-3">
        <WindCompass
          direction={direction}
          speed={speed.value}
          gust={gust.value}
          unit="mph"
          state={speed.state}
        />
        <div className="flex w-full items-center justify-center gap-4 text-sm">
          <span className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Sustained</span>
            <StateBadge state={speed.state} />
          </span>
          <Separator orientation="vertical" className="h-4" />
          <span className="flex items-center gap-1.5 tabular-nums">
            <span className="text-muted-foreground">Gust</span>
            <span className="font-medium">{gust.value ?? "--"}</span>
            <StateBadge state={gust.state} />
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

/** The ratios, each against the limit the driver judges it by. */
function Conditions() {
  const cloud = useReading("CLOUD_COVER");
  const humidity = useReading("HUMIDITY");
  const pressure = useReading("PRESSURE");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Conditions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Meter
          label="Cloud cover"
          value={cloud.value}
          max={100}
          limit={30}
          unit="%"
          state={cloud.state}
        />
        <Meter
          label="Humidity"
          value={humidity.value}
          max={100}
          limit={90}
          unit="%"
          state={humidity.state}
        />
        <Separator />
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground text-sm">Pressure</span>
          <span className="flex items-center gap-2">
            <span className="font-medium text-sm tabular-nums">
              {pressure.value ?? "--"}
              <span className="ml-0.5 text-muted-foreground text-xs">hPa</span>
            </span>
            <StateBadge state={pressure.state} />
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

/** Where the readings come from, and when the sun is up there. */
function Site() {
  const latitude = useNumber(DEVICE, "GEOGRAPHIC_COORD", "LAT");
  const longitude = useNumber(DEVICE, "GEOGRAPHIC_COORD", "LONG");
  const sunrise = useText(DEVICE, "ALMANAC", "SUNRISE");
  const sunset = useText(DEVICE, "ALMANAC", "SUNSET");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Site</CardTitle>
        <Badge variant="outline" className="tabular-nums">
          {latitude?.toFixed(2) ?? "--"}, {longitude?.toFixed(2) ?? "--"}
        </Badge>
      </CardHeader>
      <CardContent className="grid items-center gap-6 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <SiteMap latitude={latitude} longitude={longitude} />
        <div className="space-y-2">
          <p className="text-muted-foreground text-sm">Daylight</p>
          <DaylightBar sunrise={sunrise} sunset={sunset} />
        </div>
      </CardContent>
    </Card>
  );
}

/** A purpose-built observing dashboard for the Open-Meteo device. */
export function SkyReport() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-4 p-4">
      <Verdict />
      <div className="grid gap-4 md:grid-cols-2">
        <Wind />
        <Conditions />
      </div>
      <Site />
    </div>
  );
}
