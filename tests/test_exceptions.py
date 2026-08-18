"""Tests for the exception hierarchy and, above all, its backwards compatibility.

The hierarchy is only worth having if adopting it broke nothing: every type has
to keep answering to the builtin that used to be raised in its place, so a
driver in someone else's repository that catches :class:`KeyError` or
:class:`RuntimeError` goes on catching exactly what it caught before. Each test
below therefore comes in two halves - the new type is raised, and the old
``except`` still catches it.
"""

from __future__ import annotations

import asyncio

import pytest

from indi_nexus import (
    ConfigError,
    DeviceNotServing,
    IndiError,
    NotConnectedError,
    PropertyNotFound,
    PropertyRetracted,
    ProtocolError,
    SendQueueFull,
    WrongPropertyKind,
)
from indi_nexus.client import IndiClient
from indi_nexus.driver import Device
from indi_nexus.protocol import IPState, Number, NumberVector
from indi_nexus.protocol.numbers import parse_number
from indi_nexus.testing import DeviceHarness

_TYPES = [
    (ProtocolError, ValueError),
    (PropertyNotFound, KeyError),
    (WrongPropertyKind, TypeError),
    (PropertyRetracted, RuntimeError),
    (DeviceNotServing, RuntimeError),
    (NotConnectedError, ConnectionError),
    (SendQueueFull, RuntimeError),
    (ConfigError, OSError),
]


class _Probe(Device):
    """A device with one number property and one switch, for the lookups below."""

    name = "Probe"

    async def setup(self) -> None:
        """Define the two properties the tests reach for."""
        self.define_connection()
        self.define_number("EXPOSURE", [Number(name="secs", value=1.0)])


@pytest.mark.parametrize(("indi_type", "builtin"), _TYPES)
def test_every_type_is_an_indi_error_and_keeps_its_builtin(indi_type, builtin):
    """Each exception answers to IndiError and to the builtin it replaced."""
    assert issubclass(indi_type, IndiError)
    assert issubclass(indi_type, builtin)


def test_message_renders_the_way_the_builtin_did():
    """The builtin's own formatting survives, quotes and all.

    KeyError renders its argument with repr(), which is why the MRO puts the
    builtin ahead of Exception: a log line that read ``'RA' not in CCD.X``
    before must not start reading differently.
    """
    assert str(PropertyNotFound("RA not in CCD.COORD")) == str(KeyError("RA not in CCD.COORD"))


def test_missing_element_is_still_a_key_error():
    """vector[name] raises PropertyNotFound, and except KeyError still sees it."""
    vec = NumberVector(device="CCD", name="EXPOSURE", elements=[Number(name="secs", value=1.0)])
    with pytest.raises(PropertyNotFound):
        vec.element("nope")
    with pytest.raises(KeyError):
        vec["nope"]


def test_missing_property_on_a_device_is_still_a_key_error():
    """Device["NAME"] for an undefined property raises the KeyError-compatible type."""

    async def scenario() -> None:
        harness = DeviceHarness(_Probe())
        await harness.setup()
        with pytest.raises(PropertyNotFound):
            harness.device["NOT_DEFINED"]
        with pytest.raises(KeyError):
            harness.device["NOT_DEFINED"]

    asyncio.run(scenario())


def test_wrong_kind_accessor_is_still_a_type_error():
    """A typed getter for the wrong vector kind raises the TypeError-compatible type."""

    async def scenario() -> None:
        harness = DeviceHarness(_Probe())
        await harness.setup()
        with pytest.raises(WrongPropertyKind):
            harness.device.switch("EXPOSURE")
        with pytest.raises(TypeError):
            harness.device.switch("EXPOSURE")

    asyncio.run(scenario())


def test_retracted_handle_is_still_a_runtime_error():
    """Publishing through a retracted handle raises the RuntimeError-compatible type."""

    async def scenario() -> None:
        harness = DeviceHarness(_Probe())
        await harness.setup()
        prop = harness.device["EXPOSURE"]
        prop.delete()
        with pytest.raises(PropertyRetracted):
            prop.set(secs=2.0)
        with pytest.raises(RuntimeError):
            prop.set(secs=2.0)

    asyncio.run(scenario())


def test_unattached_device_is_still_a_runtime_error():
    """A device with no runtime raises the RuntimeError-compatible type on send."""
    device = _Probe()
    with pytest.raises(DeviceNotServing):
        device.message("nobody is listening")
    with pytest.raises(RuntimeError):
        device.message("nobody is listening")


def test_bad_wire_number_is_still_a_value_error():
    """The codec's refusals raise the ValueError-compatible type."""
    with pytest.raises(ProtocolError):
        parse_number("nan")
    with pytest.raises(ValueError):
        parse_number("not a number")


def test_non_finite_publish_is_still_a_value_error():
    """A driver publishing a NaN raises the ValueError-compatible type."""

    async def scenario() -> None:
        harness = DeviceHarness(_Probe())
        await harness.setup()
        with pytest.raises(ProtocolError):
            harness.device["EXPOSURE"].set(secs=float("nan"), state=IPState.OK)
        with pytest.raises(ValueError):
            harness.device["EXPOSURE"].set(secs=float("inf"))

    asyncio.run(scenario())


def test_disconnected_send_is_a_connection_error():
    """A send with no connection raises the OSError-compatible type."""

    async def scenario() -> None:
        client = IndiClient()  # never started, so never connected
        with pytest.raises(NotConnectedError):
            await client.get_properties()
        with pytest.raises(ConnectionError):
            await client.get_properties()
        with pytest.raises(OSError):
            await client.get_properties()

    asyncio.run(scenario())


def test_missing_config_directory_is_still_an_os_error():
    """A device with nowhere to save raises the OSError-compatible type.

    ``except OSError`` around a driver is the shape somebody already has - it is
    what a filesystem call raises - so persistence must not slip past it.
    """

    async def scenario() -> None:
        harness = DeviceHarness(_Probe())  # no config_dir
        await harness.setup()
        with pytest.raises(ConfigError):
            await harness.device.save_config()
        with pytest.raises(OSError):
            await harness.device.save_config()

    asyncio.run(scenario())
