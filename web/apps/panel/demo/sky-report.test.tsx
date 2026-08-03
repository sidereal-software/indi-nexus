/**
 * Renders the documentation's custom UI against the vectors the Open-Meteo
 * driver really emits.
 *
 * The values here are the ones `tests/test_openmeteo_example.py` asserts on the
 * Python side, taken from a recorded Open-Meteo response - so this checks the
 * two halves of the tutorial actually meet.
 */

import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SkyReport } from "./doc-snippets";
import { receive, renderConnected } from "./testing/render";

afterEach(cleanup);

/** Feed the harness the four properties the Open-Meteo driver publishes. */
function publishWeather(socket: Parameters<typeof receive>[0]) {
  receive(socket, {
    tag: "def",
    vector: {
      kind: "number",
      device: "Open-Meteo",
      name: "WEATHER_PARAMETERS",
      state: "Ok",
      perm: "ro",
      elements: [
        { kind: "number", name: "TEMPERATURE", label: "Temperature (°F)", value: 66.9 },
        { kind: "number", name: "HUMIDITY", label: "Humidity (%)", value: 95 },
        { kind: "number", name: "CLOUD_COVER", label: "Cloud cover (%)", value: 31 },
        { kind: "number", name: "WIND_SPEED", label: "Wind speed (mp/h)", value: 2.4 },
        { kind: "number", name: "WIND_GUST", label: "Wind gust (mp/h)", value: 2.5 },
      ],
    },
  });
  receive(socket, {
    tag: "def",
    vector: {
      kind: "light",
      device: "Open-Meteo",
      name: "WEATHER_STATUS",
      state: "Alert",
      elements: [
        { kind: "light", name: "TEMPERATURE", value: "Ok" },
        { kind: "light", name: "HUMIDITY", value: "Alert" },
        { kind: "light", name: "CLOUD_COVER", value: "Alert" },
        { kind: "light", name: "WIND_SPEED", value: "Ok" },
        { kind: "light", name: "WIND_GUST", value: "Ok" },
      ],
    },
  });
  receive(socket, {
    tag: "def",
    vector: {
      kind: "text",
      device: "Open-Meteo",
      name: "SKY",
      state: "Ok",
      perm: "ro",
      elements: [
        { kind: "text", name: "CONDITIONS", value: "Mainly clear" },
        { kind: "text", name: "DAYLIGHT", value: "Night" },
      ],
    },
  });
  receive(socket, {
    tag: "def",
    vector: {
      kind: "text",
      device: "Open-Meteo",
      name: "ALMANAC",
      state: "Ok",
      perm: "ro",
      elements: [
        { kind: "text", name: "SUNRISE", value: "2026-08-03 13:06" },
        { kind: "text", name: "SUNSET", value: "2026-08-04 02:52" },
        { kind: "text", name: "MOON_PHASE", value: "Waning gibbous (0.66)" },
      ],
    },
  });
}

describe("the tutorial's custom UI", () => {
  it("renders nothing alarming before any data arrives", () => {
    renderConnected(<SkyReport />);

    expect(screen.getByText("Waiting for data")).toBeInTheDocument();
    expect(screen.getAllByText("--").length).toBeGreaterThan(0);
  });

  it("shows the conditions, the almanac and every reading", () => {
    const { socket } = renderConnected(<SkyReport />);
    publishWeather(socket);

    expect(screen.getByText("Mainly clear")).toBeInTheDocument();
    expect(screen.getByText(/Night/)).toBeInTheDocument();
    expect(screen.getByText(/Waning gibbous/)).toBeInTheDocument();
    expect(screen.getByText("66.9")).toBeInTheDocument();
    expect(screen.getByText("31")).toBeInTheDocument();
  });

  it("reports the site as unsafe while any reading is in Alert", () => {
    const { socket } = renderConnected(<SkyReport />);
    publishWeather(socket);

    expect(screen.getByText("Not safe to open.")).toBeInTheDocument();
  });

  it("flips to safe when the driver clears the alert", () => {
    const { socket } = renderConnected(<SkyReport />);
    publishWeather(socket);

    receive(socket, {
      tag: "set",
      vector: {
        kind: "light",
        device: "Open-Meteo",
        name: "WEATHER_STATUS",
        state: "Ok",
        elements: [
          { kind: "light", name: "HUMIDITY", value: "Ok" },
          { kind: "light", name: "CLOUD_COVER", value: "Ok" },
        ],
      },
    });

    expect(screen.getByText("Safe to open.")).toBeInTheDocument();
  });

  it("updates one reading in place when the driver publishes a change", () => {
    const { socket } = renderConnected(<SkyReport />);
    publishWeather(socket);

    receive(socket, {
      tag: "set",
      vector: {
        kind: "number",
        device: "Open-Meteo",
        name: "WEATHER_PARAMETERS",
        state: "Ok",
        perm: "ro",
        elements: [{ kind: "number", name: "CLOUD_COVER", value: 4 }],
      },
    });

    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("66.9")).toBeInTheDocument(); // untouched
  });
});
