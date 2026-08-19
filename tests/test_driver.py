"""Tests for the driver SDK, exercised the way ``indiserver`` would drive it.

Each runtime test wires a :class:`DriverRuntime` to an in-memory byte
reader/writer (:class:`_Harness`) and runs it under ``asyncio.run``, then parses
the captured output back into protocol messages with the M1 codec - the repo rule
that new wire behaviour gets a round-trip test.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
import time
from types import SimpleNamespace
from typing import Any

import pytest

from indikit.driver import BoundProperty, Device, DriverRuntime, every, on_new
from indikit.driver.scheduling import iter_periodic
from indikit.logging_config import WIRE_LOGGER
from indikit.protocol import (
    BLOB,
    BLOBVector,
    DefVector,
    DelProperty,
    IndiMessage,
    IPState,
    ISRule,
    ISState,
    Message,
    Number,
    NumberVector,
    SetVector,
    Switch,
    SwitchVector,
    parse_indi,
    to_xml,
)
from indikit.protocol import xml as xml_module


class _Harness:
    """A controllable stdin (feed/eof) and a capturing stdout.

    Parameters
    ----------
    fail_write_on : int or None, optional
        Which write raises `OSError`, counting from one - a broken stdout, the
        way a real one breaks: part way through a working session.
    """

    def __init__(self, *, fail_write_on: int | None = None) -> None:
        """Create an empty inbox queue and output buffer."""
        # ``b""`` is the read-side EOF signal, matching a real closed pipe.
        self._inbox: asyncio.Queue[bytes] = asyncio.Queue()
        self.outputs: list[bytes] = []
        self._fail_write_on = fail_write_on
        self.writes = 0

    def feed(self, data: str | bytes) -> None:
        """Queue inbound bytes for the runtime's reader.

        Parameters
        ----------
        data : str or bytes
            The bytes (or text) to deliver as the next read.
        """
        self._inbox.put_nowait(data.encode() if isinstance(data, str) else data)

    def eof(self) -> None:
        """Signal end-of-input to the reader."""
        self._inbox.put_nowait(b"")

    async def read(self) -> bytes:
        """Return the next queued chunk (``b""`` at EOF)."""
        return await self._inbox.get()

    async def write(self, data: bytes) -> None:
        """Capture one outbound chunk from the runtime's writer.

        Parameters
        ----------
        data : bytes
            The serialised message.

        Raises
        ------
        OSError
            Raised on the write named by ``fail_write_on``.
        """
        self.writes += 1
        if self.writes == self._fail_write_on:
            raise OSError("broken pipe")
        self.outputs.append(data)

    def messages(self) -> list[IndiMessage]:
        """Parse everything written so far into message models."""
        return parse_indi(b"".join(self.outputs))


# --------------------------------------------------------------------------- #
# Test devices                                                                 #
# --------------------------------------------------------------------------- #
class _Simple(Device):
    """A minimal device that defines two properties and counts setup calls."""

    name = "Simple"

    def __init__(self, name: str | None = None) -> None:
        """Initialise with a zeroed setup counter."""
        super().__init__(name)
        self.setup_calls = 0

    async def setup(self) -> None:
        """Define a number and a switch vector, tracking the call count."""
        self.setup_calls += 1
        self.define_number("num", [Number(name="v", value=1.0)], state=IPState.OK)
        self.define_switch(
            "sw",
            [Switch(name="a", value=ISState.OFF), Switch(name="b", value=ISState.ON)],
            rule=ISRule.ONE_OF_MANY,
        )


class _Poller(Device):
    """A device whose periodic job defines a property and emits each tick."""

    name = "Poller"

    def __init__(self, name: str | None = None) -> None:
        """Initialise with a zeroed tick count and no stop callback."""
        super().__init__(name)
        self.count = 0
        self.stop: Any = None

    @every(seconds=0.001, start_immediately=True)
    async def tick(self) -> None:
        """Count up, emit an update, and stop the session after three ticks."""
        if "x" not in self:
            self.define_number("x", [Number(name="v")])
        self.count += 1
        self["x"].set(v=self.count)
        if self.count >= 3 and self.stop is not None:
            self.stop()


class _Boom(Device):
    """A device whose periodic job always raises, to test error isolation."""

    name = "Boom"

    def __init__(self, name: str | None = None) -> None:
        """Initialise with a zeroed tick count and no stop callback."""
        super().__init__(name)
        self.ticks = 0
        self.stop: Any = None

    @every(seconds=0.001, start_immediately=True)
    async def bad(self) -> None:
        """Stop the session after two ticks, then raise on every tick."""
        self.ticks += 1
        if self.ticks >= 2 and self.stop is not None:
            self.stop()
        raise RuntimeError("boom")


class _SetupPoller(Device):
    """A device whose @every uses a property defined in setup() (ordering guard)."""

    name = "SetupPoller"

    def __init__(self, name: str | None = None) -> None:
        """Initialise with a zeroed tick count and no stop callback."""
        super().__init__(name)
        self.ticks = 0
        self.stop: Any = None

    async def setup(self) -> None:
        """Define the property the periodic job writes to."""
        self.define_number("counters", [Number(name="v")])

    @every(seconds=0.001, start_immediately=True)
    async def animate(self) -> None:
        """Write to the setup-defined property; would KeyError before setup."""
        self.ticks += 1
        self["counters"].set(v=self.ticks)
        if self.ticks >= 3 and self.stop is not None:
            self.stop()


class _Handler(Device):
    """A device recording which writes reach its handler vs. the default."""

    name = "Handler"

    def __init__(self, name: str | None = None) -> None:
        """Initialise with no recorded handled/fallback vectors."""
        super().__init__(name)
        self.handled: SwitchVector | None = None
        self.fallback: Any = None

    @on_new("power")
    async def _power(self, vector: SwitchVector) -> None:
        """Record a client write routed to the ``power`` handler."""
        self.handled = vector

    async def on_new_default(self, vector: Any) -> None:
        """Record a client write with no matching handler."""
        self.fallback = vector


# --------------------------------------------------------------------------- #
# Lifecycle                                                                    #
# --------------------------------------------------------------------------- #
def test_get_properties_runs_setup_once_and_defines() -> None:
    """A first ``getProperties`` runs ``setup`` once and emits every def."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Simple()
        harness.feed("<getProperties version='1.7'/>")
        harness.eof()
        await DriverRuntime(dev, harness.read, harness.write).serve()

        assert dev.setup_calls == 1
        defs = [m for m in harness.messages() if isinstance(m, DefVector)]
        assert {d.vector.name for d in defs} == {"num", "sw"}

    asyncio.run(scenario())


def test_second_get_properties_reannounces_without_rerunning_setup() -> None:
    """A repeat ``getProperties`` re-announces defs without re-running setup."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Simple()
        harness.feed("<getProperties/>")
        harness.feed("<getProperties/>")
        harness.eof()
        await DriverRuntime(dev, harness.read, harness.write).serve()

        assert dev.setup_calls == 1
        defs = [m for m in harness.messages() if isinstance(m, DefVector)]
        # Two properties, announced on setup and re-announced on the 2nd request.
        assert len(defs) == 4

    asyncio.run(scenario())


def test_get_properties_for_another_device_is_ignored() -> None:
    """A getProperties naming a different device draws no response (INDI spec)."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Simple()  # device name "Simple"
        harness.feed("<getProperties device='Other'/>")
        harness.eof()
        await DriverRuntime(dev, harness.read, harness.write).serve()

        assert dev.setup_calls == 0  # setup did not run
        assert harness.messages() == []  # nothing announced

    asyncio.run(scenario())


def test_get_properties_for_our_device_responds() -> None:
    """A getProperties naming this device runs setup and announces it."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Simple()
        harness.feed("<getProperties device='Simple'/>")
        harness.eof()
        await DriverRuntime(dev, harness.read, harness.write).serve()

        assert dev.setup_calls == 1
        assert {m.vector.name for m in harness.messages() if isinstance(m, DefVector)} == {
            "num",
            "sw",
        }

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# @every                                                                       #
# --------------------------------------------------------------------------- #
def test_periodic_task_emits_updates() -> None:
    """An ``@every`` job emits one set per tick until the session ends."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Poller()
        dev.stop = harness.eof  # the 3rd tick ends the session
        harness.feed("<getProperties/>")  # runs setup(), which releases @every jobs
        async with asyncio.timeout(5):
            await DriverRuntime(dev, harness.read, harness.write).serve()

        sets = [m for m in harness.messages() if isinstance(m, SetVector)]
        assert dev.count >= 3
        assert len(sets) == dev.count  # one emit per tick

    asyncio.run(scenario())


