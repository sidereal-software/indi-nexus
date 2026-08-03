/**
 * The code snippets from `docs/guides/frontend.md`, kept compiling.
 *
 * Nothing imports this module - it exists so `pnpm typecheck` fails if the
 * frontend guide's examples stop matching the API. Keep it in step with that
 * page; if a snippet changes there, change it here.
 */
import {
  ConnectionStatus,
  DevicePanel,
  IndiClient,
  IndiProvider,
  MessageLog,
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
