---
search:
  boost: 2
---

# Getting started

By the end of this page you will have a control panel open in your browser, driven by a
driver you wrote yourself, with no observatory and no hardware.

Python 3.12 or newer is the only requirement. The panel ships compiled inside the package,
so you do not need Node or a JavaScript build.

Steps 2 and 3 use a stand-in for `indiserver` built into the CLI, so this page needs one
install. INDIkit plugs into the real hub rather than replacing it, and
[step 4](#4-running-under-indiserver) swaps it in without changing your driver.

!!! tip "Trying it without installing"

    The [live demo](demo-app/index.html) runs the real panel against a simulated dome and
    a simulated weather station inside your browser, with nothing to install.

## 1. Install

```bash
pip install indikit
```

Or with [uv](https://docs.astral.sh/uv/), which will fetch a suitable Python for you:

```bash
uv tool install indikit
```

## 2. Write a driver

```bash
indikit new my_driver.py
```

That writes a complete, commented driver: a Connect button, a number polled once a second,
and a switch. Read through it. The [driver guide](guides/writing-drivers.md) explains
every part.

## 3. Run it

```bash
indikit serve --device my_driver:MyDriver
```

Open <http://localhost:8000/>. Your device is in the sidebar. Two things to try:

- Press Connect. The Telemetry value counts up once a second and stops when you
  disconnect, because the `@every` job behind it runs only while connected.
- Set Power to On. A line appears in the Messages panel: the driver's log of everything it
  has told its clients.

Edit the file, restart the command, and refresh the browser to see the change.

`--device` takes `module:ClassName` and can be repeated, so you can run several drivers
side by side.

!!! warning "`--device` is for trying things out"

    Run anything real under `indiserver`. `--device` puts your drivers inside the web
    process: one client, and they stop when you stop the command. That is a development
    convenience, not a hub.

    Access control is the same either way. `--token` and `--allow-origin` work with
    `--device`, and `serve` refuses a non-loopback `--host` that has no `--token` unless
    you pass `--allow-insecure-bind`.

!!! note "Where the worked examples live"

    A focuser, a telescope, a dome, a camera, a flat-field lamp and two weather stations
    (one simulated, one on a live public API) are in the [examples](guides/examples.md),
    each runnable and covered by tests.

    They ship with the source rather than the wheel, so `git clone` the repository to run
    them locally. The dome and the live weather station also run together
    [in your browser](index.md#see-it-running), on one page.

## 4. Running under indiserver

Once your driver talks to hardware, it belongs here. This is how an observatory runs.
`indiserver` launches drivers as child processes and serves their combined stream on TCP,
which is what lets several clients watch the same instruments at once.

`indiserver` comes with [libindi](https://github.com/indilib/indi): `apt install indi-bin`
on Debian and Ubuntu, and packaged for most other Linux distributions. There is no macOS
package, so build it from source or run it in a container.

The same file that ran under `--device` runs here, unchanged:

```bash
# indiserver launches your driver and serves INDI on TCP :7624
indiserver ./my_driver.py

# then, in another terminal, either:
indikit serve       # the web panel at :8000, against indiserver
indikit monitor     # a live feed in the terminal
```

`indikit serve` without `--device` connects to `indiserver` instead of running drivers
itself. That is the only difference between the two setups.

Other INDI software (KStars/Ekos, PHD2, existing C++ drivers) connects to the same
`indiserver` and drives your driver unchanged, at the same time as the panel does. Nothing
extra is needed for that: your driver is an ordinary INDI driver.

!!! note "Running a driver on its own"

    `python ./my_driver.py` also works, and it will sit there saying nothing. That is not
    a hang. A driver speaks only when a client asks it to, and on its own there is no
    client. Paste `<getProperties version="1.7"/>` and press enter to see it reply.

## Where to go next

- [Writing a driver](guides/writing-drivers.md) - the main guide. Start here.
- [The examples](guides/examples.md) - which example to read for what.
- [Building a frontend](guides/frontend.md) - the ready-made panel, and your own UI.
- [Porting a pyINDI driver](guides/porting-from-pyindi.md) - what maps to what.
- [Protocol concepts](guides/protocol.md) - the INDI vocabulary, briefly.
