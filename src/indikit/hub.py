"""Run drivers inside the calling process, standing in for ``indiserver``.

At an observatory ``indiserver`` is the hub: it launches drivers as child processes
and serves their combined stream on TCP. That is one more thing to install and one
more thing to have running, which is a poor first five minutes for someone who only
wants to see their driver on a screen.

:class:`InProcessHub` plays the same part in memory. Driver output merges onto a
single channel (each runtime write is one complete XML message, so interleaving is
safe) and each client write is broadcast to every driver, whose device ignores
messages addressed to another device. The client cannot tell the difference, so the
whole web stack above it runs unchanged.

Nothing here is web-specific - it is drivers, pipes and the client transport contract -
so it sits beside them rather than inside :mod:`indikit.web`. ``indikit serve
--device`` is its loudest caller, but a test or a script that wants a driver on the
other end of an :class:`~indikit.client.IndiClient` needs it without a FastAPI app
anywhere in the process.

This is a convenience for development and for trying a driver out, not a replacement
for ``indiserver``: it serves exactly one client, has no access control, and dies
with the process. Point a real observatory at the real hub.

**There is no ``enableBLOB`` gate here**, and nothing below implements one: every
driver message reaches the client whether or not it asked for BLOBs. A real
``indiserver`` forwards no BLOB until the client sends ``enableBLOB``, and does so
silently. So a test running over this hub proves that a BLOB payload round-trips and
**cannot** prove that a client's :meth:`~indikit.client.IndiClient.enable_blob`
call was needed - the call looks removable here and is not. That is exactly the
lesson ``examples/blob_receiver.py`` exists to teach, so do not delete it from that
example, or from its test, on the strength of a green suite.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from indikit.driver import Device, DriverRuntime
from indikit.transport import CloseFn, ReadFn, WriteFn


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


class InProcessHub:
    """A miniature in-memory ``indiserver``: many drivers, one client stream.

    Parameters
    ----------
    devices : list of Device
        The driver instances to serve.
    config_dir : Path or None, optional
        Where the drivers keep their saved configuration, exactly as
        ``indiserver`` would leave it to them. Passed on so that a driver tried
        out here behaves the same way it will under the real hub, rather than
        reporting that it has nowhere to save.
    """

    def __init__(self, devices: list[Device], *, config_dir: Path | None = None) -> None:
        self._to_client = _Pipe()
        self._to_drivers = [_Pipe() for _ in devices]
        self.runtimes = [
            DriverRuntime(device, pipe.read, self._to_client.write, config_dir=config_dir)
            for device, pipe in zip(devices, self._to_drivers, strict=True)
        ]

    async def connect(self) -> tuple[ReadFn, WriteFn, CloseFn]:
        """Return the client-side transport onto the hub.

        Returns
        -------
        transport : tuple of (ReadFn, WriteFn, CloseFn)
            The read/write/close trio an :class:`~indikit.client.IndiClient`
            expects, suitable for passing as its ``connect`` factory.
        """

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
