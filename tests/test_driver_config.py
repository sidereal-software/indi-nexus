"""Tests for ``CONFIG_PROCESS`` and the persistence behind it.

Four of these are the reason the device keeps one authoritative configuration
map rather than a cache of the file, and each corresponds to a way an operator
loses work: a property restored depending on whether it was defined before or
after the load, a redefine-after-delete reverting to what is on disk, a Save
taken while a connect-time property is withdrawn erasing it, and a restore that
announces a default before correcting itself. They are written against
:class:`~indi_nexus.testing.DeviceHarness` because all four are observable in
exactly what the device emits.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat

import pytest

from indi_nexus import ConfigError
from indi_nexus.driver import Device, on_new
from indi_nexus.driver.config import MAX_CONFIG_BYTES, config_path
from indi_nexus.driver.device import CONFIG_PERSISTED, CONFIG_PERSISTED_NAMES
from indi_nexus.protocol import (
    BLOB,
    IPerm,
    IPState,
    ISRule,
    ISState,
    Light,
    Number,
    Switch,
    Text,
)
from indi_nexus.testing import DeviceHarness


class _Site(Device):
    """A device with one persisted number vector and one that is not persisted."""

    name = "Site"

    def __init__(self, name: str | None = None) -> None:
        """Record what the hooks are called with, for the assertions below."""
        super().__init__(name)
        self.writes: list[str] = []
        self.loaded: list[list[str]] = []

    async def setup(self) -> None:
        """Define the configuration switch, a persisted site and a live reading."""
        self.define_connection()
        self.define_config()
        self.define_number(
            "GEOGRAPHIC_COORD",
            [Number(name="LAT", value=34.0), Number(name="LONG", value=-118.0)],
            persist=True,
        )
        self.define_number("TEMPERATURE", [Number(name="C", value=11.0)], perm=IPerm.RO)
        # Loaded after the properties, which is what a driver that caches its
        # settings in Python attributes wants: on_config_loaded is then handed
        # the names and can act on them. A first run has nothing saved.
        with contextlib.suppress(ConfigError):
            await self.load_config()

    async def on_config_loaded(self, names: list[str]) -> None:
        """Record every load, so a test can see what it was told."""
        self.loaded.append(names)

    @on_new("GEOGRAPHIC_COORD")
    async def _on_site(self, vector) -> None:
        """Record that a client write reached the handler."""
        self.writes.append(vector.name)
        self["GEOGRAPHIC_COORD"].set(vector.values(), state=IPState.OK)


def _harness(tmp_path, device: Device | None = None) -> DeviceHarness:
    """Return a harness saving into a test's own directory.

    Parameters
    ----------
    tmp_path : Path
        pytest's per-test temporary directory.
    device : Device or None, optional
        The device under test; a fresh :class:`_Site` when omitted.

    Returns
    -------
    harness : DeviceHarness
        The harness, not yet set up.
    """
    return DeviceHarness(device if device is not None else _Site(), config_dir=tmp_path)


def _saved(harness: DeviceHarness) -> dict:
    """Return the properties block of the configuration file on disk.

    Parameters
    ----------
    harness : DeviceHarness
        The harness whose device wrote it.

    Returns
    -------
    properties : dict
        The saved property values, keyed by property name.
    """
    document = json.loads(harness.config_path.read_text())
    return document["properties"]


# --------------------------------------------------------------------------- #
# The property itself                                                          #
# --------------------------------------------------------------------------- #
async def test_config_process_is_the_standard_property(tmp_path):
    """The switch has libindi's three actions, exclusive and writable."""
    harness = _harness(tmp_path)
    await harness.setup()

    defined = harness.latest("CONFIG_PROCESS")
    assert [el.name for el in defined.elements] == ["CONFIG_LOAD", "CONFIG_SAVE", "CONFIG_PURGE"]
    assert defined.rule is ISRule.AT_MOST_ONE
    assert defined.perm is IPerm.RW
    assert all(el.value is ISState.OFF for el in defined.elements)


