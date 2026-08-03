# Getting started

By the end of this page you will have a control panel open in your browser, driven by a
driver you wrote yourself. No observatory and no hardware required.

You need [uv](https://docs.astral.sh/uv/) (which manages Python 3.12+ for you) and, for
the web panel, [pnpm](https://pnpm.io) with Node 20+.

## 1. Install

```bash
git clone https://github.com/sidereal-software/indi-nexus && cd indi-nexus

uv venv --python 3.12          # make a Python environment in .venv/
uv pip install -e ".[dev]"     # install INDINexus into it
```

The web panel ships as compiled JavaScript, which needs building once:

```bash
cd web && pnpm install && pnpm -r build && cd ..
```

## 2. Run something

```bash
uv run python -m examples.demo_bridge \
    --device examples.telescope_device:TelescopeSimulator \
    --device examples.dome_device:DomeSimulator
```

This starts two simulated instruments and a web server in a single process. Open
<http://localhost:8000/>.

Both simulators appear in the sidebar. Pick the dome, press **Connect**, then try:

- **Shutter → Open.** The status badge goes `Busy` while it travels, then `Ok`.
- **Absolute Position → 120 → Set.** Watch the azimuth count round to 120.
- **Parking → Park.** It closes the shutter and returns to the park azimuth.

The **Messages** panel is the driver's log - everything the driver told its clients. If
you want to see the raw INDI traffic instead, <http://localhost:8000/debug> shows every
frame as it goes past.

!!! tip "What just happened"

    `demo_bridge` is a development convenience: it wires drivers straight into the web
    app in one process, standing in for `indiserver`. In production the pieces are
    separate - see [Running for real](#4-running-for-real) below.

## 3. Your own driver

```bash
uv run indi-nexus new my_driver.py
```

That writes a complete, commented, runnable driver: a Connect button, a number that gets
polled, and a switch that does something when clicked. Open it and read it - it is short.

Now run *your* driver in the panel:

```bash
uv run python -m examples.demo_bridge --device my_driver:MyDriver
```

`--device` takes `module:ClassName`. Change the file, restart, refresh the browser.

When you want to understand what you are editing, the
[driver guide](guides/writing-drivers.md) walks through a complete driver line by line.

## 4. Running for real

At an observatory the pieces are separate, and the hub is the standard `indiserver`
program that INDI systems are built around:

```bash
# indiserver launches your driver and serves INDI on TCP :7624
indiserver ./my_driver.py

# then, in another terminal, either:
uv run indi-nexus serve       # the web panel at :8000
uv run indi-nexus monitor     # a live feed in the terminal
```

Because your driver is an ordinary INDI driver, other INDI software - KStars/Ekos, PHD2,
existing C++ drivers - connects to the same `indiserver` and works with it unchanged.

!!! note "Running a driver on its own"

    `python -m my_driver` also works, but it will sit there saying nothing. A driver only
    speaks when a client asks it to, and on its own there is no client. It is not hung.
    Paste `<getProperties version="1.7"/>` and press enter to see it reply.

## Where to go next

- **[Writing a driver](guides/writing-drivers.md)** - the main guide. Start here.
- **[The examples](guides/examples.md)** - which example to read for what.
- **[Building a frontend](guides/frontend.md)** - the ready-made panel, and your own UI.
- **[Coming from pyINDI?](guides/porting-from-pyindi.md)** - what maps to what.
- **[Protocol concepts](guides/protocol.md)** - the INDI vocabulary, briefly.
