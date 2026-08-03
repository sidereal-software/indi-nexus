/**
 * The code samples from the documentation guides, kept compiling.
 *
 * `pnpm typecheck` fails if the frontend guide's examples stop matching the API.
 * Keep this in step with `docs/guides/frontend.md`: change a snippet there,
 * change it here. (The tutorial's custom UI has a real home instead - see
 * `apps/panel/demo/sky-report.tsx`.)
 */
import {
  DevicePanel,
  IndiClient,
  IndiProvider,
  useDevices,
  useIndiClient,
  useNumber,
} from "./index";

export function App1() {
  return (
    <IndiProvider url="ws://localhost:8000/ws">
      <DevicePanel device="Dome Simulator" />
    </IndiProvider>
  );
}

export function Observatory() {
  const devices = useDevices();
  return devices.map((name) => <DevicePanel key={name} device={name} />);
}

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
