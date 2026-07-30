r"""Run the web bridge against in-process drivers, without ``indiserver``.

This wires one or more drivers (the reference :class:`~examples.demo_device.Demo`
by default, or any ``Device`` subclasses named with repeated ``--device
module:attr`` flags) to an :class:`~indi_nexus.client.IndiClient` through
in-memory byte pipes (the same technique as ``tests/test_integration.py``),
hands that client to the FastAPI app, and serves it with uvicorn. With several
drivers it plays a miniature ``indiserver``: every driver's output merges into
the one client stream, and each client write is broadcast to every driver (each
device ignores writes addressed to the others). The result is the full web
stack - bridge, REST, and the reference panel at ``/`` - backed by live
drivers, with no external ``indiserver`` required.

Run it from the repository root, then open the printed URL (or point the
panel's Vite dev server at it)::

    python -m examples.demo_bridge
    python -m examples.demo_bridge \\
        --device examples.telescope_device:TelescopeSimulator \\
        --device examples.ccd_device:CCDSimulator \\
        --device examples.dome_device:DomeSimulator
"""

from __future__ import annotations

import argparse
import asyncio

import uvicorn

from indi_nexus.cli import load_device
from indi_nexus.client import IndiClient
from indi_nexus.driver import Device, DriverRuntime
from indi_nexus.transport import CloseFn, ReadFn, WriteFn
from indi_nexus.web import create_app


class _Pipe:
    """A one-way in-memory byte channel with an EOF sentinel."""

    def __init__(self) -> None:
        """Create the channel's backing queue."""
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def read(self) -> bytes:
        """Return the next chunk written to the channel (``b""`` at EOF)."""
        return await self._queue.get()

    async def write(self, data: bytes) -> None:
        """Write one chunk to the channel."""
        self._queue.put_nowait(data)

    def eof(self) -> None:
        """Signal end-of-stream to the reader."""
        self._queue.put_nowait(b"")


class Hub:
    """A miniature in-memory ``indiserver``: many drivers, one client stream.

    Driver output is merged onto a single channel (each runtime write is one
    complete XML message, so interleaving is safe); each client write is
    broadcast to every driver, whose device ignores messages addressed to
    another device.

    Parameters
    ----------
    devices : list of Device
        The driver instances to serve.
    """

    def __init__(self, devices: list[Device]) -> None:
        self._to_client = _Pipe()
        self._to_drivers = [_Pipe() for _ in devices]
        self.runtimes = [
            DriverRuntime(device, pipe.read, self._to_client.write)
            for device, pipe in zip(devices, self._to_drivers, strict=True)
        ]

    async def connect(self) -> tuple[ReadFn, WriteFn, CloseFn]:
        """Return the client-side transport onto the hub."""

        async def write(data: bytes) -> None:
            """Broadcast one client message to every driver."""
            for pipe in self._to_drivers:
                await pipe.write(data)

        async def close() -> None:
            """Nothing to release for in-memory pipes; EOF is sent at shutdown."""

        return self._to_client.read, write, close

    def shutdown(self) -> None:
        """Signal EOF to every driver so their serve loops finish."""
        for pipe in self._to_drivers:
            pipe.eof()


async def _serve(host: str, port: int, devices: list[Device]) -> None:
    """Wire the drivers to the web app and serve it until interrupted.

    Parameters
    ----------
    host : str
        The interface uvicorn binds to.
    port : int
        The TCP port uvicorn listens on.
    devices : list of Device
        The driver instances to serve.
    """
    hub = Hub(devices)
    client = IndiClient(connect=hub.connect)
    app = create_app(client=client)

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info"))
    driver_tasks = [asyncio.create_task(runtime.serve()) for runtime in hub.runtimes]
    try:
        await server.serve()
    finally:
        hub.shutdown()
        await asyncio.gather(*driver_tasks, return_exceptions=True)


def main() -> None:
    """Parse CLI arguments and run the demo bridge."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on (default 8000)")
    parser.add_argument(
        "--device",
        action="append",
        help=(
            "driver to serve, as 'module:attr'; repeat for several devices "
            "(default examples.demo_device:Demo)"
        ),
    )
    args = parser.parse_args()
    specs = args.device or ["examples.demo_device:Demo"]
    asyncio.run(_serve(args.host, args.port, [load_device(spec)() for spec in specs]))


if __name__ == "__main__":
    main()
