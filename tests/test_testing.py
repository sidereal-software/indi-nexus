"""Tests for ``DeviceHarness`` - the seam driver authors test their drivers through.

The harness is what third-party driver repos will lean on, so these cover the
contract they will rely on: writes reach ``@on_new`` handlers looking like real
client writes, ticks run one iteration, and the read-back accessors report what
a client would actually be holding.
"""

from __future__ import annotations

import pytest

from indikit.driver import Device, every, on_new
from indikit.protocol import (
    BLOB,
    BLOBVector,
    IPState,
    ISRule,
    ISState,
    Light,
    Number,
    NumberVector,
    Switch,
    SwitchVector,
    Text,
)
from indikit.testing import DeviceHarness


class _Sample(Device):
    """A device with one of every vector kind, a job, and two handlers."""

    name = "Sample"

    def __init__(self, name: str | None = None) -> None:
        """Track what the handlers and the job saw."""
        super().__init__(name)
        self.ticks = 0
        self.writes: list[dict[str, object]] = []
        self.rule_seen: ISRule | None = None
        self.payloads: list[bytes | None] = []

    async def setup(self) -> None:
        """Define the five properties this device exposes."""
        self.define_number("coords", [Number(name="ra"), Number(name="dec")], group="Main")
        self.define_text("label", [Text(name="value")], group="Main")
        self.define_switch(
            "power",
            [Switch(name="on"), Switch(name="off", value=ISState.ON)],
            rule=ISRule.ONE_OF_MANY,
            group="Main",
        )
        self.define_light("health", Light.from_labels(["Link", "Sensors"]), group="Main")
        self.define_blob("frame", [BLOB(name="image")], group="Data")
        self.message("Sample ready.")

    @every(seconds=60)
    async def poll(self) -> None:
        """Count a tick and publish the count."""
        self.ticks += 1
        self["coords"].set(ra=float(self.ticks), state=IPState.OK)

    @on_new("coords")
    async def _coords(self, vector: NumberVector) -> None:
        """Record exactly what the client sent."""
        self.writes.append(vector.values())

    @on_new("power")
    async def _power(self, vector: SwitchVector) -> None:
        """Record the rule the write arrived with, and apply the selection."""
        self.rule_seen = vector.rule
        selected = vector.selected()
        if selected is not None:
            self["power"].set({selected: ISState.ON}, state=IPState.OK)

    @on_new("frame")
    async def _frame(self, vector: BLOBVector) -> None:
        """Record the BLOB payload the client sent."""
        self.payloads.append(vector.get("image"))


@pytest.fixture
async def harness():
    """Return a set-up harness over a fresh sample device."""
    harness = DeviceHarness(_Sample())
    await harness.setup()
    return harness


# --------------------------------------------------------------------------- #
# Driving                                                                      #
# --------------------------------------------------------------------------- #
async def test_setup_runs_the_device_setup(harness) -> None:
    """setup() triggers the device's own setup, capturing every def."""
    assert [vec.name for vec in harness.defs()] == [
        "coords",
        "label",
        "power",
        "health",
        "frame",
    ]
    assert harness.messages == ["[INFO] Sample ready."]


async def test_setup_twice_re_announces_for_a_late_joining_client(harness) -> None:
    """A second getProperties re-emits the defs rather than running setup again."""
    harness.clear()

    await harness.setup()

    assert len(harness.defs()) == 5
    assert harness.messages == []  # setup() itself did not run a second time


async def test_write_reaches_the_handler_as_a_partial_vector(harness) -> None:
    """A write carries only the elements named, as a real client's does."""
    await harness.write("coords", ra=3.5)

    assert harness.device.writes == [{"ra": 3.5}]


async def test_write_coerces_switch_values(harness) -> None:
    """Switch writes accept bools and wire tokens, not just ISState."""
    await harness.write("power", on=True)

    assert harness.latest("power").get("on") is ISState.ON


async def test_write_carries_no_switch_rule(harness) -> None:
    """A newSwitchVector has no rule on the wire, so the harness sends none."""
    await harness.write("power", on=True)

    assert harness.device.rule_seen is ISRule.ANY_OF_MANY  # the model default


async def test_write_to_an_unknown_property_raises(harness) -> None:
    """Writing to a property that was never defined is a test bug, so it raises."""
    with pytest.raises(KeyError):
        await harness.write("nope", value=1)


async def test_tick_runs_one_iteration_of_a_job(harness) -> None:
    """tick() runs the job body once, without waiting out the interval."""
    await harness.tick("poll")
    await harness.tick("poll")

    assert harness.device.ticks == 2
    assert harness.latest("coords").get("ra") == 2.0


