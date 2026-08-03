/**
 * The custom UI from `docs/guides/tutorial-open-meteo.md`.
 *
 * This is the file the tutorial's final code block shows, and the one the live
 * weather demo renders - so what a reader copies is what a reader saw. Keep the
 * two in step.
 *
 * The point it makes: a purpose-built screen is a handful of hooks. Each
 * `useNumber`/`useText` re-renders only when that one value changes, every hook
 * returns `undefined` until the driver has published, and the safe/unsafe
 * verdict comes from the driver's own `WEATHER_STATUS` state rather than being
 * recomputed here.
 */

import { StateBadge, useLight, useNumber, useProperty, useText } from "@indi-nexus/react";

/** One reading: its value, and the safety light beside it. */
function Reading({ element, label }: { element: string; label: string }) {
  const value = useNumber("Open-Meteo", "WEATHER_PARAMETERS", element);
  const status = useLight("Open-Meteo", "WEATHER_STATUS", element);
  return (
    <div className="flex items-baseline justify-between gap-4 border-b py-2">
      <span className="text-muted-foreground text-sm">{label}</span>
      <span className="flex items-center gap-2">
        <span className="font-mono text-2xl tabular-nums">{value ?? "--"}</span>
        <StateBadge state={status ?? "Idle"} />
      </span>
    </div>
  );
}

/** A purpose-built weather screen: the numbers an operator checks at dusk. */
export function SkyReport() {
  const conditions = useText("Open-Meteo", "SKY", "CONDITIONS");
  const daylight = useText("Open-Meteo", "SKY", "DAYLIGHT");
  const sunset = useText("Open-Meteo", "ALMANAC", "SUNSET");
  const moon = useText("Open-Meteo", "ALMANAC", "MOON_PHASE");
  const overall = useProperty("Open-Meteo", "WEATHER_STATUS");

  return (
    <section className="mx-auto max-w-md space-y-4 p-6">
      <header className="space-y-1">
        <h1 className="font-semibold text-3xl">{conditions || "Waiting for data"}</h1>
        <p className="text-muted-foreground text-sm">
          {daylight || "--"} &middot; sunset {sunset || "--"} &middot; {moon || "--"}
        </p>
      </header>

      <div>
        <Reading element="CLOUD_COVER" label="Cloud cover" />
        <Reading element="WIND_SPEED" label="Wind" />
        <Reading element="WIND_GUST" label="Gusts" />
        <Reading element="HUMIDITY" label="Humidity" />
        <Reading element="TEMPERATURE" label="Temperature" />
      </div>

      <p className="text-sm">{overall?.state === "Ok" ? "Safe to open." : "Not safe to open."}</p>
    </section>
  );
}