def test_periodic_task_error_is_isolated() -> None:
    """A raising tick is surfaced as a message and never crashes the driver."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Boom()
        dev.stop = harness.eof
        harness.feed("<getProperties/>")  # runs setup(), which releases @every jobs
        async with asyncio.timeout(5):
            # A raising tick must not propagate out of serve().
            await DriverRuntime(dev, harness.read, harness.write).serve()

        msgs = [m for m in harness.messages() if isinstance(m, Message)]
        assert msgs, "expected the failure to be surfaced as an INDI message"
        assert any("boom" in (m.message or "") for m in msgs)

    asyncio.run(scenario())


def test_periodic_task_waits_for_setup() -> None:
    """An @every job that uses a setup-defined property does not run before setup.

    Regression: without gating, ``animate`` fired after its interval before any
    ``getProperties`` had triggered ``setup()``, so ``self["counters"]`` raised
    ``KeyError: 'counters'`` (surfaced as an ERROR message).
    """

    async def scenario() -> None:
        """Serve briefly with no getProperties, so setup() never runs."""
        harness = _Harness()
        dev = _SetupPoller()
        # No getProperties is ever fed, so setup() must not run and the periodic
        # job (start_immediately=True) must stay parked rather than KeyError.
        serve = asyncio.create_task(DriverRuntime(dev, harness.read, harness.write).serve())
        await asyncio.sleep(0.05)  # ample time for a 1ms interval to have fired
        harness.eof()
        async with asyncio.timeout(5):
            await serve

        assert dev.ticks == 0  # the job waited for setup
        assert not any(isinstance(m, Message) for m in harness.messages())

    asyncio.run(scenario())


def test_periodic_task_runs_after_setup() -> None:
    """Once setup() runs, an @every job may use the properties it defined."""

    async def scenario() -> None:
        """Feed getProperties so setup() defines the property, then let it tick."""
        harness = _Harness()
        dev = _SetupPoller()
        dev.stop = harness.eof
        harness.feed("<getProperties/>")
        async with asyncio.timeout(5):
            await DriverRuntime(dev, harness.read, harness.write).serve()

        assert dev.ticks >= 3
        sets = [m for m in harness.messages() if isinstance(m, SetVector)]
        assert sets and sets[0].vector.name == "counters"
        assert not any(isinstance(m, Message) for m in harness.messages())  # no errors

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# @on_new dispatch                                                             #
# --------------------------------------------------------------------------- #
def test_on_new_routes_to_handler_and_default() -> None:
    """Client writes route to the matching handler, else ``on_new_default``."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Handler()
        harness.feed(
            "<newSwitchVector device='Handler' name='power'>"
            "<oneSwitch name='on'>On</oneSwitch></newSwitchVector>"
        )
        harness.feed(
            "<newSwitchVector device='Handler' name='other'>"
            "<oneSwitch name='x'>On</oneSwitch></newSwitchVector>"
        )
        harness.eof()
        await DriverRuntime(dev, harness.read, harness.write).serve()

        assert dev.handled is not None
        assert dev.handled.name == "power"
        assert dev.handled["on"].value == ISState.ON
        assert dev.fallback is not None
        assert dev.fallback.name == "other"

    asyncio.run(scenario())


def test_writes_addressed_to_other_devices_are_ignored() -> None:
    """A ``new`` naming a different device never reaches the handlers.

    Matches libindi's ``strcmp(dev, getDeviceName())`` guard; a broadcast hub
    (several drivers on one stream, as in ``indikit serve --device``) relies
    on this so only the addressed device reacts to a write.
    """

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Handler()
        harness.feed(
            "<newSwitchVector device='SomeoneElse' name='power'>"
            "<oneSwitch name='on'>On</oneSwitch></newSwitchVector>"
        )
        harness.eof()
        await DriverRuntime(dev, harness.read, harness.write).serve()

        assert dev.handled is None
        assert dev.fallback is None

    asyncio.run(scenario())


def test_raising_on_new_handler_does_not_kill_the_driver() -> None:
    """A handler exception is logged to the client and the driver keeps serving.

    Regression test for the panel freeze: a OneOfMany write carrying only the
    newly-selected element made a handler assuming the other element raise
    ``KeyError``, which used to unwind the reader loop and stop the driver.
    """

    class _Fragile(Device):
        """A device whose power handler assumes an element that may be absent."""

        name = "Fragile"

        def __init__(self, name: str | None = None) -> None:
            """Track which writes reached the handler."""
            super().__init__(name)
            self.handled: list[str] = []

        async def setup(self) -> None:
            """Define the switch the handler serves."""
            self.define_switch(
                "power",
                [Switch(name="on", value=ISState.OFF), Switch(name="off", value=ISState.ON)],
                rule=ISRule.ONE_OF_MANY,
            )

        @on_new("power")
        async def _power(self, vector: SwitchVector) -> None:
            """Record the write, then index an element that may not be present."""
            self.handled.append(vector.name)
            vector.element("on")  # raises KeyError when only "off" was sent

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Fragile()
        harness.feed("<getProperties version='1.7'/>")
        harness.feed(
            "<newSwitchVector device='Fragile' name='power'>"
            "<oneSwitch name='off'>On</oneSwitch></newSwitchVector>"  # no "on" element
        )
        harness.feed(
            "<newSwitchVector device='Fragile' name='power'>"
            "<oneSwitch name='on'>On</oneSwitch></newSwitchVector>"
        )
        harness.eof()
        await DriverRuntime(dev, harness.read, harness.write).serve()

        # Both writes reached the handler: the KeyError did not stop the reader.
        assert dev.handled == ["power", "power"]
        errors = [
            m for m in harness.messages() if isinstance(m, Message) and "failed" in str(m.message)
        ]
        assert errors, "the handler failure was not reported to the client"
        assert "Fragile.power" in str(errors[0].message)

    asyncio.run(scenario())


def test_a_malformed_client_write_does_not_kill_the_driver() -> None:
    """Junk on stdin costs one message; the driver keeps serving.

    The parse failure happened while the reader *iterated* the parser, so it
    came up outside ``_handle``'s per-message try/except and ended ``serve()``:
    ``indiserver`` saw the driver exit and every property went away. The
    malformed element is now dropped by the codec, so the reader never sees it.
    """

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Handler()
        harness.feed(
            "<newNumberVector device='Handler' name='power'>"
            "<oneNumber name='v'>not-a-number</oneNumber></newNumberVector>"
        )
        harness.feed(
            "<newSwitchVector device='Handler' name='power'>"
            "<oneSwitch name='on'>On</oneSwitch></newSwitchVector>"
        )
        harness.eof()
        async with asyncio.timeout(5):
            await DriverRuntime(dev, harness.read, harness.write).serve()

        # The good write that followed the junk still reached the handler.
        assert dev.handled is not None
        assert dev.handled["on"].value == ISState.ON

    asyncio.run(scenario())


def test_a_failing_setup_is_retried_and_does_not_strand_the_periodic_jobs() -> None:
    """Hardware absent at boot must leave a driver retryable, not wedged.

    ``_setup_done`` used to latch before ``setup()`` ran and ``_setup_complete``
    only after it returned, so a raising setup was never retried *and* every
    ``@every`` job waited on the gate forever: zero ticks, one ERROR message,
    and a process that looks alive to ``indiserver`` while being dead.
    """

    class _AbsentHardware(Device):
        """A device whose setup fails until its (fake) hardware turns up."""

        name = "Absent"

        def __init__(self, name: str | None = None) -> None:
            """Start with the hardware missing and nothing having run."""
            super().__init__(name)
            self.present = False
            self.setup_calls = 0
            self.ticks = 0

        async def setup(self) -> None:
            """Fail while the hardware is missing, define the property once it is not."""
            self.setup_calls += 1
            if not self.present:
                raise RuntimeError("no hardware on /dev/ttyUSB0")
            self.define_number("counters", [Number(name="v")])

        @every(seconds=0.001, start_immediately=True)
        async def poll(self) -> None:
            """Tick regardless, so a job can be what notices the hardware appear."""
            self.ticks += 1

    async def scenario() -> None:
        """Fail the first getProperties, then succeed on the second."""
        harness = _Harness()
        dev = _AbsentHardware()
        harness.feed("<getProperties/>")  # setup() raises
        serve = asyncio.create_task(DriverRuntime(dev, harness.read, harness.write).serve())
        await asyncio.sleep(0.05)

        # The gate opened despite the failure, so the jobs are running.
        assert dev.ticks > 0
        assert dev.setup_calls == 1

        dev.present = True
        harness.feed("<getProperties/>")  # retried, and this time it works
        await asyncio.sleep(0.05)
        harness.eof()
        async with asyncio.timeout(5):
            await serve

        assert dev.setup_calls == 2
        defs = [m for m in harness.messages() if isinstance(m, DefVector)]
        assert [d.vector.name for d in defs] == ["counters"]
        errors = [m for m in harness.messages() if isinstance(m, Message)]
        assert any("no hardware" in str(m.message) for m in errors)

    asyncio.run(scenario())


