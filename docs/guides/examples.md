# The examples

Runnable references live in `examples/` - each one is also how the framework
tests itself.

- **`demo_device.py`** - the reference driver: one of each INDI vector kind
  and a power switch gating a once-per-second animation.
- **`dome_device.py`** - libindi's classic Dome Simulator ported to the
  INDINexus SDK: connection, azimuth rotation (shortest way around), a timed
  shutter, park/unpark sequencing, abort, and speed limits - the ~300-line C++
  class as one compact typed device.
- **`telescope_device.py`** - libindi's Telescope Simulator: the standard
  goto/slew/sync interaction (`EQUATORIAL_EOD_COORD` + `ON_COORD_SET`),
  tracking modes with realistic sky drift when not tracking, slew rates,
  motion paddles, park, abort, and timed guide pulses.
- **`ccd_device.py`** - libindi's CCD Simulator: exposures counting down to a
  rendered 16-bit FITS star field (the `CCD1` BLOB), frame types, binning,
  gain/offset, and a TEC cooler with realistic cooling and warm-up physics.
- **`monitor_client.py`** - the reference client: subscribe to everything and
  print each event.
- **`demo_bridge.py`** - the whole stack in one process: one or more drivers
  wired into the web app through in-memory pipes (a miniature `indiserver`).

Run any of them in the panel:

```bash
python -m examples.demo_bridge \
    --device examples.telescope_device:TelescopeSimulator \
    --device examples.ccd_device:CCDSimulator \
    --device examples.dome_device:DomeSimulator
```

Or under a real hub:
`indiserver ./examples/telescope_device.py ./examples/ccd_device.py ./examples/dome_device.py`.