@pytest.mark.parametrize("action", ["CONFIG_SAVE", "CONFIG_LOAD", "CONFIG_PURGE"])
async def test_every_action_leaves_the_switch_off(tmp_path, action):
    """No member stays selected, whatever the action did.

    ``CONFIG_PROCESS`` is a momentary action, not state. Under ``AtMostOne`` a
    member left on stays selected forever, and a panel renders it as a button
    stuck in its pressed position - which is why this does not copy the
    ``CONNECTION`` handler, where a latched member is the whole point.
    """
    harness = _harness(tmp_path)
    await harness.setup()
    if action == "CONFIG_LOAD":
        await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)  # so there is one to load

    await harness.write("CONFIG_PROCESS", **{action: True})

    latest = harness.latest("CONFIG_PROCESS")
    assert all(el.value is ISState.OFF for el in latest.elements)
    assert latest.state is IPState.OK


# --------------------------------------------------------------------------- #
# Saving                                                                       #
# --------------------------------------------------------------------------- #
async def test_save_writes_only_the_persisted_properties(tmp_path):
    """A property is in the file because it said ``persist=True``, not because it exists."""
    harness = _harness(tmp_path)
    await harness.setup()

    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    assert list(_saved(harness)) == ["GEOGRAPHIC_COORD"]
    assert _saved(harness)["GEOGRAPHIC_COORD"] == {"LAT": 34.0, "LONG": -118.0}


async def test_save_keeps_a_property_that_is_withdrawn_right_now(tmp_path):
    """A Save taken while a connect-time property is gone does not erase it.

    This is the whole reason the device keeps its own configuration map instead
    of reading the live properties at save time: half a driver's settings live
    on properties that only exist while it is connected, and the operator most
    likely to press Save is the one who has just disconnected.
    """

    class _Connectable(Device):
        """A device whose persisted property exists only while connected."""

        name = "Connectable"

        async def setup(self) -> None:
            """Define the configuration switch and the connection."""
            self.define_connection()
            self.define_config()

        async def on_connect(self) -> None:
            """Define the setting the instrument owns."""
            self.define_number("BACKLASH", [Number(name="STEPS", value=0.0)], persist=True)

        async def on_disconnect(self) -> None:
            """Withdraw it again."""
            self.delete_property("BACKLASH")

    harness = _harness(tmp_path, _Connectable())
    await harness.setup()
    await harness.write("CONNECTION", CONNECT=True)
    harness.device["BACKLASH"].set(STEPS=42.0)
    await harness.write("CONNECTION", DISCONNECT=True)
    assert "BACKLASH" not in harness.device

    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    assert _saved(harness)["BACKLASH"] == {"STEPS": 42.0}


async def test_the_saved_file_is_private_and_leaves_nothing_behind(tmp_path):
    """The file is 0600 from the moment it exists, and no temporary survives."""
    harness = _harness(tmp_path)
    await harness.setup()

    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    path = harness.config_path
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [path]


async def test_a_failed_save_reports_without_naming_a_path(tmp_path, monkeypatch):
    """A refusal reaches the client as a sentence, not as an OS error with a path."""
    harness = _harness(tmp_path)
    await harness.setup()

    def _refuse(*_args, **_kwargs):
        """Fail the way a read-only directory does."""
        raise PermissionError(13, "Permission denied", str(tmp_path / "secret.json"))

    monkeypatch.setattr("tempfile.mkstemp", _refuse)
    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    assert harness.latest("CONFIG_PROCESS").state is IPState.ALERT
    reported = harness.messages[-1]
    assert "[ERROR]" in reported
    assert str(tmp_path) not in reported
    assert "Permission denied" not in reported


# --------------------------------------------------------------------------- #
# Loading                                                                      #
# --------------------------------------------------------------------------- #
async def test_load_restores_values_without_invoking_the_write_handler(tmp_path):
    """A restore is not a client write, and must not be reported as one.

    Replaying saved values through ``@on_new`` would re-run every side effect a
    handler has - a slew, a shutter, a network fetch - as a consequence of the
    driver starting up. ``on_config_loaded`` is the hook that exists so the
    driver can choose to do that itself, and it is told what was restored.
    """
    harness = _harness(tmp_path)
    await harness.setup()
    harness.device["GEOGRAPHIC_COORD"].set(LAT=47.6, LONG=-122.3)
    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)
    harness.device["GEOGRAPHIC_COORD"].set(LAT=0.0, LONG=0.0)
    harness.device.writes.clear()

    await harness.write("CONFIG_PROCESS", CONFIG_LOAD=True)

    assert harness.latest("GEOGRAPHIC_COORD").get("LAT") == pytest.approx(47.6)
    assert harness.device.writes == []
    assert harness.device.loaded == [["GEOGRAPHIC_COORD"]]


