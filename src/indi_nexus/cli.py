"""The ``indi-nexus`` command-line interface.

Four subcommands tie the layers together:

* ``new`` - scaffold a runnable driver file to start from.
* ``serve`` - run the FastAPI web bridge (the debug page + WebSocket + REST).
* ``run`` - run one or more drivers (:class:`~indi_nexus.driver.Device`
  subclasses) over stdio, as ``indiserver`` launches them.
* ``monitor`` - connect to ``indiserver`` and print every property update.

The app callback carries the logging flags, so every subcommand has them, and it
is the one place a CLI invocation configures logging.

**No option here carries a Typer ``envvar=``.** Within the package the whole
``INDI_NEXUS_*`` environment is read by :class:`~indi_nexus.settings.Settings`
and nothing else, so a variable has one reader and one documented meaning. The
one reader outside the package is ``docker/entrypoint.sh``, which reads
``INDI_NEXUS_TOKEN``, ``INDI_NEXUS_ALLOW_INSECURE_BIND`` and
``INDI_NEXUS_ALLOWED_ORIGINS`` as fallbacks for its own ``WEB_*`` names, because
it has to settle a token and print the panel's URL with it before ``serve``
starts. It passes them on as flags, which beat the environment, so ``Settings``
still resolves one value. An option that a
variable also names is declared with a ``None`` default and resolved against the
settings in the command body: ``None`` means "not given, take the environment",
and anything else is the operator's explicit choice, which wins. Resolving in the
body rather than in the signature is what keeps that true - a default computed at
import time would freeze the environment as it stood when the module was first
imported, which is a real difference under any in-process runner and a silent one.
"""

from __future__ import annotations

import asyncio
import importlib
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from indi_nexus.driver import Device, serve_stdio
from indi_nexus.logging_config import configure_logging
from indi_nexus.settings import LogLevel, settings

app = typer.Typer(help="INDINexus - modern INDI tooling.", no_args_is_help=True)


