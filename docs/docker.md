# Docker

The image runs `indiserver` and the INDINexus web bridge in one container, so a host
with Docker installed needs nothing else: no libindi, no Python, no Node.

```bash
git clone https://github.com/sidereal-software/indi-nexus
cd indi-nexus
docker compose up --build
```

Open <http://localhost:8000/>. `indiserver` is on `localhost:7624` at the same time, so
KStars, PHD2 or any other INDI client can drive the same hub while the panel is open.

With nothing configured the container runs libindi's telescope simulator, so there is a
device on screen before you have written anything.

## Running your own drivers

`compose.yaml` mounts the repository's `drivers/` directory read-only at `/drivers`.
Everything in there is launched under `indiserver` alongside whatever `INDI_DRIVERS`
names:

```bash
cp my_driver.py drivers/
docker compose up
```

Two kinds of file are recognised:

- A `.py` driver written against the INDINexus SDK. It does not need to be executable:
  the container writes a shim that runs it under the interpreter the package is
  installed into, which is both how `indiserver` gets something it can `exec` and how
  your driver gets `indi_nexus` on its import path.
- Any other executable program, meaning a compiled driver or a script with a `#!` line.

Anything else is skipped, with a line in the log saying so.

To run a driver already in the image, or one you mounted somewhere else, name it in
`INDI_DRIVERS`. The example drivers are at `/opt/indi-nexus/examples`, and `indi-nexus`
below is the image tag `docker compose` builds:

```bash
docker run --rm -p 8000:8000 -p 7624:7624 \
  -e INDI_DRIVERS="indi_simulator_ccd /opt/indi-nexus/examples/flat_panel.py" \
  indi-nexus
```

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `INDI_DRIVERS` | `indi_simulator_telescope` | Space-separated drivers: a name on `PATH`, a path to an executable, or a path to a `.py` file. |
| `INDI_DRIVER_DIR` | `/drivers` | A directory whose entries are appended to that list. |
| `INDI_PORT` | `7624` | The port `indiserver` listens on. |
| `WEB_HOST`, `WEB_PORT` | `0.0.0.0`, `8000` | Where the bridge binds. |

The container exits when either process ends, so a driver that takes the hub down with
it is restarted by Docker rather than leaving half a stack still answering on `:8000`.
The health check reports healthy only once the bridge is answering *and* connected to
the hub.

## Hardware

A container sees no USB device unless it is given one. Pass the port through on the
`indi-nexus` service in `compose.yaml`:

```yaml
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0
```

A driver that finds its instrument by broadcasting on the local network needs
`network_mode: host` instead. That one cannot be combined with `ports`, so delete the
port mapping when you add it: the container is then on the host's network and its ports
are already the host's. Neither is on by default, because the first thing most people
run here is a simulator.

## Building the image

```bash
docker build -f docker/Dockerfile -t indi-nexus .
```

The build compiles the TypeScript panel with pnpm and installs the resulting wheel, so
the image serves the real panel and not the fallback debug page. It runs as a non-root
user, and builds on `amd64` and `arm64`.

## Running the interop suite

The same Dockerfile has a `test` target holding the repository, the development
dependencies, a browser and libindi. That makes `tests/interop/` runnable on a machine
with no libindi, which includes every Mac:

```bash
docker compose --profile interop run --rm --build interop
```

It runs `pytest tests/interop` against a real `indiserver` and real C++ drivers, which
otherwise only happens in the nightly CI job. Pass a command to narrow it:

```bash
docker compose --profile interop run --rm interop pytest tests/interop/test_smoke.py -q
```