def test_a_partially_completed_setup_retracts_everything_it_defined() -> None:
    """A setup that raises half-way leaves no trace, on the wire or in the device.

    The realistic shape is a probe - "channel 1 found, channel 2 found, channel
    3 timed out" - and ``define_*`` only replaces a name the *retry* defines
    again. So an orphan used to sit in the device for the life of the process:
    never retracted, and re-announced to every client that joined later.
    """

    class _Probing(Device):
        """A device that probes for channels and fails part-way the first time."""

        name = "Probing"

        def __init__(self, name: str | None = None) -> None:
            """Start with nothing probed and no handle captured."""
            super().__init__(name)
            self.attempts = 0
            self.transient: BoundProperty[Any] | None = None

        async def setup(self) -> None:
            """Define what the probe found; the first attempt dies on the last channel."""
            self.attempts += 1
            self.define_number("ch1", [Number(name="v")])
            if self.attempts == 1:
                self.transient = self.define_number("ch2", [Number(name="v")])
                raise RuntimeError("ch3 timed out")

    async def scenario() -> None:
        """Fail the first getProperties, succeed on the second, then re-announce."""
        harness = _Harness()
        dev = _Probing()
        harness.feed("<getProperties/>")  # attempt 1: defines ch1 and ch2, then raises
        serve = asyncio.create_task(DriverRuntime(dev, harness.read, harness.write).serve())
        await asyncio.sleep(0.05)

        harness.feed("<getProperties/>")  # attempt 2: this time only ch1 exists
        await asyncio.sleep(0.05)
        harness.feed("<getProperties/>")  # what a late-joining client sees
        await asyncio.sleep(0.05)
        harness.eof()
        async with asyncio.timeout(5):
            await serve

        assert dev.attempts == 2
        assert "ch2" not in dev

        msgs = harness.messages()
        # ch2 is announced once, by the attempt that defined it, and never again.
        assert [m.vector.name for m in msgs if isinstance(m, DefVector)] == [
            "ch1",
            "ch2",
            "ch1",
            "ch1",
        ]
        deletions = [m for m in msgs if isinstance(m, DelProperty)]
        assert [m.name for m in deletions] == ["ch1", "ch2"]
        assert all("ch3 timed out" in str(m.message) for m in deletions)

        # The handle that attempt handed out is dead, not silently publishing.
        assert dev.transient is not None
        with pytest.raises(RuntimeError, match="retracted"):
            dev.transient.set(v=1.0)

    asyncio.run(scenario())


def test_the_rollback_leaves_a_property_a_job_defined_alone() -> None:
    """The rollback undoes the attempt, not everything the device happens to hold.

    Once the ``@every`` gate opens a job can define properties of its own -
    that is how a driver heals itself when the hardware turns up - and a later
    failed setup must not take them with it. Which is why the rollback compares
    handles instead of assuming a retrying device is empty.
    """

    class _Healer(Device):
        """A device whose setup keeps failing while its job defines a property."""

        name = "Healer"

        def __init__(self, name: str | None = None) -> None:
            """Start with nothing probed."""
            super().__init__(name)
            self.attempts = 0

        async def setup(self) -> None:
            """Define a property, then fail - the hardware is still not there."""
            self.attempts += 1
            self.define_number("probe", [Number(name="v")])
            raise RuntimeError("still no hardware")

        @every(seconds=0.001, start_immediately=True)
        async def heal(self) -> None:
            """Define the job's own property once, the way a recovering driver would."""
            if "healer" not in self:
                self.define_number("healer", [Number(name="v")])

    async def scenario() -> None:
        """Fail setup twice, with the job getting its property in between."""
        harness = _Harness()
        dev = _Healer()
        harness.feed("<getProperties/>")
        serve = asyncio.create_task(DriverRuntime(dev, harness.read, harness.write).serve())
        await asyncio.sleep(0.05)
        assert "healer" in dev  # the job ran once the gate opened

        harness.feed("<getProperties/>")
        await asyncio.sleep(0.05)
        harness.eof()
        async with asyncio.timeout(5):
            await serve

        assert dev.attempts == 2
        assert "healer" in dev
        msgs = harness.messages()
        assert [m.name for m in msgs if isinstance(m, DelProperty)] == ["probe", "probe"]
        # The second rollback re-announces the restored set, which is the job's
        # property and nothing else.
        assert [m.vector.name for m in msgs if isinstance(m, DefVector)] == [
            "probe",
            "healer",
            "probe",
            "healer",
        ]

    asyncio.run(scenario())


def test_a_muted_parser_is_resynced_in_place_and_keeps_its_counters(monkeypatch, caplog) -> None:
    """A driver has one stdin, so it rebuilds the parser instead of reconnecting.

    The rebuild used to throw the old parser away unread, taking the peer's
    ``dropped``/``resets`` history with it - discarded at the one moment it is
    most worth having. The counters describe the stream, so they now survive the
    rebuild and the warning reports them.
    """
    monkeypatch.setattr(xml_module, "STALL_THRESHOLD_BYTES", 32)

    async def scenario() -> None:
        """Drop an element, mute the parser, then write again after the resync."""
        harness = _Harness()
        dev = _Handler()
        harness.feed(
            "<newNumberVector device='Handler' name='power'>"
            "<oneNumber name='v'>not-a-number</oneNumber></newNumberVector>"  # dropped
        )
        # A root close landing mid-start-tag: lxml emits nothing from here on.
        harness.feed("<newSwitchVector device='Handler' name='power'")
        harness.feed("</indikit>")
        for _ in range(4):
            harness.feed("<message message='swallowed'/>")
        harness.feed(
            "<newSwitchVector device='Handler' name='power'>"
            "<oneSwitch name='on'>On</oneSwitch></newSwitchVector>"
        )
        harness.eof()
        async with asyncio.timeout(5):
            await DriverRuntime(dev, harness.read, harness.write).serve()

        # The write after the resync reached the handler: the driver kept serving.
        assert dev.handled is not None
        assert dev.handled["on"].value == ISState.ON

    with caplog.at_level(logging.WARNING, logger="indikit.driver.runtime"):
        asyncio.run(scenario())

    # Only this logger's own records: the codec logs each drop as it happens too.
    (warning,) = [r.getMessage() for r in caplog.records if r.name == "indikit.driver.runtime"]
    assert "resyncing the parser" in warning
    assert "1 dropped" in warning  # the malformed element, remembered across the rebuild


# --------------------------------------------------------------------------- #
# The writer loop's two failures                                               #
# --------------------------------------------------------------------------- #
def test_a_failed_write_stops_the_driver() -> None:
    """A broken stdout ends the session instead of leaving a mute driver running.

    The writer task used to die on its own with nobody watching: the reader kept
    accepting work, the ``@every`` jobs kept filling an explicitly unbounded
    outbox, and ``indiserver`` saw a driver that was still connected and had
    simply stopped saying anything. Note that no EOF is ever fed here - stdin
    stays open, as a real one would - so ``serve`` returning at all is the point.
    """

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness(fail_write_on=2)  # the first write works
        dev = _Poller()  # emits on every tick, forever
        harness.feed("<getProperties/>")  # opens the gate the periodic jobs wait on

        # The timeout sits outside, so a hang fails as a hang rather than being
        # swallowed by pytest.raises: TimeoutError is itself an OSError.
        async with asyncio.timeout(5):
            with pytest.raises(OSError, match="broken pipe"):
                await DriverRuntime(dev, harness.read, harness.write).serve()

        assert len(harness.outputs) == 1
        ticks = dev.count
        await asyncio.sleep(0.05)
        assert dev.count == ticks  # the periodic jobs stopped with the driver

    asyncio.run(scenario())


