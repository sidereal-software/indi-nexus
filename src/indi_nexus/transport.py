"""Shared byte-stream transport contract for the driver and client layers.

Both the driver runtime (a stdio child of ``indiserver``) and the client (a TCP
peer of ``indiserver``) are driven by the same minimal trio of callables: an async
``read`` that returns the next chunk of bytes (``b""`` at EOF), an async ``write``
that emits one serialised message, and an async ``close`` that releases the
underlying connection. Keeping the aliases - and the TCP adapter - in one place
lets the two layers agree on the contract and lets tests substitute in-memory
streams for either side.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

#: Async callable returning the next inbound chunk, or ``b""`` at end of stream.
ReadFn = Callable[[], Awaitable[bytes]]

#: Async callable that writes one serialised message to the transport.
WriteFn = Callable[[bytes], Awaitable[None]]

#: Async callable that closes the transport, releasing the OS connection.
CloseFn = Callable[[], Awaitable[None]]

_READ_CHUNK = 65536


async def open_tcp(
    host: str, port: int, *, connect_timeout: float | None = None, read_chunk: int = _READ_CHUNK
) -> tuple[ReadFn, WriteFn, CloseFn]:
    """Open a TCP connection and adapt it to ``read``/``write``/``close`` callables.

    Parameters
    ----------
    host : str
        Host to connect to (e.g. the ``indiserver`` host).
    port : int
        TCP port to connect to (``indiserver`` defaults to 7624).
    connect_timeout : float, optional
        Seconds to wait for the connection before raising ``TimeoutError``.
    read_chunk : int, optional
        Maximum number of bytes returned by a single ``read``.

    Returns
    -------
    read : ReadFn
        Awaitable returning the next chunk of inbound bytes (``b""`` at EOF).
    write : WriteFn
        Awaitable that writes bytes and drains the transport.
    close : CloseFn
        Awaitable that closes the socket (sends FIN) and waits for it to close.
    """
    opener = asyncio.open_connection(host, port)
    if connect_timeout is not None:
        async with asyncio.timeout(connect_timeout):
            reader, writer = await opener
    else:
        reader, writer = await opener

    async def read() -> bytes:
        """Read up to ``read_chunk`` bytes (``b""`` once the peer closes)."""
        return await reader.read(read_chunk)

    async def write(data: bytes) -> None:
        """Write ``data`` to the socket and wait for it to drain."""
        writer.write(data)
        await writer.drain()

    async def close() -> None:
        """Close the socket; the peer's already-dead socket is not an error."""
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()

    return read, write, close
