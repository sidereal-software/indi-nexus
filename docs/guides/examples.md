---
search:
  boost: 2
---

# The examples

Every file in `examples/` runs, and the test suite covers all of them, so none of it can
quietly rot.

Read `flat_panel.py` first: it is the shortest thing here that is still a real driver. Then
`demo_device.py` for the shape of a bigger one, and `weather_device.py` when you are ready
to talk to actual hardware. The rest are there when you need them.

## `flat_panel.py` - the shortest real driver

A flat-field lamp: a switch to turn it on and a number for its brightness. That is the
whole instrument, which makes it the smallest driver that still has both kinds of control,
and the one the [driver guide](writing-drivers.md) builds line by line. It carries the
standard `CONNECTION` switch too, so it also shows the shape every real driver needs:
commands refused while the link is down, and `on_disconnect` leaving the hardware safe.
Here that means putting the lamp out, because a panel left lit fogs the next exposure. You
can [operate it in your browser](../flat-demo/flat.html) without installing anything.

## `demo_device.py` - the reference driver

A number, a text and a light, plus a power switch that starts and stops a once-a-second
animation. Nothing else going on, so the shape of a driver is easy to see. (For a BLOB,
read `ccd_device.py` below.)

## `weather_device.py` - the one to copy

The other examples simulate their hardware inside the driver, so none of them has to cope
with an instrument that is slow, absent, or lying. This one does:

- the instrument is a blocking client, standing in for `pyserial`, a vendor SDK or an
  HTTP session, reached through `off_thread` so a slow read cannot freeze the driver;
- when the station stops answering, the readings drop to `Idle` rather than sitting there
  looking current, and it says so *once* instead of once a second;
- its readings are `on_change`, so a steady night is quiet on the wire;
- and `tests/test_weather_example.py` tests all of that with no hardware at all.

## `openmeteo_device.py` - real data, no hardware

A driver for [Open-Meteo](https://open-meteo.com), a free public weather API that needs
no account and no key, so it works the moment you run it. It reports sky conditions,
safety lights, and today's sun and moon for a site you can move from the panel. The
[tutorial](tutorial-open-meteo.md) builds it step by step and then puts a custom screen
on it, and you can [see both running](../weather-demo/weather.html) without installing
anything.

## `dome_device.py` - a realistic instrument

libindi's classic Dome Simulator, rebuilt on INDINexus. Connect, rotate to an azimuth the
short way round, open and close a shutter over time, park, unpark, abort. It uses the
standard INDI dome property names, so any INDI client recognises it. This is also the
driver behind the [live demo](../demo-app/index.html).

## `telescope_device.py` - pointing and tracking

The standard goto/slew/sync interaction, tracking modes with realistic sky drift when not
tracking, slew rates, motion paddles, park, abort, and timed guide pulses.

## `ccd_device.py` - images and long operations

Exposures that count down and deliver a rendered 16-bit FITS star field as a BLOB, plus
frame types, binning, gain and offset, and a cooler with believable warm-up physics. Read
it for how a long-running operation reports progress.

## `monitor_client.py` - the client side

The one example that is a client rather than a driver. It connects to a running
observatory, subscribes to everything, and prints each change as it happens, in about
fifteen lines.

## Running them

The quickest way to look at one is `--device`, which runs the drivers inside the web
process so there is no `indiserver` to install first. Repeat it for as many as you like:

```bash
indi-nexus serve \
    --device examples.telescope_device:TelescopeSimulator \
    --device examples.ccd_device:CCDSimulator \
    --device examples.dome_device:DomeSimulator
```

Open <http://localhost:8000/> and all three are in the sidebar.

`--device` is for looking at a driver rather than for running an observatory. A real
setup hands the same files to `indiserver`, which is what lets KStars, PHD2 and the panel
all drive them at once:

```bash
indiserver ./examples/telescope_device.py ./examples/dome_device.py
indi-nexus serve      # the panel, now talking to indiserver on :7624
```