def test_a_message_that_will_not_serialise_costs_only_that_message() -> None:
    """A codec failure is one bad message, isolated like a raising handler.

    Killing the writer over it would silence a working instrument because one
    value went strange - the opposite trade from the transport failure above,
    where there is nothing left to say it on.
    """

    class _BadPayload(Device):
        """A device whose BLOB payload is set past the handle's coercion."""

        name = "BadPayload"

        async def setup(self) -> None:
            """Define the BLOB the test then corrupts."""
            self.define_blob("img", [BLOB(name="frame")])

    async def scenario() -> None:
        """Emit an unserialisable message, then a good one."""
        harness = _Harness()
        dev = _BadPayload()
        harness.feed("<getProperties/>")
        serve = asyncio.create_task(DriverRuntime(dev, harness.read, harness.write).serve())
        await asyncio.sleep(0.05)

        # Straight onto the model: ``BoundProperty.set`` coerces the payload to
        # bytes, so this is a driver reaching past the handle - and base64
        # encoding a str raises inside ``to_xml``, in the writer task.
        blob = dev.blob("img").vector.elements[0]
        blob.data = "not bytes"  # type: ignore[assignment]
        dev["img"].set(state=IPState.BUSY)
        await asyncio.sleep(0.05)

        blob.data = b"fine now"
        dev["img"].set(state=IPState.OK)
        await asyncio.sleep(0.05)
        harness.eof()
        async with asyncio.timeout(5):
            await serve

        msgs = harness.messages()
        errors = [m for m in msgs if isinstance(m, Message)]
        assert any("could not serialise" in str(m.message) for m in errors)
        assert any("BadPayload.img" in str(m.message) for m in errors)
        # The good emission after it still went out: the driver kept serving.
        sets = [m for m in msgs if isinstance(m, SetVector)]
        assert [m.vector.state for m in sets] == [IPState.OK]

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Emissions are values, not views                                              #
# --------------------------------------------------------------------------- #
class _Slewer(Device):
    """A device whose handler announces Busy, works, and then announces Ok.

    The commonest shape there is in a real driver, and the one that exposes a
    queued message still pointing at the live vector: the writer serialises both
    emissions after the handler has finished, so both would report the final
    state.
    """

    name = "Slewer"

    async def setup(self) -> None:
        """Define the position the handler slews."""
        self.define_number("POS", [Number(name="AZ", value=0.0)])

    @on_new("POS")
    async def _go(self, vector: NumberVector) -> None:
        """Publish the move as Busy, then publish its result as Ok."""
        self["POS"].set(AZ=10.0, state=IPState.BUSY)
        self["POS"].set(AZ=90.0, state=IPState.OK)


def test_a_busy_transient_reaches_the_wire_intact() -> None:
    """Two sets in one handler serialise as two different states, not one twice."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        harness.feed("<getProperties version='1.7'/>")
        harness.feed(
            "<newNumberVector device='Slewer' name='POS'>"
            "<oneNumber name='AZ'>90</oneNumber></newNumberVector>"
        )
        harness.eof()
        await DriverRuntime(_Slewer(), harness.read, harness.write).serve()

        sets = [m for m in harness.messages() if isinstance(m, SetVector)]
        assert [(m.vector.state, m.vector.get("AZ")) for m in sets] == [
            (IPState.BUSY, 10.0),
            (IPState.OK, 90.0),
        ]

    asyncio.run(scenario())


class _Restamper(Device):
    """A device that publishes a new value the instant after defining it."""

    name = "Restamper"

    async def setup(self) -> None:
        """Define a property at its initial value, then immediately move it."""
        prop = self.define_number("POS", [Number(name="AZ", value=1.0)], state=IPState.IDLE)
        prop.set(AZ=99.0, state=IPState.OK)


def test_a_def_reports_the_values_it_was_defined_with() -> None:
    """A ``def`` is a value too: a later ``set`` must not rewrite it in the queue."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        harness.feed("<getProperties version='1.7'/>")
        harness.eof()
        await DriverRuntime(_Restamper(), harness.read, harness.write).serve()

        (definition,) = [m for m in harness.messages() if isinstance(m, DefVector)]
        assert definition.vector.get("AZ") == 1.0
        assert definition.vector.state is IPState.IDLE

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# BoundProperty                                                                #
# --------------------------------------------------------------------------- #
def test_set_one_of_many_clears_siblings_and_round_trips() -> None:
    """Setting one OneOfMany switch On clears siblings and round-trips."""
    captured: list[IndiMessage] = []
    vec = SwitchVector(
        device="d",
        name="power",
        rule=ISRule.ONE_OF_MANY,
        elements=[Switch(name="on", value=ISState.OFF), Switch(name="off", value=ISState.ON)],
    )
    prop = BoundProperty(vec, captured.append)

    prop.set(on=True, state=IPState.OK)

    assert vec.element("on").value == ISState.ON
    assert vec.element("off").value == ISState.OFF

    (msg,) = captured
    parsed = parse_indi(to_xml(msg))[0]
    assert isinstance(parsed, SetVector)
    assert parsed.vector.state == IPState.OK
    assert parsed.vector.element("on").value == ISState.ON
    assert parsed.vector.element("off").value == ISState.OFF


def test_bound_property_accessors() -> None:
    """The handle exposes its vector, name, state, elements, and values."""
    vec = NumberVector(
        device="d",
        name="coords",
        state=IPState.BUSY,
        elements=[Number(name="RA", value=1.5)],
    )
    prop = BoundProperty(vec, lambda msg: None)

    assert prop.vector is vec
    assert prop.name == "coords"
    assert prop.state == IPState.BUSY
    assert prop["RA"].value == 1.5
    assert prop.value("RA") == 1.5


def test_bound_property_value_reads_blob_data() -> None:
    """value() returns the payload bytes for a BLOB element."""
    vec = BLOBVector(device="d", name="img", elements=[BLOB(name="frame", data=b"FITS")])
    prop = BoundProperty(vec, lambda msg: None)
    assert prop.value("frame") == b"FITS"


def test_set_blob_element_updates_data_and_size() -> None:
    """Assigning a BLOB element stores the bytes and recomputes its size."""
    captured: list[IndiMessage] = []
    vec = BLOBVector(device="d", name="img", elements=[BLOB(name="frame")])
    prop = BoundProperty(vec, captured.append)

    prop.set(frame=b"\x00\x01payload", state=IPState.OK)

    el = vec.element("frame")
    assert el.data == b"\x00\x01payload"
    assert el.size == len(b"\x00\x01payload")
    (msg,) = captured
    assert isinstance(msg, SetVector)


def test_set_message_attaches_to_the_vector() -> None:
    """set(message=...) stores the message on the emitted vector."""
    captured: list[IndiMessage] = []
    vec = NumberVector(device="d", name="n", elements=[Number(name="v")])
    prop = BoundProperty(vec, captured.append)

    prop.set(v=2.0, message="slewing")

    assert vec.message == "slewing"
    (msg,) = captured
    assert isinstance(msg, SetVector)
    assert msg.vector.message == "slewing"


def test_switch_accepts_wire_string_values() -> None:
    """A switch element accepts the "On"/"Off" wire strings as values."""
    vec = SwitchVector(device="d", name="p", elements=[Switch(name="a", value=ISState.OFF)])
    prop = BoundProperty(vec, lambda msg: None)
    prop.set(a="On")
    assert vec.element("a").value == ISState.ON


def test_delete_emits_del_property() -> None:
    """delete() emits a delProperty for the wrapped vector."""
    captured: list[IndiMessage] = []
    vec = NumberVector(device="d", name="n", elements=[Number(name="v")])
    prop = BoundProperty(vec, captured.append)

    prop.delete("gone")

    (msg,) = captured
    assert isinstance(msg, DelProperty)
    assert msg.device == "d"
    assert msg.name == "n"
    assert msg.message == "gone"


def test_reserved_element_name_via_values_dict() -> None:
    """The positional values dict sets an element whose name is reserved."""
    captured: list[IndiMessage] = []
    vec = SwitchVector(
        device="d",
        name="p",
        elements=[Switch(name="state", value=ISState.OFF)],
    )
    prop = BoundProperty(vec, captured.append)

    # "state" is both an element name and the reserved vector-state keyword.
    prop.set({"state": ISState.ON}, state=IPState.BUSY)

    assert vec.element("state").value == ISState.ON
    assert vec.state == IPState.BUSY


# --------------------------------------------------------------------------- #
# Instance isolation (guards the legacy class-global @repeat regression)       #
# --------------------------------------------------------------------------- #
def test_periodic_discovery_is_per_instance() -> None:
    """Periodic jobs and handler maps are bound per instance, not shared."""
    a = _Poller("A")
    b = _Poller("B")
    ((_, a_tick),) = list(iter_periodic(a))
    ((_, b_tick),) = list(iter_periodic(b))
    assert a_tick.__self__ is a  # type: ignore[attr-defined]
    assert b_tick.__self__ is b  # type: ignore[attr-defined]
    assert a._new_handlers is not b._new_handlers


# --------------------------------------------------------------------------- #
# Device surface                                                               #
# --------------------------------------------------------------------------- #
def test_device_name_and_property_lookup() -> None:
    """The device property and property() lookup expose defined state."""
    captured: list[IndiMessage] = []
    dev = _Simple("Named")
    dev._bind(captured.append)
    assert dev.device == "Named"

    prop = dev.define_number("num", [Number(name="v", value=1.0)])
    assert dev.property("num") is prop
    assert dev["num"] is prop
    assert "num" in dev


