"""Tests for the driver SDK, exercised the way ``indiserver`` would drive it.

Each runtime test wires a :class:`DriverRuntime` to an in-memory byte
reader/writer (:class:`_Harness`) and runs it under ``anyio.run``, then parses the
captured output back into protocol messages with the M1 codec - the repo rule
that new wire behaviour gets a round-trip test.
"""

from __future__ import annotations

import math
from typing import Any

import anyio

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
        self._send, self._recv = anyio.create_memory_object_stream[bytes](math.inf)
        self.outputs: list[bytes] = []

    def feed(self, data: str | bytes) -> None:
        self._send.send_nowait(data.encode() if isinstance(data, str) else data)

    def eof(self) -> None:
        self._send.close()

    async def read(self) -> bytes:
        try:
            return await self._recv.receive()
        except anyio.EndOfStream:
            return b""

    async def write(self, data: bytes) -> None:
        self.outputs.append(data)

    def messages(self) -> list[IndiMessage]:
        return parse_indi(b"".join(self.outputs))


# --------------------------------------------------------------------------- #
# Test devices                                                                 #
# --------------------------------------------------------------------------- #
class _Simple(Device):
    name = "Simple"

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name)
        self.setup_calls = 0

    async def setup(self) -> None:
        self.setup_calls += 1
        self.define_number("num", [Number(name="v", value=1.0)], state=IPState.OK)
        self.define_switch(
            "sw",
            [Switch(name="a", value=ISState.OFF), Switch(name="b", value=ISState.ON)],
            rule=ISRule.ONE_OF_MANY,
        )


class _Poller(Device):
    name = "Poller"

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name)
        self.count = 0
        self.stop: Any = None

    @every(seconds=0.001, start_immediately=True)
    async def tick(self) -> None:
        if "x" not in self:
            self.define_number("x", [Number(name="v")])
        self.count += 1
        self["x"].set(v=self.count)
        if self.count >= 3 and self.stop is not None:
            self.stop()


class _Boom(Device):
    name = "Boom"

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name)
        self.ticks = 0
        self.stop: Any = None

    @every(seconds=0.001, start_immediately=True)
    async def bad(self) -> None:
        self.ticks += 1
        if self.ticks >= 2 and self.stop is not None:
            self.stop()
        raise RuntimeError("boom")


class _Handler(Device):
    name = "Handler"

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name)
        self.handled: SwitchVector | None = None
        self.fallback: Any = None

    @on_new("power")
    async def _power(self, vector: SwitchVector) -> None:
        self.handled = vector

    async def on_new_default(self, vector: Any) -> None:
        self.fallback = vector


# --------------------------------------------------------------------------- #
# Lifecycle                                                                    #
# --------------------------------------------------------------------------- #
def test_get_properties_runs_setup_once_and_defines() -> None:
    async def scenario() -> None:
        harness = _Harness()
        dev = _Simple()
        harness.feed("<getProperties version='1.7'/>")
        harness.eof()
        await DriverRuntime(dev, harness.read, harness.write).serve()

        assert dev.setup_calls == 1
        defs = [m for m in harness.messages() if isinstance(m, DefVector)]
        assert {d.vector.name for d in defs} == {"num", "sw"}

    anyio.run(scenario)


def test_second_get_properties_reannounces_without_rerunning_setup() -> None:
    async def scenario() -> None:
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

    anyio.run(scenario)


# --------------------------------------------------------------------------- #
# @every                                                                       #
# --------------------------------------------------------------------------- #
def test_periodic_task_emits_updates() -> None:
    async def scenario() -> None:
        harness = _Harness()
        dev = _Poller()
        dev.stop = harness.eof  # the 3rd tick ends the session
        with anyio.fail_after(5):
            await DriverRuntime(dev, harness.read, harness.write).serve()

        sets = [m for m in harness.messages() if isinstance(m, SetVector)]
        assert dev.count >= 3
        assert len(sets) == dev.count  # one emit per tick

    anyio.run(scenario)


def test_periodic_task_error_is_isolated() -> None:
    async def scenario() -> None:
        harness = _Harness()
        dev = _Boom()
        dev.stop = harness.eof
        with anyio.fail_after(5):
            # A raising tick must not propagate out of serve().
            await DriverRuntime(dev, harness.read, harness.write).serve()

        msgs = [m for m in harness.messages() if isinstance(m, Message)]
        assert msgs, "expected the failure to be surfaced as an INDI message"
        assert any("boom" in (m.message or "") for m in msgs)

    anyio.run(scenario)


# --------------------------------------------------------------------------- #
# @on_new dispatch                                                             #
# --------------------------------------------------------------------------- #
def test_on_new_routes_to_handler_and_default() -> None:
    async def scenario() -> None:
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

    anyio.run(scenario)


# --------------------------------------------------------------------------- #
# BoundProperty                                                                #
# --------------------------------------------------------------------------- #
def test_set_one_of_many_clears_siblings_and_round_trips() -> None:
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
    a = _Poller("A")
    b = _Poller("B")
    ((_, a_tick),) = list(iter_periodic(a))
    ((_, b_tick),) = list(iter_periodic(b))
    assert a_tick.__self__ is a  # type: ignore[attr-defined]
    assert b_tick.__self__ is b  # type: ignore[attr-defined]
    assert a._new_handlers is not b._new_handlers
