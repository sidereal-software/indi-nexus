# Getting started

By the end of this page you will have a control panel open in your browser, driven by a
driver you wrote yourself. No observatory and no hardware.

You need Python 3.12 or newer, and nothing else: the web panel is compiled into the
package, so there is no Node and no JavaScript build.

An observatory runs its drivers under `indiserver`, the hub every INDI system is built
around, and so should you once you have hardware. INDINexus plugs into it rather than
replacing it. To keep this page to one install, steps 2 and 3 use a stand-in for it that
is built into the CLI, and [step 4](#4-running-under-indiserver) swaps in the real thing
without changing your driver.

!!! tip "Just want to look first?"

    The [live demo](demo-app/index.html) runs the real panel against a simulated dome
    inside your browser. Nothing to install at all.

## 1. Install

```bash
pip install indi-nexus
```

Or with [uv](https://docs.astral.sh/uv/), which will fetch a suitable Python for you:

```bash
uv tool install indi-nexus
```

## 2. Write a driver

```bash
indi-nexus new my_driver.py
```

That writes a complete, commented, runnable driver: a Connect button, a number that gets
polled once a second, and a switch that does something when clicked. Open it and read it.
It is short, and every part of it is explained in the
[driver guide](guides/writing-drivers.md).

## 3. See it

```bash
indi-nexus serve --device my_driver:MyDriver
```

Open <http://localhost:8000/>. Your device is in the sidebar. Try this:

- **Press Connect.** The Telemetry value starts counting up once a second, and stops when
  you disconnect. That is the `@every` job, which only runs while connected.
- **Set Power to On.** A line appears in the **Messages** panel, which is the driver's log:
  everything the driver has told its clients.

Edit the file, restart the command, and refresh the browser to see the change.

`--device` takes `module:ClassName` and can be repeated, so you can run several drivers
side by side.

!!! warning "`--device` is for trying things out"

    It runs your drivers inside the web process, standing in for `indiserver` so that this
    page needs one install instead of two. It serves a single client, has no access
    control, and stops when you stop the command. It is a development convenience, not a
    hub: run anything real under `indiserver`.

!!! note "Where the worked examples live"

    A telescope, a dome, a camera, a flat-field lamp and a weather station are in the
    [examples](guides/examples.md), each one runnable and covered by tests. They ship with
    the source rather than the wheel, so `git clone` the repository if you want to run them
    locally. Two of them also run [in your browser](index.md#see-it-working).

## 4. Running under indiserver

This is how an observatory runs, and where your driver belongs once it talks to hardware.
`indiserver` launches drivers as child processes and serves their combined stream on TCP,
which is what lets several clients watch the same instruments at once. It comes with
[libindi](https://github.com/indilib/indi), packaged for most Linux distributions and
available through Homebrew on macOS.

Nothing about your driver changes. The same file that ran under `--device` runs here:

```bash
# indiserver launches your driver and serves INDI on TCP :7624
indiserver ./my_driver.py

# then, in another terminal, either:
indi-nexus serve       # the web panel at :8000, against indiserver
indi-nexus monitor     # a live feed in the terminal
```

`indi-nexus serve` without `--device` connects to `indiserver` instead of running drivers
itself. That is the only difference between the two setups.

Running under the real hub is what makes your driver part of an observatory rather than a
demo. Because it is an ordinary INDI driver, other INDI software (KStars/Ekos, PHD2,
existing C++ drivers) connects to the same `indiserver` and drives it unchanged, at the
same time as the panel does.

!!! note "Running a driver on its own"

    `python ./my_driver.py` also works, but it will sit there saying nothing. A driver
    only speaks when a client asks it to, and on its own there is no client. It is not
    hung. Paste `<getProperties version="1.7"/>` and press enter to see it reply.

## Where to go next

- **[Writing a driver](guides/writing-drivers.md)** - the main guide. Start here.
- **[The examples](guides/examples.md)** - which example to read for what.
- **[Building a frontend](guides/frontend.md)** - the ready-made panel, and your own UI.
- **[Coming from pyINDI?](guides/porting-from-pyindi.md)** - what maps to what.
- **[Protocol concepts](guides/protocol.md)** - the INDI vocabulary, briefly.