def test_define_fills_in_the_device_name() -> None:
    """define() stamps this device's name onto a vector with none set."""
    captured: list[IndiMessage] = []
    dev = _Simple()
    dev._bind(captured.append)

    prop = dev.define(NumberVector(device="", name="n", elements=[Number(name="v")]))

    assert prop.vector.device == "Simple"
    (msg,) = captured
    assert isinstance(msg, DefVector)
    assert msg.vector.device == "Simple"


def test_define_blob_emits_a_blob_def() -> None:
    """define_blob registers a BLOB vector and emits its def."""
    captured: list[IndiMessage] = []
    dev = _Simple()
    dev._bind(captured.append)

    dev.define_blob("img", [BLOB(name="frame", format=".fits")], group="Data")

    (msg,) = captured
    assert isinstance(msg, DefVector)
    assert isinstance(msg.vector, BLOBVector)
    assert msg.vector.name == "img"
    assert msg.vector.element("frame").format == ".fits"


def test_send_without_runtime_raises() -> None:
    """Defining or messaging on an unbound device raises RuntimeError."""
    dev = _Simple()
    with pytest.raises(RuntimeError):
        dev.message("not attached")


def test_every_rejects_non_positive_interval() -> None:
    """@every with a zero (or negative) total interval is rejected."""
    with pytest.raises(ValueError):
        every(seconds=0.0)
    with pytest.raises(ValueError):
        every(seconds=-1.0, minutes=0.0)


# --------------------------------------------------------------------------- #
# Real stdio wiring                                                            #
# --------------------------------------------------------------------------- #
def test_device_run_serves_over_real_stdio(monkeypatch) -> None:
    """Device.run() serves a session over actual stdin/stdout streams.

    stdin is replaced with the read end of an OS pipe pre-loaded with a
    ``getProperties`` and already closed (EOF), and stdout with a buffer, so the
    blocking entrypoint runs one full serve cycle and returns.
    """
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"<getProperties/>")
    os.close(write_fd)
    monkeypatch.setattr(sys, "stdin", os.fdopen(read_fd, "rb", buffering=0))
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=out))

    _Simple.run("StdioDev")

    defs = [m for m in parse_indi(out.getvalue()) if isinstance(m, DefVector)]
    assert {d.vector.name for d in defs} == {"num", "sw"}
    assert all(d.vector.device == "StdioDev" for d in defs)


class _Linked(Device):
    """A device using the built-in CONNECTION lifecycle."""

    name = "Linked"

    def __init__(self, name: str | None = None) -> None:
        """Track hook invocations."""
        super().__init__(name)
        self.opened = 0
        self.closed = 0

    async def setup(self) -> None:
        """Define the standard connection switch."""
        self.define_connection()

    async def on_connect(self) -> None:
        """Record the link opening."""
        self.opened += 1

    async def on_disconnect(self) -> None:
        """Record the link closing."""
        self.closed += 1


def _connection_write(device: str, element: str) -> str:
    """Build the XML for a client CONNECTION switch write."""
    return (
        f"<newSwitchVector device='{device}' name='CONNECTION'>"
        f"<oneSwitch name='{element}'>On</oneSwitch></newSwitchVector>"
    )


def test_define_connection_provides_the_standard_lifecycle() -> None:
    """The built-in CONNECTION handler flips the switch and runs the hooks."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Linked()
        harness.feed("<getProperties version='1.7'/>")
        harness.feed(_connection_write("Linked", "CONNECT"))
        harness.feed(_connection_write("Linked", "DISCONNECT"))
        harness.eof()
        await DriverRuntime(dev, harness.read, harness.write).serve()

        assert dev.opened == 1
        assert dev.closed == 1
        assert dev["CONNECTION"].vector.get("DISCONNECT") is ISState.ON
        messages = [str(m.message) for m in harness.messages() if isinstance(m, Message)]
        assert any("Linked is connected." in m for m in messages)
        assert any("Linked is disconnected." in m for m in messages)

    asyncio.run(scenario())


def test_connected_property_and_require_connected() -> None:
    """The connected property follows the switch; no CONNECTION means always up."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        captured: list[IndiMessage] = []
        dev = _Linked()
        dev._bind(captured.append)
        await dev.setup()
        assert dev.connected is False
        assert dev.require_connected() is False  # logs the standard error
        assert any(
            isinstance(m, Message) and "Linked is not connected." in str(m.message)
            for m in captured
        )

        await dev._dispatch_new(
            SwitchVector(
                device="Linked",
                name="CONNECTION",
                elements=[Switch(name="CONNECT", value=ISState.ON)],
            )
        )
        assert dev.connected is True
        assert dev.require_connected() is True

        plain = _Simple()
        assert plain.connected is True  # no CONNECTION property: always up

    asyncio.run(scenario())


def test_subclass_connection_handler_shadows_the_builtin() -> None:
    """A driver's own @on_new("CONNECTION") replaces the built-in handler."""

    class _Custom(_Linked):
        """A device overriding the connection handling entirely."""

        name = "Custom"

        @on_new("CONNECTION")
        async def _my_connection(self, vector: SwitchVector) -> None:
            """Record the write without flipping anything."""
            self.opened += 10

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        captured: list[IndiMessage] = []
        dev = _Custom()
        dev._bind(captured.append)
        await dev.setup()
        await dev._dispatch_new(
            SwitchVector(
                device="Custom",
                name="CONNECTION",
                elements=[Switch(name="CONNECT", value=ISState.ON)],
            )
        )
        assert dev.opened == 10  # the custom handler ran
        assert dev.connected is False  # ...and the built-in flip did not

    asyncio.run(scenario())


def test_when_connected_jobs_pause_while_disconnected() -> None:
    """@every(when_connected=True) ticks only while the device is connected."""

    class _Poller(_Linked):
        """A device whose poll job requires the link to be up."""

        name = "Poller"

        def __init__(self, name: str | None = None) -> None:
            """Track poll ticks."""
            super().__init__(name)
            self.ticks = 0

        @every(seconds=0.01, when_connected=True)
        async def poll(self) -> None:
            """Count one gated tick."""
            self.ticks += 1

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Poller()
        harness.feed("<getProperties version='1.7'/>")
        task = asyncio.create_task(DriverRuntime(dev, harness.read, harness.write).serve())
        await asyncio.sleep(0.05)
        assert dev.ticks == 0  # disconnected: the job is paused

        harness.feed(_connection_write("Poller", "CONNECT"))
        await asyncio.sleep(0.05)
        assert dev.ticks >= 1  # connected: the job runs

        harness.eof()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Tick/handler serialisation                                                   #
# --------------------------------------------------------------------------- #
class _Racy(Device):
    """A device whose tick awaits mid-flight, then publishes what it read."""

    name = "Racy"

    def __init__(self, name: str | None = None) -> None:
        """Start with the button out and nothing in flight."""
        super().__init__(name)
        self.release = asyncio.Event()
        self.in_tick = asyncio.Event()

    async def setup(self) -> None:
        """Define the button the tick and the handler fight over."""
        self.define_switch("button", [Switch(name="go")], rule=ISRule.AT_MOST_ONE)

    @every(seconds=60)
    async def poll(self) -> None:
        """Read "not pressed", await, then publish that stale reading."""
        reading = ISState.OFF  # what the hardware said before the await
        self.in_tick.set()
        await self.release.wait()
        self["button"].set(go=reading, state=IPState.IDLE)

    @on_new("button")
    async def _press(self, vector: SwitchVector) -> None:
        """Apply the press."""
        self["button"].set(go=ISState.ON, state=IPState.BUSY)


