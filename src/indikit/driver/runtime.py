"""``DriverRuntime``: the transport and supervision loop behind a ``Device``.

The runtime does three things:

* **read** the INDI XML stream from ``indiserver`` (stdin), frame it with the M1
  :class:`~indikit.protocol.xml.XMLStreamParser`, and dispatch each message to
  every device it serves (``getProperties`` -> ``setup``; ``newXxxVector`` ->
  ``@on_new``);
* **write** every message those devices emit back out (stdout), serialised by the
  M1 codec;
* **supervise** each device's ``@every`` periodic jobs.

One runtime serves **one or more** devices, which is the shape libindi drivers
have always had: one executable, one stdio pipe, several devices announcing
themselves on the first ``getProperties``. There is one stream, so there is one
parser, one outbox and one writer; the devices differ only in which of them a
message is addressed to.

Concurrency is plain :mod:`asyncio`: an outbox :class:`asyncio.Queue`, a writer
task draining it, one task per periodic job, and the reader driving the whole
thing until stdin reaches EOF. The class takes plain ``read``/``write`` callables
so it can be exercised by in-memory streams in tests; :func:`run` wires it to the
real stdin/stdout.

Both ends log one line per message on the shared ``indikit.wire`` logger when
it is turned up (``INDIKIT_WIRE_LOG=1``, or ``indikit --wire``), which
:func:`run` reads from the environment. Logging goes to **stderr**: stdout here
is the INDI wire itself.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from indikit.driver.device import Device
from indikit.driver.scheduling import PeriodicSpec, iter_periodic
from indikit.logging_config import configure_logging, log_wire
from indikit.protocol import (
    DefVector,
    GetProperties,
    IndiMessage,
    Message,
    NewVector,
    SetVector,
    XMLStreamParser,
    indi_now,
    to_xml,
)
from indikit.settings import settings
from indikit.transport import ReadFn, WriteFn

# A driver's stderr is relayed into indiserver's own log, so a warning logged
# here reaches the operator with no logging configuration at all.
logger = logging.getLogger(__name__)

_READ_CHUNK = 65536


class DriverRuntime:
    """Serve one or more :class:`~indikit.driver.device.Device` over a byte stream.

    **Inbound dispatch is sequential across co-located devices.** The reader
    awaits each dispatch inline, so while one device's ``@on_new`` handler or
    ``setup()`` is running, the *next* inbound message waits - whichever device
    it is addressed to. That is head-of-line blocking in the reader, not lock
    contention: a message naming device A never reaches device B's guard at all,
    because :meth:`~indikit.driver.device.Device._dispatch_get_properties`
    and :meth:`~indikit.driver.device.Device._dispatch_new` return on the
    device-name check before entering it. Two things follow, and both are the
    opposite of the obvious guess:

    * ``off_thread`` does not help here. It moves the blocking call off the
      loop, but the handler still awaits it, so the reader stays parked for its
      whole duration.
    * ``serialize_dispatch = False`` does not help either. It drops a device's
      own guard, and the guard was never what B was waiting behind.

    What is **not** affected: outbound traffic, because every device shares one
    outbox drained by a separate writer task; and ``@every`` jobs, which are one
    task per job taking only their own device's guard, so B keeps polling and
    publishing throughout A's handler. That is the whole concurrency story of a
    multi-device driver, and it matches libindi, whose one process dispatches
    ``ISNew*`` inline for exactly the same reason.

    When two devices must never delay each other's inbound writes, run them as
    two drivers. ``indiserver`` launches both.

    Parameters
    ----------
    devices : Device or Sequence of Device
        The device, or devices, to serve on this stream.
    read : Callable
        Awaitable returning the next chunk of inbound bytes, or ``b""`` at EOF.
    write : Callable
        Awaitable that writes one serialised message to the transport.
    config_dir : Path or None, optional
        Where the devices keep their saved configuration, resolved by whichever
        entrypoint started the driver. `None` leaves every device's persistence
        method raising :class:`~indikit.ConfigError`, which is what a driver
        with no ``CONFIG_PROCESS`` never notices.

    Raises
    ------
    ValueError
        Raised if ``devices`` is empty, or if two of them resolve to the same
        INDI device name. Two devices answering to one name on one stream is not
        resolvable by any client, and both would answer every message addressed
        to it.
    """

    def __init__(
        self,
        devices: Device | Sequence[Device],
        read: ReadFn,
        write: WriteFn,
        *,
        config_dir: Path | None = None,
    ) -> None:
        """Bind the devices to their shared transport and outbound-message callback."""
        self._devices = (devices,) if isinstance(devices, Device) else tuple(devices)
        if not self._devices:
            raise ValueError("a DriverRuntime needs at least one device to serve")
        names = [device.device for device in self._devices]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate device name(s) on one stream: {', '.join(duplicates)}")
        self._read = read
        self._write = write
        # Unbounded outbox, shared by every device; ``None`` is the writer's
        # shutdown sentinel. The queue is unbounded so a device's synchronous
        # emit never blocks.
        self._outbox: asyncio.Queue[IndiMessage | None] = asyncio.Queue()
        for device in self._devices:
            device._bind(self._emit, config_dir=config_dir)

    def _emit(self, msg: IndiMessage) -> None:
        """Queue one outbound message on the (unbounded) shared outbox."""
        self._outbox.put_nowait(msg)

    def _report(self, device: str | None, text: str) -> None:
        """Queue an ERROR-level ``message`` on the outbox, attributed if known.

        This goes straight to the outbox rather than through
        :meth:`~indikit.driver.device.Device.log_error` so the writer can
        report a failure for a message whose owner it cannot name. The
        ``[ERROR] `` prefix is what ``Device.message`` would have written, and
        the panel's log format depends on it.

        Parameters
        ----------
        device : str or None
            The INDI device the failure belongs to, or `None` if unknown.
        text : str
            The error text.
        """
        self._outbox.put_nowait(
            Message(device=device, timestamp=indi_now(), message=f"[ERROR] {text}")
        )

    async def serve(self) -> None:
        """Run until stdin reaches EOF, or the writer fails, or this is cancelled.

        On EOF the periodic jobs are cancelled and the writer is allowed to drain
        any still-queued messages before returning, so a driver that emits and
        then immediately sees EOF still gets its final messages out.

        The reader runs as a task rather than inline because it is no longer the
        only end that can finish. A writer that dies takes the driver with it:
        left running, the reader would keep accepting work and the ``@every``
        jobs would keep filling an outbox nothing drains, and the driver would
        look perfectly alive to ``indiserver`` while answering nothing.
        """
        writer = asyncio.create_task(self._writer_loop())
        reader = asyncio.create_task(self._reader_loop())
        periodic = [
            asyncio.create_task(self._run_periodic(device, spec, method))
            for device in self._devices
            for spec, method in iter_periodic(device)
        ]
        try:
            await asyncio.wait({reader, writer}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in periodic:
                task.cancel()
            reader.cancel()  # a no-op on the EOF path, where it has already returned
            await asyncio.gather(*periodic, reader, return_exceptions=True)
            self._outbox.put_nowait(None)  # let the writer drain, then stop
            await asyncio.wait({writer})
        # Surface whichever end failed. The reader comes first: when a reader
        # failure is what stopped the driver, a writer failure behind it is the
        # symptom rather than the cause.
        for task in (reader, writer):
            failure = None if task.cancelled() else task.exception()
            if failure is not None:
                raise failure

    async def _reader_loop(self) -> None:
        """Read, frame, and dispatch inbound messages until EOF.

        There is one parser for the stream, not one per device: framing is a
        property of the stdin the hub writes to, and duplicating it would
        multiply the stall-detection state by the device count for nothing.

        A driver cannot reconnect its way out of trouble - stdin is the only
        input it will ever have - so a parser that has gone mute is resynced in
        place and the stream picks up at the next well-formed element. The
        resync keeps the parser's counters, which describe this stdin and not
        the object being rebuilt, and the warning carries them: a peer's
        malformed-input history is exactly what an operator wants at the moment
        the stream goes quiet.
        """
        parser = XMLStreamParser()
        while True:
            data = await self._read()
            if not data:
                return
            for msg in parser.feed(data):
                await self._handle(msg)
            if parser.stalled:
                logger.warning(
                    "%s: no message parsed in %d bytes of input; resyncing the parser "
                    "(%d dropped, %d resets so far on this stream)",
                    ", ".join(device.device for device in self._devices),
                    parser.bytes_since_last_message,
                    parser.dropped,
                    parser.resets,
                )
                parser.resync()

    async def _handle(self, msg: IndiMessage) -> None:
        """Offer one inbound message to every device, isolating handler failures.

        Each device applies its own device-name guard, so offering the message
        to all of them is how one addressed to a single device reaches only that
        one and a ``getProperties`` naming none reaches them all.

        A raising handler (an ``@on_new`` hitting a malformed client write, or a
        failing ``setup()``) is logged to the client and swallowed, mirroring the
        per-tick isolation of ``@every`` jobs - one bad message must never kill
        the driver, and must not stop the message reaching the devices behind
        the one that raised. It is reported through the device that was
        dispatched to, so attribution needs no guessing - which matters most for
        a failing ``setup()``, whose ``getProperties`` usually names no device
        at all. ``asyncio.CancelledError`` is a ``BaseException``, so shutdown
        cancellation still propagates.
        """
        log_wire("<-", msg)
        for device in self._devices:
            try:
                if isinstance(msg, GetProperties):
                    await device._dispatch_get_properties(msg)
                elif isinstance(msg, NewVector):
                    await device._dispatch_new(msg.vector)
                # def/set/message flowing the "wrong" way into a driver are ignored.
            except Exception as exc:  # noqa: BLE001 - deliberate per-message isolation
                device.log_error(f"handler for {message_name(msg)!r} failed: {exc}")

    async def _writer_loop(self) -> None:
        """Drain the outbox to the transport until the shutdown sentinel.

        The two ways this can fail are not the same failure, and the split is
        deliberate:

        * **Serialisation** is per message. A model the codec cannot render is
          one bad message - the same class of fault as a raising ``@on_new``
          handler - so it is reported to the client and dropped, and the driver
          keeps publishing everything else, for every device. Dying here would
          silence a working instrument over one malformed value. The writer
          holds only the message, so :func:`_owner` is what attributes the
          report; the outbox is shared and nothing else here knows whose
          message it was.
        * **The write** is not recoverable. stdout is the only way out, so there
          is nothing left to report the failure *on*, and the next message would
          hit the same broken pipe. It propagates, and :meth:`serve` stops the
          driver rather than spinning against a transport that is gone while the
          unbounded outbox fills behind it.
        """
        while True:
            msg = await self._outbox.get()
            if msg is None:
                return
            try:
                data = to_xml(msg) + b"\n"
            except Exception as exc:  # noqa: BLE001 - deliberate per-message isolation
                self._report(_owner(msg), f"could not serialise {message_name(msg)!r}: {exc}")
                continue
            log_wire("->", msg, len(data))
            await self._write(data)

    async def _run_periodic(
        self, device: Device, spec: PeriodicSpec, method: Callable[[], Any]
    ) -> None:
        """Run one device's ``@every`` job forever, one tick per interval.

        Waits for that device's ``setup()`` to complete first, so a tick never
        runs against a property that has not been defined yet - each device
        gates on its own, since a ``getProperties`` naming one device runs only
        that one's ``setup()``. Jobs declared with ``when_connected=True`` skip
        ticks while their device is not connected.

        Ticks are scheduled against a running deadline rather than by sleeping
        the interval after each one, so a job's period stays at its declared
        interval instead of drifting out by however long each tick takes: at
        ``@every(seconds=1)`` around a 300 ms hardware read, sleep-after-tick
        would run every 1.3 s.

        Parameters
        ----------
        device : Device
            The device owning the job.
        spec : PeriodicSpec
            The interval and gating declared by ``@every``.
        method : Callable
            The bound method to run each tick.
        """
        await device._setup_complete.wait()
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        if spec.start_immediately and (not spec.when_connected or device.connected):
            await self._tick(device, method)
        while True:
            deadline += spec.interval
            now = loop.time()
            if deadline < now:
                # Overran the interval: resync instead of firing the backlog
                # back-to-back, which would hammer the hardware to catch up.
                deadline = now
            await asyncio.sleep(deadline - now)
            if spec.when_connected and not device.connected:
                continue
            await self._tick(device, method)

    async def _tick(self, device: Device, method: Callable[[], Any]) -> None:
        """Run one tick under its own device's guard, isolating any failure.

        The guard (see `~indikit.driver.device.Device.serialize_dispatch`)
        keeps the tick from interleaving with a client write, so a tick that
        awaits mid-flight cannot publish pre-write state over a just-applied
        one. It is the *owning* device's guard and nobody else's, which is what
        keeps a co-located device's jobs running while this one is busy. A
        raised :class:`Exception` is logged to the client and swallowed;
        :class:`asyncio.CancelledError` is a :class:`BaseException`, so shutdown
        cancellation still propagates.

        Parameters
        ----------
        device : Device
            The device owning the job.
        method : Callable
            The bound method to run.
        """
        try:
            async with device._guard():
                result = method()
                if inspect.isawaitable(result):
                    await result
        except Exception as exc:  # noqa: BLE001 - deliberate per-tick isolation
            device.log_error(f"periodic task {task_name(method)!r} failed: {exc}")


def _owner(msg: IndiMessage) -> str | None:
    """Return the INDI device a message belongs to, or `None` if it names none.

    This is a device resolver, unlike :func:`message_name`, which builds a
    display string. The writer needs one: it holds a message and no device, and
    with several devices on one outbox the report has to say whose message
    failed.

    Parameters
    ----------
    msg : IndiMessage
        The message being attributed.

    Returns
    -------
    device : str or None
        The device name the message carries. `None` only for the messages whose
        ``device`` is optional - a ``getProperties`` or a ``message`` addressed
        to no device in particular.
    """
    if isinstance(msg, (DefVector, SetVector, NewVector)):
        return msg.vector.device
    return msg.device


def message_name(msg: IndiMessage) -> str:
    """Return a readable identifier for a message, for log messages.

    Used in both directions: an inbound write being dispatched, and an outbound
    message the writer could not serialise.

    Parameters
    ----------
    msg : IndiMessage
        The message being handled.

    Returns
    -------
    name : str
        ``device.property`` for any message carrying a vector, else the message
        tag.
    """
    if isinstance(msg, (DefVector, SetVector, NewVector)):
        return f"{msg.vector.device}.{msg.vector.name}"
    return type(msg).__name__


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


async def serve_stdio(
    devices: Device | Sequence[Device], *, config_dir: Path | None = None
) -> None:
    """Serve one or more devices over real stdin/stdout (async entrypoint).

    Parameters
    ----------
    devices : Device or Sequence of Device
        The device, or devices, to serve on this process's stdio.
    config_dir : Path or None, optional
        Where the devices keep their saved configuration. Resolved by the
        caller, because this coroutine is what tests and embedders await and
        reading the environment here would make every one of them do so.
    """
    read, write = await _open_stdio()
    await DriverRuntime(devices, read, write, config_dir=config_dir).serve()


def run(devices: Device | Sequence[Device]) -> None:
    """Serve one or more devices over real stdin/stdout until stdin closes.

    A list runs several devices from one executable, the shape ``indiserver``
    has always supported::

        run([Camera(), GuideChip(), FilterWheel()])

    **This is where a driver's logging is configured**, from
    ``INDIKIT_LOG_LEVEL`` and ``INDIKIT_WIRE_LOG`` in the environment
    ``indiserver`` was started in. That is the whole answer to "what is on the
    wire" for a driver author with no CLI in the loop: a driver launched as
    ``./my_driver.py`` reaches here through
    :meth:`~indikit.driver.device.Device.run` and picks the variables up.

    It is done here, the process entrypoint of the two, and **not** in
    :func:`serve_stdio`, which is a coroutine that tests and embedders await:
    configuring inside it would have every one of them mutate global logging
    state as a side effect of running a driver.

    Parameters
    ----------
    devices : Device or Sequence of Device
        The device, or devices, to run as an ``indiserver`` stdio child.
    """
    config = settings()
    configure_logging(config.log_level, wire=config.wire_log)
    asyncio.run(serve_stdio(devices, config_dir=config.config_dir))