async def test_load_reaches_properties_defined_before_and_after_it(tmp_path):
    """Both halves of the load rule, which is what makes define order not matter.

    A load applies to every persisted property defined at the time *and* stays
    in place for every one defined afterwards. Without the second half, a
    property defined in ``on_connect`` - which is most of the interesting ones -
    would silently never be restored.
    """

    class _BothOrders(Device):
        """A device that defines one persisted property either side of the load."""

        name = "Both Orders"

        async def setup(self) -> None:
            """Define one, load, then define the other."""
            self.define_config()
            self.define_number("BEFORE", [Number(name="V", value=1.0)], persist=True)
            with contextlib.suppress(ConfigError):  # nothing saved on the first run
                await self.load_config()
            self.define_number("AFTER", [Number(name="V", value=2.0)], persist=True)

    harness = _harness(tmp_path, _BothOrders())
    await harness.setup()
    harness.device["BEFORE"].set(V=11.0)
    harness.device["AFTER"].set(V=22.0)
    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    # A second process, starting from the same directory.
    restarted = _harness(tmp_path, _BothOrders())
    await restarted.setup()

    assert restarted.latest("BEFORE").get("V") == pytest.approx(11.0)
    assert restarted.latest("AFTER").get("V") == pytest.approx(22.0)


async def test_a_restored_property_is_announced_once(tmp_path):
    """Startup puts the saved value in the ``def``, with no correction after it.

    Restoring after the announcement would emit two frames for every persisted
    property, the first of them announcing a default that no client should ever
    see and every panel would briefly render. That is what the load-then-define
    order below buys, and it is the order a property defined in ``on_connect``
    is always in.
    """

    class _LoadFirst(Device):
        """A device that loads its configuration before defining anything persisted."""

        name = "Load First"

        async def setup(self) -> None:
            """Load, then define - so the define has something to restore from."""
            self.define_config()
            with contextlib.suppress(ConfigError):
                await self.load_config()
            self.define_number(
                "GEOGRAPHIC_COORD",
                [Number(name="LAT", value=34.0), Number(name="LONG", value=-118.0)],
                persist=True,
            )

    harness = _harness(tmp_path, _LoadFirst())
    await harness.setup()
    harness.device["GEOGRAPHIC_COORD"].set(LAT=47.6, LONG=-122.3)
    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    restarted = _harness(tmp_path, _LoadFirst())
    await restarted.setup()

    defs = restarted.defs("GEOGRAPHIC_COORD")
    assert len(defs) == 1
    assert defs[0].get("LAT") == pytest.approx(47.6)
    assert restarted.sets("GEOGRAPHIC_COORD") == []


async def test_a_withdrawn_property_comes_back_as_the_operator_left_it(tmp_path):
    """Redefining after a delete restores the live value, never the on-disk one.

    Load, change, disconnect, reconnect is an ordinary evening. If the redefine
    reached for the file, every reconnect would quietly undo the change the
    operator made after starting the driver.
    """

    class _Cycling(Device):
        """A device whose persisted property is defined on each connect."""

        name = "Cycling"

        async def setup(self) -> None:
            """Define the connection and the configuration switch."""
            self.define_connection()
            self.define_config()

        async def on_connect(self) -> None:
            """Define the persisted setting."""
            self.define_number("BACKLASH", [Number(name="STEPS", value=0.0)], persist=True)

        async def on_disconnect(self) -> None:
            """Withdraw it."""
            self.delete_property("BACKLASH")

    harness = _harness(tmp_path, _Cycling())
    await harness.setup()
    await harness.write("CONNECTION", CONNECT=True)
    harness.device["BACKLASH"].set(STEPS=7.0)
    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    # The operator changes it again, without saving, and then cycles the link.
    harness.device["BACKLASH"].set(STEPS=99.0)
    await harness.write("CONNECTION", DISCONNECT=True)
    await harness.write("CONNECTION", CONNECT=True)

    assert harness.latest("BACKLASH").get("STEPS") == pytest.approx(99.0)


