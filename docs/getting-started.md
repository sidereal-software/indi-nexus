# Getting started

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12+) and, for the
frontend, [pnpm](https://pnpm.io) (Node 20+).

## Install and run the whole stack

The fastest way to see everything - backend, bridge, and web panel - with no
`indiserver` needed:

```bash
git clone https://github.com/sidereal-software/indi-nexus && cd indi-nexus

# 1. Backend: create the venv and install
uv venv --python 3.12
uv pip install -e ".[dev]"

# 2. Frontend: build the panel into the package
cd web && pnpm install && pnpm -r build && cd ..

# 3. Run the demo bridge: the web app wired to live in-process drivers
uv run python -m examples.demo_bridge \
    --device examples.telescope_device:TelescopeSimulator \
    --device examples.dome_device:DomeSimulator
```

Open <http://localhost:8000/> - both simulators appear in the panel's sidebar.
Connect one, slew it, park it, and watch the Messages log. The raw-frame
debug inspector lives at <http://localhost:8000/debug>.

## Your first driver, in one minute

```bash
uv run indi-nexus new my_driver.py
uv run python -m examples.demo_bridge --device my_driver:MyDriver
```

The scaffold is a complete, commented driver: a `CONNECTION` lifecycle, a
polled telemetry number, and a handled switch. Edit it live and reload.

## The three ways to run a driver

```bash
# 1. The web panel (easiest): drivers + bridge + UI in one process.
python -m examples.demo_bridge --device my_driver:MyDriver

# 2. Under a real C indiserver (the production arrangement), serving TCP :7624:
indiserver ./my_driver.py
indi-nexus serve        # ...then the panel at :8000
indi-nexus monitor      # ...or a terminal feed

# 3. Bare stdio (what indiserver itself launches) - only useful to pipe XML at:
echo '<getProperties version="1.7"/>' | python -m my_driver
```

Mode 3 waits **silently** for a `getProperties` before saying anything - it is
not hung, it just has no client yet.

## Next steps

- [Writing a driver](guides/writing-drivers.md) - the SDK tour.
- [Building a frontend](guides/frontend.md) - hooks and components.
- [The examples](guides/examples.md) - dome and telescope simulators, ported
  from libindi's C++.
