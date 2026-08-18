# Docker

The image runs `indiserver` and the INDINexus web bridge in one container, so a host
with Docker installed needs nothing else: no libindi, no Python, no Node.

```bash
docker run --rm -p 8000:8000 -p 7624:7624 \
  -e WEB_TOKEN=choose-a-secret \
  ghcr.io/sidereal-software/indi-nexus
```

Then open <http://localhost:8000/?token=choose-a-secret>.

**The token is not optional.** The container publishes its port, so the bridge always
starts with one; leave `WEB_TOKEN` unset and it generates a random token instead and
prints the only URL that works to the container log:

```
indi-nexus: generated a web token. Set WEB_TOKEN to keep it stable across restarts.
indi-nexus: panel on http://localhost:8000/?token=Xb3...
```

Plain <http://localhost:8000/> loads the panel either way, but its WebSocket handshake is
refused with close code 1008 and no devices ever appear - so read the URL out of the log,
or set `WEB_TOKEN` yourself as above and keep it stable across restarts. See
[The token](#the-token) for the rest, including `WEB_ALLOW_ANONYMOUS`.

## Which tag to pull

Images are published to the GitHub Container Registry under
`ghcr.io/sidereal-software/indi-nexus`.

| Tag | Points at | Built for |
|---|---|---|
| `latest` | the newest **release** | `linux/amd64`, `linux/arm64` |
| `0.2.0` | that exact patch release, forever | `linux/amd64`, `linux/arm64` |
| `0.2` | the newest `0.2.x` release | `linux/amd64`, `linux/arm64` |
| `edge` | the tip of `main`, rebuilt on every merge | `linux/amd64` |
| `sha-a1b2c3d` | one exact commit on `main` | `linux/amd64` |

`latest` is the newest *release*, not the newest commit, which is why the commands on
this page can safely leave the tag off. **Pin the patch tag for anything pointed at real
hardware**: an observatory that pulls `latest` gets a different version the day you cut a
release, usually in the dark, usually not on purpose.

`edge` is for tracking development or reproducing a bug report against a known commit,
and it is opt-in by name for that reason. It is `amd64` only, because arm64 has to be
emulated on a CI runner and a release is the thing worth spending that on; a Raspberry Pi
wants a release tag anyway. Release images are native on both, so an Apple Silicon Mac
and an observatory Pi each get a real build.

To build it yourself instead, from a checkout:

```bash
git clone https://github.com/sidereal-software/indi-nexus
cd indi-nexus
docker compose up --build
```

`compose.yaml` leaves `WEB_TOKEN` commented out, so the container generates one and
prints the URL that carries it:

```
indi-nexus: panel on http://localhost:8000/?token=Xb3...
```

Open that URL. Plain <http://localhost:8000/> loads the panel but never connects. To keep
one URL across restarts, uncomment `WEB_TOKEN` in `compose.yaml` and set it.

`indiserver` is on `localhost:7624` at the same time, so KStars, PHD2 or any other INDI
client can drive the same hub while the panel is open. Those are INDI clients rather than
browsers, so they talk to `indiserver` directly and the bridge's token does not apply to
them.

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

Two sets of variables reach this container, and which one to use follows from who reads
it.

**The container's own**, read by `docker/entrypoint.sh`, which turns them into an
`indiserver` command line and `indi-nexus serve` flags. They exist because the entrypoint
composes two processes, which no single `indi-nexus` invocation can be configured to do:

| Variable | Default | Effect |
|---|---|---|
| `INDI_DRIVERS` | `indi_simulator_telescope` | Space-separated drivers: a name on `PATH`, a path to an executable, or a path to a `.py` file. |
| `INDI_DRIVER_DIR` | `/drivers` | A directory whose entries are appended to that list. |
| `INDI_PORT` | `7624` | The port `indiserver` listens on. |
| `WEB_HOST`, `WEB_PORT` | `0.0.0.0`, `8000` | Where the bridge binds. |
| `WEB_TOKEN` | generated | The shared token `/ws` and `/api` require. Left unset, one is generated and printed with the panel's URL on startup; set it to keep that URL stable across a restart. `INDI_NEXUS_TOKEN` is accepted as the same setting. |
| `WEB_ALLOW_ANONYMOUS` | unset | Set to any value to serve with no token: the entrypoint then passes `--allow-insecure-bind` and no `--token` at all. Ignored when a token is set, which wins. Same as `INDI_NEXUS_ALLOW_INSECURE_BIND`. |
| `WEB_ALLOWED_ORIGINS` | unset | Space-separated browser origins to accept in addition to the bridge's own. Same as `INDI_NEXUS_ALLOWED_ORIGINS`, same format. |

**INDINexus's own**, read by `indi-nexus` itself wherever it runs - in this container, on a
host install, or in a driver process `indiserver` launched. They are passed straight
through by Docker, so setting one on the service is all it takes:

| Variable | Default | Effect |
|---|---|---|
| `INDI_NEXUS_LOG_LEVEL` | `INFO` | Level for INDINexus and uvicorn: `CRITICAL`, `ERROR`, `WARNING`, `INFO` or `DEBUG`. |
| `INDI_NEXUS_WIRE_LOG` | unset | Set to `1` for one log line per INDI message in each direction. BLOB payloads are reported by size, never printed. |
| `INDI_NEXUS_CONNECT_TIMEOUT` | `10.0` | Seconds the bridge waits for each attempt to reach `indiserver`. |
| `INDI_NEXUS_RECONNECT_DELAY` | `2.0` | Seconds between a lost upstream connection and the next attempt. |
| `INDI_NEXUS_MESSAGE_HISTORY` | `100` | INDI `message` frames replayed to a browser that has just connected. |
| `INDI_NEXUS_MAX_BACKLOG` | `512` | Live frames a browser may fall behind by before the bridge drops it and it reconnects. |
| `INDI_NEXUS_TOKEN` | unset (generated in this image) | The shared token `/ws` and `/api` require. In this image, `WEB_TOKEN`. |
| `INDI_NEXUS_ALLOWED_ORIGINS` | unset | Space-separated browser origins to accept. In this image, `WEB_ALLOWED_ORIGINS`. |
| `INDI_NEXUS_ALLOW_INSECURE_BIND` | unset | Permit the non-loopback bind with no token anyway. It does **not** turn off a token that is set. In this image, `WEB_ALLOW_ANONYMOUS`, which also drops `--token` - see below. |
| `INDI_NEXUS_CONFIG_DIR` | `$XDG_CONFIG_HOME/indi-nexus`, else `~/.config/indi-nexus`, else nowhere | Where a driver's `CONFIG_PROCESS` saves and loads its properties. **Set it here** - see below. |

**The last three have two names here, and they are the same setting.** The entrypoint has
to decide something about them before `serve` runs - it generates a token when none was
given and prints the panel's URL with it - so it resolves them itself and passes them as
flags, which beat the environment. It reads `WEB_TOKEN` first and falls back to
`INDI_NEXUS_TOKEN`, and likewise for the other two, so either spelling works and the URL
printed at startup is the one that opens. Set one of each pair, not both; `WEB_*` is the
name to prefer in this image, and `INDI_NEXUS_*` is what you use when you run `indi-nexus`
yourself.

`ALLOW_INSECURE_BIND` is narrower than its container spelling suggests, and it is worth
being exact about because it is the one variable here that gives something away. On its
own it only **permits a non-loopback bind that has no token**; `serve` refuses that bind
otherwise. It never disables a token that is configured. What actually serves the panel
anonymously in this image is the entrypoint: when `WEB_ALLOW_ANONYMOUS` is set and no
token is, it starts `serve` with `--allow-insecure-bind` and **no `--token`**, so there
is no token to check. Set a token as well and the token wins, on a bind that no longer
needs the permission.

**A driver's saved configuration lives in the container's filesystem and dies with it.**
An INDINexus driver that publishes `CONFIG_PROCESS` writes under `INDI_NEXUS_CONFIG_DIR`,
and a libindi driver writes under `$HOME/.indi`; neither survives `docker run --rm` or an
image upgrade. Keep both by mounting a volume and pointing the variable into it:

```bash
docker run --rm -p 8000:8000 -p 7624:7624 \
  -v indi-config:/config -e INDI_NEXUS_CONFIG_DIR=/config \
  ghcr.io/sidereal-software/indi-nexus
```

Set it even if you do not care where the file lands. The default is computed rather than
fixed - `$XDG_CONFIG_HOME/indi-nexus`, else `~/.config/indi-nexus`, else **nothing at
all** - and a container is exactly where that last case turns up, because `HOME` is
routinely unset or points somewhere read-only. With nowhere to write, every Save, Load and
Purge comes back as a `ConfigError` naming `INDI_NEXUS_CONFIG_DIR` as the fix, and the
panel reports the failure on the property. That is deliberate: the alternative is a
temporary directory that accepts every Save and loses the lot on restart.

Turning the log up is the usual first move when a driver is not appearing:

```bash
docker run --rm -p 8000:8000 -p 7624:7624 \
  -e INDI_NEXUS_LOG_LEVEL=DEBUG -e INDI_NEXUS_WIRE_LOG=1 \
  ghcr.io/sidereal-software/indi-nexus
```

## The token

The container publishes its port, so the panel and `/ws` are reachable by anything
that can reach the host - and `/ws` is the write surface: a frame sent there becomes
an INDI `new*` that moves hardware. So the bridge always starts with a token, and the
startup log prints the URL that carries it:

```
indi-nexus: panel on http://localhost:8000/?token=Xb3...
```

Open that URL and the panel connects; it carries the token from its own address to
the WebSocket, which is the only place a browser can put one and the only route that
accepts `?token=`. `/api` takes `Authorization: Bearer <token>` and nothing else, so
`curl` and other non-browser clients use the header there:

```
curl -H 'Authorization: Bearer Xb3...' http://localhost:8000/api/devices
```

`/health` needs no token, because the image's health check calls it. It reports liveness,
the upstream link and a few counters, and deliberately carries no release version, no
addresses and no device names - see
[the bridge's HTTP surface](https://github.com/sidereal-software/indi-nexus/blob/main/DEVELOPMENT.md#the-bridges-http-surface)
for the body.

Browsers apply neither the same-origin policy nor CORS to WebSockets, so the bridge
also checks the handshake's `Origin` against its own and refuses anything else. A
front end served from another origin needs `WEB_ALLOWED_ORIGINS`.

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