async def test_load_with_nothing_saved_is_an_alert_with_a_reason(tmp_path):
    """A first Load says why it did nothing rather than reporting success."""
    harness = _harness(tmp_path)
    await harness.setup()

    await harness.write("CONFIG_PROCESS", CONFIG_LOAD=True)

    assert harness.latest("CONFIG_PROCESS").state is IPState.ALERT
    assert "no saved configuration" in harness.messages[-1]


async def test_an_on_change_property_restored_to_its_own_value_says_nothing(tmp_path):
    """The emit policy governs a restore exactly as it governs any other update."""

    class _Quiet(Device):
        """A device with one persisted, on_change property."""

        name = "Quiet"

        async def setup(self) -> None:
            """Define the switch and the quiet property."""
            self.define_config()
            self.define_number(
                "LIMIT", [Number(name="V", value=5.0)], persist=True, emit="on_change"
            )

    harness = _harness(tmp_path, _Quiet())
    await harness.setup()
    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)
    harness.clear()

    await harness.write("CONFIG_PROCESS", CONFIG_LOAD=True)

    assert harness.sets("LIMIT") == []
    assert harness.device["LIMIT"].value("V") == pytest.approx(5.0)


async def test_names_the_driver_no_longer_has_are_ignored(tmp_path):
    """A configuration written by an older driver still restores what it can.

    A property or element the current version dropped is not an error: the file
    outlives the code that wrote it, and refusing the whole document over one
    stale name would make every upgrade lose the configuration.
    """
    harness = _harness(tmp_path)
    await harness.setup()
    harness.config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "device": "Site",
                "saved": "2026-08-17T21:14:03Z",
                "properties": {
                    "GEOGRAPHIC_COORD": {"LAT": 51.5, "ELEVATION": 3.0},
                    "REMOVED_IN_2_0": {"V": 1.0},
                },
            }
        )
    )

    await harness.write("CONFIG_PROCESS", CONFIG_LOAD=True)

    assert harness.latest("CONFIG_PROCESS").state is IPState.OK
    assert harness.latest("GEOGRAPHIC_COORD").get("LAT") == pytest.approx(51.5)
    assert harness.latest("GEOGRAPHIC_COORD").get("LONG") == pytest.approx(-118.0)


async def test_a_value_that_will_not_take_is_dropped_and_named(tmp_path):
    """One bad value costs its own element and is reported, not the whole property."""
    harness = _harness(tmp_path)
    await harness.setup()
    harness.config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "device": "Site",
                "saved": "2026-08-17T21:14:03Z",
                "properties": {"GEOGRAPHIC_COORD": {"LAT": "not a number", "LONG": -70.7}},
            }
        )
    )

    await harness.write("CONFIG_PROCESS", CONFIG_LOAD=True)

    assert harness.latest("GEOGRAPHIC_COORD").get("LONG") == pytest.approx(-70.7)
    assert harness.latest("GEOGRAPHIC_COORD").get("LAT") == pytest.approx(34.0)
    assert "GEOGRAPHIC_COORD.LAT" in " ".join(harness.messages)


async def test_an_oversized_file_is_refused_unread(tmp_path):
    """The size is checked by stat, so the parser never sees the payload."""
    harness = _harness(tmp_path)
    await harness.setup()
    harness.config_path.write_bytes(b"{" + b" " * (MAX_CONFIG_BYTES + 1))

    await harness.write("CONFIG_PROCESS", CONFIG_LOAD=True)

    assert harness.latest("CONFIG_PROCESS").state is IPState.ALERT
    assert "too large" in harness.messages[-1]


async def test_a_deeply_nested_file_is_refused(tmp_path):
    """A payload that exhausts the decoder's stack is a refusal, not a crash.

    ``json`` raises :class:`RecursionError` rather than a `ValueError` there, so
    catching ``JSONDecodeError`` alone would let it out of the driver.
    """
    harness = _harness(tmp_path)
    await harness.setup()
    harness.config_path.write_bytes(b"[" * 200_000 + b"]" * 200_000)

    await harness.write("CONFIG_PROCESS", CONFIG_LOAD=True)

    assert harness.latest("CONFIG_PROCESS").state is IPState.ALERT


