/**
 * The code samples from the documentation guides, kept compiling.
 *
 * `pnpm typecheck` fails if the guides' examples stop matching the API, and
 * `doc-snippets.test.tsx` renders the ones that have behaviour. Keep this in
 * step with `docs/guides/frontend.md` and
 * `docs/guides/tutorial-open-meteo.md`: change a snippet there, change it here.
 */
import {
  ConnectionStatus,
  DevicePanel,
  IndiClient,
  IndiProvider,
  MessageLog,
  StateBadge,
  useDevices,
  useIndiClient,
  useLight,
  useNumber,
  useProperty,
  useText,
} from "./index";

export function App1() {
  return (
    <IndiProvider url="ws://localhost:8000/ws">
      <DevicePanel device="Dome Simulator" />
    </IndiProvider>
  );
}

function Observatory() {
  const devices = useDevices();
  return (
    <>
      <ConnectionStatus />
      {devices.map((name) => (
        <DevicePanel key={name} device={name} />
      ))}
      <MessageLog />
    </>
  );
}

export const App2 = () => (
  <IndiProvider url="ws://localhost:8000/ws">
    <Observatory />
  </IndiProvider>
);

export function DomeAzimuth() {
  const azimuth = useNumber("Dome Simulator", "ABS_DOME_POSITION", "DOME_ABSOLUTE_POSITION");
  return <h1>{azimuth ?? "--"}°</h1>;
}

export function ShutterButtons() {
  const client = useIndiClient();
  return (
    <>
      <button
        type="button"
        onClick={() => client.setSwitch("Dome Simulator", "DOME_SHUTTER", { SHUTTER_OPEN: "On" })}
      >
        Open
      </button>
      <button
        type="button"
        onClick={() =>
          client.setNumber("Dome Simulator", "ABS_DOME_POSITION", { DOME_ABSOLUTE_POSITION: 120 })
        }
      >
        Go to 120°
      </button>
    </>
  );
}

export async function script(client: IndiClient) {
  await client.waitFor("Dome Simulator", "ABS_DOME_POSITION", (v) => v.state === "Ok");
}

export function plain() {
  const client = new IndiClient({ url: "ws://localhost:8000/ws" });
  client.subscribe((event) => console.log(event.device, event.name, event.vector?.state));
  client.connect();
}

// --------------------------------------------------------------------------- //
// docs/guides/tutorial-open-meteo.md - a custom UI for the Open-Meteo driver.  //
// --------------------------------------------------------------------------- //

/** One reading: its value, its unit, and the safety light beside it. */
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
        <h1 className="font-semibold text-3xl">{conditions ?? "Waiting for data"}</h1>
        <p className="text-muted-foreground text-sm">
          {daylight ?? "--"} &middot; sunset {sunset ?? "--"} &middot; {moon ?? "--"}
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

export const SkyApp = () => (
  <IndiProvider url="ws://localhost:8000/ws">
    <SkyReport />
  </IndiProvider>
);
