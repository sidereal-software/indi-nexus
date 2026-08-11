"""Corpus: our client against every simulator libindi ships.

Free breadth. These drivers emit XML nobody on this project wrote, so they exercise
shapes our own examples never produce: optional element metadata, unusual number
formats, groups and permissions we do not use, messages without a device, and
whatever else a decade of C++ drivers has accumulated.

The assertion is deliberately blunt. Every property every driver defines must parse
into a typed vector, because a `parse_indi` that quietly drops an unfamiliar tag is
the exact failure this suite exists to catch.
"""

from __future__ import annotations

import asyncio

import pytest
from conftest import wait_until

from indi_nexus.client import IndiClient
from indi_nexus.protocol import BLOBVector, LightVector, NumberVector, SwitchVector, TextVector

# Everything indi-bin ships as a simulator, so the corpus grows when libindi's does.
SIMULATORS = [
    "indi_simulator_telescope",
    "indi_simulator_ccd",
    "indi_simulator_dome",
    "indi_simulator_focus",
    "indi_simulator_wheel",
    "indi_simulator_gps",
    "indi_simulator_guide",
    "indi_simulator_lightpanel",
    "indi_simulator_receiver",
    "indi_simulator_rotator",
    "indi_simulator_sqm",
    "indi_simulator_weather",
]

VECTOR_TYPES = (NumberVector, TextVector, SwitchVector, LightVector, BLOBVector)


async def _snapshot(port: int, *, settle: float = 3.0) -> dict[str, dict[str, object]]:
    """Connect, let the drivers finish defining themselves, and return the cache.

    Parameters
    ----------
    port : int
        The server's port.
    settle : float, optional
        Seconds to keep reading after the first property arrives.

    Returns
    -------
    devices : dict
        Device name to its property mapping.
    """
    async with IndiClient("127.0.0.1", port) as client:
        await wait_until(lambda: bool(client.store.devices()), seconds=25)
        # Drivers define properties over several frames; keep reading past the first.
        await asyncio.sleep(settle)
        return {name: dict(client[name]) for name in client.store.devices()}


@pytest.mark.parametrize("driver", SIMULATORS)
async def test_every_simulator_parses(indi_server, driver):
    """Each libindi simulator's properties parse into typed vectors."""
    server = indi_server(driver)
    devices = await _snapshot(server.port)

    assert devices, f"{driver} defined no devices:\n{server.output()}"
    for device, properties in devices.items():
        assert properties, f"{driver}: {device} defined no properties"
        for name, vector in properties.items():
            assert isinstance(vector, VECTOR_TYPES), f"{device}.{name} is {type(vector)!r}"
            assert vector.device == device
            assert vector.name == name
            # A vector with no elements means we parsed the envelope and lost the
            # contents, which would still look like success to a naive check.
            assert vector.elements, f"{device}.{name} parsed with no elements"


async def test_the_whole_corpus_on_one_hub(indi_server):
    """Every simulator at once, which is what an observatory actually looks like.

    Running them together also exercises the multiplexing: one stream carrying many
    devices, where a parser that mixes up interleaved messages shows up as a
    property landing on the wrong device.
    """
    server = indi_server(*SIMULATORS)
    devices = await _snapshot(server.port, settle=6.0)

    assert len(devices) >= len(SIMULATORS) - 1, (
        f"expected roughly one device per simulator, got {sorted(devices)}"
    )
    for device, properties in devices.items():
        for name, vector in properties.items():
            assert vector.device == device, f"{name} landed on the wrong device"

    kinds = {type(v) for props in devices.values() for v in props.values()}
    # If a whole vector kind never appears, this corpus is not covering what we think.
    assert NumberVector in kinds and SwitchVector in kinds and TextVector in kinds