# --------------------------------------------------------------------------- #
# Purging                                                                      #
# --------------------------------------------------------------------------- #
async def test_purge_removes_the_file_and_repeats_cleanly(tmp_path):
    """Purging twice is Ok both times: afterwards there is no configuration."""
    harness = _harness(tmp_path)
    await harness.setup()
    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)
    assert harness.config_path.exists()

    await harness.write("CONFIG_PROCESS", CONFIG_PURGE=True)
    assert not harness.config_path.exists()
    assert harness.latest("CONFIG_PROCESS").state is IPState.OK

    await harness.write("CONFIG_PROCESS", CONFIG_PURGE=True)
    assert harness.latest("CONFIG_PROCESS").state is IPState.OK


# --------------------------------------------------------------------------- #
# Telling a client what Save writes                                            #
# --------------------------------------------------------------------------- #
async def test_the_device_publishes_what_save_writes(tmp_path):
    """``NEXUS_CONFIG_PERSISTED`` names the persisted properties, read-only.

    This is what ``persist=True`` being declarative buys: libindi picks the
    subset in ``saveConfigItems``, which no client can read, so a panel can only
    apologise for it.
    """
    harness = _harness(tmp_path)
    await harness.setup()

    listed = harness.latest(CONFIG_PERSISTED)
    assert listed.perm is IPerm.RO
    assert [el.name for el in listed.elements] == [CONFIG_PERSISTED_NAMES]
    # TEMPERATURE is defined and is not in it: a reading is not configuration.
    assert listed.element(CONFIG_PERSISTED_NAMES).value == "GEOGRAPHIC_COORD"


async def test_the_list_is_published_once_and_not_per_property(tmp_path):
    """One ``def`` after ``setup``, and no correction behind it.

    Emitting from each ``define_*(persist=True)`` would announce a list that is
    wrong until the last of them, and put a ``set`` on the wire for each.
    """
    harness = _harness(tmp_path)
    await harness.setup()

    assert len(harness.defs(CONFIG_PERSISTED)) == 1
    assert harness.sets(CONFIG_PERSISTED) == []


async def test_a_device_that_persists_nothing_says_so(tmp_path):
    """An empty list is an answer; only the property's absence is "cannot say".

    A panel has to tell those two apart, so a device offering Save always
    publishes the property - even when pressing Save writes nothing at all.
    """

    class _NoSettings(Device):
        """A device with a Save button and nothing behind it."""

        name = "NoSettings"

        async def setup(self) -> None:
            """Define the configuration switch and one live reading."""
            self.define_config()
            self.define_number("TEMPERATURE", [Number(name="C", value=11.0)], perm=IPerm.RO)

    harness = _harness(tmp_path, _NoSettings())
    await harness.setup()

    assert harness.latest(CONFIG_PERSISTED).element(CONFIG_PERSISTED_NAMES).value == ""


async def test_a_device_without_config_process_publishes_nothing(tmp_path):
    """No Save button, nothing to describe.

    The property answers "what does *this* Save write", so a device that offers
    no configuration action must not carry it.
    """

    class _Plain(Device):
        """A device that never calls ``define_config``."""

        name = "Plain"

        async def setup(self) -> None:
            """Define one property, persisted, with nothing to persist it with."""
            self.define_number("BACKLASH", [Number(name="STEPS", value=0.0)], persist=True)

    harness = _harness(tmp_path, _Plain())
    await harness.setup()

    assert CONFIG_PERSISTED not in harness.device
    assert harness.defs(CONFIG_PERSISTED) == []


async def test_the_list_follows_a_connect_time_property(tmp_path):
    """A persisted property defined on connect joins the list, and leaves on disconnect.

    The list answers for the properties a client can see right now: once
    ``BACKLASH`` is retracted, naming it would point a panel at a property it
    has been told is gone.
    """

    class _Connectable(Device):
        """A device whose persisted property exists only while connected."""

        name = "Connectable"

        async def setup(self) -> None:
            """Define the configuration switch and the connection."""
            self.define_connection()
            self.define_config()

        async def on_connect(self) -> None:
            """Define the setting the instrument owns."""
            self.define_number("BACKLASH", [Number(name="STEPS", value=0.0)], persist=True)

        async def on_disconnect(self) -> None:
            """Withdraw it again."""
            self.delete_property("BACKLASH")

    harness = _harness(tmp_path, _Connectable())
    await harness.setup()
    assert harness.latest(CONFIG_PERSISTED).element(CONFIG_PERSISTED_NAMES).value == ""

    await harness.write("CONNECTION", CONNECT=True)
    assert harness.latest(CONFIG_PERSISTED).element(CONFIG_PERSISTED_NAMES).value == "BACKLASH"

    await harness.write("CONNECTION", DISCONNECT=True)
    assert harness.latest(CONFIG_PERSISTED).element(CONFIG_PERSISTED_NAMES).value == ""
    # Three states, three frames: the property is on_change, so the redefinition
    # that follows a reconnect does not restate a membership nothing moved.
    assert len(harness.sets(CONFIG_PERSISTED)) == 2


