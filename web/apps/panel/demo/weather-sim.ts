/**
 * The Open-Meteo driver, in the browser: the far end of a fake WebSocket.
 *
 * A TypeScript stand-in for `examples/openmeteo_device.py` plus the bridge,
 * speaking the same JSON wire contract, so the stock panel and any custom UI
 * run against it unmodified with no server at all.
 *
 * It really does call Open-Meteo - the same free, keyless API the Python driver
 * uses - from the reader's browser. If that call cannot be made (offline, or a
 * network that blocks it) it falls back to a recorded response so the page still
 * demonstrates the UI rather than showing nothing.
 *
 * Keep the property names, the safe ranges and the safety rule in step with
 * `examples/openmeteo_device.py`; the point of the page is that they match.
 */

import type {
  IndiMessage,
  IPState,
  LightVector,
  NumberVector,
  TextVector,
  Vector,
  WebSocketLike,
} from "@indi-nexus/client";

const DEVICE = "Open-Meteo";

/** How often the browser refetches. Slower than the Python driver's 5 minutes
 *  would make for a dull page; still polite to a free API. */
const POLL_MS = 60_000;

/** (API field, element, label, safe low, safe high) - mirrors READINGS in the
 *  Python driver: published *and* judged. */
const READINGS: [string, string, string, number, number][] = [
  ["temperature_2m", "TEMPERATURE", "Temperature", -20, 110],
  ["relative_humidity_2m", "HUMIDITY", "Humidity", 0, 90],
  ["cloud_cover", "CLOUD_COVER", "Cloud cover", 0, 30],
  ["wind_speed_10m", "WIND_SPEED", "Wind speed", 0, 25],
  ["wind_gusts_10m", "WIND_GUST", "Wind gust", 0, 35],
  ["pressure_msl", "PRESSURE", "Pressure", 900, 1100],
];

/** Published but not judged - mirrors CONTEXT in the Python driver. A compass
 *  bearing has no safe range, so it gets no status light. */
const CONTEXT: [string, string, string][] = [
  ["wind_direction_10m", "WIND_DIRECTION", "Wind from"],
  ["apparent_temperature", "FEELS_LIKE", "Feels like"],
];

/** Everything published, judged or not. */
const PUBLISHED: [string, string, string][] = [
  ...READINGS.map(([field, element, label]) => [field, element, label] as [string, string, string]),
  ...CONTEXT,
];

/** WMO weather codes, condensed the way the Python driver condenses them. */
const WEATHER_CODES: Record<number, string> = {
  0: "Clear sky",
  1: "Mainly clear",
  2: "Partly cloudy",
  3: "Overcast",
  45: "Fog",
  48: "Freezing fog",
  51: "Light drizzle",
  53: "Drizzle",
  55: "Heavy drizzle",
  61: "Light rain",
  63: "Rain",
  65: "Heavy rain",
  71: "Light snow",
  73: "Snow",
  75: "Heavy snow",
  80: "Light showers",
  81: "Showers",
  82: "Violent showers",
  95: "Thunderstorm",
  96: "Thunderstorm with hail",
  99: "Severe thunderstorm with hail",
};

/** The recorded reply used when the live call cannot be made (Los Angeles). */
const RECORDED = {
  current_units: {
    temperature_2m: "°F",
    relative_humidity_2m: "%",
    cloud_cover: "%",
    wind_speed_10m: "mp/h",
    wind_gusts_10m: "mp/h",
    pressure_msl: "hPa",
    wind_direction_10m: "°",
    apparent_temperature: "°F",
  },
  current: {
    temperature_2m: 66.9,
    relative_humidity_2m: 95,
    cloud_cover: 31,
    wind_speed_10m: 2.4,
    wind_gusts_10m: 2.5,
    pressure_msl: 1008.2,
    is_day: 0,
    weather_code: 1,
    wind_direction_10m: 304,
    apparent_temperature: 71.6,
  },
  daily: {
    sunrise: ["2026-08-03T13:06"],
    sunset: ["2026-08-04T02:52"],
    moon_phase: [0.659],
  },
};

/** One decoded Open-Meteo reply, in the shape this simulator reads. */
interface Payload {
  current_units?: Record<string, string>;
  current?: Record<string, number>;
  daily?: Record<string, (string | number)[]>;
}

/** Describe a WMO weather code. */
function describe(code: number): string {
  return WEATHER_CODES[code] ?? `Unknown (${code})`;
}

