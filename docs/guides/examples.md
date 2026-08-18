---
search:
  boost: 2
---

# The examples

Every file in `examples/` runs, and the test suite covers all of them, so none of it can
quietly rot. There are eleven of them, which is more than anyone should read in order.
This page is the order.

## Start here, in this order

**`flat_panel.py` first.** A flat-field lamp: a switch to turn it on, a number for its
brightness, and the standard `CONNECTION` switch. That is the whole instrument, which makes
it the shortest thing here that is still a real driver, and the one the
[driver guide](writing-drivers.md) builds line by line. It already shows the shape every
real driver needs: commands refused while the link is down, and `on_disconnect` leaving the
hardware safe - here, putting the lamp out, because a panel left lit fogs the next
exposure. You can [operate it in your browser](../flat-demo/flat.html) without installing
anything.

**`weather_device.py` second.** Everything after it is a variation on it. The other
examples simulate their hardware inside the driver, so none of them has to cope with an
instrument that is slow, absent, or lying. This one does:

- the instrument is a blocking client, standing in for `pyserial`, a vendor SDK or an
  HTTP session, reached through `off_thread` so a slow read cannot freeze the driver;
- when the station stops answering, the readings drop to `Idle` rather than sitting there
  looking current, and it says so *once* instead of once a second;
- `SENSOR_INFO` is read off the station, so it is defined in `on_connect` and withdrawn
  with `delete_property` in `on_disconnect` - a property that only exists while the
  hardware does;
- its readings are `on_change`, so a steady night is quiet on the wire;
- and `tests/test_weather_example.py` tests all of that with no hardware at all.

## Then pick one by what you need

| You want | Read | For |
|---|---|---|
| images, and a long operation that reports progress | `ccd_device.py` | a BLOB published from a frame rendered off the event loop, plus a cooler with believable warm-up physics |
| several devices in one driver process | `guided_camera.py` | a camera and its guide chip behind one shared link, ending in `run([MainChip(), GuideChip()])` |
| a full instrument's property vocabulary | `dome_device.py`, then `telescope_device.py` | the dome is the one to *read* - two axes, park, abort, and the driver behind the [live demo](../demo-app/index.html). The telescope is the one to *refer to*: goto/sync, tracking modes with real sky drift, slew rates, paddles and guide pulses, in the standard mount property names |
| real data, end to end, today | `openmeteo_device.py` | a driver for [Open-Meteo](https://open-meteo.com) - a free public API with no account and no key. The [tutorial](tutorial-open-meteo.md) builds it step by step and then puts a custom screen on it; you can [see both running](../weather-demo/weather.html) |
| all four property kinds on one screen | `demo_device.py` | a number, a text and a light, plus a power switch gating a once-a-second animation. It is also the device the CLI documentation and the integration tests use as a stand-in driver |

Every one of them defines a `CONNECTION` switch, refuses commands while disconnected,
pauses its timers with the link, and leaves the instrument safe on the way out. That is not
decoration; it is what [the driver guide](writing-drivers.md#connecting-and-disconnecting)
means by a driver being finished.

## The client side

The same library talks the other way, and three examples cover the three things a client
is ever doing.

- **`monitor_client.py` - watching.** Connects, subscribes to everything, and prints each
  change as it happens. The shortest of the three, and the one to read first.
- **`scripted_session.py` - driving.** A client used as a script: connect a mount, point
  it, wait for it to arrive, exit. It is where `wait_for` earns its place - a timeout
  instead of a poll loop, and a detached snapshot of the value that satisfied it - and
  where the rule that **a send with no connection raises rather than being queued** is
  visible, because a slew delivered an hour late would reach a mount pointing somewhere
  else. One `except IndiError` at the top covers everything the library raises on purpose.
- **`blob_receiver.py` - collecting images.** Takes an exposure and writes the FITS to
  disk. It exists for `enable_blob`: **without that call `indiserver` forwards no BLOB at
  all, and reports no error**, which is the usual reason an image never arrives.

Each takes an already-connected client, so the logic is importable and testable. These
speak INDI over TCP, so they want a real `indiserver` rather than `serve --device`, which
puts its drivers behind the web bridge and opens no INDI port:

```bash
indiserver ./examples/ccd_device.py ./examples/telescope_device.py   # terminal 1

python examples/blob_receiver.py                                     # terminal 2
python examples/scripted_session.py                                  # ...and this one
```

## The frontend side

The browser examples live in `web/apps/panel/demo/`, not in `examples/`: `dome-sim.ts`,
`weather-sim.ts` and `flat-panel-sim.ts` are TypeScript ports of the drivers above behind
a fake socket, which is how the demos linked from this page run with no server at all, and
`sky-report.tsx` is the tutorial's custom wallboard UI. The
[frontend guide](frontend.md) is the way in.

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
