"""``DriverRuntime``: the transport and supervision loop behind a ``Device``.

The runtime does three things:

* **read** the INDI XML stream from ``indiserver`` (stdin), frame it with the M1
  :class:`~indi_nexus.protocol.xml.XMLStreamParser`, and dispatch each message to
  the device (``getProperties`` -> ``setup``; ``newXxxVector`` -> ``@on_new``);
* **write** every message the device emits back out (stdout), serialised by the
  M1 codec;
* **supervise** the device's ``@every`` periodic jobs.

Concurrency is plain :mod:`asyncio`: an outbox :class:`asyncio.Queue`, a writer
task draining it, one task per periodic job, and the reader driving the whole
thing until stdin reaches EOF. The class takes plain ``read``/``write`` callables
so it can be exercised by in-memory streams in tests; :func:`run` wires it to the
real stdin/stdout.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from collections.abc import Callable
from typing import Any

from indi_nexus.driver.device import Device
from indi_nexus.driver.scheduling import PeriodicSpec, iter_periodic
from indi_nexus.protocol import (
    GetProperties,
    IndiMessage,
    NewVector,
    XMLStreamParser,
    to_xml,
)
from indi_nexus.transport import ReadFn, WriteFn

_READ_CHUNK = 65536


class DriverRuntime:
    """Serve one :class:`~indi_nexus.driver.device.Device` over a byte stream.

    Parameters
    ----------
    device : Device
        The device to serve.
    read : Callable
        Awaitable returning the next chunk of inbound bytes, or ``b""`` at EOF.
    write : Callable
        Awaitable that writes one serialised message to the transport.
    """

    def __init__(self, device: Device, read: ReadFn, write: WriteFn) -> None:
        """Bind the device to its transport and its outbound-message callback."""
        self._device = device
        self._read = read
        self._write = write
        # Unbounded outbox; ``None`` is the writer's shutdown sentinel. The queue
        # is unbounded so the device's synchronous emit never blocks.
        self._outbox: asyncio.Queue[IndiMessage | None] = asyncio.Queue()
        device._bind(self._emit)

    def _emit(self, msg: IndiMessage) -> None:
        """Queue one outbound message on the (unbounded) outbox."""
        self._outbox.put_nowait(msg)

    async def serve(self) -> None:
        """Run until stdin reaches EOF (or the caller cancels this coroutine).

        On EOF the periodic jobs are cancelled and the writer is allowed to drain
        any still-queued messages before returning, so a driver that emits and
        then immediately sees EOF still gets its final messages out.
        """
        writer = asyncio.create_task(self._writer_loop())
        periodic = [
            asyncio.create_task(self._run_periodic(spec, method))
            for spec, method in iter_periodic(self._device)
        ]
        try:
            await self._reader_loop()
        finally:
            for task in periodic:
                task.cancel()
            await asyncio.gather(*periodic, return_exceptions=True)
            self._outbox.put_nowait(None)  # let the writer drain, then stop
            await writer

    async def _reader_loop(self) -> None:
        """Read, frame, and dispatch inbound messages until EOF."""
        parser = XMLStreamParser()
        while True:
            data = await self._read()
            if not data:
                return
            for msg in parser.feed(data):
                await self._handle(msg)

    async def _handle(self, msg: IndiMessage) -> None:
        """Route one inbound message to the device."""
        if isinstance(msg, GetProperties):
            await self._device._dispatch_get_properties(msg)
        elif isinstance(msg, NewVector):
            await self._device._dispatch_new(msg.vector)
        # def/set/message flowing the "wrong" way into a driver are ignored.

    async def _writer_loop(self) -> None:
        """Drain the outbox to the transport until the shutdown sentinel."""
        while True:
            msg = await self._outbox.get()
            if msg is None:
                return
            await self._write(to_xml(msg) + b"\n")

    async def _run_periodic(self, spec: PeriodicSpec, method: Callable[[], Any]) -> None:
        """Run one ``@every`` job forever, one tick per interval.

        Waits for the device's ``setup()`` to complete first, so a tick never
        runs against a property that has not been defined yet.
        """
        await self._device._setup_complete.wait()
        if spec.start_immediately:
            await self._tick(method)
        while True:
            await asyncio.sleep(spec.interval)
            await self._tick(method)

    async def _tick(self, method: Callable[[], Any]) -> None:
        """Run one tick, isolating any failure so the driver stays up.

        A raised :class:`Exception` is logged to the client and swallowed;
        :class:`asyncio.CancelledError` is a :class:`BaseException`, so shutdown
        cancellation still propagates.
        """
        try:
            result = method()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # noqa: BLE001 - deliberate per-tick isolation
            self._device.log_error(f"periodic task {task_name(method)!r} failed: {exc}")


def task_name(method: Callable[..., Any]) -> str:
    """Return a readable name for a scheduled method, for log messages.

    Parameters
    ----------
    method : Callable
        The scheduled method.

    Returns
    -------
    name : str
        The method's ``__name__`` if present, else its `repr`.
    """
    return getattr(method, "__name__", repr(method))


# --------------------------------------------------------------------------- #
# Real stdio wiring                                                            #
# --------------------------------------------------------------------------- #
async def _open_stdio() -> tuple[ReadFn, WriteFn]:
    """Build async ``read``/``write`` callables bound to real stdin/stdout.

    Reading uses an :class:`asyncio.StreamReader` over stdin; writing is a
    blocking-but-flushed write to stdout. Unix only - ``indiserver`` is a Unix
    hub, so the legacy Windows ``WinIO`` thread shim is intentionally dropped.
    """
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)

    async def read() -> bytes:
        """Read the next chunk from stdin (``b""`` at EOF)."""
        return await reader.read(_READ_CHUNK)

    async def write(data: bytes) -> None:
        """Write one serialised message to stdout and flush."""
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    return read, write


async def serve_stdio(device: Device) -> None:
    """Serve ``device`` over real stdin/stdout (async entrypoint)."""
    read, write = await _open_stdio()
    await DriverRuntime(device, read, write).serve()


def run(device: Device) -> None:
    """Serve ``device`` over real stdin/stdout until stdin closes.

    Parameters
    ----------
    device : Device
        The device to run as an ``indiserver`` stdio child.
    """
    asyncio.run(serve_stdio(device))
