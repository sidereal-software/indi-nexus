"""``DriverRuntime``: the transport + supervision loop behind a ``Device``.

Responsibilities:

* **read** the INDI XML stream from ``indiserver`` (stdin), frame it with the
  M1 :class:`~indi_nexus.protocol.xml.XMLStreamParser`, and dispatch each message
  to the device (``getProperties`` -> ``setup``; ``newXxxVector`` -> ``@on_new``);
* **write** every message the device emits back out (stdout), serialized by the
  M1 codec;
* **supervise** the device's ``@every`` periodic jobs.

It uses ``anyio`` structured concurrency (works on our 3.10 floor, unlike
``asyncio.TaskGroup``). The class takes plain ``read``/``write`` callables so it
can be driven by real stdio *or* by in-memory streams in tests; :func:`run` wires
it to actual stdin/stdout.
"""

from __future__ import annotations

import asyncio
import inspect
import math
import sys
from collections.abc import Awaitable, Callable
from typing import Any

import anyio

from indi_nexus.driver.device import Device
from indi_nexus.driver.scheduling import PeriodicSpec, iter_periodic
from indi_nexus.protocol import (
    GetProperties,
    IndiMessage,
    NewVector,
    XMLStreamParser,
    to_xml,
)

ReadFn = Callable[[], Awaitable[bytes]]
WriteFn = Callable[[bytes], Awaitable[None]]

_READ_CHUNK = 65536


class DriverRuntime:
    """Drives one :class:`Device` over a byte ``read``/``write`` pair."""

    def __init__(self, device: Device, read: ReadFn, write: WriteFn) -> None:
        self._device = device
        self._read = read
        self._write = write
        # Unbounded outbox so the device's synchronous emit never blocks.
        self._out_send, self._out_receive = anyio.create_memory_object_stream[IndiMessage](math.inf)
        device._bind(self._emit)

    def _emit(self, msg: IndiMessage) -> None:
        self._out_send.send_nowait(msg)

    async def serve(self) -> None:
        """Run until stdin reaches EOF (or the caller cancels the scope)."""
        async with anyio.create_task_group() as outer:
            outer.start_soon(self._writer_loop)
            async with anyio.create_task_group() as workers:
                for spec, method in iter_periodic(self._device):
                    workers.start_soon(self._run_periodic, spec, method)
                await self._reader_loop()
                # EOF on stdin: stop the periodic jobs...
                workers.cancel_scope.cancel()
            # ...then close the outbox so the writer drains what's left and exits.
            await self._out_send.aclose()

    # -- reading ----------------------------------------------------------- #
    async def _reader_loop(self) -> None:
        parser = XMLStreamParser()
        while True:
            data = await self._read()
            if not data:
                return
            for msg in parser.feed(data):
                await self._handle(msg)

    async def _handle(self, msg: IndiMessage) -> None:
        if isinstance(msg, GetProperties):
            await self._device._dispatch_get_properties()
        elif isinstance(msg, NewVector):
            await self._device._dispatch_new(msg.vector)
        # def/set/message flowing the "wrong" way into a driver are ignored.

    # -- writing ----------------------------------------------------------- #
    async def _writer_loop(self) -> None:
        async with self._out_receive:
            async for msg in self._out_receive:
                await self._write(to_xml(msg) + b"\n")

    # -- periodic jobs ----------------------------------------------------- #
    async def _run_periodic(self, spec: PeriodicSpec, method: Callable[[], Any]) -> None:
        if spec.start_immediately:
            await self._tick(method)
        while True:
            await anyio.sleep(spec.interval)
            await self._tick(method)

    async def _tick(self, method: Callable[[], Any]) -> None:
        # A failing tick must never take down the driver; log it and carry on.
        # (CancelledError is a BaseException, so cancellation still propagates.)
        try:
            result = method()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # noqa: BLE001 - deliberate per-tick isolation
            name = spec_name(method)
            self._device.log_error(f"periodic task {name!r} failed: {exc}")


def spec_name(method: Callable[..., Any]) -> str:
    return getattr(method, "__name__", repr(method))


# --------------------------------------------------------------------------- #
# Real stdio wiring                                                            #
# --------------------------------------------------------------------------- #
async def _open_stdio() -> tuple[ReadFn, WriteFn]:
    """Async reader on stdin; blocking-but-flushed writer on stdout.

    Unix only - ``indiserver`` is a Unix hub, so the legacy Windows ``WinIO``
    thread shim is intentionally dropped.
    """
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)

    async def read() -> bytes:
        return await reader.read(_READ_CHUNK)

    async def write(data: bytes) -> None:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    return read, write


async def serve_stdio(device: Device) -> None:
    read, write = await _open_stdio()
    await DriverRuntime(device, read, write).serve()


def run(device: Device) -> None:
    """Serve ``device`` over real stdin/stdout until stdin closes."""
    anyio.run(serve_stdio, device)