def test_a_tick_in_flight_cannot_overwrite_a_client_write() -> None:
    """The device guard keeps a mid-await tick from publishing pre-write state."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        captured: list[IndiMessage] = []
        dev = _Racy()
        harness = _Harness()
        runtime = DriverRuntime(dev, harness.read, harness.write)
        dev._bind(captured.append)  # after the runtime, which binds its own outbox
        await dev.setup()

        tick = asyncio.create_task(runtime._tick(dev, dev.poll))
        await dev.in_tick.wait()

        # The client presses while the tick is parked on its await. Without the
        # guard this handler would run now and the tick would then undo it.
        press = asyncio.create_task(
            dev._dispatch_new(
                SwitchVector(
                    device="Racy", name="button", elements=[Switch(name="go", value=ISState.ON)]
                )
            )
        )
        await asyncio.sleep(0.02)
        assert not press.done()  # the write is queued behind the tick

        dev.release.set()
        await asyncio.gather(tick, press)

        final = [m for m in captured if isinstance(m, SetVector)][-1]
        assert final.vector.get("go") is ISState.ON
        assert final.vector.state is IPState.BUSY

    asyncio.run(scenario())


def test_serialize_dispatch_can_be_turned_off() -> None:
    """A device that opts out lets a client write land during a tick."""

    class _Unguarded(_Racy):
        """The same device with serialisation disabled."""

        name = "Unguarded"
        serialize_dispatch = False

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        dev = _Unguarded()
        dev._bind(lambda msg: None)
        await dev.setup()

        tick = asyncio.create_task(dev.poll())
        await dev.in_tick.wait()
        await dev._dispatch_new(
            SwitchVector(
                device="Unguarded", name="button", elements=[Switch(name="go", value=ISState.ON)]
            )
        )
        assert dev["button"].value("go") is ISState.ON  # the write got through

        dev.release.set()
        await tick
        assert dev["button"].value("go") is ISState.OFF  # ...and the tick undid it

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Scheduling                                                                   #
# --------------------------------------------------------------------------- #
def test_every_holds_its_period_across_slow_ticks() -> None:
    """The interval is a deadline, not a gap: a slow tick does not push it out."""

    class _Slow(Device):
        """A device whose tick takes most of its own interval."""

        name = "Slow"

        def __init__(self, name: str | None = None) -> None:
            """Record the loop time of each tick."""
            super().__init__(name)
            self.at: list[float] = []

        async def setup(self) -> None:
            """Nothing to define."""

        @every(seconds=0.05)
        async def poll(self) -> None:
            """Take 40 ms of a 50 ms interval."""
            self.at.append(asyncio.get_running_loop().time())
            await asyncio.sleep(0.04)

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Slow()
        harness.feed("<getProperties version='1.7'/>")
        task = asyncio.create_task(DriverRuntime(dev, harness.read, harness.write).serve())
        await asyncio.sleep(0.28)
        harness.eof()
        await asyncio.wait_for(task, timeout=2)

        gaps = [b - a for a, b in zip(dev.at, dev.at[1:], strict=False)]
        assert gaps, "expected more than one tick"
        # Sleep-after-tick would put every gap at ~0.09s; a deadline keeps ~0.05s.
        assert max(gaps) < 0.075

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# off_thread                                                                   #
# --------------------------------------------------------------------------- #
def test_off_thread_keeps_the_event_loop_turning() -> None:
    """A blocking call routed through off_thread does not stall the reactor."""

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        turns = 0

        async def spin() -> None:
            """Count event-loop turns while the blocking call is in flight."""
            nonlocal turns
            while True:
                await asyncio.sleep(0.005)
                turns += 1

        spinner = asyncio.create_task(spin())
        result = await Device.off_thread(_blocking_add, 2, offset=3)
        spinner.cancel()

        assert result == 5
        assert turns > 3

    asyncio.run(scenario())


def _blocking_add(value: int, *, offset: int) -> int:
    """Sleep, then add, standing in for a blocking hardware call."""
    time.sleep(0.1)
    return value + offset


# --------------------------------------------------------------------------- #
# Connection rollback                                                          #
# --------------------------------------------------------------------------- #
def test_a_failing_on_connect_rolls_the_switch_back() -> None:
    """Hardware that is not there leaves CONNECTION disconnected and in Alert."""

    class _Absent(Device):
        """A device whose link cannot be opened."""

        name = "Absent"

        async def setup(self) -> None:
            """Define only the connection switch."""
            self.define_connection()

        async def on_connect(self) -> None:
            """Fail the way a missing serial port does."""
            raise OSError("No such file or directory: '/dev/ttyUSB0'")

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        captured: list[IndiMessage] = []
        dev = _Absent()
        dev._bind(captured.append)
        await dev.setup()
        await dev._dispatch_new(
            SwitchVector(
                device="Absent",
                name="CONNECTION",
                elements=[Switch(name="CONNECT", value=ISState.ON)],
            )
        )

        assert dev.connected is False
        final = [m for m in captured if isinstance(m, SetVector)][-1]
        assert final.vector.state is IPState.ALERT
        assert final.vector.get("DISCONNECT") is ISState.ON
        assert any("ttyUSB0" in m.message for m in captured if isinstance(m, Message))

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Typed property access                                                        #
# --------------------------------------------------------------------------- #
def test_typed_getters_return_the_property() -> None:
    """self.switch(name) is self[name], with the vector kind pinned down."""

    class _Kinds(Device):
        """A device with one switch and one number."""

        name = "Kinds"

        async def setup(self) -> None:
            """Define one of two kinds."""
            self.define_switch("sw", [Switch(name="a")])
            self.define_number("num", [Number(name="n")])

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        dev = _Kinds()
        dev._bind(lambda msg: None)
        await dev.setup()

        assert dev.switch("sw") is dev["sw"]
        assert [el.name for el in dev.switch("sw").vector.elements] == ["a"]
        with pytest.raises(TypeError, match="not a NumberVector"):
            dev.number("sw")
        with pytest.raises(KeyError):
            dev.switch("missing")

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Property deletion                                                            #
# --------------------------------------------------------------------------- #
class _Retractor(Device):
    """A device whose cooler exists only while the link is up.

    The canonical INDI shape, and the one the libindi driver corpus is full of:
    hardware-dependent properties are defined in the connect hook and withdrawn
    in the disconnect hook, once per connection, for the life of the process.
    """

    name = "Retractor"

    async def setup(self) -> None:
        """Define the connection switch; the cooler waits for the link."""
        self.define_connection()

    async def on_connect(self) -> None:
        """Publish the cooler now that the camera is talking."""
        self.define_number("CCD_COOLER", [Number(name="TEMPERATURE", value=25.0)])

    async def on_disconnect(self) -> None:
        """Withdraw the cooler; nothing behind it is readable any more."""
        self.delete_property("CCD_COOLER", "only while connected")


def test_a_deleted_property_is_not_reannounced_to_a_later_client() -> None:
    """A withdrawn property stays withdrawn, including for a client joining later.

    The bug this pins: ``delete`` announced the retraction but left the property
    in the device, so the next ``getProperties`` - a second client connecting,
    which is routine - was told about a property the driver had withdrawn, and
    got a handle that raises on the first ``set``.
    """

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        harness = _Harness()
        dev = _Retractor()
        harness.feed("<getProperties version='1.7'/>")
        harness.feed(_connection_write("Retractor", "CONNECT"))
        harness.feed(_connection_write("Retractor", "DISCONNECT"))
        # A second client asking what this device exposes.
        harness.feed("<getProperties version='1.7'/>")
        harness.eof()
        await DriverRuntime(dev, harness.read, harness.write).serve()

        assert "CCD_COOLER" not in dev

        messages = harness.messages()
        deletions = [m for m in messages if isinstance(m, DelProperty)]
        assert [m.name for m in deletions] == ["CCD_COOLER"]
        assert deletions[0].message == "only while connected"

        # Everything defined after the retraction is what the late client was
        # told, and the cooler is not in it.
        cut = messages.index(deletions[0])
        later = [m.vector.name for m in messages[cut:] if isinstance(m, DefVector)]
        assert later == ["CONNECTION"]

    asyncio.run(scenario())


def test_deleting_through_the_handle_unregisters_the_property() -> None:
    """``self[name].delete()`` removes the property, not just announces it.

    The handle form is the older API and the one existing drivers hold, so it
    has to mean the same thing as the name form; both go through one
    implementation precisely so they cannot drift apart.
    """

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        captured: list[IndiMessage] = []
        dev = _Simple()
        dev._bind(captured.append)
        await dev.setup()

        dev["num"].delete("withdrawn")

        assert "num" not in dev
        with pytest.raises(KeyError):
            dev["num"]
        (deletion,) = [m for m in captured if isinstance(m, DelProperty)]
        assert deletion.name == "num"
        assert deletion.message == "withdrawn"

    asyncio.run(scenario())


def test_deleting_an_unknown_property_says_nothing() -> None:
    """An unknown name is a silent no-op: no wire traffic, no exception.

    This is what lets a disconnect hook retract unconditionally, which is what
    the whole libindi driver corpus does. ``removeProperty`` returns an error
    there and ``deleteProperty`` never reads it.
    """

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        captured: list[IndiMessage] = []
        dev = _Simple()
        dev._bind(captured.append)
        await dev.setup()
        captured.clear()

        dev.delete_property("NEVER_DEFINED", "gone")

        assert captured == []

    asyncio.run(scenario())


def test_two_disconnects_in_a_row_are_a_silent_no_op() -> None:
    """The second connect/disconnect cycle behaves exactly like the first.

    Define-delete-define is the normal life of an INDI property, not an edge
    case, so a driver must be able to run the cycle indefinitely: the second
    disconnect finds nothing to retract and says nothing about it.
    """

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        captured: list[IndiMessage] = []
        dev = _Retractor()
        dev._bind(captured.append)
        await dev.setup()

        for _ in range(2):
            await dev._dispatch_new(
                SwitchVector(
                    device="Retractor",
                    name="CONNECTION",
                    elements=[Switch(name="CONNECT", value=ISState.ON)],
                )
            )
            assert "CCD_COOLER" in dev
            await dev._dispatch_new(
                SwitchVector(
                    device="Retractor",
                    name="CONNECTION",
                    elements=[Switch(name="DISCONNECT", value=ISState.ON)],
                )
            )
            assert "CCD_COOLER" not in dev

        # Two cycles, two retractions - not three, and not one.
        deletions = [m for m in captured if isinstance(m, DelProperty)]
        assert [m.name for m in deletions] == ["CCD_COOLER", "CCD_COOLER"]

        # A third disconnect with nothing defined retracts nothing at all.
        captured.clear()
        await dev.on_disconnect()
        assert [m for m in captured if isinstance(m, DelProperty)] == []

    asyncio.run(scenario())


def test_a_property_defined_after_deletion_is_live_again() -> None:
    """Redefining a withdrawn property announces it and hands back a live handle.

    The re-define path has to be completely unobstructed: the retracted handle
    is dead, but the name is free and the property that takes it is new.
    """

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        captured: list[IndiMessage] = []
        dev = _Simple()
        dev._bind(captured.append)
        await dev.setup()
        first = dev["num"]

        dev.delete_property("num")
        captured.clear()
        second = dev.define_number("num", [Number(name="v", value=7.0)])

        assert second is not first
        assert dev["num"] is second
        assert [m.vector.name for m in captured if isinstance(m, DefVector)] == ["num"]

        # The new handle publishes; the old one still refuses to.
        second.set(v=8.0)
        assert dev.number("num")["v"].value == 8.0
        with pytest.raises(RuntimeError, match="retracted"):
            first.set(v=9.0)

    asyncio.run(scenario())


def test_deleting_connection_is_allowed() -> None:
    """No property is protected, CONNECTION included - libindi guards none here.

    Asserting the consequence rather than inventing a guard: the device becomes
    one without connection semantics, which is exactly what a device with no
    CONNECTION property already means here.
    """

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        captured: list[IndiMessage] = []
        dev = _Linked()
        dev._bind(captured.append)
        await dev.setup()
        captured.clear()

        dev.delete_property("CONNECTION", "no longer switchable")

        assert "CONNECTION" not in dev
        (deletion,) = [m for m in captured if isinstance(m, DelProperty)]
        assert deletion.name == "CONNECTION"
        # No CONNECTION property means no connection semantics, so commands run.
        assert dev.connected is True
        assert dev.require_connected() is True

    asyncio.run(scenario())


def test_a_superseded_handle_retracts_nothing_at_all() -> None:
    """A late delete on a redefined name touches neither the device nor the wire.

    Identity decides what a handle owns, not the name it was defined under. A
    driver that redefines a property and then retracts the handle it had been
    holding must not take the replacement down with it - and must not send a
    ``delProperty`` for that name either, because every client would apply it to
    the replacement and lose a property the driver still has.
    """

    async def scenario() -> None:
        """Run the async body of this test on the event loop."""
        captured: list[IndiMessage] = []
        dev = _Simple()
        dev._bind(captured.append)
        await dev.setup()
        stale = dev["num"]
        replacement = dev.define_number("num", [Number(name="v", value=2.0)])
        captured.clear()

        stale.delete()

        assert dev["num"] is replacement
        assert [m for m in captured if isinstance(m, DelProperty)] == []
        replacement.set(v=3.0)  # still live, and still the one clients hold
        assert dev.number("num")["v"].value == 3.0

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Several devices on one stream                                                #
# --------------------------------------------------------------------------- #
class _Head(Device):
    """One device of a multi-device driver, recording everything it was asked.

    Parameters
    ----------
    name : str
        The INDI device name this instance answers to.
    fail : bool, optional
        Whether ``setup`` and the ``@on_new`` handler raise, to exercise the
        runtime's per-device error isolation.
    """

    def __init__(self, name: str, *, fail: bool = False) -> None:
        """Initialise with zeroed counters and no recorded writes."""
        super().__init__(name)
        self.fail = fail
        self.setup_calls = 0
        self.ticks = 0
        self.writes: list[float] = []

    async def setup(self) -> None:
        """Define this head's one property, raising first when asked to fail."""
        self.setup_calls += 1
        if self.fail:
            raise RuntimeError("no hardware")
        self.define_number("count", [Number(name="v", value=0.0)])

    @every(seconds=0.001, start_immediately=True)
    async def poll(self) -> None:
        """Count one tick; the gate opens only after this head's own setup."""
        self.ticks += 1

    @on_new("count")
    async def _write(self, vector: NumberVector) -> None:
        """Record a client write, raising first when asked to fail."""
        if self.fail:
            raise RuntimeError("write refused")
        self.writes.append(vector.get("v", 0.0))


