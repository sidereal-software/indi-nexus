"""Interop: ``CONFIG_PROCESS`` against a real libindi driver.

Every libindi driver carries ``CONFIG_PROCESS``, and the panel's configuration
card is built on what its four members really do. Two of those claims are about
a file on disk rather than about the wire, so nothing in the unit suites can
check them: ``CONFIG_SAVE`` writes ``$HOME/.indi/<device>_config.xml`` and
``CONFIG_PURGE`` deletes it outright, with no backup left behind.

The per-test ``HOME`` the ``indi_server`` fixture already gives each server is
what makes that observable: the file the driver writes is inside ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

from conftest import wait_until

from indikit.client import IndiClient

DEVICE = "Telescope Simulator"


def config_files(home: Path) -> list[Path]:
    """Return the driver-written configuration files under a server's HOME.

    Globbed rather than named: the exact filename is libindi's business, and the
    claim under test is that saving produces one and purging removes it.

    Parameters
    ----------
    home : Path
        The server's private HOME directory.

    Returns
    -------
    files : list of Path
        Every ``*_config.xml`` in ``home/.indi``, empty when there is none.
    """
    return sorted((home / ".indi").glob("*_config.xml"))


async def test_saving_writes_a_config_file_and_purging_deletes_it(indi_server):
    """``CONFIG_SAVE`` creates the driver's config file; ``CONFIG_PURGE`` removes it."""
    server = indi_server("indi_simulator_telescope")

    async with IndiClient("127.0.0.1", server.port) as client:
        await client.wait_for(DEVICE, "CONFIG_PROCESS", timeout=20)
        # The private HOME starts clean, so anything found later was written by
        # this driver during this test.
        assert config_files(server.home) == []

        await client.set_switch(DEVICE, "CONFIG_PROCESS", {"CONFIG_SAVE": "On"})
        assert await wait_until(lambda: bool(config_files(server.home))), (
            f"no config file appeared under {server.home}:\n{server.output()}"
        )
        saved = config_files(server.home)[0]
        assert saved.read_text().strip() != ""

        await client.set_switch(DEVICE, "CONFIG_PROCESS", {"CONFIG_PURGE": "On"})
        assert await wait_until(lambda: not saved.exists()), (
            f"{saved} survived CONFIG_PURGE:\n{server.output()}"
        )
        # libindi's purge is a bare remove(): nothing is kept beside the file.
        assert config_files(server.home) == []