async def test_tick_on_an_unknown_job_raises(harness) -> None:
    """Naming a job that does not exist raises rather than silently doing nothing."""
    with pytest.raises(KeyError, match="no @every job"):
        await harness.tick("nonexistent")


async def test_write_of_a_blob_carries_bytes(harness) -> None:
    """A BLOB write is built from bytes, not a value field."""
    await harness.write("frame", image=b"\x01\x02")

    assert harness.device.payloads == [b"\x01\x02"]


# --------------------------------------------------------------------------- #
# Reading back                                                                 #
# --------------------------------------------------------------------------- #
async def test_latest_falls_back_to_the_definition(harness) -> None:
    """Before anything is published, the def is what a client holds."""
    assert harness.latest("label").get("value") == ""


async def test_latest_returns_the_most_recent_publish(harness) -> None:
    """After a set, that set is what a client holds."""
    await harness.tick("poll")

    assert harness.latest("coords").state is IPState.OK


async def test_latest_raises_for_an_undefined_property(harness) -> None:
    """Asking about a property that does not exist is a test bug."""
    with pytest.raises(KeyError):
        harness.latest("nope")


async def test_latest_survives_a_clear(harness) -> None:
    """After clear() the device's live vector still answers for the property."""
    await harness.tick("poll")
    harness.clear()

    assert harness.latest("coords").get("ra") == 1.0


async def test_latest_reports_a_published_blob_payload(harness) -> None:
    """A driver author asserting "the exposure produced this image" reads it here.

    The payload is the one thing the harness reports that is not a scalar, and it
    has to come back as the bytes that were published rather than as their
    length or their base64.
    """
    harness.device["frame"].set(image=b"\x00FITS\xff", state=IPState.OK)

    latest = harness.latest("frame")
    assert latest.get("image") == b"\x00FITS\xff"
    assert latest.element("image").size == 6
    assert latest.state is IPState.OK


async def test_each_recorded_blob_holds_the_frame_it_was_published_with(harness) -> None:
    """Two exposures leave two distinct images in the history, not the last one twice.

    A recorded emission is a value, and the handle publishing frame two must not
    reach back into the message that announced frame one.
    """
    harness.device["frame"].set(image=b"frame-one")
    harness.device["frame"].set(image=b"frame-two")

    assert [v.get("image") for v in harness.sets("frame")] == [b"frame-one", b"frame-two"]


async def test_sets_can_be_filtered_by_property(harness) -> None:
    """sets(name) narrows to one property; sets() returns everything."""
    await harness.tick("poll")
    await harness.write("power", on=True)

    assert len(harness.sets("coords")) == 1
    assert len(harness.sets()) == 2


async def test_deletes_are_recorded(harness) -> None:
    """A property the driver withdraws shows up in deletes()."""
    harness.device["frame"].delete("no camera attached")

    assert [d.name for d in harness.deletes()] == ["frame"]


async def test_clear_drops_history_but_not_state(harness) -> None:
    """clear() separates arrange from act without resetting the device."""
    await harness.tick("poll")
    harness.clear()

    assert harness.emitted == []
    assert harness.device.ticks == 1


# --------------------------------------------------------------------------- #
# Emissions are values, not views                                              #
# --------------------------------------------------------------------------- #
class _Slewer(Device):
    """A device whose handler announces Busy, works, and then announces Ok."""

    name = "Slewer"

    async def setup(self) -> None:
        """Define the position the handler slews."""
        self.define_number("POS", [Number(name="AZ")])

    @on_new("POS")
    async def _go(self, vector: NumberVector) -> None:
        """Publish the move as Busy, then publish its result as Ok."""
        self["POS"].set(AZ=10.0, state=IPState.BUSY)
        self["POS"].set(AZ=90.0, state=IPState.OK)


async def test_each_recorded_set_holds_the_state_it_was_published_with() -> None:
    """Announce-Busy-then-Ok is the commonest driver shape, so both must be visible.

    A recorded emission is a value, not a window onto the device's live vector:
    a test that read the second ``set`` back off the first would see the driver's
    end state twice and never notice a transient that never happened.
    """
    harness = DeviceHarness(_Slewer())
    await harness.setup()

    await harness.write("POS", AZ=90.0)

    assert [(v.state, v.get("AZ")) for v in harness.sets("POS")] == [
        (IPState.BUSY, 10.0),
        (IPState.OK, 90.0),
    ]
