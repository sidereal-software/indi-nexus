"""Tests for the driver SDK, exercised the way ``indiserver`` would drive it.

Each runtime test wires a :class:`DriverRuntime` to an in-memory byte
reader/writer (:class:`_Harness`) and runs it under ``asyncio.run``, then parses
the captured output back into protocol messages with the M1 codec - the repo rule
that new wire behaviour gets a round-trip test.
"""

from __future__ import annotations

import asyncio
from typing import Any

from indi_nexus.driver import BoundProperty, Device, DriverRuntime, every, on_new
from indi_nexus.driver.scheduling import iter_periodic
from indi_nexus.protocol import (
    DefVector,
    IndiMessage,
    IPState,
    ISRule,
    ISState,
    Message,
    Number,
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
