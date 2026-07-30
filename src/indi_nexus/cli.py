"""The ``indi-nexus`` command-line interface.

Four subcommands tie the layers together:

* ``new`` - scaffold a runnable driver file to start from.
* ``serve`` - run the FastAPI web bridge (the debug page + WebSocket + REST).
* ``run`` - run a driver (a :class:`~indi_nexus.driver.Device` subclass) over
  stdio, as ``indiserver`` launches it.
* ``monitor`` - connect to ``indiserver`` and print every property update.
"""

from __future__ import annotations

import asyncio
import importlib
import re
import sys
from pathlib import Path
from typing import Annotated

import typer

from indi_nexus.driver import Device

app = typer.Typer(help="INDINexus - modern INDI tooling.", no_args_is_help=True)

_DRIVER_TEMPLATE = '''#!/usr/bin/env python3
"""{device_name}: an INDI driver built on INDINexus.

Try it in the web panel (no indiserver needed), from the directory holding
this file::

    python -m examples.demo_bridge --device {module_name}:{class_name}

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
    typer.echo(f"  python -m examples.demo_bridge --device {path.stem}:{class_name}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Web bind address."),
    port: int = typer.Option(8000, help="Web bind port."),
    indi_host: str = typer.Option("localhost", help="Upstream indiserver host."),
    indi_port: int = typer.Option(7624, help="Upstream indiserver port."),
) -> None:
    """Run the web bridge (debug page at ``/``, WebSocket at ``/ws``)."""
    import uvicorn

    from indi_nexus.web import create_app

    uvicorn.run(create_app(indi_host=indi_host, indi_port=indi_port), host=host, port=port)


@app.command()
def run(spec: str = typer.Argument(..., help="Driver as 'module:attr'.")) -> None:
    """Run a driver over stdio (as ``indiserver`` would launch it)."""
    load_device(spec).run()


@app.command()
def monitor(
    host: str = typer.Option("localhost", help="indiserver host."),
    port: int = typer.Option(7624, help="indiserver port."),
) -> None:
    """Connect to ``indiserver`` and print every property update."""
    import contextlib

    from indi_nexus.client import IndiClient, PropertyEvent

    def show(event: PropertyEvent) -> None:
        """Print one property event as a compact line."""
        state = f" ({event.vector.state.value})" if event.vector is not None else ""
        typer.echo(f"[{event.type:>3}] {event.device}.{event.name}{state}")

    async def _main() -> None:
        """Connect and stream updates until interrupted."""
        async with IndiClient(host, port) as client:
            client.subscribe(show)
            await asyncio.Event().wait()

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())


if __name__ == "__main__":
    app()
