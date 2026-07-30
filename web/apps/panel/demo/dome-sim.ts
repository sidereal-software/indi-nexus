/**
 * An in-browser dome simulator: the far end of a fake WebSocket.
 *
 * This is a TypeScript stand-in for `examples/dome_device.py` (plus the
 * bridge), speaking the same JSON wire contract the FastAPI bridge speaks -
 * so the stock panel runs against it unmodified, with no server at all. It
 * powers the live demo embedded in the documentation site.
 */

import type { IndiMessage, SwitchVector, Vector, WebSocketLike } from "@indi-nexus/client";

const DEVICE = "Dome Simulator";
const PARK_AZ = 90;
const SHUTTER_TRAVEL_M = 0.5;

/** Normalise an angle to the [0, 360) range. */
function range360(degrees: number): number {
  return ((degrees % 360) + 360) % 360;
}

/** The first element a (possibly partial) switch write turned On, if any. */
function selected(vector: SwitchVector): string | undefined {
  return vector.elements.find((el) => el.value === "On")?.name;
}

/**
 * A `WebSocketLike` whose server side simulates the dome bridge.
 *
 * The panel's `IndiClient` uses it through `webSocketFactory`; everything the
 * client sends is handled here, and simulated frames flow back via
 * `onmessage`.
 */