async def test_two_persisted_properties_are_separated_by_a_space(tmp_path):
    """The encoding is one space between names, in the order they were defined."""

    class _Pair(Device):
        """A device with two persisted properties."""

        name = "Pair"

        async def setup(self) -> None:
            """Define the configuration switch and two settings."""
            self.define_config()
            self.define_number("GEOGRAPHIC_COORD", [Number(name="LAT", value=0.0)], persist=True)
            self.define_text("SITE_NAME", [Text(name="NAME", value="home")], persist=True)

    harness = _harness(tmp_path, _Pair())
    await harness.setup()

    value = harness.latest(CONFIG_PERSISTED).element(CONFIG_PERSISTED_NAMES).value
    assert value == "GEOGRAPHIC_COORD SITE_NAME"


# --------------------------------------------------------------------------- #
# What cannot be persisted, and where it cannot be written                     #
# --------------------------------------------------------------------------- #
async def test_a_persisted_name_with_whitespace_is_refused(tmp_path):
    """The guard is what makes the space-separated list unambiguous.

    Nothing in INDI forbids the space - the models put no pattern on ``name``
    and the 1.7 DTD types it CDATA - so without this, one such property would
    read to every client as two properties, neither of which exists.
    """
    harness = _harness(tmp_path, Device("Spacey"))

    with pytest.raises(ValueError, match=CONFIG_PERSISTED):
        harness.device.define_number("SITE COORD", [Number(name="LAT", value=0.0)], persist=True)
    # Unpersisted, the same name is nobody's business: it never reaches the list.
    harness.device.define_number("SITE COORD", [Number(name="LAT", value=0.0)])


@pytest.mark.parametrize("kind", ["light", "blob"])
async def test_persisting_a_light_or_a_blob_is_refused_at_define_time(tmp_path, kind):
    """Neither kind is configuration, and the refusal is loud and immediate."""
    harness = _harness(tmp_path, Device("Refuser"))
    device = harness.device

    with pytest.raises(ValueError, match="cannot be persisted"):
        if kind == "light":
            device.define_light("L", [Light(name="A")], persist=True)
        else:
            device.define_blob("B", [BLOB(name="A")], persist=True)


@pytest.mark.parametrize(
    "device", ["CCD Simulator", "Open-Meteo", "focuser_1.2", "auxiliary.dome", "console"]
)
def test_a_real_device_name_is_accepted(tmp_path, device):
    """Spaces and punctuation are ordinary in INDI device names, so they pass.

    The last two are the near misses: a reserved name is reserved as a whole
    component, so a name that merely starts with one is an ordinary file.
    """
    assert config_path(tmp_path, device) == tmp_path / f"{device}.json"


@pytest.mark.parametrize(
    "device",
    [
        ".",
        "..",
        "CON",
        "com1",
        "a/b",
        "a\\b",
        "c:name",
        "trailing.",
        "trailing ",
        "nul\x00byte",
        "",
        # Windows reserves the component before the first dot, so a suffix is
        # no escape: all three of these are the AUX, COM1 and NUL devices.
        "aux.telescope",
        "com1.controller",
        "nul .json",
    ],
)
def test_a_name_that_is_not_a_filename_is_refused(tmp_path, device):
    r"""The check is an allowlist, so every one of these fails for the same reason.

    A denylist of separators has to know about ``/``, ``\``, ``:``, NUL and the
    Windows device names, and is wrong the moment it misses one.
    """
    with pytest.raises(ConfigError):
        config_path(tmp_path, device)


