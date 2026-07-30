"""Run the web bridge against the in-process demo device, without ``indiserver``.

This wires the reference :class:`~examples.demo_device.Demo` driver directly to an
:class:`~indi_nexus.client.IndiClient` through two in-memory byte pipes (the same
technique as ``tests/test_integration.py``), hands that client to the FastAPI app,
and serves it with uvicorn. The result is the full web stack - bridge, REST, and
the reference panel at ``/`` - backed by live demo data, with no external
``indiserver`` required. It is meant for local development and end-to-end testing
of the frontend.

Run it from the repository root with ``python -m examples.demo_bridge`` (optionally
``--host``/``--port``), then open the printed URL, or point the panel's Vite dev
server at it.
"""

from __future__ import annotations

import argparse
import asyncio

import uvicorn

from examples.demo_device import Demo
from indi_nexus.client import IndiClient
from indi_nexus.driver import DriverRuntime
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


async def _serve(host: str, port: int) -> None:
    """Wire the demo driver to the web app and serve it until interrupted.

    Parameters
    ----------
    host : str
        The interface uvicorn binds to.
    port : int
        The TCP port uvicorn listens on.
    """
    to_client = _Pipe()  # driver -> client
    to_driver = _Pipe()  # client -> driver

    runtime = DriverRuntime(Demo(), to_driver.read, to_client.write)

    async def connect() -> tuple[ReadFn, WriteFn, CloseFn]:
        """Wire the client's read/write onto the two in-memory pipes."""

        async def close() -> None:
            """Nothing to release for in-memory pipes; EOF is sent at shutdown."""

        return to_client.read, to_driver.write, close

    client = IndiClient(connect=connect)
    app = create_app(client=client)

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info"))
    driver_task = asyncio.create_task(runtime.serve())
    try:
        await server.serve()
    finally:
        to_driver.eof()
        await asyncio.gather(driver_task, return_exceptions=True)


def main() -> None:
    """Parse CLI arguments and run the demo bridge."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on (default 8000)")
    args = parser.parse_args()
    asyncio.run(_serve(args.host, args.port))


if __name__ == "__main__":
    main()
