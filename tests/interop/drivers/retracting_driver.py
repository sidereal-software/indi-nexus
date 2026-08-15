#!/usr/bin/env python3
"""A driver whose cooler property exists only while the link is up.

The shape the libindi driver corpus is full of, and the one that makes property
deletion observable from outside: a property is defined in the connect hook and
withdrawn in the disconnect hook, so its presence is a fact about the current
session rather than about the driver.

It lives here rather than in ``examples/`` because its whole purpose is to be
driven by ``tests/interop/test_reverse_interop.py`` against a real
``indiserver``; nothing about it is meant to be read as a model driver.
"""

from __future__ import annotations

from indi_nexus.driver import Device
from indi_nexus.protocol import IPState, Number

#: What the sensor reads once the (imaginary) camera is talking.
AMBIENT_C = 25.0


class Retractor(Device):
    """A camera-shaped device that publishes its cooler only while connected."""

    name = "Retractor"

    async def setup(self) -> None:
        """Define the connection switch. The cooler waits for a link."""
        self.define_connection()

    async def on_connect(self) -> None:
        """Publish the cooler, which is only readable while the camera answers."""
        self.define_number(
            "CCD_COOLER",
            [Number(name="TEMPERATURE", label="Temperature (C)", format="%5.2f", value=AMBIENT_C)],
            label="Cooler",
            group="Main Control",
            state=IPState.OK,
        )

    async def on_disconnect(self) -> None:
        """Withdraw the cooler: nothing behind it is readable any more."""
        self.delete_property("CCD_COOLER", "only while connected")


if __name__ == "__main__":
    Retractor.run()