def _new_count(device: str, value: float) -> str:
    """Return a client ``newNumberVector`` for one head's ``count`` property.

    Parameters
    ----------
    device : str
        The device the write is addressed to.
    value : float
        The value written to element ``v``.

    Returns
    -------
    xml : str
        The serialised client write.
    """
    return (
        f"<newNumberVector device='{device}' name='count'>"
        f"<oneNumber name='v'>{value}</oneNumber></newNumberVector>"
    )


def test_a_runtime_needs_at_least_one_device() -> None:
    """An empty sequence is refused at construction rather than serving nothing."""
    with pytest.raises(ValueError, match="at least one device"):
        DriverRuntime([], _Harness().read, _Harness().write)


def test_two_devices_answering_to_one_name_are_refused() -> None:
    """Duplicate device names on one stream are unresolvable, so they raise.

    No client could route a write between them, and both device-name guards
    would answer every message addressed to the shared name.
    """
    harness = _Harness()
    with pytest.raises(ValueError, match="duplicate device name"):
        DriverRuntime([_Head("Twin"), _Head("Twin")], harness.read, harness.write)


def test_get_properties_reaches_every_device_or_only_the_named_one() -> None:
    """An unaddressed getProperties sets up both heads; an addressed one, only its own."""

    async def scenario() -> None:
        """Broadcast a getProperties, then address one head alone."""
        harness = _Harness()
        main, guide = _Head("Main"), _Head("Guide")
        harness.feed("<getProperties version='1.7'/>")
        harness.eof()
        await DriverRuntime([main, guide], harness.read, harness.write).serve()

        assert (main.setup_calls, guide.setup_calls) == (1, 1)
        assert {d.vector.device for d in harness.messages() if isinstance(d, DefVector)} == {
            "Main",
            "Guide",
        }

        harness = _Harness()
        main, guide = _Head("Main"), _Head("Guide")
        harness.feed("<getProperties device='Main'/>")
        harness.eof()
        await DriverRuntime([main, guide], harness.read, harness.write).serve()

        assert (main.setup_calls, guide.setup_calls) == (1, 0)
        assert {d.vector.device for d in harness.messages() if isinstance(d, DefVector)} == {"Main"}

    asyncio.run(scenario())


def test_a_write_reaches_only_the_device_it_names() -> None:
    """Each device's own name guard is what routes a client write on a shared stream."""

    async def scenario() -> None:
        """Write to one head and check the other never heard it."""
        harness = _Harness()
        main, guide = _Head("Main"), _Head("Guide")
        harness.feed("<getProperties/>")
        harness.feed(_new_count("Guide", 7.0))
        harness.eof()
        await DriverRuntime([main, guide], harness.read, harness.write).serve()

        assert guide.writes == [7.0]
        assert main.writes == []

    asyncio.run(scenario())


def test_every_device_gets_its_own_periodic_jobs() -> None:
    """``@every`` discovery is per device, so both heads poll on one runtime."""

    async def scenario() -> None:
        """Serve both heads briefly and check each one ticked."""
        harness = _Harness()
        main, guide = _Head("Main"), _Head("Guide")
        harness.feed("<getProperties/>")
        serve = asyncio.create_task(
            DriverRuntime([main, guide], harness.read, harness.write).serve()
        )
        await asyncio.sleep(0.05)
        harness.eof()
        async with asyncio.timeout(5):
            await serve

        assert main.ticks >= 2
        assert guide.ticks >= 2

    asyncio.run(scenario())


def test_a_failing_setup_on_one_device_leaves_the_others_alone() -> None:
    """One head's raising setup is reported against it and the rest still define.

    The reader offers the message to every device in turn, so the isolation has
    to be per device and not per message: a broadcast getProperties that killed
    the loop at the first failure would leave every device behind it silent.
    """

    async def scenario() -> None:
        """Broadcast a getProperties past a head whose setup raises."""
        harness = _Harness()
        broken, guide = _Head("Broken", fail=True), _Head("Guide")
        harness.feed("<getProperties/>")
        harness.eof()
        await DriverRuntime([broken, guide], harness.read, harness.write).serve()

        msgs = harness.messages()
        assert [d.vector.device for d in msgs if isinstance(d, DefVector)] == ["Guide"]
        (error,) = [m for m in msgs if isinstance(m, Message)]
        assert error.device == "Broken"  # attributed to the device dispatched to
        assert str(error.message).startswith("[ERROR] ")
        assert "no hardware" in str(error.message)

    asyncio.run(scenario())


