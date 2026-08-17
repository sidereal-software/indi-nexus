/**
 * An in-browser flat-field lamp simulator: the far end of a fake WebSocket.
 *
 * A TypeScript stand-in for `examples/flat_panel.py` (plus the bridge), speaking
 * the same JSON wire contract the FastAPI bridge speaks - so the stock panel runs
 * against it unmodified, with no server at all. It backs the demo linked from the
 * "Writing a driver" guide, so a reader can drive the driver they just read.
 *
 * Keep it in step with the Python driver: same property names, same rule, same
 * declared range, same clamping, same connection lifecycle, or the demo stops
 * demonstrating that driver.
 */

import {
  CLIENT_PROTOCOL_VERSION,
  type IndiMessage,
  type SwitchVector,
  type Vector,
  type WebSocketLike,
} from "@indi-nexus/client";

const DEVICE = "Flat Panel";
const MIN_BRIGHTNESS = 0;
const MAX_BRIGHTNESS = 255;

/** The first element a (possibly partial) switch write turned On, if any. */
function selected(vector: SwitchVector): string | undefined {
  return vector.elements.find((el) => el.value === "On")?.name;
}

/**
 * A `WebSocketLike` whose server side simulates the flat panel bridge.
 *
 * The panel's `IndiClient` uses it through `webSocketFactory`; everything the
 * client sends is handled here, and simulated frames flow back via `onmessage`.
 */
export class FlatPanelSimSocket implements WebSocketLike {
  readyState = 0;
  onopen: ((event: unknown) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;

  private connected = false;
  private lampOn = false;
  private brightness = 128;

  constructor() {
    // Open asynchronously, like a real socket; then prime the panel with the
    // bridge's snapshot (defs + connection control frame + a hello message).
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.({});
      // The hello leads, exactly as the real bridge's does: without it the
      // client logs "the bridge sent no hello frame" into the demo's own
      // message panel, where a visitor would read it as a fault.
      this.deliver({ event: "hello", protocol: CLIENT_PROTOCOL_VERSION, server: "demo" });
      this.deliver({ event: "connection", connected: true });
      for (const vector of this.defs()) this.deliver({ tag: "def", vector });
      this.sendMessage("Flat panel ready. (This demo runs entirely in your browser.)");
    }, 0);
  }

  close(): void {
    this.readyState = 3;
    this.onclose?.({});
  }

  send(data: string): void {
    const frame = JSON.parse(data) as IndiMessage;
    if (frame.tag !== "new" || frame.vector.device !== DEVICE) return;
    this.handle(frame.vector);
  }

  // -- outbound ----------------------------------------------------------- //
  private deliver(frame: object): void {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }

  private sendMessage(text: string, severity = "INFO"): void {
    this.deliver({
      tag: "message",
      device: DEVICE,
      timestamp: new Date().toISOString(),
      message: `[${severity}] ${text}`,
    });
  }

  private set(vector: Vector): void {
    this.deliver({ tag: "set", vector });
  }

  // -- property state ----------------------------------------------------- //
  private defs(): Vector[] {
    return [this.connectionVector("Idle"), this.lampVector("Idle"), this.brightnessVector("Idle")];
  }

  /** The standard INDI CONNECTION switch, as `define_connection()` defines it. */
  private connectionVector(state: Vector["state"]): Vector {
    return {
      kind: "switch",
      device: DEVICE,
      name: "CONNECTION",
      label: "Connection",
      group: "Main Control",
      state,
      perm: "rw",
      rule: "OneOfMany",
      elements: [
        { kind: "switch", name: "CONNECT", label: "Connect", value: this.connected ? "On" : "Off" },
        {
          kind: "switch",
          name: "DISCONNECT",
          label: "Disconnect",
          value: this.connected ? "Off" : "On",
        },
      ],
    };
  }

  /** The lamp switch: exactly one of On/Off, so the panel draws radio buttons. */
  private lampVector(state: Vector["state"]): Vector {
    return {
      kind: "switch",
      device: DEVICE,
      name: "LIGHT_CONTROL",
      label: "Lamp",
      group: "Main Control",
      state,
      perm: "rw",
      rule: "OneOfMany",
      elements: [
        { kind: "switch", name: "ON", label: "On", value: this.lampOn ? "On" : "Off" },
        { kind: "switch", name: "OFF", label: "Off", value: this.lampOn ? "Off" : "On" },
      ],
    };
  }

  /** The brightness dial, carrying the range the panel enforces on the input. */
  private brightnessVector(state: Vector["state"]): Vector {
    return {
      kind: "number",
      device: DEVICE,
      name: "LIGHT_BRIGHTNESS",
      label: "Brightness",
      group: "Main Control",
      state,
      perm: "rw",
      elements: [
        {
          kind: "number",
          name: "BRIGHTNESS",
          label: "Brightness",
          format: "%.0f",
          min: MIN_BRIGHTNESS,
          max: MAX_BRIGHTNESS,
          value: this.brightness,
        },
      ],
    };
  }

  // -- inbound ------------------------------------------------------------ //
  /** The `require_connected()` guard: refuse the command and say why. */
  private requireConnected(): boolean {
    if (this.connected) return true;
    this.sendMessage(`${DEVICE} is not connected.`, "ERROR");
    return false;
  }

  private handle(vector: Vector): void {
    if (vector.kind === "switch" && vector.name === "CONNECTION") {
      this.connected = selected(vector) === "CONNECT";
      // A panel left lit fogs the next exposure, so the link never goes down
      // with the lamp on - the same reason `on_disconnect` does it in Python,
      // and announced every time for the same reason it is there.
      if (!this.connected) {
        this.lampOn = false;
        this.set(this.lampVector("Idle"));
        this.sendMessage("Lamp turned off on disconnect.");
      }
      this.set(this.connectionVector("Ok"));
      this.sendMessage(`${DEVICE} is ${this.connected ? "connected" : "disconnected"}.`);
      return;
    }
    if (vector.kind === "switch" && vector.name === "LIGHT_CONTROL") {
      if (!this.requireConnected()) return;
      this.lampOn = selected(vector) === "ON";
      this.set(this.lampVector("Ok"));
      this.sendMessage(`Lamp turned ${this.lampOn ? "on" : "off"}.`);
      return;
    }
    if (vector.kind === "number" && vector.name === "LIGHT_BRIGHTNESS") {
      if (!this.requireConnected()) return;
      const wanted = vector.elements.find((el) => el.name === "BRIGHTNESS")?.value ?? 0;
      // The declared min/max is a promise about the hardware, so hold the request
      // to it exactly as the Python driver does.
      this.brightness = Math.max(MIN_BRIGHTNESS, Math.min(MAX_BRIGHTNESS, wanted));
      this.set(this.brightnessVector("Ok"));
    }
  }
}
