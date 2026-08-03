/**
 * Renders the documentation's custom UI against the vectors the Open-Meteo
 * driver really emits.
 *
 * The values here are the ones `tests/test_openmeteo_example.py` asserts on the
 * Python side, taken from a recorded Open-Meteo response - so this checks the
 * two halves of the tutorial actually meet.
 */

import { receive, renderConnected } from "@indi-nexus/react/testing";
import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SkyReport } from "./sky-report";

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
        { kind: "number", name: "PRESSURE", label: "Pressure (hPa)", value: 1008.2 },
        { kind: "number", name: "WIND_DIRECTION", label: "Wind from (°)", value: 304 },
        { kind: "number", name: "FEELS_LIKE", label: "Feels like (°F)", value: 71.6 },
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
        { kind: "light", name: "PRESSURE", value: "Ok" },
      ],
    },
  });
  receive(socket, {
    tag: "def",
    vector: {
      kind: "number",
      device: "Open-Meteo",
      name: "GEOGRAPHIC_COORD",
      state: "Ok",
      perm: "rw",
      elements: [
        { kind: "number", name: "LAT", label: "Latitude", value: 34.0522 },
        { kind: "number", name: "LONG", label: "Longitude", value: -118.2437 },
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

    expect(screen.getByText("Not safe to open")).toBeInTheDocument();
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

    expect(screen.getByText("Safe to open")).toBeInTheDocument();
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

describe("the dashboard's figures", () => {
  it("names the wind's bearing as a compass point, not just degrees", () => {
    const { socket } = renderConnected(<SkyReport />);
    publishWeather(socket);

    // 304° is north-west; the badge says so in words as well as numbers.
    expect(screen.getByText(/from NW 304/)).toBeInTheDocument();
  });

  it("labels the wind compass for a screen reader", () => {
    const { socket } = renderConnected(<SkyReport />);
    publishWeather(socket);

    expect(screen.getByRole("img", { name: /Wind from 304 degrees, NW/ })).toBeInTheDocument();
  });

  it("shows the site coordinates and maps them", () => {
    const { socket } = renderConnected(<SkyReport />);
    publishWeather(socket);

    expect(screen.getByText("34.05, -118.24")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Site at 34.05, -118.24/ })).toBeInTheDocument();
  });

  it("draws the moon at its illuminated fraction", () => {
    const { socket } = renderConnected(<SkyReport />);
    publishWeather(socket);

    // phase 0.66 -> a touch past last-quarter-to-full, ~78% lit.
    expect(screen.getByRole("img", { name: /Moon 7[0-9]% illuminated/ })).toBeInTheDocument();
  });

  it("shows the feels-like temperature beside the hero reading", () => {
    const { socket } = renderConnected(<SkyReport />);
    publishWeather(socket);

    expect(screen.getByText("66.9")).toBeInTheDocument();
    expect(screen.getByText("feels like 71.6°")).toBeInTheDocument();
  });

  it("renders every figure before any data arrives", () => {
    renderConnected(<SkyReport />);

    expect(screen.getByText("Waiting for data")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Wind direction unknown" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Site unknown" })).toBeInTheDocument();
  });
});