export class DomeSimSocket implements WebSocketLike {
  readyState = 0;
  onopen: ((event: unknown) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;

  private connected = false;
  private az = 0;
  private targetAz: number | null = null;
  private shutterOpen = false;
  private shutterTravel = 0;
  private parking = false;
  private unparking = false;
  private domeSpeed = 5;
  private shutterSpeed = 0.1;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    // Open asynchronously, like a real socket; then prime the panel with the
    // bridge's snapshot (defs + connection control frame + a hello message).
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.({});
      this.deliver({ event: "connection", connected: true });
      for (const vector of this.defs()) this.deliver({ tag: "def", vector });
      this.sendMessage("Dome simulator ready. (This demo runs entirely in your browser.)");
      this.timer = setInterval(() => this.tick(), 1000);
    }, 0);
  }

  close(): void {
    if (this.timer !== null) clearInterval(this.timer);
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
    return [
      this.connectionVector("Idle"),
      this.positionVector("Idle"),
      {
        kind: "number",
        device: DEVICE,
        name: "REL_DOME_POSITION",
        label: "Relative Position",
        group: "Motion",
        state: "Idle",
        perm: "rw",
        elements: [
          {
            kind: "number",
            name: "DOME_RELATIVE_POSITION",
            label: "Degrees",
            format: "%.2f",
            min: -180,
            max: 180,
            value: 0,
          },
        ],
      },
      {
        kind: "number",
        device: DEVICE,
        name: "SPEEDS",
        label: "Speeds",
        group: "Main Control",
        state: "Idle",
        perm: "rw",
        elements: [
          {
            kind: "number",
            name: "DOME",
            label: "Dome (deg/s)",
            format: "%.2f",
            min: 0.1,
            max: 10,
            value: this.domeSpeed,
          },
          {
            kind: "number",
            name: "SHUTTER",
            label: "Shutter (m/s)",
            format: "%.2f",
            min: 0.01,
            max: 1,
            value: this.shutterSpeed,
          },
        ],
      },
      this.shutterVector("Idle"),
      this.parkVector("Idle"),
      {
        kind: "switch",
        device: DEVICE,
        name: "DOME_ABORT_MOTION",
        label: "Abort Motion",
        group: "Main Control",
        state: "Idle",
        perm: "rw",
        rule: "AtMostOne",
        elements: [{ kind: "switch", name: "ABORT", label: "Abort", value: "Off" }],
      },
    ];
  }

  private connectionVector(state: string): Vector {
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
    } as Vector;
  }

  private positionVector(state: string): Vector {
    return {
      kind: "number",
      device: DEVICE,
      name: "ABS_DOME_POSITION",
      label: "Absolute Position",
      group: "Motion",
      state,
      perm: "rw",
      elements: [
        {
          kind: "number",
          name: "DOME_ABSOLUTE_POSITION",
          label: "Degrees",
          format: "%.2f",
          min: 0,
          max: 360,
          value: this.az,
        },
      ],
    } as Vector;
  }

  private shutterVector(state: string): Vector {
    return {
      kind: "switch",
      device: DEVICE,
      name: "DOME_SHUTTER",
      label: "Shutter",
      group: "Main Control",
      state,
      perm: "rw",
      rule: "OneOfMany",
      elements: [
        {
          kind: "switch",
          name: "SHUTTER_OPEN",
          label: "Open",
          value: this.shutterOpen ? "On" : "Off",
        },
        {
          kind: "switch",
          name: "SHUTTER_CLOSE",
          label: "Close",
          value: this.shutterOpen ? "Off" : "On",
        },
      ],
    } as Vector;
  }

  private parkVector(state: string): Vector {
    const parked = !this.parking && !this.unparking && this.az === PARK_AZ && !this.shutterOpen;
    return {
      kind: "switch",
      device: DEVICE,
      name: "DOME_PARK",
      label: "Parking",
      group: "Main Control",
      state,
      perm: "rw",
      rule: "OneOfMany",
      elements: [
        { kind: "switch", name: "PARK", label: "Park", value: parked ? "On" : "Off" },
        { kind: "switch", name: "UNPARK", label: "Unpark", value: parked ? "Off" : "On" },
      ],
    } as Vector;
  }

  // -- inbound handling --------------------------------------------------- //
  private requireConnected(): boolean {
    if (this.connected) return true;
    this.sendMessage(`${DEVICE} is not connected.`, "ERROR");
    return false;
  }

  private handle(vector: Vector): void {
    switch (vector.name) {
      case "CONNECTION": {
        this.connected = selected(vector as SwitchVector) === "CONNECT";
        if (!this.connected) {
          this.targetAz = null;
          this.shutterTravel = 0;
          this.parking = this.unparking = false;
        }
        this.set(this.connectionVector("Ok"));
        this.sendMessage(`${DEVICE} is ${this.connected ? "connected" : "disconnected"}.`);
        break;
      }
      case "ABS_DOME_POSITION": {
        if (!this.requireConnected()) return;
        const el = vector.kind === "number" ? vector.elements[0] : undefined;
        if (el) this.slewTo(el.value);
        break;
      }
      case "REL_DOME_POSITION": {
        if (!this.requireConnected()) return;
        const el = vector.kind === "number" ? vector.elements[0] : undefined;
        if (el) this.slewTo(this.az + el.value);
        break;
      }
      case "SPEEDS": {
        if (!this.requireConnected() || vector.kind !== "number") return;
        for (const el of vector.elements) {
          if (el.name === "DOME") this.domeSpeed = Math.min(10, Math.max(0.1, el.value));
          if (el.name === "SHUTTER") this.shutterSpeed = Math.min(1, Math.max(0.01, el.value));
        }
        this.set({
          ...this.defs()[3],
          state: "Ok",
        } as Vector);
        break;
      }
      case "DOME_SHUTTER": {
        if (!this.requireConnected()) return;
        const which = selected(vector as SwitchVector);
        if (which === undefined) return;
        this.moveShutter(which === "SHUTTER_OPEN");
        break;
      }
      case "DOME_PARK": {
        if (!this.requireConnected()) return;
        if (selected(vector as SwitchVector) === "PARK") {
          this.parking = true;
          this.unparking = false;
          this.moveShutter(false);
          this.slewTo(PARK_AZ);
          this.sendMessage("Parking...");
        } else {
          this.unparking = true;
          this.parking = false;
          this.moveShutter(true);
        }
        this.set(this.parkVector("Busy"));
        break;
      }
      case "DOME_ABORT_MOTION": {
        if (!this.requireConnected()) return;
        this.targetAz = null;
        this.parking = this.unparking = false;
        if (this.shutterTravel > 0) {
          this.shutterTravel = 0;
          this.set(this.shutterVector("Alert"));
          this.sendMessage("Shutter operation aborted. Status: unknown.", "ERROR");
        }
        this.set(this.positionVector("Idle"));
        this.sendMessage("Motion aborted.");
        break;
      }
    }
  }

  private slewTo(azimuth: number): void {
    this.targetAz = range360(azimuth);
    this.set(this.positionVector("Busy"));
  }

  private moveShutter(open: boolean): void {
    this.shutterOpen = open;
    this.shutterTravel = SHUTTER_TRAVEL_M;
    this.set(this.shutterVector("Busy"));
  }

  // -- simulation --------------------------------------------------------- //
  private tick(): void {
    if (!this.connected) return;
    this.tickRotation();
    this.tickShutter();
  }

  private tickRotation(): void {
    if (this.targetAz === null) return;
    const delta = range360(this.targetAz - this.az);
    if (Math.min(delta, 360 - delta) <= this.domeSpeed) {
      this.az = this.targetAz;
      this.targetAz = null;
      this.set(this.positionVector("Ok"));
      this.sendMessage("Dome reached requested azimuth angle.");
      if (this.parking) {
        this.parking = false;
        this.set(this.parkVector("Ok"));
        this.sendMessage("Dome parked.");
      }
      return;
    }
    this.az = range360(this.az + (delta <= 180 ? this.domeSpeed : -this.domeSpeed));
    this.set(this.positionVector("Busy"));
  }

  private tickShutter(): void {
    if (this.shutterTravel <= 0) return;
    this.shutterTravel -= this.shutterSpeed;
    if (this.shutterTravel > 1e-9) return;
    this.shutterTravel = 0;
    this.set(this.shutterVector("Ok"));
    this.sendMessage(`Shutter is ${this.shutterOpen ? "open" : "closed"}.`);
    if (this.unparking) {
      this.unparking = false;
      this.set(this.parkVector("Ok"));
      this.sendMessage("Dome unparked.");
    }
  }
}
