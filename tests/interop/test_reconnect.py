"""Reconnect behaviour against a real TCP peer.

The client's reconnect loop is otherwise only exercised over in-memory pipes, where
a "closed connection" is a queue sentinel rather than a socket going away. A real
``indiserver`` dying gives the real thing: a half-open socket, an EOF mid-frame, a
refused connect while nothing is listening.

The web bridge's startup semantics changed recently so that it comes up with the hub
down, which is precisely the behaviour that needs a real socket to be believed.
"""

from __future__ import annotations

import asyncio
import socket

from conftest import free_port, wait_until

from indikit.client import IndiClient


async def test_client_reconnects_after_the_hub_restarts(indi_server):
    """The client notices a hub going away and re-enumerates when it returns."""
    server = indi_server("indi_simulator_focus")
    port = server.port

    states: list[bool] = []
    client = IndiClient("127.0.0.1", port, reconnect_delay=0.2)
    client.on_connection(states.append)
    await client.start()
    try:
        await client.wait_for("Focuser Simulator", "CONNECTION", timeout=25)
        assert client.connected

        server.stop()
        # The drop has to be observed, not assumed.
        await wait_until(lambda: not client.connected, seconds=20)
        assert not client.connected, "client still thinks it is connected after the hub died"

        # Same port, new server: the client should find its way back on its own.
        restarted = None
        for _ in range(20):
            try:
                restarted = _restart_on(port)
                break
            except OSError:  # pragma: no cover - the old socket is still in TIME_WAIT
                await asyncio.sleep(0.5)
        assert restarted is not None, "could not restart indiserver on the same port"

        try:
            await wait_until(lambda: client.connected, seconds=30)
            assert client.connected, "client never reconnected"
            # Reconnecting is only useful if it re-enumerates: the handshake has to
            # be replayed, not just the socket reopened.
            await client.wait_for("Focuser Simulator", "CONNECTION", timeout=25)
        finally:
            restarted.terminate()
            restarted.wait(timeout=10)
    finally:
        await client.aclose()

    assert True in states and False in states, f"connection callbacks were {states}"


def _restart_on(port: int):
    """Start a fresh indiserver bound to a specific port.

    Parameters
    ----------
    port : int
        The port to bind.

    Returns
    -------
    process : subprocess.Popen
        The running server.

    Raises
    ------
    OSError
        If the port is not yet reusable.
    """
    import subprocess

    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))

    process = subprocess.Popen(
        ["indiserver", "-p", str(port), "indi_simulator_focus"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = asyncio.get_event_loop().time() + 20
    while asyncio.get_event_loop().time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.25):
                return process
        except OSError:
            if process.poll() is not None:
                raise OSError("restarted indiserver exited") from None
    process.terminate()
    raise OSError("restarted indiserver never listened")


async def test_client_waits_for_a_hub_that_is_not_there_yet():
    """Starting against a dead port keeps retrying instead of failing.

    This is what lets `indikit serve` come up before `indiserver` does, which is
    the ordinary case when both are started by the same service manager.
    """
    port = free_port()
    client = IndiClient("127.0.0.1", port, reconnect_delay=0.2)
    await client.start(wait=False)
    try:
        await asyncio.sleep(1.0)
        assert not client.connected
    finally:
        await client.aclose()
