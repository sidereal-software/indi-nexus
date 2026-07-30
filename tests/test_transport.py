"""Tests for the shared TCP transport adapter (:func:`open_tcp`).

Each test starts a real ``asyncio`` TCP server on an ephemeral localhost port and
drives :func:`open_tcp`'s ``read``/``write`` callables against it, so the adapter
is exercised over an actual socket rather than an in-memory stand-in.
"""

from __future__ import annotations

import asyncio

from indi_nexus.transport import open_tcp


class _EchoServer:
    """A localhost TCP server that records inbound bytes and can send/close."""

    def __init__(self) -> None:
        """Create the server with no connection yet."""
        self.received: list[bytes] = []
        self._server: asyncio.Server | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = asyncio.Event()
        self._data_arrived = asyncio.Event()
        self._eof = asyncio.Event()

    async def __aenter__(self) -> _EchoServer:
        """Start listening on an ephemeral port and return the server."""
        self._server = await asyncio.start_server(self._on_connect, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Stop listening and drop any open connection."""
        if self._writer is not None:
            self._writer.close()
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    @property
    def port(self) -> int:
        """The ephemeral port the server is listening on."""
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]

    async def _on_connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Record the peer and capture everything it sends."""
        self._writer = writer
        self._connected.set()
        while True:
            data = await reader.read(65536)
            if not data:
                self._eof.set()
                return
            self.received.append(data)
            self._data_arrived.set()

    async def wait_for_eof(self) -> None:
        """Wait until the client has closed its end of the connection."""
        await self._eof.wait()

    async def wait_for_received(self, expected: bytes) -> None:
        """Wait until exactly ``expected`` bytes have been received.

        Parameters
        ----------
        expected : bytes
            The full inbound payload the caller is waiting for.
        """
        while b"".join(self.received) != expected:
            self._data_arrived.clear()
            await self._data_arrived.wait()

    async def send(self, data: bytes) -> None:
        """Send bytes to the connected client."""
        await self._connected.wait()
        assert self._writer is not None
        self._writer.write(data)
        await self._writer.drain()

    async def close_connection(self) -> None:
        """Close the server side of the open connection."""
        await self._connected.wait()
        assert self._writer is not None
        self._writer.close()


async def _read_until(read, expected: bytes) -> bytes:
    """Accumulate reads until ``expected`` bytes have arrived.

    Parameters
    ----------
    read : ReadFn
        The transport's read callable.
    expected : bytes
        The full payload the caller is waiting for.

    Returns
    -------
    data : bytes
        The accumulated bytes (exactly ``expected`` on success).
    """
    got = b""
    while len(got) < len(expected):
        chunk = await read()
        assert chunk, "stream closed before the expected bytes arrived"
        got += chunk
    return got


def test_open_tcp_write_and_read_round_trip():
    """Bytes written reach the server and server bytes come back via read."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        async with _EchoServer() as server:
            read, write, _close = await open_tcp("127.0.0.1", server.port)
            await write(b"<getProperties/>")
            async with asyncio.timeout(2):
                await server.wait_for_received(b"<getProperties/>")
            await server.send(b"<message/>")
            async with asyncio.timeout(2):
                assert await _read_until(read, b"<message/>") == b"<message/>"

    asyncio.run(scenario())


def test_open_tcp_read_returns_empty_at_eof():
    """read returns b"" once the server closes the connection."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        async with _EchoServer() as server:
            read, _write, _close = await open_tcp("127.0.0.1", server.port)
            await server.close_connection()
            async with asyncio.timeout(2):
                assert await read() == b""

    asyncio.run(scenario())


def test_open_tcp_with_connect_timeout_connects():
    """The connect_timeout branch still yields a working connection."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        async with _EchoServer() as server:
            read, write, _close = await open_tcp("127.0.0.1", server.port, connect_timeout=5.0)
            await write(b"ping")
            async with asyncio.timeout(2):
                await server.wait_for_received(b"ping")
            await server.send(b"pong")
            async with asyncio.timeout(2):
                assert await _read_until(read, b"pong") == b"pong"

    asyncio.run(scenario())


def test_open_tcp_read_chunk_caps_single_read():
    """A single read never returns more than read_chunk bytes."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        async with _EchoServer() as server:
            read, _write, _close = await open_tcp("127.0.0.1", server.port, read_chunk=4)
            await server.send(b"0123456789")
            got = b""
            async with asyncio.timeout(2):
                while len(got) < 10:
                    chunk = await read()
                    assert len(chunk) <= 4
                    got += chunk
            assert got == b"0123456789"

    asyncio.run(scenario())


def test_open_tcp_close_sends_eof_to_the_peer():
    """close() releases the socket so the server promptly sees a clean EOF."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        async with _EchoServer() as server:
            _read, write, close = await open_tcp("127.0.0.1", server.port)
            await write(b"hello")
            async with asyncio.timeout(2):
                await server.wait_for_received(b"hello")
            await close()
            async with asyncio.timeout(2):
                await server.wait_for_eof()

    asyncio.run(scenario())


def test_open_tcp_refused_raises_oserror():
    """Connecting to a port nobody listens on raises OSError."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        # Bind-then-close a listener so the port is known to be free.
        probe = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
        port = probe.sockets[0].getsockname()[1]
        probe.close()
        await probe.wait_closed()
        try:
            await open_tcp("127.0.0.1", port)
            raise AssertionError("expected OSError")
        except OSError:
            pass

    asyncio.run(scenario())