/** Name the moon phase from Open-Meteo's 0-1 fraction. */
function moonPhaseName(fraction: number): string {
  const names = [
    "New moon",
    "Waxing crescent",
    "First quarter",
    "Waxing gibbous",
    "Full moon",
    "Waning gibbous",
    "Last quarter",
    "Waning crescent",
  ];
  return names[Math.round((((fraction % 1) + 1) % 1) * 8) % 8] as string;
}

/** Whether a weather code means water is falling out of the sky. */
function isWet(code: number): boolean {
  return code >= 51 && code < 100;
}

/**
 * A `WebSocketLike` whose server side is the Open-Meteo driver.
 *
 * The panel's `IndiClient` uses it through `webSocketFactory`; everything the
 * client sends is handled here, and frames flow back via `onmessage`.
 */
export class WeatherSimSocket implements WebSocketLike {
  readyState = 0;
  onopen: ((event: unknown) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;

  private connected = false;
  private latitude = 34.0522;
  private longitude = -118.2437;
  private timer: ReturnType<typeof setInterval> | null = null;
  private live = false;

  /** Injectable so tests can drive the simulator without a network. */
  constructor(private readonly fetchPayload: (lat: number, lon: number) => Promise<Payload>) {
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.({});
      this.deliver({ event: "connection", connected: true });
      for (const vector of this.defs()) this.deliver({ tag: "def", vector });
      this.sendMessage("Open-Meteo driver ready. Press Connect to fetch.");
    }, 0);
  }

  /** Handle one frame from the client. */
  send(data: string): void {
    let message: IndiMessage;
    try {
      message = JSON.parse(data) as IndiMessage;
    } catch {
      return;
    }
    if (message.tag !== "new") return;
    const vector = message.vector;
    if (vector.device !== DEVICE) return;
    if (vector.name === "CONNECTION") void this.handleConnection(vector);
    if (vector.name === "GEOGRAPHIC_COORD") void this.handleSite(vector);
  }

  /** Close the socket and stop polling. */
  close(): void {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    this.readyState = 3;
    this.onclose?.({});
  }

  // -- client writes -------------------------------------------------------- //
  /** Connect (fetch once, then poll) or disconnect (park the readings). */
  private async handleConnection(vector: Vector): Promise<void> {
    const wantsConnect =
      vector.kind === "switch" &&
      vector.elements.some((el) => el.name === "CONNECT" && el.value === "On");

    if (!wantsConnect) {
      this.connected = false;
      if (this.timer !== null) clearInterval(this.timer);
      this.timer = null;
      this.deliver({ tag: "set", vector: this.connectionVector(false, "Ok") });
      this.parkReadings();
      this.sendMessage(`${DEVICE} is disconnected.`);
      return;
    }

    this.deliver({ tag: "set", vector: this.connectionVector(true, "Busy") });
    try {
      this.publish(await this.fetchPayload(this.latitude, this.longitude));
    } catch (error) {
      // Same contract as the Python driver: a failed on_connect rolls the
      // switch back rather than claiming a link that is not there.
      this.deliver({ tag: "set", vector: this.connectionVector(false, "Alert") });
      this.sendMessage(`[ERROR] ${DEVICE} failed to connect: ${String(error)}`);
      return;
    }
    this.connected = true;
    this.deliver({ tag: "set", vector: this.connectionVector(true, "Ok") });
    this.sendMessage(`${DEVICE} is connected.`);
    this.timer = setInterval(() => void this.poll(), POLL_MS);
  }

  /** Point the driver at a new site and refetch. */
  private async handleSite(vector: Vector): Promise<void> {
    if (vector.kind !== "number") return;
    for (const element of vector.elements) {
      if (element.name === "LAT") this.latitude = element.value;
      if (element.name === "LONG") this.longitude = element.value;
    }
    this.deliver({ tag: "set", vector: this.siteVector("Busy") });
    if (!this.connected) {
      this.deliver({ tag: "set", vector: this.siteVector("Ok") });
      return;
    }
    try {
      const payload = await this.fetchPayload(this.latitude, this.longitude);
      this.deliver({ tag: "set", vector: this.siteVector("Ok") });
      this.publish(payload);
      this.sendMessage(
        `Now reporting for ${this.latitude.toFixed(4)}, ${this.longitude.toFixed(4)}.`,
      );
    } catch (error) {
      this.deliver({ tag: "set", vector: this.siteVector("Alert") });
      this.sendMessage(`[ERROR] ${DEVICE} is not answering: ${String(error)}`);
    }
  }

  /** Refetch on the timer. */
  private async poll(): Promise<void> {
    try {
      this.publish(await this.fetchPayload(this.latitude, this.longitude));
    } catch {
      this.parkReadings();
    }
  }

  // -- publishing ----------------------------------------------------------- //
  /** Turn one reply into the four property updates the Python driver sends. */
  private publish(payload: Payload): void {
    const current = payload.current ?? {};
    const units = payload.current_units ?? {};

    const values: Record<string, number> = {};
    for (const [field, element] of PUBLISHED) {
      const reading = current[field];
      if (reading !== undefined) values[element] = reading;
    }

    this.deliver({
      tag: "set",
      vector: {
        kind: "number",
        device: DEVICE,
        name: "WEATHER_PARAMETERS",
        state: "Ok",
        perm: "ro",
        elements: PUBLISHED.filter(([, element]) => element in values).map(
          ([field, element, label]) => ({
            kind: "number" as const,
            name: element,
            label: units[field] ? `${label} (${units[field]})` : label,
            format: "%.1f",
            value: values[element] as number,
          }),
        ),
      } satisfies NumberVector,
    });

    const code = current.weather_code ?? 0;
    const lights = READINGS.map(([, element, label, low, high]) => {
      const value = values[element];
      const state: IPState =
        value === undefined ? "Idle" : value >= low && value <= high ? "Ok" : "Alert";
      return { kind: "light" as const, name: element, label, value: state };
    });
    const anyAlert = lights.some((light) => light.value === "Alert");
    this.deliver({
      tag: "set",
      vector: {
        kind: "light",
        device: DEVICE,
        name: "WEATHER_STATUS",
        state: isWet(code) || anyAlert ? "Alert" : "Ok",
        elements: lights,
      } satisfies LightVector,
    });

    this.deliver({
      tag: "set",
      vector: {
        kind: "text",
        device: DEVICE,
        name: "SKY",
        state: "Ok",
        perm: "ro",
        elements: [
          { kind: "text", name: "CONDITIONS", label: "Conditions", value: describe(code) },
          {
            kind: "text",
            name: "DAYLIGHT",
            label: "Daylight",
            value: current.is_day ? "Day" : "Night",
          },
        ],
      } satisfies TextVector,
    });

    const daily = payload.daily ?? {};
    const first = (field: string) => daily[field]?.[0];
    const sunrise = first("sunrise");
    const sunset = first("sunset");
    const phase = first("moon_phase");
    if (sunrise !== undefined && sunset !== undefined && phase !== undefined) {
      this.deliver({
        tag: "set",
        vector: {
          kind: "text",
          device: DEVICE,
          name: "ALMANAC",
          state: "Ok",
          perm: "ro",
          elements: [
            {
              kind: "text",
              name: "SUNRISE",
              label: "Sunrise (UTC)",
              value: String(sunrise).replace("T", " "),
            },
            {
              kind: "text",
              name: "SUNSET",
              label: "Sunset (UTC)",
              value: String(sunset).replace("T", " "),
            },
            {
              kind: "text",
              name: "MOON_PHASE",
              label: "Moon phase",
              value: `${moonPhaseName(Number(phase))} (${Number(phase).toFixed(2)})`,
            },
          ],
        } satisfies TextVector,
      });
    }
  }

  /**
   * Drop the readings to Idle rather than leaving them looking current.
   *
   * The three properties `on_disconnect` idles in `examples/openmeteo_device.py`,
   * in the same way: a `set` carrying only a state keeps the last values (the
   * store merges by element name), so the card still reads but stops claiming
   * the reading is good.
   */
  private parkReadings(): void {
    this.deliver({
      tag: "set",
      vector: {
        kind: "number",
        device: DEVICE,
        name: "WEATHER_PARAMETERS",
        state: "Idle",
        perm: "ro",
        elements: [],
      } satisfies NumberVector,
    });
    this.deliver({
      tag: "set",
      vector: {
        kind: "light",
        device: DEVICE,
        name: "WEATHER_STATUS",
        state: "Idle",
        elements: READINGS.map(([, element, label]) => ({
          kind: "light" as const,
          name: element,
          label,
          value: "Idle" as const,
        })),
      } satisfies LightVector,
    });
    this.deliver({
      tag: "set",
      vector: {
        kind: "text",
        device: DEVICE,
        name: "SKY",
        state: "Idle",
        perm: "ro",
        elements: [],
      } satisfies TextVector,
    });
  }

  /** Note whether the page is showing live data or the recording. */
  setLive(live: boolean): void {
    this.live = live;
  }

  /** Whether the last fetch reached the real API. */
  isLive(): boolean {
    return this.live;
  }

  // -- property definitions ------------------------------------------------- //
  /** The CONNECTION switch in one of its two positions. */
  private connectionVector(connected: boolean, state: "Ok" | "Busy" | "Alert"): Vector {
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
        { kind: "switch", name: "CONNECT", label: "Connect", value: connected ? "On" : "Off" },
        {
          kind: "switch",
          name: "DISCONNECT",
          label: "Disconnect",
          value: connected ? "Off" : "On",
        },
      ],
    };
  }

  /** The site coordinates. */
  private siteVector(state: "Ok" | "Busy" | "Alert"): NumberVector {
    return {
      kind: "number",
      device: DEVICE,
      name: "GEOGRAPHIC_COORD",
      label: "Site",
      group: "Site",
      state,
      perm: "rw",
      elements: [
        {
          kind: "number",
          name: "LAT",
          label: "Latitude",
          format: "%.4f",
          min: -90,
          max: 90,
          value: this.latitude,
        },
        {
          kind: "number",
          name: "LONG",
          label: "Longitude",
          format: "%.4f",
          min: -180,
          max: 180,
          value: this.longitude,
        },
      ],
    };
  }

  /** Everything the device exposes, as the Python driver's setup() defines it. */
  private defs(): Vector[] {
    return [
      this.connectionVector(false, "Ok"),
      this.siteVector("Ok"),
      {
        kind: "number",
        device: DEVICE,
        name: "WEATHER_PARAMETERS",
        label: "Conditions",
        group: "Main Control",
        state: "Idle",
        perm: "ro",
        elements: PUBLISHED.map(([, element, label]) => ({
          kind: "number" as const,
          name: element,
          label,
          format: "%.1f",
          value: 0,
        })),
      },
      {
        kind: "light",
        device: DEVICE,
        name: "WEATHER_STATUS",
        label: "Status",
        group: "Main Control",
        state: "Idle",
        elements: READINGS.map(([, element, label]) => ({
          kind: "light" as const,
          name: element,
          label,
          value: "Idle" as const,
        })),
      },
      {
        kind: "text",
        device: DEVICE,
        name: "SKY",
        label: "Sky",
        group: "Main Control",
        state: "Idle",
        perm: "ro",
        elements: [
          { kind: "text", name: "CONDITIONS", label: "Conditions", value: "" },
          { kind: "text", name: "DAYLIGHT", label: "Daylight", value: "" },
        ],
      },
      {
        kind: "text",
        device: DEVICE,
        name: "ALMANAC",
        label: "Almanac",
        group: "Almanac",
        state: "Idle",
        perm: "ro",
        elements: [
          { kind: "text", name: "SUNRISE", label: "Sunrise (UTC)", value: "" },
          { kind: "text", name: "SUNSET", label: "Sunset (UTC)", value: "" },
          { kind: "text", name: "MOON_PHASE", label: "Moon phase", value: "" },
        ],
      },
    ];
  }

  // -- plumbing ------------------------------------------------------------- //
  /** Send one INDI `message` to the client. */
  private sendMessage(text: string): void {
    this.deliver({
      tag: "message",
      device: DEVICE,
      timestamp: new Date().toISOString().slice(0, 19),
      message: text,
    });
  }

  /** Hand one frame to the client as JSON. */
  private deliver(frame: unknown): void {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

/**
 * Fetch live conditions from Open-Meteo, falling back to the recording.
 *
 * The reader's browser calls the real API. When that is not possible - offline,
 * or a network that blocks it - the page still shows the UI working, driven by
 * a response recorded from the real service.
 *
 * @param latitude - Site latitude.
 * @param longitude - Site longitude.
 * @param onLive - Told whether this reply came from the network.
 * @returns The decoded reply.
 */
export async function fetchOpenMeteo(
  latitude: number,
  longitude: number,
  onLive: (live: boolean) => void = () => {},
): Promise<Payload> {
  const query = new URLSearchParams({
    latitude: latitude.toFixed(4),
    longitude: longitude.toFixed(4),
    current: `${PUBLISHED.map(([field]) => field).join(",")},is_day,weather_code`,
    daily: "sunrise,sunset,moon_phase",
    forecast_days: "1",
    timezone: "GMT",
    temperature_unit: "fahrenheit",
    wind_speed_unit: "mph",
  });
  try {
    const response = await fetch(`https://api.open-meteo.com/v1/forecast?${query}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = (await response.json()) as Payload;
    if (!payload.current) throw new Error("no current conditions");
    onLive(true);
    return payload;
  } catch {
    onLive(false);
    return RECORDED;
  }
}