async def test_a_raising_hook_still_leaves_the_switch_off(tmp_path):
    """Any failure resets the switch, not only the ones the filesystem raises.

    ``on_config_loaded`` is a documented extension point, so a bug in a driver
    author's override is the likeliest exception here by some distance. Letting
    it past the handler would skip the reset and leave ``CONFIG_LOAD`` selected
    for the life of the process - the stuck button the reset exists to prevent -
    on top of whatever the bug itself did.
    """

    class _BadHook(Device):
        """A device whose configuration hook raises the way buggy code does."""

        name = "Bad Hook"

        async def setup(self) -> None:
            """Define the switch and one persisted property."""
            self.define_config()
            self.define_number("LIMIT", [Number(name="V", value=5.0)], persist=True)

        async def on_config_loaded(self, names: list[str]) -> None:
            """Fail, in a way that is not a ConfigError."""
            raise ZeroDivisionError("division by zero")

    harness = _harness(tmp_path, _BadHook())
    await harness.setup()
    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    await harness.write("CONFIG_PROCESS", CONFIG_LOAD=True)

    latest = harness.latest("CONFIG_PROCESS")
    assert all(el.value is ISState.OFF for el in latest.elements)
    assert latest.state is IPState.ALERT
    assert "division by zero" in harness.messages[-1]


async def test_a_device_with_nowhere_to_save_says_so(tmp_path):
    """No configuration directory is a reported failure naming the fix."""
    harness = DeviceHarness(_Site())  # no config_dir
    await harness.setup()

    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    assert harness.latest("CONFIG_PROCESS").state is IPState.ALERT
    assert "INDI_NEXUS_CONFIG_DIR" in harness.messages[-1]


# --------------------------------------------------------------------------- #
# The other element kinds                                                      #
# --------------------------------------------------------------------------- #
async def test_text_and_switch_values_round_trip(tmp_path):
    """Switches are saved as the wire tokens a client would send back."""

    class _Mixed(Device):
        """A device with a persisted text vector and a persisted switch vector."""

        name = "Mixed"

        async def setup(self) -> None:
            """Define one of each."""
            self.define_config()
            self.define_text("LABELS", [Text(name="SLOT_1", value="Luminance")], persist=True)
            self.define_switch(
                "MODE",
                [Switch(name="FAST"), Switch(name="SLOW")],
                rule=ISRule.ONE_OF_MANY,
                persist=True,
            )
            with contextlib.suppress(ConfigError):
                await self.load_config()

    harness = _harness(tmp_path, _Mixed())
    await harness.setup()
    harness.device["LABELS"].set(SLOT_1="Halpha")
    harness.device["MODE"].set(SLOW=True)
    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    assert _saved(harness)["MODE"] == {"FAST": "Off", "SLOW": "On"}
    assert _saved(harness)["LABELS"] == {"SLOT_1": "Halpha"}

    restarted = _harness(tmp_path, _Mixed())
    await restarted.setup()
    assert restarted.latest("LABELS").get("SLOT_1") == "Halpha"
    assert restarted.latest("MODE").get("SLOW") is ISState.ON


async def test_the_saved_file_carries_no_definitions(tmp_path):
    """Values only: a label or a limit in the file would outrank the code forever."""
    harness = _harness(tmp_path)
    await harness.setup()

    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    document = json.loads(harness.config_path.read_text())
    assert set(document) == {"version", "device", "saved", "properties"}
    assert document["device"] == "Site"
    assert all(
        isinstance(value, float)
        for values in document["properties"].values()
        for value in values.values()
    )


async def test_the_file_is_replaced_whole_rather_than_merged(tmp_path):
    """A Save states the whole configuration, so nothing stale can survive in it."""
    harness = _harness(tmp_path)
    await harness.setup()
    harness.config_path.parent.mkdir(parents=True, exist_ok=True)
    harness.config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "device": "Site",
                "saved": "2020-01-01T00:00:00Z",
                "properties": {"LEFTOVER": {"V": 1.0}},
            }
        )
    )

    await harness.write("CONFIG_PROCESS", CONFIG_SAVE=True)

    assert "LEFTOVER" not in _saved(harness)
    # The replace is a rename onto the same filesystem, so the inode is new and
    # nothing is left half-written under the final name.
    assert os.access(harness.config_path, os.R_OK)