def test_a_raising_handler_is_attributed_to_its_own_device() -> None:
    """A failing write on one head neither stops nor is blamed on the other."""

    async def scenario() -> None:
        """Write to the failing head, then to the healthy one."""
        harness = _Harness()
        broken, guide = _Head("Broken", fail=True), _Head("Guide")
        harness.feed("<getProperties device='Guide'/>")
        harness.feed(_new_count("Broken", 1.0))
        harness.feed(_new_count("Guide", 2.0))
        harness.eof()
        await DriverRuntime([broken, guide], harness.read, harness.write).serve()

        (error,) = [m for m in harness.messages() if isinstance(m, Message)]
        assert error.device == "Broken"
        assert str(error.message).startswith("[ERROR] ")
        assert "Broken.count" in str(error.message)
        assert guide.writes == [2.0]  # the driver kept serving the other head

    asyncio.run(scenario())


def test_an_unserialisable_message_is_blamed_on_the_device_that_sent_it() -> None:
    """The writer holds no device, so the message's own device is what it reports.

    With one outbox behind several devices, an unattributed report would send an
    operator looking at the wrong instrument.
    """

    class _BadBlob(Device):
        """A device whose BLOB payload is set past the handle's coercion."""

        async def setup(self) -> None:
            """Define the BLOB the test then corrupts."""
            self.define_blob("img", [BLOB(name="frame")])

    async def scenario() -> None:
        """Emit an unserialisable message from one device, a good one from the other."""
        harness = _Harness()
        camera, guide = _BadBlob("Camera"), _Head("Guide")
        harness.feed("<getProperties/>")
        serve = asyncio.create_task(
            DriverRuntime([camera, guide], harness.read, harness.write).serve()
        )
        await asyncio.sleep(0.05)

        # Reaching past the handle: base64 encoding a str raises inside to_xml,
        # in the writer task, with only the message to go on.
        camera.blob("img").vector.elements[0].data = "not bytes"  # type: ignore[assignment]
        camera["img"].set(state=IPState.BUSY)
        guide["count"].set(v=5.0)
        await asyncio.sleep(0.05)
        harness.eof()
        async with asyncio.timeout(5):
            await serve

        msgs = harness.messages()
        (error,) = [m for m in msgs if isinstance(m, Message)]
        assert error.device == "Camera"
        assert str(error.message).startswith("[ERROR] could not serialise 'Camera.img'")
        # The other device's emission still went out: the writer dropped one message.
        assert [(m.vector.device, m.vector.name) for m in msgs if isinstance(m, SetVector)] == [
            ("Guide", "count")
        ]

    asyncio.run(scenario())


def test_a_slow_handler_on_one_device_does_not_stop_the_others_ticking() -> None:
    """The concurrency boundary of a multi-device driver, pinned in both directions.

    Inbound dispatch is sequential - the reader awaits each handler inline - so a
    slow handler does delay the *next* inbound message for every device. What it
    must not delay is the other devices' ``@every`` jobs: those are one task per
    job taking only their own device's guard, and they are what keeps a
    co-located instrument publishing while its neighbour is busy.
    """

    class _Slow(Device):
        """A device whose handler parks until the test releases it."""

        def __init__(self, name: str) -> None:
            """Initialise with the two events the test drives it by."""
            super().__init__(name)
            self.in_handler = asyncio.Event()
            self.release = asyncio.Event()

        async def setup(self) -> None:
            """Define the property the client writes to."""
            self.define_number("count", [Number(name="v", value=0.0)])

        @on_new("count")
        async def _write(self, vector: NumberVector) -> None:
            """Announce arrival and park, holding this device's guard."""
            self.in_handler.set()
            await self.release.wait()

    async def scenario() -> None:
        """Park a write on one device and watch the other keep polling."""
        harness = _Harness()
        slow, guide = _Slow("Slow"), _Head("Guide")
        harness.feed("<getProperties/>")
        harness.feed(_new_count("Slow", 1.0))
        serve = asyncio.create_task(
            DriverRuntime([slow, guide], harness.read, harness.write).serve()
        )
        async with asyncio.timeout(5):
            await slow.in_handler.wait()

        ticks = guide.ticks
        await asyncio.sleep(0.05)
        assert guide.ticks > ticks  # the neighbour polled right through it

        slow.release.set()
        harness.eof()
        async with asyncio.timeout(5):
            await serve

    asyncio.run(scenario())


def test_the_stall_warning_names_every_device_on_the_stream(monkeypatch, caplog) -> None:
    """One stream, one parser, so the warning has to name everything it carries.

    An operator reading ``indiserver``'s log needs to know which driver process
    went quiet, and with several devices in one process naming only the first
    would point at an instrument that may be perfectly healthy.
    """
    monkeypatch.setattr(xml_module, "STALL_THRESHOLD_BYTES", 32)

    async def scenario() -> None:
        """Mute the parser with a root close landing mid-start-tag."""
        harness = _Harness()
        harness.feed("<newSwitchVector device='Main' name='count'")
        harness.feed("</indikit>")
        for _ in range(4):
            harness.feed("<message message='swallowed'/>")
        harness.eof()
        async with asyncio.timeout(5):
            await DriverRuntime(
                [_Head("Main"), _Head("Guide")], harness.read, harness.write
            ).serve()

    with caplog.at_level(logging.WARNING, logger="indikit.driver.runtime"):
        asyncio.run(scenario())

    (warning,) = [r.getMessage() for r in caplog.records if r.name == "indikit.driver.runtime"]
    assert warning.startswith("Main, Guide: ")


# --------------------------------------------------------------------------- #
# Wire logging                                                                 #
# --------------------------------------------------------------------------- #
class _Blobber(Device):
    """A device that publishes one BLOB, so the log has a payload to not print."""

    name = "Cam"

    async def setup(self) -> None:
        """Define and immediately publish a BLOB big enough to notice."""
        prop = self.define_blob("CCD1", [BLOB(name="image")])
        payload = b"\x00\xff" * 512
        prop.set(image=payload)


def test_wire_logging_reports_both_directions(caplog):
    """One line per message, on one logger, whichever end of the driver saw it.

    An operator wants a single switch for "show me the wire", not to learn that
    the reader and the writer are different modules - which is why this is not on
    ``indikit.driver.runtime``'s own logger.
    """

    async def scenario() -> None:
        """Drive a getProperties and a client write through the runtime."""
        harness = _Harness()
        harness.feed("<getProperties version='1.7'/>")
        harness.feed(_new_count("Main", 3.0))
        harness.eof()
        await DriverRuntime(_Head("Main"), harness.read, harness.write).serve()

    with caplog.at_level(logging.DEBUG, logger=WIRE_LOGGER):
        asyncio.run(scenario())

    lines = [r.getMessage() for r in caplog.records if r.name == WIRE_LOGGER]
    assert "<- getProperties" in lines
    assert "<- new Main.count" in lines
    assert any(line.startswith("-> def Main.count (") for line in lines)


def test_a_blob_is_logged_by_size_and_never_by_payload(caplog):
    """One BLOB frame is megabytes; logging it would make the log the bottleneck."""

    async def scenario() -> None:
        """Define and publish a BLOB, then let the driver shut down."""
        harness = _Harness()
        harness.feed("<getProperties version='1.7'/>")
        harness.eof()
        await DriverRuntime(_Blobber(), harness.read, harness.write).serve()

    with caplog.at_level(logging.DEBUG, logger=WIRE_LOGGER):
        asyncio.run(scenario())

    lines = [r.getMessage() for r in caplog.records if r.name == WIRE_LOGGER]
    (published,) = [line for line in lines if line.startswith("-> set Cam.CCD1")]
    assert "[1024 byte payload]" in published
    assert "\\x00" not in published and "AP8A" not in published


def test_nothing_is_logged_on_the_wire_below_debug(caplog):
    """The ``isEnabledFor`` guard: a normal run pays one flag check per message."""

    async def scenario() -> None:
        """Run a driver through a full getProperties round trip."""
        harness = _Harness()
        harness.feed("<getProperties version='1.7'/>")
        harness.eof()
        await DriverRuntime(_Head("Main"), harness.read, harness.write).serve()

    with caplog.at_level(logging.INFO, logger=WIRE_LOGGER):
        asyncio.run(scenario())

    assert [r for r in caplog.records if r.name == WIRE_LOGGER] == []