@app.callback()
def main(
    ctx: typer.Context,
    log_level: Annotated[
        LogLevel | None,
        typer.Option(
            "--log-level",
            case_sensitive=False,
            help="Logging level for indi_nexus and uvicorn. "
            "(env var: INDI_NEXUS_LOG_LEVEL; this flag wins)",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("-v", "--verbose", help="Shorthand for --log-level DEBUG."),
    ] = False,
    wire: Annotated[
        bool | None,
        typer.Option(
            "--wire",
            help="Log one line per INDI message in each direction, on indi_nexus.wire. "
            "BLOB payloads are reported by size and never printed. "
            "(env var: INDI_NEXUS_WIRE_LOG; this flag wins)",
        ),
    ] = None,
) -> None:
    """Configure logging for whichever subcommand runs next.

    Parameters
    ----------
    ctx : typer.Context
        Click's context; the chosen level is stored on it for ``serve``, which
        has to start uvicorn at the same level rather than leaving it at its own
        default.
    log_level : LogLevel or None
        The level to log at, or ``None`` to take ``INDI_NEXUS_LOG_LEVEL``.
    verbose : bool
        Shorthand for ``--log-level DEBUG``; it wins over ``--log-level``.
    wire : bool or None
        Whether to turn the ``indi_nexus.wire`` logger up to DEBUG, or ``None``
        to take ``INDI_NEXUS_WIRE_LOG``.
    """
    config = settings()
    level = LogLevel.DEBUG if verbose else (config.log_level if log_level is None else log_level)
    configure_logging(level, wire=config.wire_log if wire is None else wire)
    ctx.obj = level


def run_devices(devices: list[Device]) -> None:
    """Serve one or more devices over this process's stdio until stdin closes.

    Deliberately **not** :func:`indi_nexus.driver.run`. That is the other process
    entrypoint, and it configures logging from the environment itself - for the
    driver author who runs ``./my_driver.py`` under ``indiserver`` with no CLI in
    the loop. Reaching it from here would run that configuration a second time
    and throw away this invocation's ``--log-level``, which :func:`main` has
    already applied.

    Parameters
    ----------
    devices : list of Device
        The device instances to serve on one stdio pipe.
    """
    asyncio.run(serve_stdio(devices, config_dir=settings().config_dir))


_DRIVER_TEMPLATE = '''#!/usr/bin/env python3
"""{device_name}: an INDI driver built on INDINexus.

To try it out, run it in the web panel from the directory holding this file::

    indi-nexus serve --device {module_name}:{class_name}

or under a real ``indiserver``::

    indiserver ./{file_name}
"""

from __future__ import annotations

from indi_nexus.driver import Device, every, on_new
from indi_nexus.protocol import IPState, ISRule, ISState, Number, NumberVector, Switch, SwitchVector


class {class_name}(Device):
    """A {device_name} driver."""

    name = "{device_name}"

    async def setup(self) -> None:
        """Define this device's properties (runs once, on first getProperties)."""
        # The standard connect/disconnect lifecycle: clients see a CONNECTION
        # switch, and on_connect()/on_disconnect() below are called on writes.
        self.define_connection()

        # A read-only telemetry value, updated by the @every job below.
        self.define_number(
            "TELEMETRY",
            [Number(name="VALUE", label="Value", format="%.2f", value=0)],
            label="Telemetry",
            group="Main Control",
        )
        # A writable switch handled by the @on_new method below.
        self.define_switch(
            "POWER",
            [
                Switch(name="ON", label="On", value=ISState.OFF),
                Switch(name="OFF", label="Off", value=ISState.ON),
            ],
            rule=ISRule.ONE_OF_MANY,
            label="Power",
            group="Main Control",
        )
        self.message("{device_name} ready.")

    async def on_connect(self) -> None:
        """Open your serial/network link to the hardware here."""

    async def on_disconnect(self) -> None:
        """Halt motion and close your hardware link here."""
        # Nothing polls while disconnected, so stop claiming the last reading is
        # current. Leave every property that could still be moving safe and Idle.
        self["TELEMETRY"].set(state=IPState.IDLE)

    @every(seconds=1, when_connected=True)
    async def poll(self) -> None:
        """Read the hardware and publish updates (paused while disconnected)."""
        current: float = self["TELEMETRY"]["VALUE"].value
        self["TELEMETRY"].set(VALUE=current + 1, state=IPState.OK)

    @on_new("POWER")
    async def _power(self, vector: SwitchVector) -> None:
        """Apply a client write to POWER; confirm what actually happened."""
        if not self.require_connected():
            return
        # selected() names the member the client turned On - a OneOfMany write
        # often carries only that member, so never assume an element is present.
        turned_on = vector.selected() == "ON"
        self["POWER"].set(ON=ISState.ON if turned_on else ISState.OFF, state=IPState.OK)
        self.message(f"Power turned {{'on' if turned_on else 'off'}}.")

    @on_new("TELEMETRY")
    async def _telemetry(self, vector: NumberVector) -> None:
        """Accept a client write to TELEMETRY (get() tolerates partial writes)."""
        if not self.require_connected():
            return
        self["TELEMETRY"].set(VALUE=vector.get("VALUE", 0.0), state=IPState.OK)


if __name__ == "__main__":
    {class_name}.run()
'''


def load_device(spec: str) -> type[Device]:
    """Import and return a ``Device`` subclass from a ``module:attr`` spec.

    Parameters
    ----------
    spec : str
        A ``module:attr`` reference, e.g. ``examples.demo_device:Demo``.

    Returns
    -------
    device_cls : type[Device]
        The referenced ``Device`` subclass.

    Raises
    ------
    typer.BadParameter
        If the spec is malformed, the target cannot be imported, or it is not a
        ``Device`` subclass.
    """
    if ":" not in spec:
        raise typer.BadParameter("expected 'module:attr' (e.g. examples.demo_device:Demo)")
    module_name, _, attr = spec.partition(":")
    # Console scripts don't put the working directory on the path; add it so a
    # user can run a driver module living in the directory they invoke from.
    if "" not in sys.path:
        sys.path.insert(0, "")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise typer.BadParameter(f"cannot import module {module_name!r}: {exc}") from exc
    obj = getattr(module, attr, None)
    if not (isinstance(obj, type) and issubclass(obj, Device)):
        raise typer.BadParameter(f"{spec!r} is not a Device subclass")
    return obj


@app.command()
def new(
    path: Annotated[Path, typer.Argument(help="Driver file to create, e.g. my_driver.py")],
    name: Annotated[str, typer.Option(help="Device name (default: from the file name).")] = "",
) -> None:
    """Scaffold a runnable INDI driver file to start from."""
    if path.exists():
        raise typer.BadParameter(f"{path} already exists; refusing to overwrite")
    words = [w for w in re.split(r"[^0-9A-Za-z]+", path.stem) if w]
    if not words:
        raise typer.BadParameter(f"cannot derive a class name from {path.name!r}")
    class_name = "".join(w.capitalize() for w in words)
    device_name = name or " ".join(w.capitalize() for w in words)
    path.write_text(
        _DRIVER_TEMPLATE.format(
            class_name=class_name,
            device_name=device_name,
            module_name=path.stem,
            file_name=path.name,
        )
    )
    path.chmod(path.stat().st_mode | 0o111)
    typer.echo(f"Created {path} (device {device_name!r}).")
    typer.echo("Try it in the web panel with:")
    typer.echo(f"  indi-nexus serve --device {path.stem}:{class_name}")


async def _serve_devices(
    host: str,
    port: int,
    specs: list[str],
    token: str,
    allowed_origins: Sequence[str],
    log_level: LogLevel,
) -> None:
    """Serve the panel against drivers running in this process.

    Parameters
    ----------
    host : str
        The interface uvicorn binds to.
    port : int
        The TCP port uvicorn listens on.
    specs : list of str
        Drivers to run, each as ``module:attr``.
    token : str
        Shared token required on ``/ws`` and ``/api``; ``""`` for none.
    allowed_origins : Sequence of str
        Browser origins accepted in addition to the server's own.
    log_level : LogLevel
        The level uvicorn is started at, so its request log follows
        ``--log-level`` instead of staying at its own default.
    """
    import uvicorn

    from indi_nexus.client import IndiClient
    from indi_nexus.hub import InProcessHub
    from indi_nexus.web import create_app

    config = settings()
    hub = InProcessHub([load_device(spec)() for spec in specs], config_dir=config.config_dir)
    app_ = create_app(
        client=IndiClient(connect=hub.connect),
        token=token,
        allowed_origins=allowed_origins,
        message_history=config.message_history,
        max_backlog=config.max_backlog,
    )
    server = uvicorn.Server(
        uvicorn.Config(app_, host=host, port=port, log_level=log_level.value.lower())
    )
    tasks = [asyncio.create_task(runtime.serve()) for runtime in hub.runtimes]
    try:
        await server.serve()
    finally:
        hub.shutdown()
        await asyncio.gather(*tasks, return_exceptions=True)


@app.command()
def serve(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", help="Web bind address."),
    port: int = typer.Option(8000, help="Web bind port."),
    indi_host: str = typer.Option("localhost", help="Upstream indiserver host."),
    indi_port: int = typer.Option(7624, help="Upstream indiserver port."),
    device: Annotated[
        list[str] | None,
        typer.Option(
            "--device",
            help="For trying a driver out: run it in this process instead of under "
            "indiserver, as 'module:attr'. Repeat for several devices.",
        ),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option(
            "--token",
            help="Shared token required on /ws and /api. "
            "(env var: INDI_NEXUS_TOKEN; this flag wins)",
        ),
    ] = None,
    allow_origin: Annotated[
        list[str] | None,
        typer.Option(
            "--allow-origin",
            help="Browser origin to accept, e.g. http://localhost:5173. Repeatable; "
            "'*' accepts any. The server's own origin is always accepted. "
            "(env var: INDI_NEXUS_ALLOWED_ORIGINS, space separated; this flag wins)",
        ),
    ] = None,
    allow_insecure_bind: Annotated[
        bool | None,
        typer.Option(
            "--allow-insecure-bind",
            help="Bind a non-loopback address with no token. This exposes the instrument. "
            "(env var: INDI_NEXUS_ALLOW_INSECURE_BIND; this flag wins)",
        ),
    ] = None,
) -> None:
    """Run the web bridge, serving the panel at / and a WebSocket at /ws.

    With no --device this connects to a running indiserver. That is how an observatory
    runs and what anything real should use: the hub is what lets several clients drive
    the same instruments at once.

    --device runs the named drivers inside this process instead, so a driver can be seen
    on screen without installing indiserver first. It serves one client and stops with
    the command, so it is for development, not for an observatory.

    /ws is the whole write surface - a frame there becomes an INDI new* that moves
    hardware - so binding it where anything but this machine can reach it needs either
    --token or an explicit --allow-insecure-bind. Each of the three access-control
    options is also an INDI_NEXUS_* environment variable; the flag wins, and its absence
    falls back to the variable. See docs/docker.md or DEVELOPMENT.md for the full list.
    """
    from indi_nexus.web.security import is_loopback

    config = settings()
    level = ctx.obj if isinstance(ctx.obj, LogLevel) else config.log_level
    # None is "the flag was not given, so take the environment". Any other value
    # is the operator saying so on this invocation and wins - `--token ""`
    # included, which is how a command line turns a configured token back off.
    # Resolved here rather than as a default in the signature: a default is
    # evaluated once at import, which would pin the environment as it stood then.
    chosen_token = config.token if token is None else token
    origins = config.allowed_origins if allow_origin is None else tuple(allow_origin)
    insecure = config.allow_insecure_bind if allow_insecure_bind is None else allow_insecure_bind
    if not chosen_token and not is_loopback(host) and not insecure:
        raise typer.BadParameter(
            f"--host {host} exposes the instrument to the network with no authentication. "
            "Pass --token (or INDI_NEXUS_TOKEN), or --allow-insecure-bind to accept that."
        )
    if device:
        asyncio.run(_serve_devices(host, port, device, chosen_token, origins, level))
        return

    import uvicorn

    from indi_nexus.web import create_app

    uvicorn.run(
        create_app(
            indi_host=indi_host,
            indi_port=indi_port,
            token=chosen_token,
            allowed_origins=origins,
            connect_timeout=config.connect_timeout,
            reconnect_delay=config.reconnect_delay,
            message_history=config.message_history,
            max_backlog=config.max_backlog,
        ),
        host=host,
        port=port,
        # Without this uvicorn stays at its own default while indi_nexus.* moved,
        # so `--log-level DEBUG` would silently leave out the request log - which
        # is usually the half the operator was after. Its own log_config stands:
        # owning the tree here would mean reimplementing its access-log format
        # for nothing.
        log_level=level.value.lower(),
    )


@app.command()
def run(
    specs: Annotated[list[str], typer.Argument(help="Drivers as 'module:attr', one or more.")],
) -> None:
    """Run one or more drivers over stdio (as indiserver would launch them).

    Several specs put every named device on this one stdio pipe, which is what a
    multi-device libindi driver does. They share a reader, so a slow handler on
    one delays the next inbound message for all of them; run them as separate
    indiserver drivers when that matters.
    """
    run_devices([load_device(spec)() for spec in specs])


@app.command()
def monitor(
    host: str = typer.Option("localhost", help="indiserver host."),
    port: int = typer.Option(7624, help="indiserver port."),
) -> None:
    """Connect to indiserver and print every property update."""
    import contextlib

    from indi_nexus.client import IndiClient, PropertyEvent

    def show(event: PropertyEvent) -> None:
        """Print one property event as a compact line."""
        state = f" ({event.vector.state.value})" if event.vector is not None else ""
        typer.echo(f"[{event.type:>3}] {event.device}.{event.name}{state}")

    config = settings()

    async def _main() -> None:
        """Connect and stream updates until interrupted."""
        async with IndiClient(
            host,
            port,
            connect_timeout=config.connect_timeout,
            reconnect_delay=config.reconnect_delay,
        ) as client:
            client.subscribe(show)
            await asyncio.Event().wait()

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())


if __name__ == "__main__":
    app()
