"""The ``indi-nexus`` command-line interface.

Three subcommands tie the layers together:

* ``serve`` - run the FastAPI web bridge (the debug page + WebSocket + REST).
* ``run`` - run a driver (a :class:`~indi_nexus.driver.Device` subclass) over
  stdio, as ``indiserver`` launches it.
* ``monitor`` - connect to ``indiserver`` and print every property update.
"""

from __future__ import annotations

import asyncio
import importlib
import sys

import typer

from indi_nexus.driver import Device

app = typer.Typer(help="INDINexus - modern INDI tooling.", no_args_is_help=True)


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
