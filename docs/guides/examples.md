# The examples

Everything in `examples/` runs, and every one is covered by the test suite, so none of it
can quietly rot.

## Which one should I read?

| If you want to... | Read |
|---|---|
| See the smallest complete driver | `demo_device.py` |
| **Write a driver for real hardware** | **`weather_device.py`** |
| See a realistic instrument with motion and state | `dome_device.py` |
| See pointing and tracking | `telescope_device.py` |
| See images and long-running operations | `ccd_device.py` |
| **Talk to a real, public data source** | **`openmeteo_device.py`** |
| Talk *to* an observatory instead of being one | `monitor_client.py` |

### `demo_device.py` - the smallest complete driver

One property of every kind, and a power switch that starts and stops a once-a-second
animation. Read this first to see the shape of a driver with nothing else going on.

### `weather_device.py` - the one to copy

The other examples simulate their hardware inside the driver, so none of them has to cope
with an instrument that is slow, absent, or lying. This one is built the way a real site
driver is, and is the one worth copying:

- the instrument is a **blocking** client - standing in for `pyserial`, a vendor SDK, or
  an HTTP session - reached through `off_thread` so a slow read cannot freeze the driver;
- it has the standard Connect lifecycle, and stops polling when disconnected;
- when the station stops answering, the readings drop to `Idle` rather than sitting there
  looking current, and it says so *once* instead of once a second;
- its readings are `on_change`, so a steady night is quiet on the wire;
- and `tests/test_weather_example.py` tests all of that with no hardware at all.

### `openmeteo_device.py` - real data, no hardware

A driver for [Open-Meteo](https://open-meteo.com), a free public weather API
with no account and no key - so it works the moment you run it. It reports sky
conditions, safety lights, and today's sun and moon for a site you can move from
the panel. The [tutorial](tutorial-open-meteo.md) builds it step by step and
then puts a custom screen on it.

### `dome_device.py` - a realistic instrument

libindi's classic Dome Simulator, rebuilt on INDINexus. Connect, rotate to an azimuth the
short way round, open and close a shutter over time, park, unpark, abort. It uses the
standard INDI dome property names, so any INDI client recognises it. This is also the
driver behind the [live demo](../index.md#see-it-working).

### `telescope_device.py` - pointing and tracking

The standard goto/slew/sync interaction, tracking modes with realistic sky drift when not
tracking, slew rates, motion paddles, park, abort, and timed guide pulses.

### `ccd_device.py` - images and long operations

Exposures that count down and deliver a rendered 16-bit FITS star field as a BLOB, plus
frame types, binning, gain and offset, and a cooler with believable warm-up physics. Read
it for how a long-running operation reports progress.

### `monitor_client.py` - the other side

Not a driver. Connects to a running observatory, subscribes to everything, and prints each
change as it happens - about fifteen lines.

## Running them

The quickest way is the development bridge, which puts drivers and the web panel in one
process. Repeat `--device` for as many as you like:

```bash
python -m examples.demo_bridge \
    --device examples.telescope_device:TelescopeSimulator \
    --device examples.ccd_device:CCDSimulator \
    --device examples.dome_device:DomeSimulator
```

Open <http://localhost:8000/> and all three are in the sidebar.

To run them the way an observatory does, hand them to `indiserver` instead:

```bash
indiserver ./examples/telescope_device.py ./examples/dome_device.py
indi-nexus serve      # the panel, now talking to indiserver on :7624
```
