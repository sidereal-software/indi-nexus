"""Tests for the driver SDK, exercised the way ``indiserver`` would drive it.

Each runtime test wires a :class:`DriverRuntime` to an in-memory byte
reader/writer (:class:`_Harness`) and runs it under ``asyncio.run``, then parses
the captured output back into protocol messages with the M1 codec - the repo rule
that new wire behaviour gets a round-trip test.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import time
from types import SimpleNamespace
from typing import Any

import pytest

from indi_nexus.driver import BoundProperty, Device, DriverRuntime, every, on_new
from indi_nexus.driver.scheduling import iter_periodic
from indi_nexus.protocol import (
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


class _Harness:
    """A controllable stdin (feed/eof) and a capturing stdout."""

    def __init__(self) -> None:
        """Create an empty inbox queue and output buffer."""
        # ``b""`` is the read-side EOF signal, matching a real closed pipe.
        self._inbox: asyncio.Queue[bytes] = asyncio.Queue()
        self.outputs: list[bytes] = []

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
        """Capture one outbound chunk from the runtime's writer."""
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
    (several drivers on one stream, as in ``examples/demo_bridge.py``) relies
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

        tick = asyncio.create_task(runtime._tick(dev.poll))
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
        assert any(
            "ttyUSB0" in m.message for m in captured if isinstance(m, Message)
        )

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
