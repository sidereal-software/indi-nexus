/**
 * One fake bridge presenting two simulated devices to one client.
 *
 * `DomeSimSocket` and `WeatherSimSocket` each implement `WebSocketLike` and each
 * own exactly one device, because each stands in for one driver. A real bridge
 * is not per-driver: `indiserver` multiplexes every driver onto one TCP stream
 * and the bridge puts that whole stream on one WebSocket. This socket is that
 * layer - it owns both simulators, interleaves their frames onto one
 * `onmessage`, and fans every client write out to both, which is why the demo
 * runs an observatory rather than a device.
 *
 * Two things it has to get right, both of them wire contract rather than
 * rendering:
 *
 * - **Exactly one `hello`, and it leads.** The bridge sends one per socket. Two
 *   would be a bridge that reintroduced itself mid-stream; none makes the client
 *   log "the bridge sent no hello frame" into the demo's own message panel,
 *   where a visitor reads it as a fault on the page most people meet first. The
 *   same goes for the `connection` control frame. Both are the *bridge's* to
 *   send, and here this socket is the bridge, so every control frame a child
 *   emits is dropped and this class emits its own.
 * - **Both simulators keep their own `CONNECTION` lifecycle.** Nothing here
 *   connects, disconnects or filters a device write; a `new` frame goes to both
 *   children and each ignores what is not addressed to it, exactly as it would
 *   over a shared `indiserver` stream.
 */

import { CLIENT_PROTOCOL_VERSION, type WebSocketLike } from "@indikit/client";
import { DomeSimSocket } from "./dome-sim";
import { type Payload, WeatherSimSocket } from "./weather-sim";

/** A `WebSocketLike` whose server side is a dome and a weather station. */
export class ObservatorySimSocket implements WebSocketLike {
  readyState = 0;
  onopen: ((event: unknown) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;

  private readonly devices: WebSocketLike[] = [];
  private closed = false;

  /**
   * Open the pair.
   *
   * @param fetchWeather - How the weather simulator gets its readings;
   *   injectable so a test can drive it without a network.
   */
  constructor(fetchWeather: (latitude: number, longitude: number) => Promise<Payload>) {
    // Open asynchronously, like a real socket. The children are constructed
    // *here* rather than in this constructor for two reasons: a simulator starts
    // delivering the moment it exists, so it must not exist before the client
    // has attached its handlers; and each schedules its own opening burst on a
    // timer booked from here, which therefore runs strictly after the `hello`
    // below. They are attached before `onopen` because a client with anything
    // buffered flushes it from that callback, and a write with nowhere to go
    // would be dropped in silence.
    setTimeout(() => {
      if (this.closed) return;
      this.attach(new DomeSimSocket());
      this.attach(new WeatherSimSocket(fetchWeather));
      this.readyState = 1;
      this.onopen?.({});
      this.deliver({ event: "hello", protocol: CLIENT_PROTOCOL_VERSION, server: "demo" });
      this.deliver({ event: "connection", connected: true });
    }, 0);
  }

  /** Hand one client write to every device; each ignores what is not its own. */
  send(data: string): void {
    for (const device of this.devices) device.send(data);
  }

  /** Close both devices, and refuse to open if this lands before they exist. */
  close(): void {
    this.closed = true;
    for (const device of this.devices) device.close();
    this.devices.length = 0;
    this.readyState = 3;
    this.onclose?.({});
  }

  /** Take ownership of one simulator and route its frames through this socket. */
  private attach(device: WebSocketLike): void {
    device.onmessage = (event) => this.relay(event);
    this.devices.push(device);
  }

  /**
   * Pass one device frame on, dropping the control frames it thinks it owns.
   *
   * A child's `hello` and `connection` describe a bridge that does not exist -
   * there is one bridge here and it has already introduced itself. Anything
   * tagged (`def`, `set`, `del`, `message`) is the device speaking and goes
   * straight through, interleaved with the other device's in arrival order.
   */
  private relay(event: { data: unknown }): void {
    let frame: unknown;
    try {
      frame = JSON.parse(String(event.data));
    } catch {
      return;
    }
    if (typeof frame === "object" && frame !== null && "event" in frame) return;
    this.onmessage?.(event);
  }

  /** Hand one frame of this socket's own to the client. */
  private deliver(frame: object): void {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}
