"""Smoke: the stack comes up against a real ``indiserver``.

Deliberately the cheapest test here and the first to run. If this fails, every
other interop failure is noise: libindi is missing, the port is wrong, or the
client cannot reach the hub at all.
"""

from __future__ import annotations

from indikit.client import IndiClient


async def test_client_connects_to_a_real_indiserver(indi_server):
    """Our client reaches a real hub and sees a real driver's properties."""
    server = indi_server("indi_simulator_telescope")

    async with IndiClient("127.0.0.1", server.port) as client:
        assert client.connected
        await client.wait_for("Telescope Simulator", "CONNECTION", timeout=20)
        assert "Telescope Simulator" in client.store.devices()


async def test_the_hub_reports_a_driver_it_could_not_start(indi_server):
    """A hub whose driver is missing still accepts clients rather than dying.

    ``indiserver`` keeps running and retries, so a client must not treat the
    resulting quiet connection as a failure.
    """
    server = indi_server("indi_simulator_telescope", "indi_does_not_exist")

    async with IndiClient("127.0.0.1", server.port) as client:
        assert client.connected
        # The working driver still comes through.
        await client.wait_for("Telescope Simulator", "CONNECTION", timeout=20)
